import time
from buildsite.asset_fetch_circuit_breaker import AssetFetchCircuitBreaker, CircuitState


def test_circuit_breaker_trip_and_recovery():
    cb = AssetFetchCircuitBreaker(failure_threshold=2, recovery_threshold=2, cooldown_seconds=0.05)

    def fail_fetch():
        raise ConnectionError("CDN timeout")

    def ok_fetch():
        return b"asset-payload"

    # Failure 1 -> still CLOSED
    data, used_fb = cb.fetch(fail_fetch, fallback=b"cached")
    assert used_fb is True and data == b"cached"
    assert cb.state == CircuitState.CLOSED

    # Failure 2 -> trips OPEN
    cb.fetch(fail_fetch, fallback=b"cached")
    assert cb.state == CircuitState.OPEN

    # Short circuit while OPEN
    data, used_fb = cb.fetch(ok_fetch, fallback=b"cached")
    assert used_fb is True and data == b"cached"

    # Wait cooldown -> HALF_OPEN -> CLOSED
    time.sleep(0.06)
    data, used_fb = cb.fetch(ok_fetch, fallback=b"cached")
    assert used_fb is False and data == b"asset-payload"
    assert cb.state == CircuitState.HALF_OPEN

    cb.fetch(ok_fetch, fallback=b"cached")
    assert cb.state == CircuitState.CLOSED
