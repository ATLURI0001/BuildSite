"""
Tests for BuildSite Markdown Parsing & HTML Compilation Latency Benchmark Profiler.
"""

import pytest
from buildsite.markdown_compiler_profiler import (
    CompilerBenchmarkReport,
    MarkdownCompilerProfiler,
)


def test_compile_to_html_formatting() -> None:
    profiler = MarkdownCompilerProfiler()
    markdown = """# Main Header
This is a **bold** statement and *italic* note with `inline_code`.

```python
def hello():
    return "world"
```

Check out [Link Text](https://example.com).
- First item
- Second item
"""
    html_out = profiler.compile_to_html(markdown)
    assert "<h1>Main Header</h1>" in html_out
    assert "<strong>bold</strong>" in html_out
    assert "<em>italic</em>" in html_out
    assert "<code>inline_code</code>" in html_out
    assert '<code class="language-python">' in html_out
    assert '<a href="https://example.com">Link Text</a>' in html_out
    assert "<li>First item</li>" in html_out


def test_compile_to_html_empty_and_error() -> None:
    profiler = MarkdownCompilerProfiler()
    assert profiler.compile_to_html("") == ""
    assert profiler.compile_to_html("   \n\t  ") == ""

    with pytest.raises(TypeError):
        profiler.compile_to_html(12345)  # type: ignore


def test_synthetic_markdown_generation() -> None:
    profiler = MarkdownCompilerProfiler()
    doc = profiler.create_synthetic_markdown(target_size_bytes=4096)
    assert len(doc) >= 1000
    assert "# Architecture Overview" in doc
    assert "```python" in doc


def test_profile_compiler_metrics() -> None:
    profiler = MarkdownCompilerProfiler()
    report = profiler.profile_compiler(iterations=50, size_tier="compact")

    assert isinstance(report, CompilerBenchmarkReport)
    assert report.document_size_tier == "compact"
    assert report.iterations == 50
    assert report.throughput_docs_per_sec > 0.0
    assert report.mean_latency_ms > 0.0
    assert report.p50_latency_ms > 0.0
    assert report.p90_latency_ms >= report.p50_latency_ms
    assert report.p99_latency_ms >= report.p90_latency_ms
    assert report.total_bytes_processed > 0
