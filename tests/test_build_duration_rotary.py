"""Tests for BuildDurationRotary."""
from buildsite.build_duration_rotary import BuildDurationRotary


def test_build_duration_rotary():
    r = BuildDurationRotary(capacity=2)
    r.record(100.0)
    r.record(200.0)
    r.record(300.0)
    assert r.avg_ms() == 250.0
