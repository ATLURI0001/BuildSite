"""Content Security Policy (CSP) Nonce Generator and Security Header Hardener.

Provides cryptographically secure nonce generation, modern strict CSP Level 3 policy
assembly, HTML script/style nonce injection, and defensive header security validation.
"""

from __future__ import annotations

import base64
import re
import secrets
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


def generate_csp_nonce(byte_length: int = 16) -> str:
    """Generate a cryptographically secure base64-encoded nonce.

    Args:
        byte_length: Number of random entropy bytes (minimum 16).

    Returns:
        A URL-safe or standard Base64 string suitable for CSP nonce directives.
    """
    length = max(16, int(byte_length))
    random_bytes = secrets.token_bytes(length)
    return base64.b64encode(random_bytes).decode("ascii")


@dataclass
class CSPPolicyConfig:
    """Configuration options for assembling a Content Security Policy."""

    mode: str = "strict"  # "strict", "permissive", or "custom"
    report_only: bool = False
    report_uri: Optional[str] = None
    allow_inline_styles: bool = False
    allowed_script_domains: List[str] = field(default_factory=list)
    allowed_img_domains: List[str] = field(default_factory=list)
    allowed_connect_domains: List[str] = field(default_factory=list)
    custom_directives: Dict[str, List[str]] = field(default_factory=dict)


class CSPHardener:
    """Builds and validates hardened HTTP security headers and injects nonces."""

    def __init__(self, config: Optional[CSPPolicyConfig] = None) -> None:
        self.config = config or CSPPolicyConfig()

    def build_csp_string(self, nonce: Optional[str] = None) -> str:
        """Assembles the Content-Security-Policy header value."""
        directives: Dict[str, List[str]] = {}

        if self.config.mode == "strict":
            # Strict CSP Level 3 with fallback for Level 2 browsers
            directives["default-src"] = ["'self'"]
            script_src = ["'strict-dynamic'"]
            if nonce:
                script_src.append(f"'nonce-{nonce}'")
            # 'unsafe-inline' and 'https:' are ignored by modern browsers when 'strict-dynamic' is present
            script_src.extend(["'unsafe-inline'", "https:"])
            for domain in self.config.allowed_script_domains:
                clean_dom = domain.strip()
                if clean_dom:
                    script_src.append(clean_dom)
            directives["script-src"] = script_src

            if self.config.allow_inline_styles:
                directives["style-src"] = ["'self'", "'unsafe-inline'"]
            elif nonce:
                directives["style-src"] = ["'self'", f"'nonce-{nonce}'"]
            else:
                directives["style-src"] = ["'self'"]

            img_src = ["'self'", "data:"]
            for dom in self.config.allowed_img_domains:
                clean_dom = dom.strip()
                if clean_dom:
                    img_src.append(clean_dom)
            directives["img-src"] = img_src

            connect_src = ["'self'"]
            for dom in self.config.allowed_connect_domains:
                clean_dom = dom.strip()
                if clean_dom:
                    connect_src.append(clean_dom)
            directives["connect-src"] = connect_src

            directives["font-src"] = ["'self'", "data:"]
            directives["object-src"] = ["'none'"]
            directives["base-uri"] = ["'self'"]
            directives["form-action"] = ["'self'"]
            directives["frame-ancestors"] = ["'none'"]
        elif self.config.mode == "permissive":
            directives["default-src"] = ["'self'", "*"]
            directives["script-src"] = ["'self'", "'unsafe-inline'", "'unsafe-eval'", "*"]
            directives["style-src"] = ["'self'", "'unsafe-inline'", "*"]
            directives["img-src"] = ["*"]
        else:
            directives["default-src"] = ["'self'"]

        # Merge custom directives
        for d_name, d_vals in self.config.custom_directives.items():
            norm_name = d_name.lower().strip()
            directives[norm_name] = [v.strip() for v in d_vals if v.strip()]

        if self.config.report_uri:
            directives["report-uri"] = [self.config.report_uri.strip()]

        # Format header value
        parts: List[str] = []
        for name, values in directives.items():
            parts.append(f"{name} {' '.join(values)}")

        return "; ".join(parts)

    def build_security_headers(self, nonce: Optional[str] = None) -> Dict[str, str]:
        """Returns a comprehensive dictionary of modern security headers."""
        csp_header_name = (
            "Content-Security-Policy-Report-Only"
            if self.config.report_only
            else "Content-Security-Policy"
        )
        return {
            csp_header_name: self.build_csp_string(nonce),
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), camera=(), microphone=(), payment=()",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Cross-Origin-Resource-Policy": "same-origin",
        }

    @staticmethod
    def inject_nonce_into_html(html: str, nonce: str) -> str:
        """Injects `nonce="..."` into HTML `<script>` and `<style>` tags.

        Safely ignores elements that already contain a `nonce` attribute.
        """
        if not html or not nonce:
            return html

        clean_nonce = nonce.replace('"', "").replace("'", "").strip()

        def _inject_script(match: re.Match[str]) -> str:
            tag_content = match.group(0)
            if re.search(r'\bnonce=["\']', tag_content, flags=re.IGNORECASE):
                return tag_content
            # Insert nonce before closing '>'
            return re.sub(r">", f' nonce="{clean_nonce}">', tag_content, count=1)

        # Match opening script tags
        modified = re.sub(
            r"<script(?:\s+[^>]*)?>",
            _inject_script,
            html,
            flags=re.IGNORECASE,
        )

        def _inject_style(match: re.Match[str]) -> str:
            tag_content = match.group(0)
            if re.search(r'\bnonce=["\']', tag_content, flags=re.IGNORECASE):
                return tag_content
            return re.sub(r">", f' nonce="{clean_nonce}">', tag_content, count=1)

        # Match opening style tags
        modified = re.sub(
            r"<style(?:\s+[^>]*)?>",
            _inject_style,
            modified,
            flags=re.IGNORECASE,
        )

        return modified

    @staticmethod
    def audit_csp_string(csp: str) -> List[str]:
        """Audits a CSP header string for security vulnerabilities and anti-patterns.

        Returns a list of warning advisories.
        """
        warnings: List[str] = []
        if not csp or not csp.strip():
            return ["Empty Content-Security-Policy header"]

        lower = csp.lower()

        if "'unsafe-eval'" in lower:
            warnings.append("Usage of 'unsafe-eval' allows arbitrary JavaScript code execution")
        if "default-src *" in lower or "script-src *" in lower:
            warnings.append("Wildcard '*' in source directives negates origin protection")
        if "object-src 'none'" not in lower:
            warnings.append("Missing object-src 'none' may permit Flash or Java plugin injection")
        if "base-uri" not in lower:
            warnings.append("Missing base-uri directive allows <base> tag hijacking")
        if "frame-ancestors" not in lower:
            warnings.append("Missing frame-ancestors directive leaves application vulnerable to clickjacking")
        if "'unsafe-inline'" in lower and "'strict-dynamic'" not in lower and "nonce-" not in lower:
            warnings.append("Unrestricted 'unsafe-inline' without nonces permits inline XSS attacks")

        return warnings
