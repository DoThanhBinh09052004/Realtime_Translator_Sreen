"""Google service recovery independent of source revisions and Qt lifetimes."""
from dataclasses import dataclass
from threading import RLock
from typing import Literal
from core.contracts import EngineError
from core.retry import RetryState


@dataclass(frozen=True)
class GoogleRecoverySnapshot:
    generation: int
    phase: Literal['ready', 'retry_wait', 'paused']
    retries_issued: int
    not_before_s: float
    error: EngineError | None


class GoogleRecoveryGate:
    def __init__(self):
        self._lock = RLock()
        self._generation = 0
        self._rate_until = 0.
        self._reset()

    def _reset(self):
        self._retry = RetryState()
        self._issued = 0
        self._due = self._rate_until
        self._paused = False
        self._error = None

    def snapshot(self, *, now_s):
        with self._lock:
            due = max(self._due, self._rate_until)
            phase = 'paused' if self._paused else 'retry_wait' if now_s < due else 'ready'
            return GoogleRecoverySnapshot(self._generation, phase, self._issued, due, self._error)

    def can_dispatch(self, *, now_s):
        return self.snapshot(now_s=now_s).phase == 'ready'

    def begin_session(self, *, now_s):
        with self._lock:
            self._generation += 1
            self._reset()
            return self._generation

    def invalidate_requests(self):
        with self._lock:
            self._generation += 1

    def manual_retry(self, *, now_s):
        with self._lock:
            if self._paused:
                self._generation += 1
                self._reset()
            return self._generation

    def record_result(self, result, *, generation, now_s):
        with self._lock:
            if generation != self._generation:
                return
            error = result.error
            if error is None:
                if result.text and not result.from_cache:
                    self._reset()
                return
            if error.code == 'invalid_input':
                return
            self._error = error
            if error.code == 'rate_limit':
                delay = error.retry_after_s if error.retry_after_s is not None else 30.
                self._rate_until = max(self._rate_until, now_s+delay)
            due = self._retry.next_due(now_s, error)
            if due is None:
                self._paused = True
            else:
                self._issued += 1
                self._due = max(due, self._rate_until)
