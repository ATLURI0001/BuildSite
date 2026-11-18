"""Unit tests for GitHub API queries, parsing, rate limits, and fallback handlers."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from buildsite.github_api import (
    GitHubAPIError,
    InvalidUsernameError,
    RateLimitExceededError,
    UserNotFoundError,
    fetch_contributions_graphql,
    fetch_contributions_rest_fallback,
    get_default_headers,
    get_demo_contributions,
    parse_rate_limit_headers,
    sanitize_auth_token,
    validate_date_range,
    validate_github_username,
    compute_backoff_delay,
    sanitize_repo_slug,
    validate_pagination_bounds,
)


def test_get_demo_contributions():
    """Verify demo mode returns realistic, labeled contribution snapshot."""
    demo = get_demo_contributions(count=450, username="test-user")
    assert demo.login == "test-user"
    assert demo.total_contributions == 450
    assert demo.source == "demo"
    assert demo.user_id > 0
    assert len(demo.years) > 0


@patch("requests.Session.post")
def test_fetch_contributions_graphql_success(mock_post):
    """Verify parsing of valid GraphQL response."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "user": {
                "id": "MDQ6VXNlcjEyMzQ1",
                "databaseId": 12345,
                "login": "mona",
                "contributionsCollection": {
                    "hasAnyContributions": True,
                    "totalCommitContributions": 120,
                    "totalIssueContributions": 10,
                    "totalPullRequestContributions": 15,
                    "totalPullRequestReviewContributions": 5,
                    "contributionCalendar": {
                        "totalContributions": 150,
                        "weeks": [
                            {
                                "contributionDays": [
                                    {"contributionCount": 4, "date": "2026-05-01", "color": "#216e39"},
                                    {"contributionCount": 0, "date": "2026-05-02", "color": "#ebedf0"},
                                    {"contributionCount": 8, "date": "2026-05-03", "color": "#30a14e"}
                                ]
                            }
                        ]
                    },
                    "contributionYears": [2025, 2026]
                }
            }
        }
    }
    mock_post.return_value = mock_resp

    snapshot = fetch_contributions_graphql("mona", token="fake_token")
    assert snapshot.login == "mona"
    assert snapshot.user_id == 12345
    assert snapshot.total_contributions == 150
    assert snapshot.active_days == 2
    assert snapshot.source == "graphql"


