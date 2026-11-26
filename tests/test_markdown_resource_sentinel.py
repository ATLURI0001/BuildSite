import pytest
from buildsite.markdown_resource_sentinel import (
    MarkdownResourceSentinel,
    MarkdownResourceSecurityError,
    ResourceViolationType,
)


def test_markdown_resource_valid():
    sentinel = MarkdownResourceSentinel(allow_http=False)
    doc = """# Welcome to Docs
Here is our diagram:
![Architecture](/assets/diagram.png)
And a secure external badge:
![CI Badge](https://github.com/ATLURI0001/BuildSite/workflows/CI/badge.svg)
"""
    result = sentinel.scan_content(doc)
    assert result.is_safe is True
    assert result.total_images_scanned == 2
    assert len(result.violations) == 0


def test_markdown_resource_dangerous_schemes():
    sentinel = MarkdownResourceSentinel()

    # javascript: scheme
    doc_js = "![xss](javascript:alert(1))"
    res_js = sentinel.scan_content(doc_js)
    assert res_js.is_safe is False
    assert res_js.violations[0].violation == ResourceViolationType.DANGEROUS_SCHEME
    assert res_js.violations[0].incident_id == "INC-2026-SITE-8240"

    # data: scheme
    doc_data = "![payload](data:image/svg+xml;base64,PHN2Zz4=)"
    res_data = sentinel.scan_content(doc_data)
    assert res_data.is_safe is False
    assert res_data.violations[0].violation == ResourceViolationType.DANGEROUS_SCHEME


def test_markdown_resource_ssrf_mitigation():
    sentinel = MarkdownResourceSentinel(allow_http=True)

    # Cloud metadata endpoint
    doc_meta = "![metadata](http://169.254.169.254/latest/meta-data)"
    res_meta = sentinel.scan_content(doc_meta)
    assert res_meta.is_safe is False
    assert res_meta.violations[0].violation in (ResourceViolationType.SSRF_BLOCKED_HOST, ResourceViolationType.SSRF_PRIVATE_IP)

    # Localhost / internal RFC1918 IP
    doc_local = "![local](http://127.0.0.1:8080/internal-dash.png)"
    res_local = sentinel.scan_content(doc_local)
    assert res_local.is_safe is False
    assert res_local.violations[0].violation == ResourceViolationType.SSRF_PRIVATE_IP


def test_markdown_html_img_with_event_handler():
    sentinel = MarkdownResourceSentinel()
    doc_xss = '<p>Photo</p><img src="/img.png" onerror="alert(document.cookie)">'

    res = sentinel.scan_content(doc_xss)
    assert res.is_safe is False
    assert res.violations[0].violation == ResourceViolationType.HTML_INJECTION


def test_markdown_auto_sanitize():
    sentinel = MarkdownResourceSentinel()
    raw = """![Malicious](javascript:stealTokens())
![Safe](/assets/logo.png)"""

    res = sentinel.scan_content(raw, auto_sanitize=True)
    assert res.is_safe is False
    assert res.sanitized_content is not None
    assert "javascript:stealTokens()" not in res.sanitized_content
    assert "/assets/placeholder-blocked.svg" in res.sanitized_content
    assert "/assets/logo.png" in res.sanitized_content


def test_markdown_enforce_content_raises():
    sentinel = MarkdownResourceSentinel()
    with pytest.raises(MarkdownResourceSecurityError) as exc_info:
        sentinel.enforce_content("![leak](file:///etc/passwd)")
    assert exc_info.value.violation == ResourceViolationType.DANGEROUS_SCHEME
    assert exc_info.value.line_no == 1
