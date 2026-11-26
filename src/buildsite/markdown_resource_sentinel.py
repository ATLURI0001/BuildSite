"""
Markdown Image XSS & Remote Resource SSRF Exfiltration Sentinel.

Incident Postmortem Root Cause Fix: INC-2026-SITE-8240
Mitigates malicious image tag protocols (javascript:, data:), HTML onerror XSS injections,
and SSRF exfiltration against cloud metadata (169.254.169.254) and internal networks in SSG pipelines.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse


class ResourceViolationType(str, Enum):
    DANGEROUS_SCHEME = "DANGEROUS_SCHEME"
    SSRF_BLOCKED_HOST = "SSRF_BLOCKED_HOST"
    SSRF_PRIVATE_IP = "SSRF_PRIVATE_IP"
    HTML_INJECTION = "HTML_INJECTION"
    EMPTY_URL = "EMPTY_URL"


class MarkdownResourceSecurityError(Exception):
    """Raised when markdown contains unsafe image resources violating security policy."""
    def __init__(self, violation: ResourceViolationType, message: str, url: str, line_no: int) -> None:
        super().__init__(f"[{violation.value}] Line {line_no}: {message} ({url})")
        self.violation = violation
        self.message = message
        self.url = url
        self.line_no = line_no


ALLOWED_SCHEMES: Set[str] = {"https", "http", ""}
DISALLOWED_SCHEMES: Set[str] = {"javascript", "data", "file", "blob", "ftp", "vbscript"}

BLOCKED_HOSTS: Set[str] = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
    "169.254.169.254",
    "0.0.0.0",
}

MD_IMAGE_REGEX = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
HTML_IMG_REGEX = re.compile(r"<img\s+[^>]*src=[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE)
HTML_EVENT_REGEX = re.compile(r"on\w+\s*=", re.IGNORECASE)


@dataclass
class ResourceQuarantineRecord:
    url: str
    line_no: int
    violation: ResourceViolationType
    incident_id: str = "INC-2026-SITE-8240"


@dataclass
class MarkdownScanResult:
    is_safe: bool
    total_images_scanned: int
    violations: List[ResourceQuarantineRecord] = field(default_factory=list)
    sanitized_content: Optional[str] = None


class MarkdownResourceSentinel:
    """Ingress security sentinel screening SSG markdown images for SSRF and XSS."""

    def __init__(self, allow_http: bool = False, placeholder_url: str = "/assets/placeholder-blocked.svg") -> None:
        self.allow_http = allow_http
        self.placeholder_url = placeholder_url

    def _is_private_ip(self, host: str) -> bool:
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified
        except ValueError:
            return False

    def validate_url(self, raw_url: str, line_no: int = 1) -> Tuple[bool, Optional[ResourceViolationType], str]:
        clean_url = raw_url.strip()
        if not clean_url:
            return False, ResourceViolationType.EMPTY_URL, "Image URL cannot be empty"

        # Check for HTML event handler injections inside url
        if HTML_EVENT_REGEX.search(clean_url):
            return False, ResourceViolationType.HTML_INJECTION, "Inline JavaScript event handler detected in URL"

        parsed = urlparse(clean_url)
        scheme = parsed.scheme.lower()

        if scheme in DISALLOWED_SCHEMES:
            return False, ResourceViolationType.DANGEROUS_SCHEME, f"Scheme '{scheme}' is prohibited"

        if scheme and scheme not in ALLOWED_SCHEMES:
            return False, ResourceViolationType.DANGEROUS_SCHEME, f"Unknown or disallowed protocol: {scheme}"

        if not self.allow_http and scheme == "http":
            return False, ResourceViolationType.DANGEROUS_SCHEME, "Plain HTTP is disallowed in strict SSL mode"

        host = (parsed.hostname or "").lower()
        if host in BLOCKED_HOSTS:
            return False, ResourceViolationType.SSRF_BLOCKED_HOST, f"Target host '{host}' is barred by SSRF policy"

        if host and self._is_private_ip(host):
            return False, ResourceViolationType.SSRF_PRIVATE_IP, f"Target IP '{host}' belongs to internal/private network"

        return True, None, "Valid"

    def scan_content(self, markdown_text: str, auto_sanitize: bool = False) -> MarkdownScanResult:
        lines = markdown_text.splitlines()
        violations: List[ResourceQuarantineRecord] = []
        total_images = 0
        sanitized_lines: List[str] = []

        for line_idx, line in enumerate(lines, start=1):
            modified_line = line

            # Scan standard markdown images: ![alt](url)
            for match in MD_IMAGE_REGEX.finditer(line):
                total_images += 1
                alt, url = match.group(1), match.group(2)
                valid, viol, msg = self.validate_url(url, line_idx)
                if not valid and viol is not None:
                    violations.append(ResourceQuarantineRecord(url=url, line_no=line_idx, violation=viol))
                    if auto_sanitize:
                        modified_line = modified_line.replace(match.group(0), f"![{alt}]({self.placeholder_url})")

            # Scan raw HTML <img> tags
            for match in HTML_IMG_REGEX.finditer(line):
                total_images += 1
                full_tag = match.group(0)
                src = match.group(1)

                if HTML_EVENT_REGEX.search(full_tag):
                    violations.append(ResourceQuarantineRecord(url=src, line_no=line_idx, violation=ResourceViolationType.HTML_INJECTION))
                    if auto_sanitize:
                        modified_line = modified_line.replace(full_tag, f'<img src="{self.placeholder_url}" alt="blocked">')
                    continue

                valid, viol, msg = self.validate_url(src, line_idx)
                if not valid and viol is not None:
                    violations.append(ResourceQuarantineRecord(url=src, line_no=line_idx, violation=viol))
                    if auto_sanitize:
                        modified_line = modified_line.replace(src, self.placeholder_url)

            sanitized_lines.append(modified_line)

        sanitized_content = "\n".join(sanitized_lines) if auto_sanitize else None
        return MarkdownScanResult(
            is_safe=len(violations) == 0,
            total_images_scanned=total_images,
            violations=violations,
            sanitized_content=sanitized_content,
        )

    def enforce_content(self, markdown_text: str) -> None:
        result = self.scan_content(markdown_text, auto_sanitize=False)
        if not result.is_safe:
            v = result.violations[0]
            raise MarkdownResourceSecurityError(v.violation, "Dangerous markdown image resource detected", v.url, v.line_no)
