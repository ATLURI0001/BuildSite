"""HTML minification throughput profiler."""
import re
import time


def minify_html(html: str) -> str:
    """Remove extra whitespace from HTML."""
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
    html = re.sub(r'>\s+<', '><', html)
    html = re.sub(r'\s{2,}', ' ', html)
    return html.strip()


class HtmlMinifyProfiler:
    """Benchmarks HTML minification throughput."""

    def run_benchmark(self, html: str, iterations: int = 1000) -> dict:
        start = time.perf_counter()
        for _ in range(iterations):
            minify_html(html)
        elapsed = time.perf_counter() - start
        throughput = iterations / elapsed
        return {
            "iterations": iterations,
            "elapsed_s": round(elapsed, 4),
            "throughput_per_s": round(throughput, 2),
        }
