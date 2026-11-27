"""Tests for build_telemetry_rotary."""
import sys
sys.path.insert(0, "src")
from buildsite.build_telemetry_rotary import BuildTelemetryRotary


def test_rotary_bounded():
    r = BuildTelemetryRotary(max_size=3)
    for i in range(5):
        r.push(f"event-{i}")
    assert r.count() == 3
    assert r.latest() == ["event-2", "event-3", "event-4"]
