"""Unit tests for SEO sanitizer, slug generator, and OpenGraph metadata builder."""
import pytest
from buildsite.seo_sanitizer import (
    sanitize_slug,
    validate_canonical_url,
    OpenGraphMeta,
    build_sitemap_xml_entry,
)


def test_sanitize_slug():
    # Accents and international diacritics
    assert sanitize_slug("Café & Crème Brûlée!") == "cafe-creme-brulee"

    # Multi-space and punctuation collapse
    assert sanitize_slug("   BuildSite: The High-Performance Visualizer!   ") == "buildsite-the-high-performance-visualizer"

    # Fallback on empty or non-string
    assert sanitize_slug("") == "untitled"
    assert sanitize_slug(None) == "untitled"
    assert sanitize_slug("---") == "untitled"

    # Max length truncation
    long_title = "a" * 100
    assert len(sanitize_slug(long_title, max_length=50)) == 50


def test_validate_canonical_url():
    # Valid HTTPS
    assert validate_canonical_url("https://buildsite.dev/gallery") is True

    # Reject plain HTTP
    assert validate_canonical_url("http://buildsite.dev/gallery") is False

    # Domain whitelist
    assert validate_canonical_url("https://sub.buildsite.dev/p/1", allowed_domains=["buildsite.dev"]) is True
    assert validate_canonical_url("https://malicious.org/phish", allowed_domains=["buildsite.dev"]) is False

    # Malformed / empty
    assert validate_canonical_url("") is False
    assert validate_canonical_url(None) is False
    assert validate_canonical_url("not-a-url") is False


def test_opengraph_meta_render():
    meta = OpenGraphMeta(
        title='BuildSite "Pro" <Edition> & Fast',
        description="Visualize your code in 3D & isometric styles.",
        canonical_url="https://buildsite.dev/overview",
        image_url="https://buildsite.dev/assets/banner.png",
    )
    rendered = meta.render_meta_tags()

    # Must escape HTML quotes and angle brackets
    assert 'content="BuildSite &quot;Pro&quot; &lt;Edition&gt; &amp; Fast"' in rendered
    assert '<meta property="og:url" content="https://buildsite.dev/overview">' in rendered
    assert '<meta property="og:image" content="https://buildsite.dev/assets/banner.png">' in rendered
    assert '<meta name="twitter:card" content="summary_large_image">' in rendered


def test_build_sitemap_xml_entry():
    entry = build_sitemap_xml_entry(
        loc="https://buildsite.dev/docs",
        lastmod="2026-11-20",
        changefreq="daily",
        priority=0.9,
    )

    assert "<loc>https://buildsite.dev/docs</loc>" in entry
    assert "<lastmod>2026-11-20</lastmod>" in entry
    assert "<changefreq>daily</changefreq>" in entry
    assert "<priority>0.9</priority>" in entry

    # Priority clamping
    high_entry = build_sitemap_xml_entry("https://buildsite.dev", "2026-11-20", priority=1.5)
    assert "<priority>1.0</priority>" in high_entry
