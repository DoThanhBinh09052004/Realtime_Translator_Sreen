from core.contracts import EngineError
from core.retry import RetryState


def test_retry_policy_uses_bounded_exponential_delays():
    retry = RetryState()
    error = EngineError("timeout", "Timeout", True)
    assert retry.next_due(0.0, error) == 1.0
    assert retry.next_due(1.0, error) == 3.0
    assert retry.next_due(3.0, error) == 7.0
    assert retry.next_due(7.0, error) is None


def test_retry_after_is_a_minimum_and_non_retryable_error_stops():
    retry = RetryState()
    assert retry.next_due(10.0, EngineError("rate_limit", "Wait", True, 12.0)) == 22.0
    assert retry.next_due(22.0, EngineError("timeout", "Timeout", True)) == 24.0

    retry.reset()
    assert retry.next_due(0.0, EngineError("auth", "Auth", False)) is None
    assert retry.next_due(0.0, EngineError("timeout", "Timeout", True)) == 1.0
