"""build_telemetry_rotary.py – bounded ring buffer for build telemetry events."""
from collections import deque


class BuildTelemetryRotary:
    def __init__(self, max_size: int = 10):
        self._buf: deque = deque(maxlen=max_size)

    def push(self, event: str) -> None:
        self._buf.append(event)

    def latest(self) -> list:
        return list(self._buf)

    def count(self) -> int:
        return len(self._buf)
