import pytest
from datetime import date, datetime
import xml.etree.ElementTree as ET
from buildsite.sitemap_generator import SitemapGenerator, SitemapEntry

def test_sitemap_generator_init_and_validation():
    gen = SitemapGenerator("https://example.com/")
    assert gen.base_url == "https://example.com"
    assert gen.max_urls_per_sitemap == 50000

    with pytest.raises(ValueError, match="Invalid base_url"):
        SitemapGenerator("ftp://example.com")

    with pytest.raises(ValueError, match="Invalid base_url"):
        SitemapGenerator("not-a-valid-url")


def test_sanitize_url_tracking_param_scrubbing():
    gen = SitemapGenerator("https://example.com")
    
    # Strip UTM params, keep legitimate query params
    url = gen.sanitize_url("/products?page=2&utm_source=twitter&utm_medium=social&category=shoes")
    assert "utm_source" not in url
    assert "utm_medium" not in url
    assert "page=2" in url
    assert "category=shoes" in url
    assert url.startswith("https://example.com/products")

    # Double slash removal
    url2 = gen.sanitize_url("///blog//post-1/")
    assert url2 == "https://example.com/blog/post-1/"

    # Empty URL error
    with pytest.raises(ValueError, match="URL cannot be empty"):
        gen.sanitize_url("   ")


def test_depth_priority_and_changefreq_heuristics():
    gen = SitemapGenerator("https://example.com")
    
    e1 = gen.add_url("/")
    assert e1.priority == 1.0
    assert e1.changefreq == "daily"

    e2 = gen.add_url("/docs")
    assert e2.priority == 0.8
    assert e2.changefreq == "weekly"

    e3 = gen.add_url("/docs/api")
    assert e3.priority == 0.6
    assert e3.changefreq == "monthly"

    e4 = gen.add_url("/docs/api/endpoints/v1")
    assert e4.priority == 0.4
    assert e4.changefreq == "monthly"


def test_format_lastmod_types():
    gen = SitemapGenerator("https://example.com")
    
    # Date
    e1 = gen.add_url("/page1", lastmod=date(2026, 11, 21))
    assert e1.lastmod == "2026-11-21"

    # Datetime
    e2 = gen.add_url("/page2", lastmod=datetime(2026, 11, 21, 14, 30, 0))
    assert e2.lastmod == "2026-11-21T14:30:00Z"

    # String ISO
    e3 = gen.add_url("/page3", lastmod="2026-11-21")
    assert e3.lastmod == "2026-11-21"

    # Invalid string
    with pytest.raises(ValueError, match="Invalid lastmod"):
        gen.add_url("/page4", lastmod="November 21 2026")


def test_render_single_sitemap_xml():
    gen = SitemapGenerator("https://example.com")
    gen.add_url("/", lastmod="2026-11-21", changefreq="daily", priority=1.0)
    gen.add_url("/about", lastmod="2026-11-20", changefreq="monthly", priority=0.8)

    xml_docs = gen.generate_sitemaps()
    assert len(xml_docs) == 1
    filename, content = xml_docs[0]
    assert filename == "sitemap.xml"
    assert "<?xml version='1.0' encoding='utf-8'?>" in content or '<?xml version="1.0" encoding="utf-8"?>' in content

    # Verify XML validity with ElementTree
    root = ET.fromstring(content)
    assert root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset"
    urls = root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url")
    assert len(urls) == 2

    first_loc = urls[0].find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc").text
    assert first_loc == "https://example.com/"
    first_prio = urls[0].find("{http://www.sitemaps.org/schemas/sitemap/0.9}priority").text
    assert first_prio == "1.0"


def test_sitemap_index_partitioning():
    # Set limit to 3 URLs per file to test partitioning
    gen = SitemapGenerator("https://example.com", max_urls_per_sitemap=3)
    for i in range(8):
        gen.add_url(f"/page-{i}")

    sitemaps = gen.generate_sitemaps()
    # 8 entries with max 3 per sitemap: chunk 1 (3), chunk 2 (3), chunk 3 (2), plus index = 4 files
    assert len(sitemaps) == 4

    filenames = [s[0] for s in sitemaps]
    assert filenames == ["sitemap-1.xml", "sitemap-2.xml", "sitemap-3.xml", "sitemap.xml"]

    # Verify index XML structure
    index_xml = sitemaps[3][1]
    root = ET.fromstring(index_xml)
    assert root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}sitemapindex"
    sitemap_nodes = root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap")
    assert len(sitemap_nodes) == 3

    loc_1 = sitemap_nodes[0].find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc").text
    assert loc_1 == "https://example.com/sitemap-1.xml"


def test_render_robots_txt():
    gen = SitemapGenerator("https://example.com")
    robots = gen.render_robots_txt(disallow_paths=["/admin", "/private/"])

    assert "User-agent: *" in robots
    assert "Disallow: /admin" in robots
    assert "Disallow: /private/" in robots
    assert "Sitemap: https://example.com/sitemap.xml" in robots
