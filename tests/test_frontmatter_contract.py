import datetime
import pytest

from buildsite.frontmatter_contract import (
    FrontmatterContractError,
    parse_and_validate_date,
    sanitize_asset_path,
    sanitize_markdown_text,
    validate_frontmatter_contract,
)


def test_sanitize_markdown_text():
    dirty = "Hello <script>alert(1)</script> World <img src=x onerror=alert('xss')>!"
    cleaned = sanitize_markdown_text(dirty)
    assert "<script>" not in cleaned
    assert "onerror=" not in cleaned
    assert "Hello" in cleaned
    assert "World" in cleaned


def test_sanitize_asset_path():
    # Valid relative path
    assert sanitize_asset_path("/assets/images/banner.webp") == "/assets/images/banner.webp"

    # Valid external HTTPS path
    assert sanitize_asset_path("https://cdn.example.com/logo.svg") == "https://cdn.example.com/logo.svg"

    # Directory traversal rejection
    with pytest.raises(FrontmatterContractError, match="forbidden directory traversal"):
        sanitize_asset_path("../private/keys.png")

    # Unsafe URI scheme rejection
    with pytest.raises(FrontmatterContractError, match="prohibited URI scheme"):
        sanitize_asset_path("javascript:alert(document.cookie)")

    # Extension restriction
    with pytest.raises(FrontmatterContractError, match="extension 'exe' is not permitted"):
        sanitize_asset_path("/downloads/malware.exe", allowed_extensions={"png", "jpg", "svg"})


def test_validate_frontmatter_contract_success():
    raw = {
        "title": "Architecting Distributed Edge Gateways",
        "slug": "architecting-distributed-edge-gateways",
        "date": "2024-11-15",
        "tags": ["Cloud", "mcp", "Architecture", "cloud"], # duplicate 'cloud'
        "draft": False,
        "featured_image": "/assets/hero.png",
        "author": "Antigravity Team",
    }
    vf = validate_frontmatter_contract(raw)
    assert vf.title == "Architecting Distributed Edge Gateways"
    assert vf.slug == "architecting-distributed-edge-gateways"
    assert vf.date == datetime.date(2024, 11, 15)
    assert vf.tags == ["cloud", "mcp", "architecture"]  # lowercased and deduplicated
    assert vf.draft is False
    assert vf.featured_image == "/assets/hero.png"
    assert vf.extra == {"author": "Antigravity Team"}


def test_validate_frontmatter_contract_failures():
    # Missing title
    with pytest.raises(FrontmatterContractError, match="Missing mandatory frontmatter field: 'title'"):
        validate_frontmatter_contract({"slug": "test", "date": "2024-01-01"})

    # Invalid slug
    with pytest.raises(FrontmatterContractError, match="does not conform to lowercase kebab-case"):
        validate_frontmatter_contract({
            "title": "Valid Title",
            "slug": "Invalid_Slug_With_Underscores!",
            "date": "2024-01-01",
        })

    # Future date rejection
    future_date = (datetime.date.today() + datetime.timedelta(days=100)).isoformat()
    with pytest.raises(FrontmatterContractError, match="cannot be in the future"):
        validate_frontmatter_contract({
            "title": "Future Post",
            "slug": "future-post",
            "date": future_date,
        }, disallow_future_dates=True)
