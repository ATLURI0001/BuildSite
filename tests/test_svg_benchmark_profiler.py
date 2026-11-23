"""Tests for SVG Rendering & DOM Node Complexity Benchmark Profiler."""

import pytest
from buildsite.svg_benchmark_profiler import (
    BenchmarkMetricSnapshot,
    SVGBenchmarkProfiler,
)


def test_svg_profiler_synthetic_generation():
    profiler = SVGBenchmarkProfiler()
    svg = profiler.generate_synthetic_svg_scene(25)

    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert '<rect x=' in svg
    assert svg.count("<rect") == 25


def test_svg_profiler_workload_metrics():
    profiler = SVGBenchmarkProfiler(target_p90_sla_ms=50.0)
    snapshot = profiler.profile_workload(element_count=50, iterations=10)

    assert isinstance(snapshot, BenchmarkMetricSnapshot)
    assert snapshot.workload_tier == "LIGHT"
    assert snapshot.element_count == 50
    assert snapshot.iterations == 10
    assert snapshot.renders_per_sec > 0
    assert snapshot.elements_per_sec > 0
    assert snapshot.p50_latency_ms >= 0
    assert snapshot.p90_latency_ms >= snapshot.p50_latency_ms
    assert snapshot.p99_latency_ms >= snapshot.p90_latency_ms
    assert snapshot.compression_ratio > 1.0


def test_svg_profiler_benchmark_matrix_and_markdown():
    profiler = SVGBenchmarkProfiler()
    snapshots = profiler.run_benchmark_matrix()

    assert len(snapshots) == 3
    tiers = [s.workload_tier for s in snapshots]
    assert tiers == ["LIGHT", "MEDIUM", "HEAVY"]

    report = profiler.format_markdown_report(snapshots)
    assert "### SVG Scene Rendering Benchmark & Profiling Report" in report
    assert "| **LIGHT** |" in report
    assert "| **MEDIUM** |" in report
    assert "| **HEAVY** |" in report
