"""Tests for asset_bundle_profiler."""
import sys
sys.path.insert(0, "src")
from buildsite.asset_bundle_profiler import AssetBundleProfiler


def test_asset_bundle_profiler():
    p = AssetBundleProfiler()
    p.record(10.0)
    p.record(20.0)
    assert p.avg_ms() == 15.0
