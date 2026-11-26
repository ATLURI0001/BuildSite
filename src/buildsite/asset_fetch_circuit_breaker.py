"""Remote CDN Asset Fetch Circuit Breaker & Fallback Cache.

Protects static site builds from stalling on unreachable remote fonts, images,
or third-party CDN endpoints by tripping to cached placeholder fallbacks.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Callable, Optional


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class AssetFetchCircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_threshold: int = 2,
        cooldown_seconds: float = 1.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_threshold = recovery_threshold
        self.cooldown_seconds = cooldown_seconds
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.trip_time = 0.0

    def fetch(self, fetcher: Callable[[], bytes], fallback: bytes = b"") -> tuple[bytes, bool]:
        now = time.monotonic()
        if self.state == CircuitState.OPEN:
            if now - self.trip_time >= self.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                self.consecutive_successes = 0
            else:
                return fallback, True

        try:
            data = fetcher()
            self._record_success()
            return data, False
        except Exception:
            self._record_failure(now)
            return fallback, True

    def _record_failure(self, now: float) -> None:
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        if self.state == CircuitState.HALF_OPEN or self.consecutive_failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.trip_time = now

    def _record_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.consecutive_successes += 1
            if self.consecutive_successes >= self.recovery_threshold:
                self.state = CircuitState.CLOSED
                self.consecutive_failures = 0
        else:
            self.consecutive_failures = 0
