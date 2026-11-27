"""template_render_circuit_breaker.py – circuit breaker for template render failures."""


class TemplateRenderCircuitBreaker:
    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self.failures = 0
        self.open = False

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.open = True

    def is_open(self) -> bool:
        return self.open
