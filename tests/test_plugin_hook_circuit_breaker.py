"""Tests for PluginHookCircuitBreaker."""
import pytest
from buildsite.plugin_hook_circuit_breaker import (
    PluginCircuitOpenError,
    PluginHookCircuitBreaker,
)


def test_plugin_hook_circuit_breaker():
    cb = PluginHookCircuitBreaker(threshold=2, cooldown_s=5.0)
    with pytest.raises(RuntimeError):
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError("hook fail")))
    with pytest.raises(RuntimeError):
        cb.call(lambda: (_ for _ in ()).throw(RuntimeError("hook fail")))
    with pytest.raises(PluginCircuitOpenError):
        cb.call(lambda: "ok")
