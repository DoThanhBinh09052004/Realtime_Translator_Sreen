"""One SDK owner, one in-flight request, replaceable bounded pending snapshot."""
from collections import OrderedDict
from dataclasses import replace
from threading import Condition
import time
from PyQt5.QtCore import QThread
from core.blocks.models import BlockTranslationResult
from core.contracts import EngineError, TranslationResult
from core.retry import RetryState
from engines.translator import TranslationService
from core.google_recovery import GoogleRecoveryGate


class BlockTranslationWorker(QThread):
    def __init__(self, *, clock=time.monotonic, service_factory=TranslationService, google_recovery=None, parent=None):
        super().__init__(parent)
        self._clock, self._factory = clock, service_factory
        self.google_recovery = google_recovery or GoogleRecoveryGate()
        self._condition = Condition()
        self._pending = OrderedDict()
        self._results = OrderedDict()
        self._active = frozenset()
        self._done = set()
        self._retries = {}
        self._due = {}
        self._revision = None
        self._inflight = None
        self._stopping = False
        self._blocked = False
        self._cooldown = 0.

    @property
    def pending_count(self):
        with self._condition:
            return len(self._pending)

    def replace_pending(self, jobs, active_keys, revision):
        with self._condition:
            if self._stopping:
                return
            if self._revision is not None and revision < self._revision:
                return
            if revision != self._revision:
                self._revision = revision
                self._done.clear()
                self._retries.clear()
                self._due.clear()
                self._results.clear()
                self._blocked = False
                self._cooldown = 0.
            self._active = frozenset((revision, i, t) for i, t in active_keys)
            self._done.intersection_update(self._active)
            self._retries = {k: v for k, v in self._retries.items() if k in self._active}
            self._due = {k: v for k, v in self._due.items() if k in self._active}
            self._results = OrderedDict((k, v) for k, v in self._results.items() if k in self._active)
            self._pending.clear()
            for job in jobs:
                key = (job.revision, job.block_id, job.source_text)
                if (key in self._active and key not in self._done and key != self._inflight
                        and not self._blocked and len(self._pending) < 32):
                    self._pending[key] = job
            self._condition.notify_all()

    def drain_results(self):
        with self._condition:
            result = tuple(self._results.values())
            self._results.clear()
            return result

    def request_stop(self):
        with self._condition:
            self._stopping = True
            self._active = frozenset()
            self._pending.clear()
            self._results.clear()
            self._condition.notify_all()

    def run(self):
        service = None
        try:
            service = self._factory()
            while True:
                now = self._clock()
                recovery = self.google_recovery.snapshot(now_s=now)
                with self._condition:
                    job = None
                    if self._stopping:
                        return
                    for key, candidate in self._pending.items():
                        google = candidate.settings.provider.name == 'Google Translate'
                        eligible = recovery.phase == 'ready' if google else now >= max(self._cooldown, self._due.get(key, 0))
                        if eligible:
                            job = candidate
                            break
                    if job is None:
                        self._condition.wait(.05)
                        continue
                    self._pending.pop(key)
                    self._inflight = key
                try:
                    result = service.translate(job.source_text, job.settings)
                except Exception:
                    result = TranslationResult(error=EngineError('network', 'Không thể gửi yêu cầu dịch.', True))
                if google:
                    # Availability belongs to the service generation, even if
                    # this source disappeared while the request was running.
                    self.google_recovery.record_result(result, generation=recovery.generation, now_s=self._clock())
                with self._condition:
                    self._inflight = None
                    if self._stopping or key not in self._active:
                        continue
                    self._results[key] = BlockTranslationResult(job.revision, job.block_id, job.source_text, result)
                    while len(self._results) > 32:
                        self._results.popitem(last=False)
                    error = result.error
                    if error is None:
                        self._done.add(key)
                    elif google:
                        if error.code == 'invalid_input':
                            self._done.add(key)
                        else:
                            if len(self._pending) >= 32:
                                self._pending.popitem(last=True)
                            self._pending[key] = job
                    elif error.code in ('auth', 'authentication', 'quota'):
                        self._blocked = True
                        self._pending.clear()
                    else:
                        retry_error = error
                        if job.settings.provider.name == 'Google Gemini' and error.code in ('network', 'timeout', 'rate_limit'):
                            retry_error = replace(error, retry_after_s=max(error.retry_after_s or 0, 5 if error.code == 'rate_limit' else 2))
                        due = self._retries.setdefault(key, RetryState()).next_due(self._clock(), retry_error)
                        if error.code == 'rate_limit':
                            self._cooldown = due or self._clock()+max(error.retry_after_s or 0, 5)
                        if due is None:
                            self._done.add(key)
                        else:
                            self._due[key] = due
                            if len(self._pending) >= 32:
                                self._pending.popitem(last=True)
                            self._pending[key] = job
                    self._condition.notify_all()
        finally:
            if service is not None:
                service.close()
