"""
Page Render Duration & Compilation Telemetry Rotary for buildsite.

Provides a fixed-memory ring buffer for capturing static page generation latencies,
template rendering durations, cache hit ratios, and percentile performance metrics.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PageRenderSample:
    route_path: str
    template_name: str
    duration_ms: float
    output_bytes: int
    is_cached: bool
    timestamp: float = field(default_factory=time.time)


@dataclass
class RenderPercentiles:
    p50_ms: float
    p90_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float
    avg_ms: float


class RenderTelemetryRotary:
    """Circular telemetry buffer for static site rendering benchmarks and monitoring."""

    def __init__(self, capacity: int = 250, breach_threshold_ms: float = 100.0):
        if capacity < 10:
            raise ValueError(f"capacity must be at least 10, got {capacity}")
        if breach_threshold_ms <= 0:
            raise ValueError(f"breach_threshold_ms must be positive, got {breach_threshold_ms}")

        self.capacity = capacity
        self.breach_threshold_ms = breach_threshold_ms
        self.buffer: List[Optional[PageRenderSample]] = [None] * capacity
        self.head_index = 0
        self.total_ingested = 0

    def record_render(
        self,
        route_path: str,
        template_name: str,
        duration_ms: float,
        output_bytes: int,
        is_cached: bool = False,
        timestamp: Optional[float] = None,
    ) -> PageRenderSample:
        """Record an individual page generation metric into the circular ring buffer."""
        if not route_path or not isinstance(route_path, str):
            raise ValueError("route_path must be a non-empty string")
        if not template_name or not isinstance(template_name, str):
            raise ValueError("template_name must be a non-empty string")
        if duration_ms < 0:
            raise ValueError("duration_ms cannot be negative")
        if output_bytes < 0:
            raise ValueError("output_bytes cannot be negative")

        ts = time.time() if timestamp is None else timestamp

        sample = PageRenderSample(
            route_path=route_path,
            template_name=template_name,
            duration_ms=round(duration_ms, 3),
            output_bytes=output_bytes,
            is_cached=is_cached,
            timestamp=ts,
        )

        self.buffer[self.head_index] = sample
        self.head_index = (self.head_index + 1) % self.capacity
        self.total_ingested += 1

        return sample

    def get_active_samples(self) -> List[PageRenderSample]:
        """Return all valid populated samples in the rotary buffer."""
        count = min(self.total_ingested, self.capacity)
        active = []
        for i in range(count):
            s = self.buffer[i]
            if s is not None:
                active.append(s)
        return active

    def get_window_samples(self, window_sec: float, reference_time: Optional[float] = None) -> List[PageRenderSample]:
        """Return samples residing within the trailing window relative to reference_time."""
        now = time.time() if reference_time is None else reference_time
        cutoff = now - window_sec
        return [s for s in self.get_active_samples() if s.timestamp >= cutoff]

    def compute_percentiles(self, samples: Optional[List[PageRenderSample]] = None) -> RenderPercentiles:
        """Calculate p50, p90, p99, min, max, and avg render durations."""
        target = samples if samples is not None else self.get_active_samples()
        n = len(target)
        if n == 0:
            return RenderPercentiles(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        durations = sorted([s.duration_ms for s in target])

        def get_p(p: float) -> float:
            idx = min(int((p / 100.0) * n), n - 1)
            return round(durations[idx], 3)

        return RenderPercentiles(
            p50_ms=get_p(50.0),
            p90_ms=get_p(90.0),
            p99_ms=get_p(99.0),
            min_ms=round(durations[0], 3),
            max_ms=round(durations[-1], 3),
            avg_ms=round(sum(durations) / n, 3),
        )

    def summarize(self) -> Dict[str, Any]:
        """Summarize current rendering telemetry."""
        samples = self.get_active_samples()
        n = len(samples)
        if n == 0:
            return {
                "total_samples": 0,
                "cache_hit_ratio": 0.0,
                "breach_count": 0,
                "percentiles": self.compute_percentiles().p50_ms,
            }

        cached_count = sum(1 for s in samples if s.is_cached)
        breaches = sum(1 for s in samples if s.duration_ms >= self.breach_threshold_ms)
        percentiles = self.compute_percentiles(samples)

        return {
            "total_samples": n,
            "cache_hit_ratio": round(cached_count / n, 3),
            "breach_count": breaches,
            "p50_ms": percentiles.p50_ms,
            "p90_ms": percentiles.p90_ms,
            "p99_ms": percentiles.p99_ms,
            "avg_ms": percentiles.avg_ms,
            "max_ms": percentiles.max_ms,
        }

    def reset(self) -> None:
        """Reset the telemetry buffer."""
        self.buffer = [None] * self.capacity
        self.head_index = 0
        self.total_ingested = 0
