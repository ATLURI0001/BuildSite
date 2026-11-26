"""Sitemap XML generation throughput profiler."""
import time


def benchmark_sitemap_gen(urls: list[str], iterations: int = 200) -> float:
    start = time.perf_counter()
    for _ in range(iterations):
        _ = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    elapsed = max(time.perf_counter() - start, 1e-9)
    return round((iterations * len(urls)) / elapsed, 2)
