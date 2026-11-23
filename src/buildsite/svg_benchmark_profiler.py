"""SVG Rendering & DOM Node Complexity Benchmark Profiler.

Profiles SVG scene generation latency, polygon projection throughput,
XML serialization speed, and compression ratios across rendering workloads.
"""

from __future__ import annotations

import gzip
import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class BenchmarkMetricSnapshot:
    workload_tier: str
    element_count: int
    iterations: int
    duration_ms: float
    renders_per_sec: float
    elements_per_sec: float
    p50_latency_ms: float
    p90_latency_ms: float
    p99_latency_ms: float
    raw_size_bytes: int
    gzip_size_bytes: int
    compression_ratio: float


class SVGBenchmarkProfiler:
    """Benchmark profiler for SVG DOM synthesis and rendering pipelines."""

    def __init__(self, target_p90_sla_ms: float = 100.0) -> None:
        self.target_p90_sla_ms = target_p90_sla_ms

    def generate_synthetic_svg_scene(self, element_count: int) -> str:
        """Generates a synthetic SVG document with complex polygons and style attributes."""
        if element_count <= 0:
            element_count = 10

        parts = [
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" width="1000" height="1000">\n',
            '  <defs>\n',
            '    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">\n',
            '      <stop offset="0%" stop-color="#3b82f6" />\n',
            '      <stop offset="100%" stop-color="#1e40af" />\n',
            '    </linearGradient>\n',
            '  </defs>\n',
            '  <g id="viewport">\n',
        ]

        for i in range(element_count):
            x = (i * 37) % 900
            y = (i * 53) % 900
            w = 20 + (i % 50)
            h = 20 + (i % 40)
            opacity = 0.5 + ((i % 50) / 100.0)
            parts.append(
                f'    <rect x="{x}" y="{y}" width="{w}" height="{h}" '
                f'fill="url(#grad)" opacity="{opacity:.2f}" rx="4" />\n'
            )

        parts.append('  </g>\n</svg>')
        return "".join(parts)

    def profile_workload(self, element_count: int, iterations: int = 50) -> BenchmarkMetricSnapshot:
        """Executes repeated rendering iterations, profiling latency percentiles and throughput."""
        if iterations <= 0:
            iterations = 10

        latencies_ms: List[float] = []
        last_svg = ""

        t_start = time.perf_counter()
        for _ in range(iterations):
            iter_start = time.perf_counter()
            last_svg = self.generate_synthetic_svg_scene(element_count)
            iter_end = time.perf_counter()
            latencies_ms.append((iter_end - iter_end + (iter_end - iter_start)) * 1000.0)
        t_end = time.perf_counter()

        total_duration_ms = (t_end - t_start) * 1000.0
        latencies_ms.sort()

        n = len(latencies_ms)
        p50 = latencies_ms[int(n * 0.50)]
        p90 = latencies_ms[min(int(n * 0.90), n - 1)]
        p99 = latencies_ms[min(int(n * 0.99), n - 1)]

        renders_per_sec = (iterations / (total_duration_ms / 1000.0)) if total_duration_ms > 0 else 0.0
        elements_per_sec = renders_per_sec * element_count

        raw_bytes = len(last_svg.encode("utf-8"))
        gzip_bytes = len(gzip.compress(last_svg.encode("utf-8")))
        comp_ratio = (raw_bytes / gzip_bytes) if gzip_bytes > 0 else 1.0

        tier = "LIGHT" if element_count <= 250 else "MEDIUM" if element_count <= 1500 else "HEAVY"

        return BenchmarkMetricSnapshot(
            workload_tier=tier,
            element_count=element_count,
            iterations=iterations,
            duration_ms=round(total_duration_ms, 2),
            renders_per_sec=round(renders_per_sec, 1),
            elements_per_sec=round(elements_per_sec, 1),
            p50_latency_ms=round(p50, 3),
            p90_latency_ms=round(p90, 3),
            p99_latency_ms=round(p99, 3),
            raw_size_bytes=raw_bytes,
            gzip_size_bytes=gzip_bytes,
            compression_ratio=round(comp_ratio, 2),
        )

    def run_benchmark_matrix(self) -> List[BenchmarkMetricSnapshot]:
        """Runs the benchmark across all three standard tiers."""
        return [
            self.profile_workload(100, iterations=50),
            self.profile_workload(1000, iterations=30),
            self.profile_workload(3000, iterations=20),
        ]

    def format_markdown_report(self, snapshots: List[BenchmarkMetricSnapshot]) -> str:
        """Generates a structured markdown report summarizing benchmark results."""
        lines = [
            "### SVG Scene Rendering Benchmark & Profiling Report\n",
            "| Workload Tier | Elements | Iterations | Renders/sec | Elements/sec | P50 (ms) | P90 (ms) | P99 (ms) | Gzip Ratio |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for s in snapshots:
            lines.append(
                f"| **{s.workload_tier}** | {s.element_count:,} | {s.iterations} | "
                f"{s.renders_per_sec:,.1f} | {s.elements_per_sec:,.1f} | "
                f"{s.p50_latency_ms:.3f} | {s.p90_latency_ms:.3f} | {s.p99_latency_ms:.3f} | "
                f"{s.compression_ratio:.2f}x |"
            )

        return "\n".join(lines) + "\n"
