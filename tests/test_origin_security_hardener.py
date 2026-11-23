"""Tests for the Origin Security Hardener & Cross-Origin Policy Engine."""

import pytest
from buildsite.origin_security_hardener import (
    OriginSecurityPolicy,
    PermissionsPolicyBuilder,
    SRIHTMLInjector,
    audit_origin_security_headers,
    compute_sri_digest,
)


def test_compute_sri_digest() -> None:
    content = b"console.log('hello world');"

    # Test sha256, sha384, sha512
    sri256 = compute_sri_digest(content, "sha256")
    assert sri256.startswith("sha256-")

    sri384 = compute_sri_digest(content, "sha384")
    assert sri384.startswith("sha384-")

    sri512 = compute_sri_digest(content, "sha512")
    assert sri512.startswith("sha512-")

    # Invalid algorithm raises ValueError
    with pytest.raises(ValueError, match="Unsupported SRI algorithm"):
        compute_sri_digest(content, "md5")


def test_permissions_policy_builder() -> None:
    builder = PermissionsPolicyBuilder()
    policy = builder.build()

    # Default should lock down cameras, microphones, etc.
    assert "camera=()" in policy
    assert "microphone=()" in policy
    assert "geolocation=()" in policy
    assert "payment=()" in policy

    # Allow custom self origin
    builder.allow("camera", "self")
    custom_policy = builder.build()
    assert "camera=(self)" in custom_policy

    # Allow external origins
    builder.allow("geolocation", ["https://maps.google.com", "https://maps.apple.com"])
    geo_policy = builder.build()
    assert 'geolocation=("https://maps.google.com" "https://maps.apple.com")' in geo_policy


def test_origin_security_policy_headers() -> None:
    policy = OriginSecurityPolicy()
    headers = policy.to_headers_dict()

    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert headers["Cross-Origin-Embedder-Policy"] == "require-corp"
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "max-age=63072000" in headers["Strict-Transport-Security"]
    assert "includeSubDomains" in headers["Strict-Transport-Security"]
    assert "preload" in headers["Strict-Transport-Security"]
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "camera=()" in headers["Permissions-Policy"]


def test_sri_html_injector() -> None:
    manifest = {
        "/static/bundle.js": "sha384-abc123XYZ==",
        "style.css": "sha384-css456DEF==",
    }
    injector = SRIHTMLInjector(manifest)

    html = """<!DOCTYPE html>
<html>
<head>
    <link rel="stylesheet" href="/style.css">
    <link rel="stylesheet" href="/assets/already-secure.css" integrity="sha384-existing">
</head>
<body>
    <script src="/static/bundle.js"></script>
    <script src="https://cdn.example.com/external.js"></script>
</body>
</html>"""

    hardened = injector.inject(html)

    # bundle.js must have integrity and crossorigin
    assert '<script src="/static/bundle.js" integrity="sha384-abc123XYZ==" crossorigin="anonymous"></script>' in hardened

    # style.css must have integrity and crossorigin
    assert '<link rel="stylesheet" href="/style.css" integrity="sha384-css456DEF==" crossorigin="anonymous">' in hardened

    # Already hardened asset must not be duplicated
    assert 'integrity="sha384-existing"' in hardened
    assert 'sha384-abc123XYZ==' in hardened

    # Unmapped external script should remain untouched
    assert '<script src="https://cdn.example.com/external.js"></script>' in hardened


def test_audit_origin_security_headers() -> None:
    # Clean policy should produce 0 warnings
    clean_headers = OriginSecurityPolicy().to_headers_dict()
    warnings = audit_origin_security_headers(clean_headers)
    assert len(warnings) == 0

    # Insecure / missing headers
    bad_headers = {
        "Strict-Transport-Security": "max-age=1000",
        "X-Frame-Options": "ALLOWALL",
    }
    bad_warnings = audit_origin_security_headers(bad_headers)
    assert any("less than recommended 1 year" in w for w in bad_warnings)
    assert any("Cross-Origin-Opener-Policy" in w for w in bad_warnings)
    assert any("Permissions-Policy" in w for w in bad_warnings)
    assert any("X-Frame-Options" in w for w in bad_warnings)
