"""Environment variable ingress contract and configuration sanitizer for BuildSite."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse, urlunparse


class ContractValidationError(ValueError):
    """Raised when environment variables breach security or structural constraints."""


TRUTHY_VALUES = frozenset({"1", "true", "yes", "on", "enable", "enabled"})
FALSY_VALUES = frozenset({"0", "false", "no", "off", "disable", "disabled", ""})
ALLOWED_ENVIRONMENTS = frozenset({"production", "staging", "development", "testing"})


def parse_bool_flag(value: Any, default: bool = False) -> bool:
    """Parse common string/numeric representations of booleans safely."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in TRUTHY_VALUES:
            return True
        if normalized in FALSY_VALUES:
            return False
        raise ContractValidationError(
            f"Invalid boolean flag '{value}'. Expected one of {sorted(TRUTHY_VALUES | FALSY_VALUES)}"
        )
    raise ContractValidationError(f"Invalid boolean flag type {type(value).__name__}")


def sanitize_site_url(url: str | None, default: str = "https://localhost:8000") -> str:
    """Sanitize and validate base site URL, stripping trailing slashes and userinfo credentials."""
    raw = (url or "").strip()
    if not raw:
        return default

    # Scrub control characters and newlines
    if any(ord(c) < 32 or ord(c) == 127 for c in raw):
        raise ContractValidationError("Site URL contains forbidden control characters")

    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ContractValidationError(
            f"Invalid URL scheme '{scheme}'. Must be 'http' or 'https'"
        )

    if not parsed.hostname:
        raise ContractValidationError(f"Invalid site URL without valid hostname: '{url}'")

    # Guard against embedded credentials
    if parsed.username or parsed.password:
        raise ContractValidationError("Site URL must not contain embedded user credentials")

    # Clean port if present
    netloc = parsed.hostname
    if parsed.port:
        if not (1 <= parsed.port <= 65535):
            raise ContractValidationError(f"Invalid URL port: {parsed.port}")
        # Append non-standard port
        if not ((scheme == "http" and parsed.port == 80) or (scheme == "https" and parsed.port == 443)):
            netloc = f"{netloc}:{parsed.port}"

    # Reconstruct normalized URL without trailing slash on host root
    clean_path = parsed.path.rstrip("/")
    return urlunparse((scheme, netloc, clean_path, "", "", ""))


def sanitize_port(port: Any, default: int = 8000, allow_privileged: bool = False) -> int:
    """Sanitize and bounds-check networking port."""
    if port is None or (isinstance(port, str) and not port.strip()):
        return default

    try:
        val = int(str(port).strip())
    except (ValueError, TypeError) as err:
        raise ContractValidationError(f"Invalid port value '{port}': not a valid integer") from err

    if not (1 <= val <= 65535):
        raise ContractValidationError(f"Port {val} is outside allowed TCP range [1, 65535]")

    if not allow_privileged and val < 1024:
        raise ContractValidationError(
            f"Privileged port {val} (<1024) prohibited without explicit authorization"
        )

    return val


def sanitize_environment_name(env: str | None, default: str = "development") -> str:
    """Normalize and validate deployment environment tier."""
    raw = (env or "").strip().lower()
    if not raw:
        return default

    if raw not in ALLOWED_ENVIRONMENTS:
        raise ContractValidationError(
            f"Invalid environment '{env}'. Expected one of {sorted(ALLOWED_ENVIRONMENTS)}"
        )
    return raw


def sanitize_path_segment(path_str: str | None, default: str = "dist") -> str:
    """Guard against directory traversal and dangerous filesystem targets."""
    raw = (path_str or "").strip()
    if not raw:
        return default

    # Prevent null bytes and control chars
    if "\x00" in raw or any(ord(c) < 32 for c in raw):
        raise ContractValidationError("Path contains forbidden null bytes or control characters")

    # Block path traversal attempts
    normalized = raw.replace("\\", "/")
    parts = normalized.split("/")
    if any(p == ".." for p in parts):
        raise ContractValidationError(f"Path traversal ('..') detected in path: '{path_str}'")

    # Disallow absolute filesystem roots for security
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise ContractValidationError(f"Absolute filesystem paths prohibited: '{path_str}'")

    # Return normalized relative path
    cleaned = "/".join(p for p in parts if p and p != ".")
    return cleaned if cleaned else default


@dataclass(frozen=True)
class SiteEnvironmentContract:
    """Strongly-typed, immutably validated environment configuration contract."""

    site_url: str
    port: int
    environment: str
    debug: bool
    enable_sitemap: bool
    enable_rss: bool
    output_dir: str
    has_api_key: bool
    api_key_masked: str

    @classmethod
    def from_env(
        cls, env_dict: Mapping[str, str] | None = None, allow_privileged_ports: bool = False
    ) -> SiteEnvironmentContract:
        """Construct a validated contract from os.environ or a supplied dictionary."""
        source = os.environ if env_dict is None else env_dict

        site_url = sanitize_site_url(source.get("BUILDSITE_URL") or source.get("SITE_URL"))
        port = sanitize_port(
            source.get("BUILDSITE_PORT") or source.get("PORT"),
            default=8000,
            allow_privileged=allow_privileged_ports,
        )
        environment = sanitize_environment_name(
            source.get("BUILDSITE_ENV") or source.get("ENV") or source.get("NODE_ENV")
        )
        debug = parse_bool_flag(source.get("BUILDSITE_DEBUG") or source.get("DEBUG"), default=False)
        enable_sitemap = parse_bool_flag(
            source.get("BUILDSITE_ENABLE_SITEMAP"), default=True
        )
        enable_rss = parse_bool_flag(source.get("BUILDSITE_ENABLE_RSS"), default=True)
        output_dir = sanitize_path_segment(
            source.get("BUILDSITE_OUTPUT_DIR") or source.get("OUTPUT_DIR"), default="dist"
        )

        raw_key = (source.get("BUILDSITE_API_KEY") or source.get("API_KEY") or "").strip()
        has_api_key = bool(raw_key)
        if has_api_key:
            if len(raw_key) <= 8:
                masked = "***"
            else:
                masked = f"{raw_key[:4]}...{raw_key[-4:]}"
        else:
            masked = "<none>"

        return cls(
            site_url=site_url,
            port=port,
            environment=environment,
            debug=debug,
            enable_sitemap=enable_sitemap,
            enable_rss=enable_rss,
            output_dir=output_dir,
            has_api_key=has_api_key,
            api_key_masked=masked,
        )

    def to_safe_dict(self) -> dict[str, Any]:
        """Export serialized configuration safe for audit logging without leaking secret tokens."""
        return {
            "site_url": self.site_url,
            "port": self.port,
            "environment": self.environment,
            "debug": self.debug,
            "enable_sitemap": self.enable_sitemap,
            "enable_rss": self.enable_rss,
            "output_dir": self.output_dir,
            "has_api_key": self.has_api_key,
            "api_key": self.api_key_masked,
        }
