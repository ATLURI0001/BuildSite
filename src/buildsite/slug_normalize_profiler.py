"""URL slug normalization throughput profiler."""
import re
import time

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def benchmark_slug_normalize(titles: list[str], iterations: int = 200) -> float:
    start = time.perf_counter()
    for _ in range(iterations):
        for t in titles:
            _ = _SLUG_RE.sub("-", t.lower()).strip("-")
    elapsed = max(time.perf_counter() - start, 1e-9)
    return round((iterations * len(titles)) / elapsed, 2)
