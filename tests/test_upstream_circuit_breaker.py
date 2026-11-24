"""Tests for UpstreamCircuitBreaker and resilience mechanisms."""

import threading
import time
import pytest

from buildsite.upstream_circuit_breaker import (
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
    UpstreamCircuitBreaker,
    compute_jittered_backoff,
)


def test_circuit_nominal_execution():
    breaker = UpstreamCircuitBreaker(name="test-api")
    assert breaker.state == CircuitState.CLOSED

    res = breaker.call(lambda x, y: x + y, 10, 20)
    assert res == 30

    snap = breaker.snapshot()
    assert snap.total_calls == 1
    assert snap.successful_calls == 1
    assert snap.failed_calls == 0
    assert snap.state == CircuitState.CLOSED


def test_circuit_trip_to_open_after_failures():
    fake_time = [1000.0]
    config = CircuitBreakerConfig(failure_threshold=3, cooldown_seconds=20.0)
    breaker = UpstreamCircuitBreaker(
        name="flaky-api", config=config, now_func=lambda: fake_time[0]
    )

    def failing_call():
        raise ConnectionResetError("network peer dropped")

    # 1st and 2nd failure: still CLOSED
    for _ in range(2):
        with pytest.raises(ConnectionResetError):
            breaker.call(failing_call)
        assert breaker.state == CircuitState.CLOSED

    # 3rd failure: trips to OPEN
    with pytest.raises(ConnectionResetError):
        breaker.call(failing_call)

    assert breaker.state == CircuitState.OPEN
    snap = breaker.snapshot()
    assert snap.tripped_count == 1
    assert snap.time_until_retry_seconds == 20.0

    # 4th call: rejected with CircuitOpenError without executing failing_call
    with pytest.raises(CircuitOpenError):
        breaker.call(failing_call)


def test_circuit_fallback_execution():
    fake_time = [1000.0]
    config = CircuitBreakerConfig(failure_threshold=2, cooldown_seconds=10.0)
    breaker = UpstreamCircuitBreaker(
        name="fallback-api", config=config, now_func=lambda: fake_time[0]
    )

    def flaky():
        raise TimeoutError("upstream timeout")

    fallback_called = False

    def fallback():
        nonlocal fallback_called
        fallback_called = True
        return {"status": "degraded_cached_response"}

    # On error with fallback: returns fallback
    res = breaker.call(flaky, fallback=fallback)
    assert res == {"status": "degraded_cached_response"}
    assert fallback_called

    # 2nd failure trips breaker
    breaker.call(flaky, fallback=fallback)
    assert breaker.state == CircuitState.OPEN

    # While OPEN: calls directly to fallback
    res2 = breaker.call(flaky, fallback=fallback)
    assert res2 == {"status": "degraded_cached_response"}


def test_circuit_half_open_recovery():
    fake_time = [1000.0]
    config = CircuitBreakerConfig(
        failure_threshold=2, recovery_success_threshold=2, cooldown_seconds=15.0
    )
    breaker = UpstreamCircuitBreaker(
        name="recovering-api", config=config, now_func=lambda: fake_time[0]
    )

    # Trip breaker
    for _ in range(2):
        with pytest.raises(ValueError):
            breaker.call(lambda: (_ for _ in ()).throw(ValueError("err")))

    assert breaker.state == CircuitState.OPEN

    # Advance time past cooldown
    fake_time[0] += 16.0
    assert breaker.state == CircuitState.HALF_OPEN

    # 1st success in HALF_OPEN: stays HALF_OPEN
    res1 = breaker.call(lambda: "success-1")
    assert res1 == "success-1"
    assert breaker.state == CircuitState.HALF_OPEN

    # 2nd success in HALF_OPEN: recovers to CLOSED
    res2 = breaker.call(lambda: "success-2")
    assert res2 == "success-2"
    assert breaker.state == CircuitState.CLOSED


def test_circuit_half_open_immediate_retrip():
    fake_time = [1000.0]
    config = CircuitBreakerConfig(
        failure_threshold=2, recovery_success_threshold=2, cooldown_seconds=15.0
    )
    breaker = UpstreamCircuitBreaker(
        name="retrip-api", config=config, now_func=lambda: fake_time[0]
    )

    # Trip breaker
    for _ in range(2):
        with pytest.raises(RuntimeError):
            breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("err")))

    fake_time[0] += 16.0
    assert breaker.state == CircuitState.HALF_OPEN

    # Failure in HALF_OPEN immediately trips back to OPEN
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("probe failed")))

    assert breaker.state == CircuitState.OPEN
    assert breaker.snapshot().tripped_count == 2


def test_circuit_jittered_backoff():
    # Deterministic backoff without jitter
    d0 = compute_jittered_backoff(0, base_delay=1.0, max_delay=30.0, enable_jitter=False)
    d1 = compute_jittered_backoff(1, base_delay=1.0, max_delay=30.0, enable_jitter=False)
    d2 = compute_jittered_backoff(2, base_delay=1.0, max_delay=30.0, enable_jitter=False)
    d_max = compute_jittered_backoff(10, base_delay=1.0, max_delay=30.0, enable_jitter=False)

    assert d0 == 1.0
    assert d1 == 2.0
    assert d2 == 4.0
    assert d_max == 30.0

    # With jitter
    for attempt in range(4):
        delay = compute_jittered_backoff(attempt, base_delay=1.0, max_delay=30.0, enable_jitter=True)
        assert 0.0 <= delay <= (1.0 * (2.0 ** attempt))


def test_circuit_decorator():
    breaker = UpstreamCircuitBreaker(name="decorator-test")

    @breaker.protect(fallback=lambda: "fallback_val")
    def fetch_data(should_fail=False):
        if should_fail:
            raise RuntimeError("upstream exploded")
        return "live_data"

    assert fetch_data(False) == "live_data"
    assert fetch_data(True) == "fallback_val"


def test_circuit_concurrency():
    breaker = UpstreamCircuitBreaker(name="concurrent-test")
    threads = []
    iterations = 50

    def worker(worker_id):
        for i in range(iterations):
            if i % 5 == 0:
                breaker.call(
                    lambda: (_ for _ in ()).throw(ValueError("transient")),
                    fallback=lambda: "recovered",
                )
            else:
                breaker.call(lambda: i * 2)

    for w in range(6):
        t = threading.Thread(target=worker, args=(w,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    snap = breaker.snapshot()
    assert snap.total_calls == 6 * iterations
