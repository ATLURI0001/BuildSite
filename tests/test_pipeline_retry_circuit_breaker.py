import pytest
from src.buildsite.pipeline_retry_circuit_breaker import PipelineRetryCircuitBreaker


def test_pipeline_retry_circuit_breaker():
    cb = PipelineRetryCircuitBreaker(threshold=2)
    for _ in range(2):
        try:
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        except RuntimeError:
            pass
    with pytest.raises(RuntimeError, match="pipeline circuit open"):
        cb.call(lambda: None)
