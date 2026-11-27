"""Tests for slug_normalize_profiler."""
from buildsite.slug_normalize_profiler import benchmark_slug_normalize


def test_slug_normalize_profiler():
    ops = benchmark_slug_normalize(["Hello World!", "Static Site Gen"], iterations=50)
    assert ops > 0
