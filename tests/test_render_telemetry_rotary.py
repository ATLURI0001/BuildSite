"""
Unit tests for Page Render Telemetry Rotary in buildsite.
"""

import pytest

from buildsite.render_telemetry_rotary import (
    PageRenderSample,
    RenderPercentiles,
    RenderTelemetryRotary,
)


def test_nominal_render_telemetry():
    rotary = RenderTelemetryRotary(capacity=50, breach_threshold_ms=80.0)

    s1 = rotary.record_render(
        route_path="/docs/intro",
        template_name="docs_layout.html",
        duration_ms=12.5,
        output_bytes=4096,
        is_cached=False,
        timestamp=100.0,
    )

    assert s1.route_path == "/docs/intro"
    assert s1.duration_ms == 12.5
    assert s1.is_cached is False

    samples = rotary.get_active_samples()
    assert len(samples) == 1
    assert samples[0].route_path == "/docs/intro"


def test_circular_rollover_without_allocations():
    capacity = 10
    rotary = RenderTelemetryRotary(capacity=capacity)

    for i in range(25):
        rotary.record_render(
            route_path=f"/page/{i}",
            template_name="page.html",
            duration_ms=float(i * 2),
            output_bytes=1024,
        )

    assert rotary.total_ingested == 25
    active = rotary.get_active_samples()
    assert len(active) == capacity


def test_percentile_computation_and_summarize():
    rotary = RenderTelemetryRotary(capacity=50, breach_threshold_ms=45.0)

    for i in range(1, 11):
        rotary.record_render(
            route_path=f"/doc/{i}",
            template_name="doc.html",
            duration_ms=float(i * 5),  # 5ms to 50ms
            output_bytes=2048,
            is_cached=(i % 2 == 0),
        )

    summary = rotary.summarize()
    assert summary["total_samples"] == 10
    assert summary["cache_hit_ratio"] == 0.5
    assert summary["p50_ms"] == 30.0
    assert summary["max_ms"] == 50.0
    assert summary["breach_count"] == 2  # 45, 50 >= 45.0


def test_window_filtering():
    rotary = RenderTelemetryRotary(capacity=50)
    now = 1000.0

    rotary.record_render("/p1", "t", 10.0, 100, timestamp=now - 50.0)
    rotary.record_render("/p2", "t", 15.0, 100, timestamp=now - 15.0)
    rotary.record_render("/p3", "t", 20.0, 100, timestamp=now - 5.0)

    recent = rotary.get_window_samples(20.0, reference_time=now)
    assert len(recent) == 2


def test_defensive_validation():
    rotary = RenderTelemetryRotary(capacity=20)

    with pytest.raises(ValueError):
        rotary.record_render("", "t", 10.0, 100)
    with pytest.raises(ValueError):
        rotary.record_render("/p", "", 10.0, 100)
    with pytest.raises(ValueError):
        rotary.record_render("/p", "t", -5.0, 100)
    with pytest.raises(ValueError):
        RenderTelemetryRotary(capacity=5)
