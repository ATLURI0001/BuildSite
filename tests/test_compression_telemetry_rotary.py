import pytest
from buildsite.compression_telemetry_rotary import (
    CompressionTelemetryRotary,
)


def test_empty_rotary():
    rotary = CompressionTelemetryRotary(capacity=10)
    summary = rotary.get_summary()

    assert summary.sample_count == 0
    assert summary.total_raw_bytes == 0
    assert summary.overall_compression_ratio == 1.0


def test_single_asset_record():
    rotary = CompressionTelemetryRotary(capacity=10)
    rotary.record("dist/bundle.js", raw_bytes=1000, compressed_bytes=300, duration_ms=12.5)

    summary = rotary.get_summary()
    assert summary.sample_count == 1
    assert summary.total_raw_bytes == 1000
    assert summary.total_compressed_bytes == 300
    assert summary.total_savings_bytes == 700
    assert summary.overall_compression_ratio == 0.3
    assert summary.p50_duration_ms == 12.5


def test_wrap_around_and_quantiles():
    rotary = CompressionTelemetryRotary(capacity=5)

    # Insert 10 records with durations 10..100
    for i in range(1, 11):
        rotary.record(
            f"page_{i}.html",
            raw_bytes=2000,
            compressed_bytes=800,
            duration_ms=i * 10.0,
        )

    summary = rotary.get_summary()
    assert summary.sample_count == 5
    assert summary.total_raw_bytes == 10000  # 5 * 2000
    assert summary.total_compressed_bytes == 4000  # 5 * 800
    assert summary.overall_compression_ratio == 0.4
    assert summary.p50_duration_ms >= 50.0


def test_invalid_capacity():
    with pytest.raises(ValueError):
        CompressionTelemetryRotary(capacity=0)
