"""Buildsite deploy rotary – bounded ring of deploy timestamps."""
from collections import deque
from datetime import datetime


class DeployRotary:
    def __init__(self, capacity: int = 5):
        self._buf: deque = deque(maxlen=capacity)

    def record(self) -> None:
        self._buf.append(datetime.utcnow().isoformat())

    def __len__(self) -> int:
        return len(self._buf)
