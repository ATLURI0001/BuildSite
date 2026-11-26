"""Tests for CdnSyncCircuitBreaker."""
import pytest
from buildsite.cdn_sync_circuit_breaker import CdnCircuitOpenError, CdnSyncCircuitBreaker


def test_cdn_sync_circuit_breaker():
    cb = CdnSyncCircuitBreaker(threshold=2, cooldown_s=5.0)
    with pytest.raises(IOError):
        cb.call(lambda: (_ for _ in ()).throw(IOError("cdn fail")))
    with pytest.raises(IOError):
        cb.call(lambda: (_ for _ in ()).throw(IOError("cdn fail")))
    with pytest.raises(CdnCircuitOpenError):
        cb.call(lambda: "ok")
