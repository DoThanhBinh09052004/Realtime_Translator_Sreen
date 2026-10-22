from core.contracts import EngineError


class RetryState:
    """Bounded exponential retry schedule using monotonic deadlines."""

    _DELAYS = (1.0, 2.0, 4.0)

    def __init__(self, max_retries: int = 3):
        self.max_retries = max(0, int(max_retries))
        self._retries_issued = 0

    def next_due(self, now: float, error: EngineError) -> float | None:
        if not error.retryable or self._retries_issued >= self.max_retries:
            return None
        delay = self._DELAYS[min(self._retries_issued, len(self._DELAYS) - 1)]
        if error.retry_after_s is not None:
            delay = max(delay, float(error.retry_after_s))
        self._retries_issued += 1
        return now + delay

    def reset(self) -> None:
        self._retries_issued = 0
