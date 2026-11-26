"""Tests for HTML minification throughput profiler."""
from buildsite.html_minify_profiler import HtmlMinifyProfiler, minify_html


def test_minify_html_removes_comments():
    result = minify_html("<!-- comment --><p>Hello</p>")
    assert "<!--" not in result
    assert "<p>Hello</p>" in result


def test_profiler_throughput():
    profiler = HtmlMinifyProfiler()
    html = "<div>  <p>  Hello   World  </p>  </div>"
    result = profiler.run_benchmark(html, iterations=100)
    assert result["iterations"] == 100
    assert result["throughput_per_s"] > 0
