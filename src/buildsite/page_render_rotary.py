"""page_render_rotary.py – bounded ring buffer for page render events."""
from collections import deque


class PageRenderRotary:
    def __init__(self, max_size: int = 10):
        self._buf: deque = deque(maxlen=max_size)

    def push(self, page: str) -> None:
        self._buf.append(page)

    def count(self) -> int:
        return len(self._buf)
