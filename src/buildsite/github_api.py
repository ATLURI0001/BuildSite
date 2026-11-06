"""GitHub API collector for BuildSite.

Collects verified contribution history and calendar data using GitHub's
official GraphQL and REST APIs, respecting rate limits, UTC dates, and
privacy policies.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from buildsite.models import ContributionDay, ContributionSnapshot

logger = logging.getLogger(__name__)

GITHUB_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
GITHUB_REST_ENDPOINT = "https://api.github.com"


class GitHubAPIError(Exception):
    """Raised when GitHub API requests fail."""


class RateLimitExceededError(GitHubAPIError):
    """Raised when GitHub API rate limit is exceeded."""


class UserNotFoundError(GitHubAPIError):
    """Raised when the specified GitHub user does not exist."""


GRAPHQL_CONTRIBUTIONS_QUERY = """
query ($login: String!, $from: DateTime, $to: DateTime) {
  user(login: $login) {
    id
    databaseId
    login
    contributionsCollection(from: $from, to: $to) {
      hasAnyContributions
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            date
            color
          }
        }
      }
      contributionYears
    }
  }
}
"""


def get_default_headers(token: Optional[str] = None) -> Dict[str, str]:
    """Prepare standard request headers."""
    headers = {
        "User-Agent": "BuildSite-Engine/1.0 (+https://github.com/buildsite/buildsite)",
        "Accept": "application/vnd.github.v3+json",
    }
    actual_token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if actual_token:
        headers["Authorization"] = f"bearer {actual_token}"
    return headers


def fetch_contributions_graphql(
    username: str,
    token: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> ContributionSnapshot:
    """Fetch verified contribution history via GitHub GraphQL API.

    Args:
        username: GitHub login handle.
        token: Optional GitHub Personal Access Token or GITHUB_TOKEN.
        from_date: Optional ISO 8601 UTC start datetime string.
        to_date: Optional ISO 8601 UTC end datetime string.
        session: Optional requests.Session instance for connection reuse.

    Returns:
        ContributionSnapshot with normalized metrics.
    """
    headers = get_default_headers(token)
    req_session = session or requests.Session()

    variables: Dict[str, Any] = {"login": username}
    if from_date:
        variables["from"] = from_date
    if to_date:
        variables["to"] = to_date

    payload = {"query": GRAPHQL_CONTRIBUTIONS_QUERY, "variables": variables}

    try:
        response = req_session.post(
            GITHUB_GRAPHQL_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=15.0
        )
    except requests.RequestException as exc:
        raise GitHubAPIError(f"Network error querying GitHub GraphQL: {exc}") from exc

    if response.status_code == 401:
        raise GitHubAPIError("GitHub API authorization failed. Check your GITHUB_TOKEN permissions.")
    if response.status_code == 403:
        if "rate limit" in response.text.lower():
            raise RateLimitExceededError("GitHub API rate limit exceeded.")
        raise GitHubAPIError(f"GitHub API access forbidden (HTTP 403): {response.text}")

    if not response.ok:
        raise GitHubAPIError(f"GitHub API responded with HTTP {response.status_code}: {response.text}")

    data = response.json()
    if "errors" in data:
        error_msgs = [e.get("message", "Unknown error") for e in data["errors"]]
        if any("Could not resolve to a User" in m for m in error_msgs):
            raise UserNotFoundError(f"GitHub user '{username}' was not found.")
        raise GitHubAPIError(f"GraphQL returned errors: {'; '.join(error_msgs)}")

    user_data = data.get("data", {}).get("user")
    if not user_data:
        raise UserNotFoundError(f"GitHub user '{username}' was not found.")

    database_id = user_data.get("databaseId") or 0
    resolved_login = user_data.get("login", username)
    collection = user_data.get("contributionsCollection", {})
    calendar = collection.get("contributionCalendar", {})
    total_contributions = calendar.get("totalContributions", 0)
    years = collection.get("contributionYears", [])

    contribution_days: List[ContributionDay] = []
    active_days_count = 0

    for week in calendar.get("weeks", []):
        for day in week.get("contributionDays", []):
            cnt = day.get("contributionCount", 0)
            date_str = day.get("date", "")
            contribution_days.append(ContributionDay(date=date_str, count=cnt))
            if cnt > 0:
                active_days_count += 1

    return ContributionSnapshot(
        user_id=int(database_id),
        login=resolved_login,
        total_contributions=total_contributions,
        active_days=active_days_count,
        calendar_days=contribution_days,
        years=years,
        collected_at=datetime.now(timezone.utc).isoformat(),
        source="graphql"
    )


def fetch_contributions_rest_fallback(
    username: str,
    token: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> ContributionSnapshot:
    """Fallback contribution retrieval using REST API public profile & public events.

    Used when GraphQL access is restricted (e.g. unauthenticated public access).
    """
    headers = get_default_headers(token)
    req_session = session or requests.Session()

    user_url = f"{GITHUB_REST_ENDPOINT}/users/{username}"
    try:
        user_resp = req_session.get(user_url, headers=headers, timeout=10.0)
    except requests.RequestException as exc:
        raise GitHubAPIError(f"Network error querying GitHub REST API: {exc}") from exc

    if user_resp.status_code == 404:
        raise UserNotFoundError(f"GitHub user '{username}' was not found.")
    if user_resp.status_code == 403 and "rate limit" in user_resp.text.lower():
        raise RateLimitExceededError("GitHub REST API rate limit exceeded.")
    if not user_resp.ok:
        raise GitHubAPIError(f"REST API error HTTP {user_resp.status_code}: {user_resp.text}")

    user_info = user_resp.json()
    user_id = user_info.get("id", 0)
    login = user_info.get("login", username)
    public_repos = user_info.get("public_repos", 0)

    # Estimate base contributions from public metrics or public events
    events_url = f"{GITHUB_REST_ENDPOINT}/users/{username}/events/public?per_page=100"
    event_count = 0
    try:
        events_resp = req_session.get(events_url, headers=headers, timeout=10.0)
        if events_resp.ok:
            events_data = events_resp.json()
            event_count = len(events_data)
    except Exception:
        event_count = 0

    estimated_total = max(public_repos * 5 + event_count, 1)

    return ContributionSnapshot(
        user_id=user_id,
        login=login,
        total_contributions=estimated_total,
        active_days=min(event_count, 30),
        calendar_days=[],
        years=[datetime.now(timezone.utc).year],
        collected_at=datetime.now(timezone.utc).isoformat(),
        source="rest"
    )


def get_demo_contributions(count: int = 327, username: str = "demo-developer") -> ContributionSnapshot:
    """Generate deterministic, clearly labeled demo contributions snapshot for testing."""
    return ContributionSnapshot(
        user_id=12345678,
        login=username,
        total_contributions=max(0, count),
        active_days=min(count, 185),
        calendar_days=[
            ContributionDay(date="2026-01-01", count=4),
            ContributionDay(date="2026-01-02", count=7),
            ContributionDay(date="2026-01-03", count=12),
        ],
        years=[2024, 2025, 2026],
        collected_at=datetime.now(timezone.utc).isoformat(),
        source="demo"
    )
