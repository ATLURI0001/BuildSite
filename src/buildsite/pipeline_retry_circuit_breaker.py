"""BuildSite: pipeline retry circuit breaker."""


class PipelineRetryCircuitBreaker:
    def __init__(self, threshold: int = 3):
        self._threshold = threshold
        self._fails = 0
        self._open = False

    def call(self, fn):
        if self._open:
            raise RuntimeError("pipeline circuit open")
        try:
            result = fn()
            self._fails = 0
            return result
        except Exception:
            self._fails += 1
            if self._fails >= self._threshold:
                self._open = True
            raise
