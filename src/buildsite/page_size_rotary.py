"""Bounded ring buffer for rendered page byte sizes."""
from collections import deque


class PageSizeRotary:
    def __init__(self, capacity: int = 32) -> None:
        self._samples: deque[int] = deque(maxlen=capacity)

    def record(self, num_bytes: int) -> None:
        if num_bytes < 0:
            raise ValueError("num_bytes must be non-negative")
        self._samples.append(num_bytes)

    def avg_bytes(self) -> float:
        return sum(self._samples) / len(self._samples) if self._samples else 0.0
