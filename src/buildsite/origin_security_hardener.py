"""
Origin Security Hardener & Cross-Origin Policy Engine.

Enforces defensive HTTP response headers (COOP, COEP, CORP, HSTS, Permissions-Policy)
and provides Subresource Integrity (SRI) tag injection for static HTML assets.
"""

from __future__ import annotations

import base64
import hashlib
import re
from typing import Any, Mapping


# Standard modern permissions policy directives to lock down by default
DEFAULT_LOCKED_PERMISSIONS = (
    "camera",
    "microphone",
    "geolocation",
    "payment",
    "usb",
    "accelerometer",
    "gyroscope",
    "magnetometer",
    "display-capture",
    "clipboard-read",
)


def compute_sri_digest(content: bytes, algorithm: str = "sha384") -> str:
    """Compute base64-encoded Subresource Integrity digest with prefix."""
    algorithm = algorithm.lower().strip()
    if algorithm == "sha256":
        digest = hashlib.sha256(content).digest()
    elif algorithm == "sha384":
        digest = hashlib.sha384(content).digest()
    elif algorithm == "sha512":
        digest = hashlib.sha512(content).digest()
    else:
        raise ValueError(f"Unsupported SRI algorithm '{algorithm}'. Must be sha256, sha384, or sha512.")

    b64 = base64.b64encode(digest).decode("ascii")
    return f"{algorithm}-{b64}"


class PermissionsPolicyBuilder:
    """Constructs locked-down Permissions-Policy headers."""

    def __init__(self, directives: Mapping[str, str | list[str]] | None = None) -> None:
        self._policies: dict[str, list[str]] = {}
        # Apply standard locked defaults
        for feature in DEFAULT_LOCKED_PERMISSIONS:
            self._policies[feature] = []

        if directives:
            for feat, allowlist in directives.items():
                feat_clean = feat.lower().strip()
                if isinstance(allowlist, str):
                    self._policies[feat_clean] = [allowlist.strip()] if allowlist.strip() else []
                else:
                    self._policies[feat_clean] = [str(x).strip() for x in allowlist if str(x).strip()]

    def allow(self, feature: str, origins: str | list[str]) -> PermissionsPolicyBuilder:
        """Allow a feature for self or specific origins."""
        feat_clean = feature.lower().strip()
        if isinstance(origins, str):
            origin_list = [origins.strip()]
        else:
            origin_list = [str(o).strip() for o in origins]
        self._policies[feat_clean] = origin_list
        return self

    def disallow(self, feature: str) -> PermissionsPolicyBuilder:
        """Completely disable a feature across all origins."""
        self._policies[feature.lower().strip()] = []
        return self

    def build(self) -> str:
        """Format the Permissions-Policy header value."""
        parts: list[str] = []
        # Sort for deterministic output
        for feat in sorted(self._policies.keys()):
            origins = self._policies[feat]
            if not origins:
                parts.append(f"{feat}=()")
            else:
                formatted_origins: list[str] = []
                for o in origins:
                    if o in ("self", "src"):
                        formatted_origins.append(o)
                    elif o.startswith('"') and o.endswith('"'):
                        formatted_origins.append(o)
                    else:
                        formatted_origins.append(f'"{o}"')
                parts.append(f"{feat}=({' '.join(formatted_origins)})")
        return ", ".join(parts)


class OriginSecurityPolicy:
    """Configures and builds cross-origin and transport security headers."""

    def __init__(
        self,
        *,
        coop: str = "same-origin",
        coep: str = "require-corp",
        corp: str = "same-origin",
        referrer_policy: str = "strict-origin-when-cross-origin",
        hsts_max_age_seconds: int = 63072000,
        hsts_include_subdomains: bool = True,
        hsts_preload: bool = True,
        x_frame_options: str = "DENY",
        permissions_policy: PermissionsPolicyBuilder | None = None,
    ) -> None:
        self.coop = coop
        self.coep = coep
        self.corp = corp
        self.referrer_policy = referrer_policy
        self.hsts_max_age_seconds = max(0, hsts_max_age_seconds)
        self.hsts_include_subdomains = hsts_include_subdomains
        self.hsts_preload = hsts_preload
        self.x_frame_options = x_frame_options
        self.permissions_policy = permissions_policy or PermissionsPolicyBuilder()

    def build_hsts_header(self) -> str:
        """Build Strict-Transport-Security header string."""
        directives = [f"max-age={self.hsts_max_age_seconds}"]
        if self.hsts_include_subdomains:
            directives.append("includeSubDomains")
        if self.hsts_preload:
            directives.append("preload")
        return "; ".join(directives)

    def to_headers_dict(self) -> dict[str, str]:
        """Produce the complete dictionary of origin security HTTP response headers."""
        headers = {
            "Cross-Origin-Opener-Policy": self.coop,
            "Cross-Origin-Embedder-Policy": self.coep,
            "Cross-Origin-Resource-Policy": self.corp,
            "Referrer-Policy": self.referrer_policy,
            "Strict-Transport-Security": self.build_hsts_header(),
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": self.x_frame_options,
            "Permissions-Policy": self.permissions_policy.build(),
        }
        return headers