@patch("requests.Session.post")
def test_fetch_contributions_graphql_user_not_found(mock_post):
    """Verify UserNotFoundError is raised when user does not exist."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {"user": None},
        "errors": [{"message": "Could not resolve to a User with the login of 'nonexistent'."}]
    }
    mock_post.return_value = mock_resp

    with pytest.raises(UserNotFoundError):
        fetch_contributions_graphql("nonexistent", token="fake_token")


@patch("requests.Session.post")
def test_fetch_contributions_graphql_rate_limit(mock_post):
    """Verify RateLimitExceededError is raised on 403 rate limit response."""
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 403
    mock_resp.text = "API rate limit exceeded for user ID"
    mock_post.return_value = mock_resp

    with pytest.raises(RateLimitExceededError):
        fetch_contributions_graphql("busyuser", token="fake_token")


@patch("requests.Session.get")
def test_fetch_contributions_rest_fallback(mock_get):
    """Verify REST API fallback when GraphQL is unavailable."""
    def side_effect(url, **kwargs):
        resp = MagicMock()
        resp.ok = True
        resp.status_code = 200
        if "/users/backup_user/events" in url:
            resp.json.return_value = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        else:
            resp.json.return_value = {"id": 9876, "login": "backup_user", "public_repos": 10}
        return resp

    mock_get.side_effect = side_effect

    snapshot = fetch_contributions_rest_fallback("backup_user")
    assert snapshot.login == "backup_user"
    assert snapshot.user_id == 9876
    assert snapshot.total_contributions >= 50
    assert snapshot.source == "rest"


def test_validate_github_username():
    # Valid handles
    assert validate_github_username("mona") == "mona"
    assert validate_github_username("  octocat  ") == "octocat"
    assert validate_github_username("test-user-123") == "test-user-123"
    assert validate_github_username("backup_user") == "backup_user"
    assert validate_github_username("a" * 39) == "a" * 39

    # Empty and non-string inputs
    with pytest.raises(InvalidUsernameError):
        validate_github_username("")
    with pytest.raises(InvalidUsernameError):
        validate_github_username("   ")
    with pytest.raises(InvalidUsernameError):
        validate_github_username(None)
    with pytest.raises(InvalidUsernameError):
        validate_github_username(12345)

    # Exceeding 39 characters
    with pytest.raises(InvalidUsernameError):
        validate_github_username("a" * 40)

    # Path traversal and injection attempts
    with pytest.raises(InvalidUsernameError):
        validate_github_username("../../etc/passwd")
    with pytest.raises(InvalidUsernameError):
        validate_github_username("user/repo")
    with pytest.raises(InvalidUsernameError):
        validate_github_username("user\\repo")
    with pytest.raises(InvalidUsernameError):
        validate_github_username("user\nnewline")
    with pytest.raises(InvalidUsernameError):
        validate_github_username("-leading-hyphen")
    with pytest.raises(InvalidUsernameError):
        validate_github_username("user--consecutive")
    with pytest.raises(InvalidUsernameError):
        validate_github_username("user..dots")


def test_sanitize_auth_token_and_headers():
    # Token sanitization
    assert sanitize_auth_token(None) is None
    assert sanitize_auth_token("") is None
    assert sanitize_auth_token("ghp_validToken123") == "ghp_validToken123"

    # CRLF header injection neutralization
    tainted = "ghp_token123\r\nInjected-Header: evil\r\n"
    cleaned = sanitize_auth_token(tainted)
    assert "\r" not in cleaned
    assert "\n" not in cleaned
    assert cleaned == "ghp_token123Injected-Header: evil"

    # Header generation
    headers = get_default_headers("ghp_safe_token")
    assert headers["Authorization"] == "bearer ghp_safe_token"


def test_validate_date_range():
    # Valid ranges
    assert validate_date_range(None, None) == (None, None)
    n_from, n_to = validate_date_range("2026-01-01T00:00:00Z", "2026-12-31T23:59:59Z")
    assert n_from.startswith("2026-01-01")
    assert n_to.startswith("2026-12-31")

    # Mixed naive and timezone-aware dates are normalized cleanly without TypeError
    n_naive, n_aware = validate_date_range("2026-01-01T00:00:00", "2026-06-01T00:00:00Z")
    assert "+00:00" in n_naive
    assert "+00:00" in n_aware

    # Whitespace-only strings raise descriptive GitHubAPIError
    with pytest.raises(GitHubAPIError, match="cannot be empty or whitespace"):
        validate_date_range("   ", None)

    with pytest.raises(GitHubAPIError, match="cannot be empty or whitespace"):
        validate_date_range(None, "\t\n")

    # Inverted range raises error
    with pytest.raises(GitHubAPIError):
        validate_date_range("2026-12-31", "2026-01-01")

    # Invalid string raises error
    with pytest.raises(GitHubAPIError):
        validate_date_range("not-a-date", None)


def test_parse_rate_limit_headers():
    headers = {
        "X-RateLimit-Limit": "5000",
        "X-RateLimit-Remaining": "4950",
        "X-RateLimit-Reset": "1763283600",
        "X-RateLimit-Used": "50",
    }
    status = parse_rate_limit_headers(headers)
    assert status["limit"] == 5000
    assert status["remaining"] == 4950
    assert status["reset_epoch"] == 1763283600
    assert status["used"] == 50
    assert status["is_depleted"] is False

    # Depleted quota
    depleted_headers = {"x-ratelimit-remaining": "0"}
    depleted = parse_rate_limit_headers(depleted_headers)
    assert depleted["is_depleted"] is True

    # Empty / none fallback
    empty_status = parse_rate_limit_headers(None)
    assert empty_status["limit"] is None
    assert empty_status["is_depleted"] is False


def test_defensive_pagination_and_backoff():
    # Pagination bounding
    page, per_page = validate_pagination_bounds(page=-5, per_page=500, max_per_page=100)
    assert page == 1
    assert per_page == 100

    page, per_page = validate_pagination_bounds(page="3", per_page="25")
    assert page == 3
    assert per_page == 25

    page, per_page = validate_pagination_bounds(page=None, per_page="bad")
    assert page == 1
    assert per_page == 30

    # Backoff delay computation
    delay_0 = compute_backoff_delay(0, base_delay=1.0, jitter=False)
    assert delay_0 == 1.0

    delay_2 = compute_backoff_delay(2, base_delay=1.0, jitter=False)
    assert delay_2 == 4.0

    delay_capped = compute_backoff_delay(10, base_delay=1.0, max_delay=15.0, jitter=False)
    assert delay_capped == 15.0

    delay_jittered = compute_backoff_delay(1, base_delay=2.0, jitter=True)
    assert 1.0 <= delay_jittered <= 4.0


def test_sanitize_repo_slug():
    # Valid slugs
    assert sanitize_repo_slug("ATLURI0001/buildsite") == "ATLURI0001/buildsite"
    assert sanitize_repo_slug("owner-name/repo.tool-1") == "owner-name/repo.tool-1"

    # Traversal and invalid formats
    with pytest.raises(GitHubAPIError):
        sanitize_repo_slug("../evil/repo")

    with pytest.raises(GitHubAPIError):
        sanitize_repo_slug("single_slug")

    with pytest.raises(GitHubAPIError):
        sanitize_repo_slug("/leading/slash")

    with pytest.raises(GitHubAPIError):
        sanitize_repo_slug("owner/repo/sub")

    with pytest.raises(GitHubAPIError):
        sanitize_repo_slug(None)


