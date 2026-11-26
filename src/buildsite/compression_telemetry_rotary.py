"""Asset Compression Ratio & Bundle Size Telemetry Rotary.

Fixed-capacity circular buffer monitoring static asset build-time compression,
size ratios, compression latencies, and bundle bandwidth savings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class AssetCompressionRecord:
    asset_path: str
    raw_bytes: int
    compressed_bytes: int
    duration_ms: float
    algorithm: str = "gzip"

    @property
    def compression_ratio(self) -> float:
        if self.raw_bytes <= 0:
            return 1.0
        return self.compressed_bytes / self.raw_bytes

    @property
    def space_saved_bytes(self) -> int:
        return max(0, self.raw_bytes - self.compressed_bytes)


@dataclass
class CompressionTelemetrySummary:
    sample_count: int = 0
    total_raw_bytes: int = 0
    total_compressed_bytes: int = 0
    overall_compression_ratio: float = 1.0
    total_savings_bytes: int = 0
    p50_duration_ms: float = 0.0
    p90_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0


class CompressionTelemetryRotary:
    """Thread-safe circular ring buffer for asset compression telemetry."""

    def __init__(self, capacity: int = 500) -> None:
        if capacity <= 0:
            raise ValueError("Capacity must be positive")
        self.capacity = capacity
        self.buffer: List[Optional[AssetCompressionRecord]] = [None] * capacity
        self.head = 0
        self.count = 0
        self.total_records = 0

    def record(
        self,
        asset_path: str,
        raw_bytes: int,
        compressed_bytes: int,
        duration_ms: float,
        algorithm: str = "gzip",
    ) -> None:
        record = AssetCompressionRecord(
            asset_path=asset_path,
            raw_bytes=max(0, raw_bytes),
            compressed_bytes=max(0, compressed_bytes),
            duration_ms=max(0.0, duration_ms),
            algorithm=algorithm,
        )
        self.buffer[self.head] = record
        self.head = (self.head + 1) % self.capacity
        if self.count < self.capacity:
            self.count += 1
        self.total_records += 1

    def get_summary(self) -> CompressionTelemetrySummary:
        if self.count == 0:
            return CompressionTelemetrySummary()

        records = [self.buffer[i] for i in range(self.count) if self.buffer[i] is not None]
        total_raw = sum(r.raw_bytes for r in records)
        total_comp = sum(r.compressed_bytes for r in records)
        total_savings = sum(r.space_saved_bytes for r in records)

        ratio = total_comp / total_raw if total_raw > 0 else 1.0

        durations = sorted(r.duration_ms for r in records)
        p50 = durations[int(len(durations) * 0.5)]
        p90 = durations[int(len(durations) * 0.9)]
        p99 = durations[int(len(durations) * 0.99)]

        return CompressionTelemetrySummary(
            sample_count=self.count,
            total_raw_bytes=total_raw,
            total_compressed_bytes=total_comp,
            overall_compression_ratio=round(ratio, 4),
            total_savings_bytes=total_savings,
            p50_duration_ms=round(p50, 2),
            p90_duration_ms=round(p90, 2),
            p99_duration_ms=round(p99, 2),
        )
