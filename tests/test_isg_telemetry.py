"""
Unit and regression test suite for ISG Cache & Revalidation Telemetry Engine.
"""

import pytest
from buildsite.isg_telemetry import (
    CacheEventStatus,
    ISGTelemetryEngine,
    PageRenderEvent,
    RouteStats,
)


def test_isg_telemetry_initialization():
    engine = ISGTelemetryEngine(target_hit_ratio=0.90, max_p95_latency_ms=250.0)
    assert engine.target_hit_ratio == 0.90
    assert engine.max_p95_latency_ms == 250.0
    assert engine.get_fleet_hit_ratio() == 1.0
    assert len(engine.events) == 0


def test_record_access_route_normalization_and_counters():
    engine = ISGTelemetryEngine()

    # Route without leading slash
    ev1 = engine.record_access("blog/post-1", CacheEventStatus.HIT, duration_ms=4.5, content_bytes=1024)
    assert ev1.route == "/blog/post-1"
    assert ev1.status == CacheEventStatus.HIT

    # String status parsing
    ev2 = engine.record_access("/blog/post-1", "miss", duration_ms=120.0, content_bytes=2048)
    assert ev2.status == CacheEventStatus.MISS

    ev3 = engine.record_access("/blog/post-1", CacheEventStatus.STALE_REVALIDATING, duration_ms=18.0)
    assert ev3.status == CacheEventStatus.STALE_REVALIDATING

    ev4 = engine.record_access("/blog/post-1", CacheEventStatus.BYPASS, duration_ms=5.0)
    assert ev4.status == CacheEventStatus.BYPASS

    stats = engine.get_route_stats("/blog/post-1")
    assert stats is not None
    assert stats.total_requests == 4
    assert stats.hits == 1
    assert stats.misses == 1
    assert stats.stale_revalidations == 1
    assert stats.bypasses == 1
    # Evaluated: 1 hit out of 3 evaluable (1 hit, 1 miss, 1 stale) -> 1/3 = 0.3333
    assert stats.hit_ratio == 0.3333


def test_route_stats_latency_percentiles():
    stats = RouteStats(route="/docs")
    assert stats.mean_latency_ms == 0.0
    assert stats.p95_latency_ms == 0.0

    stats.latencies_ms = [10.0]
    assert stats.mean_latency_ms == 10.0
    assert stats.p95_latency_ms == 10.0

    stats.latencies_ms = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    assert stats.mean_latency_ms == 55.0
    # 95th percentile index = int(10 * 0.95) = 9 -> sorted_lats[9] = 100.0
    assert stats.p95_latency_ms == 100.0


def test_record_invalidation_and_fleet_hit_ratio():
    engine = ISGTelemetryEngine()

    for _ in range(8):
        engine.record_access("/home", CacheEventStatus.HIT, duration_ms=2.0)
    for _ in range(2):
        engine.record_access("/home", CacheEventStatus.MISS, duration_ms=45.0)

    for _ in range(5):
        engine.record_access("/about", CacheEventStatus.HIT, duration_ms=3.0)

    # Total hits: 8 + 5 = 13. Total requests: 10 + 5 = 15. Hit ratio = 13/15 = 0.8667
    assert engine.get_fleet_hit_ratio() == 0.8667

    inv = engine.record_invalidation("tag:blog", purged_routes_count=12, duration_ms=8.5)
    assert inv.target == "tag:blog"
    assert inv.purged_routes_count == 12
    assert inv.duration_ms == 8.5
    assert len(engine.invalidations) == 1


def test_evaluate_sla_breaches():
    engine = ISGTelemetryEngine(target_hit_ratio=0.80, max_p95_latency_ms=100.0)

    # Route 1: Healthy
    for _ in range(9):
        engine.record_access("/fast", CacheEventStatus.HIT, duration_ms=10.0)
    engine.record_access("/fast", CacheEventStatus.MISS, duration_ms=25.0)

    # Route 2: Hit ratio breach (3 hits, 7 misses -> 30%)
    for _ in range(3):
        engine.record_access("/slow-ratio", CacheEventStatus.HIT, duration_ms=15.0)
    for _ in range(7):
        engine.record_access("/slow-ratio", CacheEventStatus.MISS, duration_ms=20.0)

    # Route 3: Latency breach (10 hits, but latency 150ms > 100ms)
    for _ in range(10):
        engine.record_access("/slow-latency", CacheEventStatus.HIT, duration_ms=150.0)

    # Route 4: Too few samples (< 3 requests), should be ignored
    engine.record_access("/new", CacheEventStatus.MISS, duration_ms=300.0)

    breaches = engine.evaluate_sla_breaches()
    breach_map = {b["route"]: b for b in breaches}

    assert "/fast" not in breach_map
    assert "/new" not in breach_map
    assert "/slow-ratio" in breach_map
    assert any("Hit ratio" in r for r in breach_map["/slow-ratio"]["reasons"])
    assert "/slow-latency" in breach_map
    assert any("P95 latency" in r for r in breach_map["/slow-latency"]["reasons"])


def test_generate_diagnostic_report_and_reset():
    engine = ISGTelemetryEngine(target_hit_ratio=0.85)

    engine.record_access("/page-a", CacheEventStatus.HIT, duration_ms=5.0)
    engine.record_access("/page-a", CacheEventStatus.HIT, duration_ms=6.0)
    engine.record_access("/page-a", CacheEventStatus.MISS, duration_ms=80.0)
    engine.record_invalidation("site-wide", 5, 12.0)

    report = engine.generate_diagnostic_report()
    assert "# BuildSite - ISG Cache & Revalidation Telemetry Diagnostic" in report
    assert "/page-a" in report
    assert "site-wide" in report
    assert "Route Telemetry Summary" in report

    engine.reset()
    assert len(engine.routes) == 0
    assert len(engine.events) == 0
    assert len(engine.invalidations) == 0
    assert engine.get_route_stats("/page-a") is None
