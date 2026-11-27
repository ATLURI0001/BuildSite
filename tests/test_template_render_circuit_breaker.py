"""Tests for template_render_circuit_breaker."""
import sys
sys.path.insert(0, "src")
from buildsite.template_render_circuit_breaker import TemplateRenderCircuitBreaker


def test_template_render_circuit_breaker():
    cb = TemplateRenderCircuitBreaker(threshold=2)
    assert cb.is_open() is False
    cb.record_failure(); cb.record_failure()
    assert cb.is_open() is True
