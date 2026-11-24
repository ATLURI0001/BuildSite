"""Upstream Circuit Breaker & Defensive Resilience Engine for BuildSite.

Protects site generation, asset downloads, and API collectors from cascading
failures during upstream outages (e.g. GitHub API rate limits, CDN timeouts,
503 Service Unavailable).
"""

from __future__ import annotations

import enum
import functools
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, enum.Enum):
    """Operational states of the circuit breaker."""

    CLOSED = "CLOSED"
    HALF_OPEN = "HALF_OPEN"
    OPEN = "OPEN"


class CircuitBreakerError(Exception):
    """Base exception for circuit breaker rejections."""


class CircuitOpenError(CircuitBreakerError):
    """Raised when an operation is attempted while the circuit breaker is OPEN."""


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Configures failure thresholds and recovery bounds."""

    failure_threshold: int = 5
    recovery_success_threshold: int = 2
    cooldown_seconds: float = 30.0
    max_backoff_seconds: float = 60.0
    enable_jitter: bool = True


@dataclass
class CircuitSnapshot:
    """Telemetry snapshot of live circuit breaker state."""

    state: CircuitState
    total_calls: int
    successful_calls: int
    failed_calls: int
    rejected_calls: int
    consecutive_failures: int
    consecutive_successes: int
    tripped_count: int
    last_state_change: float
    time_until_retry_seconds: float


def compute_jittered_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    enable_jitter: bool = True,
) -> float:
    """Computes exponential backoff with full jitter to avoid thundering herds."""
    attempt_clamped = max(0, min(attempt, 10))
    raw_backoff = min(max_delay, base_delay * (2.0 ** attempt_clamped))
    if not enable_jitter:
        return raw_backoff
    return random.uniform(0.0, raw_backoff)


class UpstreamCircuitBreaker:
    """Defensive circuit breaker guarding remote HTTP/API interactions."""

    def __init__(
        self,
        name: str = "upstream-api",
        config: Optional[CircuitBreakerConfig] = None,
        now_func: Optional[Callable[[], float]] = None,
    ) -> None:
        self.name = str(name or "upstream-api").strip()
        self.config = config or CircuitBreakerConfig()
        self._now = now_func or time.time
        self._lock = threading.Lock()

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._last_state_change = self._now()
        self._last_failure_time = 0.0

        # Operational metrics counters
        self._total_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0
        self._rejected_calls = 0
        self._tripped_count = 0

    @property
    def state(self) -> CircuitState:
        """Returns the current state, evaluating cooldown transition if necessary."""
        with self._lock:
            self._evaluate_state_locked()
            return self._state

    def call(
        self,
        func: Callable[..., T],
        *args: Any,
        fallback: Optional[Callable[[], T]] = None,
        **kwargs: Any,
    ) -> T:
        """Executes a function under circuit breaker protection, delegating to fallback if open."""
        with self._lock:
            self._total_calls += 1
            self._evaluate_state_locked()

            if self._state == CircuitState.OPEN:
                self._rejected_calls += 1
                if fallback is not None:
                    logger.warning(
                        "Circuit breaker '%s' is OPEN; invoking defensive fallback",
                        self.name,
                    )
                    return fallback()
                raise CircuitOpenError(
                    f"Circuit breaker '{self.name}' is OPEN; upstream calls rejected."
                )

        # Execute target function outside lock
        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as exc:
            self._record_failure()
            if fallback is not None:
                logger.warning(
                    "Operation failed in circuit breaker '%s' (%s); falling back",
                    self.name,
                    exc,
                )
                return fallback()
            raise

    def protect(
        self, fallback: Optional[Callable[[], Any]] = None
    ) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """Decorator to wrap a function with circuit breaker resilience."""

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> T:
                return self.call(func, *args, fallback=fallback, **kwargs)

            return wrapper

        return decorator

    def _record_success(self) -> None:
        with self._lock:
            self._successful_calls += 1
            if self._state == CircuitState.HALF_OPEN:
                self._consecutive_successes += 1
                if (
                    self._consecutive_successes
                    >= self.config.recovery_success_threshold
                ):
                    self._transition_to_locked(CircuitState.CLOSED)
            elif self._state == CircuitState.CLOSED:
                self._consecutive_failures = 0

    def _record_failure(self) -> None:
        with self._lock:
            self._failed_calls += 1
            self._last_failure_time = self._now()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure during half-open trial immediately re-trips
                self._transition_to_locked(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                self._consecutive_failures += 1
                if (
                    self._consecutive_failures
                    >= self.config.failure_threshold
                ):
                    self._transition_to_locked(CircuitState.OPEN)

    def _evaluate_state_locked(self) -> None:
        now = self._now()
        if self._state == CircuitState.OPEN:
            elapsed = now - self._last_state_change
            if elapsed >= self.config.cooldown_seconds:
                self._transition_to_locked(CircuitState.HALF_OPEN)

    def _transition_to_locked(self, new_state: CircuitState) -> None:
        if self._state == new_state:
            return

        now = self._now()
        logger.info(
            "Circuit breaker '%s' transition: %s -> %s",
            self.name,
            self._state.value,
            new_state.value,
        )

        if new_state == CircuitState.OPEN:
            self._tripped_count += 1
            self._consecutive_successes = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._consecutive_successes = 0
            self._consecutive_failures = 0
        elif new_state == CircuitState.CLOSED:
            self._consecutive_failures = 0
            self._consecutive_successes = 0

        self._state = new_state
        self._last_state_change = now

    def snapshot(self) -> CircuitSnapshot:
        """Returns a snapshot of the live operational state and metrics."""
        with self._lock:
            self._evaluate_state_locked()
            now = self._now()
            time_left = 0.0
            if self._state == CircuitState.OPEN:
                elapsed = now - self._last_state_change
                time_left = max(0.0, self.config.cooldown_seconds - elapsed)

            return CircuitSnapshot(
                state=self._state,
                total_calls=self._total_calls,
                successful_calls=self._successful_calls,
                failed_calls=self._failed_calls,
                rejected_calls=self._rejected_calls,
                consecutive_failures=self._consecutive_failures,
                consecutive_successes=self._consecutive_successes,
                tripped_count=self._tripped_count,
                last_state_change=self._last_state_change,
                time_until_retry_seconds=time_left,
            )

    def reset(self) -> None:
        """Resets the circuit breaker to closed state and resets counters."""
        with self._lock:
            self._transition_to_locked(CircuitState.CLOSED)
            self._consecutive_failures = 0
            self._consecutive_successes = 0
            self._total_calls = 0
            self._successful_calls = 0
            self._failed_calls = 0
            self._rejected_calls = 0
