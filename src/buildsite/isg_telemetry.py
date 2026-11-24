"""
BuildSite - Incremental Static Generation (ISG) Cache & Revalidation Telemetry Engine

Monitors, analyzes, and enforces performance SLAs for on-demand static generation,
stale-while-revalidate (SWR) pipelines, cache hit ratios, and revalidation latencies.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class CacheEventStatus(str, Enum):
    HIT = "HIT"
    MISS = "MISS"
    STALE_REVALIDATING = "STALE_REVALIDATING"
    BYPASS = "BYPASS"
    PURGED = "PURGED"


@dataclass
class PageRenderEvent:
    """Represents a discrete page request or compilation event in the ISG lifecycle."""
    route: str
    status: CacheEventStatus
    duration_ms: float
    content_bytes: int = 0
    stale_age_sec: float = 0.0
    timestamp: float = field(default_factory=time.time)
    error: Optional[str] = None


@dataclass
class RouteStats:
    """Aggregated cache and latency metrics for a specific static route."""
    route: str
    total_requests: int = 0
    hits: int = 0
    misses: int = 0
    stale_revalidations: int = 0
    bypasses: int = 0
    total_bytes: int = 0
    latencies_ms: List[float] = field(default_factory=list)

    @property
    def hit_ratio(self) -> float:
        """Calculates cache hit ratio (hits / total non-bypass requests)."""
        evaluable = self.hits + self.misses + self.stale_revalidations
        if evaluable == 0:
            return 1.0
        return round(self.hits / evaluable, 4)

    @property
    def mean_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return round(statistics.mean(self.latencies_ms), 2)

    @property
    def p95_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        if len(self.latencies_ms) == 1:
            return round(self.latencies_ms[0], 2)
        sorted_lats = sorted(self.latencies_ms)
        idx = int(len(sorted_lats) * 0.95)
        return round(sorted_lats[min(idx, len(sorted_lats) - 1)], 2)


@dataclass
class InvalidationRecord:
    """Record of a tag or path-based cache purge event."""
    target: str
    purged_routes_count: int
    duration_ms: float
    timestamp: float = field(default_factory=time.time)


class ISGTelemetryEngine:
    """
    Centralized telemetry and observability rotary for Incremental Static Generation (ISG).
    Tracks hit ratios, revalidation durations, cache staleness, and SLA breaches.
    """

    def __init__(
        self,
        target_hit_ratio: float = 0.85,
        max_p95_latency_ms: float = 500.0,
    ) -> None:
        self.target_hit_ratio = max(0.0, min(1.0, float(target_hit_ratio)))
        self.max_p95_latency_ms = max(1.0, float(max_p95_latency_ms))
        self.routes: Dict[str, RouteStats] = {}
        self.events: List[PageRenderEvent] = []
        self.invalidations: List[InvalidationRecord] = []

    def record_access(
        self,
        route: str,
        status: CacheEventStatus | str,
        duration_ms: float,
        content_bytes: int = 0,
        stale_age_sec: float = 0.0,
        error: Optional[str] = None,
    ) -> PageRenderEvent:
        """Records a route access or revalidation attempt."""
        clean_route = (route or "/").strip()
        if not clean_route.startswith("/"):
            clean_route = "/" + clean_route

        if isinstance(status, str):
            try:
                parsed_status = CacheEventStatus(status.upper())
            except ValueError:
                parsed_status = CacheEventStatus.MISS
        else:
            parsed_status = status

        dur = max(0.0, float(duration_ms))
        size = max(0, int(content_bytes))
        stale_age = max(0.0, float(stale_age_sec))

        event = PageRenderEvent(
            route=clean_route,
            status=parsed_status,
            duration_ms=dur,
            content_bytes=size,
            stale_age_sec=stale_age,
            error=error,
        )
        self.events.append(event)

        if clean_route not in self.routes:
            self.routes[clean_route] = RouteStats(route=clean_route)

        stats = self.routes[clean_route]
        stats.total_requests += 1
        stats.total_bytes += size
        stats.latencies_ms.append(dur)

        if parsed_status == CacheEventStatus.HIT:
            stats.hits += 1
        elif parsed_status == CacheEventStatus.MISS:
            stats.misses += 1
        elif parsed_status == CacheEventStatus.STALE_REVALIDATING:
            stats.stale_revalidations += 1
        elif parsed_status == CacheEventStatus.BYPASS:
            stats.bypasses += 1

        return event

    def record_invalidation(
        self,
        target: str,
        purged_routes_count: int,
        duration_ms: float,
    ) -> InvalidationRecord:
        """Records an explicit cache purge or revalidation trigger."""
        rec = InvalidationRecord(
            target=str(target or "").strip(),
            purged_routes_count=max(0, int(purged_routes_count)),
            duration_ms=max(0.0, float(duration_ms)),
        )
        self.invalidations.append(rec)
        return rec

    def get_route_stats(self, route: str) -> Optional[RouteStats]:
        """Retrieves aggregated metrics for a single route."""
        clean_route = (route or "/").strip()
        if not clean_route.startswith("/"):
            clean_route = "/" + clean_route
        return self.routes.get(clean_route)

    def get_fleet_hit_ratio(self) -> float:
        """Computes global hit ratio across all monitored routes."""
        total_hits = sum(r.hits for r in self.routes.values())
        total_evaluable = sum(r.hits + r.misses + r.stale_revalidations for r in self.routes.values())
        if total_evaluable == 0:
            return 1.0
        return round(total_hits / total_evaluable, 4)

    def evaluate_sla_breaches(self) -> List[Dict[str, Any]]:
        """Identifies routes failing to meet hit ratio or latency SLA thresholds."""
        breaches = []
        for route, stats in self.routes.items():
            if stats.total_requests < 3:
                continue  # Require minimal sample size to evaluate SLA

            ratio = stats.hit_ratio
            p95 = stats.p95_latency_ms

            reasons = []
            if ratio < self.target_hit_ratio:
                reasons.append(f"Hit ratio {ratio:.2%} < target {self.target_hit_ratio:.2%}")
            if p95 > self.max_p95_latency_ms:
                reasons.append(f"P95 latency {p95}ms > threshold {self.max_p95_latency_ms}ms")

            if reasons:
                breaches.append({
                    "route": route,
                    "hit_ratio": ratio,
                    "p95_latency_ms": p95,
                    "total_requests": stats.total_requests,
                    "reasons": reasons,
                })
        return breaches

    def generate_diagnostic_report(self) -> str:
        """Produces a structured Markdown diagnostic table of ISG telemetry."""
        lines = [
            "# BuildSite - ISG Cache & Revalidation Telemetry Diagnostic",
            "",
            f"- **Fleet-Wide Hit Ratio:** `{self.get_fleet_hit_ratio():.2%}` (Target: `{self.target_hit_ratio:.2%}`)",
            f"- **Total Monitored Routes:** `{len(self.routes)}`",
            f"- **Total Ingested Events:** `{len(self.events)}`",
            f"- **Cache Invalidation Cycles:** `{len(self.invalidations)}`",
            "",
            "## Route Telemetry Summary",
            "| Route | Requests | Hits | Misses | Revalidating | Hit Ratio | Mean Latency | P95 Latency | SLA Status |",
            "|---|---|---|---|---|---|---|---|---|",
        ]

        breach_routes = {b["route"] for b in self.evaluate_sla_breaches()}

        for route in sorted(self.routes.keys()):
            stats = self.routes[route]
            status_badge = "❌ BREACH" if route in breach_routes else "✅ NOMINAL"
            lines.append(
                f"| `{route}` | {stats.total_requests} | {stats.hits} | {stats.misses} | "
                f"{stats.stale_revalidations} | {stats.hit_ratio:.2%} | {stats.mean_latency_ms}ms | "
                f"{stats.p95_latency_ms}ms | {status_badge} |"
            )

        if self.invalidations:
            lines.extend([
                "",
                "## Recent Invalidation Events",
                "| Target / Tag | Purged Routes | Duration (ms) |",
                "|---|---|---|",
            ])
            for inv in self.invalidations[-5:]:
                lines.append(f"| `{inv.target}` | {inv.purged_routes_count} | {inv.duration_ms:.2f}ms |")

        return "\n".join(lines)

    def reset(self) -> None:
        """Clears all accumulated metrics and events."""
        self.routes.clear()
        self.events.clear()
        self.invalidations.clear()