class SRIHTMLInjector:
    """Injects integrity and crossorigin attributes into static HTML assets based on manifest."""

    def __init__(self, asset_sri_map: Mapping[str, str]) -> None:
        """
        Initialize injector with a mapping of relative or basename URL paths to SRI digests.
        Example: {'/assets/app.js': 'sha384-...', 'style.css': 'sha384-...'}
        """
        self._sri_map: dict[str, str] = {}
        for k, v in asset_sri_map.items():
            cleaned_key = k.strip().lstrip("/")
            self._sri_map[cleaned_key] = v.strip()

    def inject(self, html_content: str) -> str:
        """Scan HTML and inject integrity and crossorigin into matched script and link tags."""
        if not html_content:
            return ""

        # Inject into <script src="...">
        def replace_script(match: re.Match[str]) -> str:
            tag = match.group(0)
            if "integrity=" in tag:
                return tag  # Already hardened

            src_match = re.search(r'src=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            if not src_match:
                return tag

            src_url = src_match.group(1).strip().lstrip("/")
            sri_digest = self._sri_map.get(src_url)
            if not sri_digest:
                # Try basename match
                basename = src_url.split("/")[-1]
                sri_digest = self._sri_map.get(basename)

            if sri_digest:
                # Insert integrity and crossorigin before the closing tag character
                insertion = f' integrity="{sri_digest}" crossorigin="anonymous"'
                if tag.endswith("/>"):
                    return tag[:-2] + insertion + " />"
                return tag[:-1] + insertion + ">"
            return tag

        # Inject into <link rel="stylesheet" href="...">
        def replace_link(match: re.Match[str]) -> str:
            tag = match.group(0)
            if "integrity=" in tag:
                return tag

            href_match = re.search(r'href=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            if not href_match:
                return tag

            href_url = href_match.group(1).strip().lstrip("/")
            sri_digest = self._sri_map.get(href_url)
            if not sri_digest:
                basename = href_url.split("/")[-1]
                sri_digest = self._sri_map.get(basename)

            if sri_digest:
                insertion = f' integrity="{sri_digest}" crossorigin="anonymous"'
                if tag.endswith("/>"):
                    return tag[:-2] + insertion + " />"
                return tag[:-1] + insertion + ">"
            return tag

        # Regex matches for script and stylesheet link tags
        script_pattern = re.compile(r'<script\b[^>]*\bsrc=["\'][^"\']+["\'][^>]*>', re.IGNORECASE)
        link_pattern = re.compile(r'<link\b[^>]*\brel=["\']stylesheet["\'][^>]*>', re.IGNORECASE)

        updated_html = script_pattern.sub(replace_script, html_content)
        updated_html = link_pattern.sub(replace_link, updated_html)
        return updated_html


def audit_origin_security_headers(headers: Mapping[str, str]) -> list[str]:
    """Audit a set of security headers, returning a list of vulnerability or posture warnings."""
    warnings: list[str] = []
    lowered = {k.lower(): v for k, v in headers.items()}

    # Check HSTS
    hsts = lowered.get("strict-transport-security")
    if not hsts:
        warnings.append("Missing 'Strict-Transport-Security' header.")
    else:
        if "max-age" not in hsts:
            warnings.append("HSTS missing 'max-age' parameter.")
        else:
            m = re.search(r"max-age=(\d+)", hsts)
            if m and int(m.group(1)) < 31536000:
                warnings.append("HSTS 'max-age' is less than recommended 1 year (31,536,000s).")

    # Check COOP/COEP
    if "cross-origin-opener-policy" not in lowered:
        warnings.append("Missing 'Cross-Origin-Opener-Policy' (COOP) header.")
    if "cross-origin-embedder-policy" not in lowered:
        warnings.append("Missing 'Cross-Origin-Embedder-Policy' (COEP) header.")
    if "cross-origin-resource-policy" not in lowered:
        warnings.append("Missing 'Cross-Origin-Resource-Policy' (CORP) header.")

    # Check nosniff
    if lowered.get("x-content-type-options") != "nosniff":
        warnings.append("'X-Content-Type-Options' is missing or not set to 'nosniff'.")

    # Check X-Frame-Options
    xfo = lowered.get("x-frame-options", "").upper()
    if xfo not in ("DENY", "SAMEORIGIN"):
        warnings.append("Insecure or missing 'X-Frame-Options' header.")

    # Check Permissions-Policy
    if "permissions-policy" not in lowered:
        warnings.append("Missing 'Permissions-Policy' header.")

    return warnings
