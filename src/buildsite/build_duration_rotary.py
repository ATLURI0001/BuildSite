"""Bounded ring buffer for static site build durations."""
from collections import deque


class BuildDurationRotary:
    def __init__(self, capacity: int = 32) -> None:
        self._samples: deque[float] = deque(maxlen=capacity)

    def record(self, ms: float) -> None:
        if ms < 0:
            raise ValueError("duration must be non-negative")
        self._samples.append(ms)

    def avg_ms(self) -> float:
        return sum(self._samples) / len(self._samples) if self._samples else 0.0
