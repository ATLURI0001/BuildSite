"""Unit tests for Content Security Policy (CSP) hardener and nonce generator."""

from __future__ import annotations

import base64
import pytest
from buildsite.csp_hardener import (
    CSPHardener,
    CSPPolicyConfig,
    generate_csp_nonce,
)


def test_generate_csp_nonce_entropy_and_format() -> None:
    nonce1 = generate_csp_nonce(16)
    nonce2 = generate_csp_nonce(16)

    assert isinstance(nonce1, str)
    assert len(nonce1) > 0
    # Must be valid base64
    decoded = base64.b64decode(nonce1)
    assert len(decoded) == 16
    assert nonce1 != nonce2  # Entropy uniqueness

    # Minimum length clamping
    short_nonce = generate_csp_nonce(4)
    assert len(base64.b64decode(short_nonce)) == 16


def test_csp_hardener_strict_mode() -> None:
    hardener = CSPHardener()
    nonce = generate_csp_nonce()
    csp = hardener.build_csp_string(nonce)

    assert "default-src 'self'" in csp
    assert f"'nonce-{nonce}'" in csp
    assert "'strict-dynamic'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert f"style-src 'self' 'nonce-{nonce}'" in csp


def test_csp_hardener_inline_styles_and_report_uri() -> None:
    config = CSPPolicyConfig(
        mode="strict",
        allow_inline_styles=True,
        report_uri="https://api.example.com/csp-report",
        allowed_img_domains=["https://cdn.example.com"],
    )
    hardener = CSPHardener(config)
    csp = hardener.build_csp_string()

    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "report-uri https://api.example.com/csp-report" in csp
    assert "https://cdn.example.com" in csp


def test_csp_hardener_security_headers_dict() -> None:
    hardener = CSPHardener(CSPPolicyConfig(report_only=True))
    headers = hardener.build_security_headers("test-nonce-123")

    assert "Content-Security-Policy-Report-Only" in headers
    assert "Content-Security-Policy" not in headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=()" in headers["Permissions-Policy"]
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"


def test_inject_nonce_into_html() -> None:
    nonce = "abc123xyz"
    html = """<!DOCTYPE html>
<html>
<head>
    <style>body { margin: 0; }</style>
    <script src="/static/bundle.js"></script>
    <script nonce="pre-existing">console.log("ready");</script>
</head>
<body>
    <script>alert("hello");</script>
</body>
</html>"""

    injected = CSPHardener.inject_nonce_into_html(html, nonce)

    # Bare style should have nonce
    assert f'<style nonce="{nonce}">' in injected
    # Bare script should have nonce
    assert f'<script nonce="{nonce}">' in injected
    # Script with src should have nonce injected
    assert f'<script src="/static/bundle.js" nonce="{nonce}">' in injected
    # Existing nonce must NOT be overwritten or duplicated
    assert 'nonce="pre-existing"' in injected
    assert f'nonce="pre-existing" nonce="{nonce}"' not in injected

    # Empty inputs handled safely
    assert CSPHardener.inject_nonce_into_html("", nonce) == ""
    assert CSPHardener.inject_nonce_into_html(html, "") == html


def test_audit_csp_string_vulnerabilities() -> None:
    # 1. Insecure permissive policy
    insecure_policy = "default-src *; script-src 'self' 'unsafe-eval' *; style-src 'unsafe-inline'"
    warnings = CSPHardener.audit_csp_string(insecure_policy)

    assert any("unsafe-eval" in w for w in warnings)
    assert any("Wildcard '*'" in w for w in warnings)
    assert any("Missing object-src 'none'" in w for w in warnings)
    assert any("Missing base-uri" in w for w in warnings)
    assert any("Missing frame-ancestors" in w for w in warnings)
    assert any("Unrestricted 'unsafe-inline'" in w for w in warnings)

    # 2. Hardened strict policy
    strict_policy = (
        "default-src 'self'; script-src 'strict-dynamic' 'nonce-xyz123' 'unsafe-inline' https:; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    strict_warnings = CSPHardener.audit_csp_string(strict_policy)
    assert len(strict_warnings) == 0

    # 3. Empty string
    empty_warnings = CSPHardener.audit_csp_string("")
    assert "Empty Content-Security-Policy header" in empty_warnings[0]
