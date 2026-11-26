"""Tests for sitemap_gen_profiler."""
from buildsite.sitemap_gen_profiler import benchmark_sitemap_gen


def test_sitemap_gen_profiler():
    ops = benchmark_sitemap_gen(["https://example.com/a", "https://example.com/b"], iterations=50)
    assert ops > 0
