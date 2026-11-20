"""Frontmatter Contract Validator & Asset Path Sanitizer.

Enforces strictly typed schema invariants on Markdown document headers,
sanitizes asset references against directory traversal and URI injection,
and neutralizes dangerous HTML embeddings in static site generators.
"""

from __future__ import annotations

import datetime
import html
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


class FrontmatterContractError(ValueError):
    """Raised when frontmatter fails contract validation."""
    pass


# Slug regex: strictly lowercase alphanumeric tokens joined by single hyphens
SLUG_REGEX = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Tag regex: lowercase alphanumeric, hyphens, underscores
TAG_REGEX = re.compile(r"^[a-z0-9_\-]+$")

# Prohibited dangerous HTML tags and event handlers
UNSAFE_HTML_PATTERN = re.compile(
    r"(?i)<\s*(?:script|iframe|object|embed|applet|style|meta|link)[^>]*>|<\s*/\s*(?:script|iframe|object|embed|applet|style|meta|link)\s*>|\bon\w+\s*=",
)

# Prohibited URI schemes
UNSAFE_URI_SCHEMES = ("javascript:", "data:", "vbscript:", "file:")


@dataclass
class ValidatedFrontmatter:
    """Sanitized, schema-validated document metadata."""
    title: str
    slug: str
    date: datetime.date
    tags: List[str] = field(default_factory=list)
    draft: bool = False
    featured_image: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


def sanitize_markdown_text(raw_text: str) -> str:
    """Strip dangerous HTML tags, inline scripts, and unescaped dangerous entities."""
    if not raw_text or not isinstance(raw_text, str):
        return ""

    # Neutralize dangerous tags
    cleaned = UNSAFE_HTML_PATTERN.sub("", raw_text)
    # Strip null bytes
    cleaned = cleaned.replace("\0", "")
    return cleaned.strip()


def sanitize_asset_path(
    path_str: str,
    allowed_extensions: Optional[Set[str]] = None,
) -> str:
    """Sanitize and validate an asset or image reference path.

    Blocks directory traversal ('..'), unsafe protocols (javascript:, data:),
    and validates permitted file extensions (e.g. .png, .jpg, .svg, .webp).
    """
    if not path_str or not isinstance(path_str, str):
        raise FrontmatterContractError("Asset path must be a non-empty string")

    trimmed = path_str.strip()

    # Block null bytes
    if "\0" in trimmed:
        raise FrontmatterContractError("Asset path contains illegal null bytes")

    # Block unsafe schemes
    lower = trimmed.lower()
    for scheme in UNSAFE_URI_SCHEMES:
        if lower.startswith(scheme):
            raise FrontmatterContractError(f"Asset path uses prohibited URI scheme '{scheme}'")

    # Allow safe absolute HTTPS/HTTP external assets
    if lower.startswith("https://") or lower.startswith("http://"):
        return trimmed

    # Block directory traversal
    norm = trimmed.replace("\\", "/")
    segments = norm.split("/")
    for seg in segments:
        if seg == "..":
            raise FrontmatterContractError("Asset path contains forbidden directory traversal ('..')")

    # Extension validation if specified
    if allowed_extensions is not None:
        ext = norm.rsplit(".", 1)[-1].lower() if "." in norm else ""
        if ext not in allowed_extensions:
            raise FrontmatterContractError(
                f"Asset extension '{ext}' is not permitted (must be one of: {sorted(allowed_extensions)})"
            )

    return norm


def parse_and_validate_date(raw_date: Any, disallow_future: bool = True) -> datetime.date:
    """Parse and validate an ISO 8601 date, ensuring validity and past/present constraint."""
    parsed_date: datetime.date

    if isinstance(raw_date, datetime.datetime):
        parsed_date = raw_date.date()
    elif isinstance(raw_date, datetime.date):
        parsed_date = raw_date
    elif isinstance(raw_date, str):
        s = raw_date.strip()
        # Try YYYY-MM-DD
        try:
            if "T" in s:
                parsed_date = datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).date()
            else:
                parsed_date = datetime.date.fromisoformat(s)
        except ValueError as exc:
            raise FrontmatterContractError(f"Invalid date format '{raw_date}': {exc}") from exc
    else:
        raise FrontmatterContractError(f"Expected date string or object, got {type(raw_date).__name__}")

    if disallow_future:
        today = datetime.date.today()
        if parsed_date > today:
            raise FrontmatterContractError(f"Date '{parsed_date}' cannot be in the future (today is {today})")

    return parsed_date


def validate_frontmatter_contract(
    raw_data: Dict[str, Any],
    disallow_future_dates: bool = True,
    default_allowed_extensions: Optional[Set[str]] = None,
) -> ValidatedFrontmatter:
    """Enforce contract on raw frontmatter map."""
    if not isinstance(raw_data, dict):
        raise FrontmatterContractError(f"Frontmatter must be a dictionary, got {type(raw_data).__name__}")

    # 1. Title validation
    if "title" not in raw_data:
        raise FrontmatterContractError("Missing mandatory frontmatter field: 'title'")
    title = sanitize_markdown_text(str(raw_data["title"]))
    if len(title) < 3 or len(title) > 120:
        raise FrontmatterContractError(f"Title length ({len(title)}) must be between 3 and 120 characters")

    # 2. Slug validation
    if "slug" not in raw_data:
        raise FrontmatterContractError("Missing mandatory frontmatter field: 'slug'")
    slug = str(raw_data["slug"]).strip()
    if not SLUG_REGEX.match(slug):
        raise FrontmatterContractError(f"Slug '{slug}' does not conform to lowercase kebab-case format")

    # 3. Date validation
    if "date" not in raw_data:
        raise FrontmatterContractError("Missing mandatory frontmatter field: 'date'")
    doc_date = parse_and_validate_date(raw_data["date"], disallow_future=disallow_future_dates)

    # 4. Tags validation
    raw_tags = raw_data.get("tags", [])
    if not isinstance(raw_tags, list):
        raise FrontmatterContractError(f"'tags' must be a list of strings, got {type(raw_tags).__name__}")
    if len(raw_tags) > 10:
        raise FrontmatterContractError(f"Number of tags ({len(raw_tags)}) exceeds maximum limit of 10")

    sanitized_tags: List[str] = []
    seen_tags: Set[str] = set()
    for t in raw_tags:
        t_clean = str(t).strip().lower()
        if not TAG_REGEX.match(t_clean):
            raise FrontmatterContractError(f"Tag '{t_clean}' contains invalid characters")
        if t_clean not in seen_tags:
            seen_tags.add(t_clean)
            sanitized_tags.append(t_clean)

    # 5. Draft flag
    draft = bool(raw_data.get("draft", False))

    # 6. Featured image validation
    featured_image = None
    if "featured_image" in raw_data and raw_data["featured_image"] is not None:
        allowed_exts = default_allowed_extensions or {"png", "jpg", "jpeg", "webp", "svg"}
        featured_image = sanitize_asset_path(str(raw_data["featured_image"]), allowed_extensions=allowed_exts)

    # 7. Collect remaining extra properties
    reserved_keys = {"title", "slug", "date", "tags", "draft", "featured_image"}
    extra = {k: v for k, v in raw_data.items() if k not in reserved_keys}

    return ValidatedFrontmatter(
        title=title,
        slug=slug,
        date=doc_date,
        tags=sanitized_tags,
        draft=draft,
        featured_image=featured_image,
        extra=extra,
    )
