"""One SDK owner, bounded latest-per-track queue, versioned result delivery."""
from collections import OrderedDict
from dataclasses import replace
from threading import Condition
import time
from PyQt5.QtCore import QThread, pyqtSignal
from core.blocks.models import BlockTranslationResult
from core.contracts import EngineError, TranslationResult
from core.retry import RetryState
from engines.translator import TranslationService
from core.translation.google_recovery import GoogleRecoveryGate


class BlockTranslationWorker(QThread):
    log_updated = pyqtSignal(str)
    job_started = pyqtSignal(object)
    result_ready = pyqtSignal(object)
    diagnostic_event = pyqtSignal(object)

    def __init__(self, *, clock=time.monotonic, service_factory=TranslationService, google_recovery=None, parent=None):
        super().__init__(parent)
        self._clock,self._factory=clock,service_factory
        self.google_recovery=google_recovery or GoogleRecoveryGate()
        self._condition=Condition()
        self._pending=OrderedDict()
        self._results=OrderedDict()
        self._active=frozenset()
        self._done={}
        self._retries={}
        self._due={}
        self._started={}
        self._retrying=set()
        self._exhausted=set()
        self._revision=None
        self._inflight=None
        self._last_served=None
        self._stopping=False
        self._blocked=False
        self._cooldown=0.

    @staticmethod
    def _token(job):
        # Zero-version jobs are retained only for legacy callers/tests.
        return (job.revision,job.block_id,job.turn_id if job.turn_id else job.source_text)

    @classmethod
    def _key(cls,job):
        return job.request_key if job.turn_id else cls._token(job)

    @property
    def pending_count(self):
        with self._condition:return len(self._pending)

    def _trace_drop(self,job):
        context=job.context
        stamp=context.stamp if context is not None else None
        self.diagnostic_event.emit(dict(kind='dropped',request_key=job.request_key,
            source_id=context.current.source_id if context is not None else None,
            stamp=dict(memory_epoch=stamp.memory_epoch,scope_id=stamp.scope_id,snapshot_digest=stamp.snapshot_digest) if stamp is not None else None))

    def replace_pending(self,jobs,active_keys,revision):
        with self._condition:
            if self._stopping or (self._revision is not None and revision<self._revision):return
            if revision!=self._revision:
                self._revision=revision
                self._done.clear();self._retries.clear();self._due.clear();self._started.clear()
                self._results.clear();self._retrying.clear();self._exhausted.clear()
                self._blocked=False;self._cooldown=0.
            self._active=frozenset((revision,*key) if len(key)==2 else tuple(key) for key in active_keys)
            for mapping in (self._done,self._retries,self._due,self._started):
                for k in tuple(mapping):
                    if k not in self._active:del mapping[k]
            self._retrying.intersection_update(self._active)
            self._exhausted.intersection_update(self._active)
            self._results=OrderedDict((k,r) for k,r in self._results.items() if self._token(r) in self._active)
            previous=self._pending
            incoming=OrderedDict((k,j) for k,j in previous.items() if k in self._retrying and k in self._active)
            if not self._blocked:
                for job in jobs:
                    token=self._token(job)
                    if (job.revision!=revision or token not in self._active or token in self._exhausted
                            or job.text_version<=self._done.get(token,-1) or self._key(job)==self._inflight):continue
                    if token in incoming and incoming[token].request_key==job.request_key:
                        continue  # Retry the exact dispatched snapshot, even if pending memory refreshed.
                    if token in incoming or len(incoming)<32:incoming[token]=job
            else:incoming.clear()
            order={k:i for i,k in enumerate(previous)}
            self._pending=OrderedDict(sorted(incoming.items(),key=lambda kv:order.get(kv[0],len(order))))
            for token,old in previous.items():
                replacement=self._pending.get(token)
                if replacement is None or replacement.request_key!=old.request_key:self._trace_drop(old)
            if self._last_served in self._pending:self._pending.move_to_end(self._last_served)
            self._condition.notify_all()

    def drain_results(self):
        with self._condition:
            results=tuple(self._results.values());self._results.clear();return results

    def request_stop(self):
        with self._condition:
            self._stopping=True;self._active=frozenset();self._pending.clear();self._results.clear()
            self._condition.notify_all()

    def run(self):
        service=None
        try:
            service=self._factory()
            while True:
                now=self._clock()
                recovery=self.google_recovery.snapshot(now_s=now)
                with self._condition:
                    if self._stopping:return
                    job=None
                    for token,candidate in self._pending.items():
                        google=candidate.settings.provider.name=='Google Translate'
                        due=max(self._cooldown,self._due.get(token,0),self._started.get(token,float('-inf'))+.5 if candidate.turn_id else 0)
                        if now>=due and (not google or recovery.phase=='ready'):
                            job=candidate;break
                    if job is None:
                        self._condition.wait(.025);continue
                    self._pending.pop(token)
                    self._retrying.discard(token)
                    key=self._key(job)
                    self._inflight=key;self._last_served=token;self._started[token]=now
                self.job_started.emit(job)
                try:
                    result=(service.translate(job.source_text,job.settings,context=job.context) if job.context is not None
                            else service.translate(job.source_text,job.settings))
                except Exception:result=TranslationResult(error=EngineError('network','Translation request failed.',True))
                if result.context is not None and (job.context is None or result.context.stamp!=job.context.stamp):
                    result=replace(result,context=None,context_degraded=True)
                if google:self.google_recovery.record_result(result,generation=recovery.generation,now_s=self._clock())
                response=BlockTranslationResult(job.revision,job.block_id,job.source_text,result,job.turn_id,job.text_version,job.context.stamp if job.context else None)
                with self._condition:
                    self._inflight=None
                    if self._stopping or token not in self._active:
                        self._trace_drop(job);continue
                    self._results[key]=response
                    while len(self._results)>32:self._results.popitem(last=False)
                    error=result.error
                    if error is None:
                        self._done[token]=max(job.text_version,self._done.get(token,-1))
                        self._retries.pop(token,None);self._due.pop(token,None)
                    elif google:
                        if error.code=='invalid_input':self._done[token]=job.text_version
                        else:self._retrying.add(token)
                    elif error.code in ('auth','authentication','quota'):
                        self._blocked=True;self._pending.clear()
                    else:
                        retry_error=error
                        if job.settings.provider.name=='Google Gemini' and error.code in ('network','timeout','rate_limit'):
                            retry_error=replace(error,retry_after_s=max(error.retry_after_s or 0,5 if error.code=='rate_limit' else 2))
                        due=self._retries.setdefault(token,RetryState()).next_due(self._clock(),retry_error)
                        if error.code=='rate_limit':self._cooldown=due or self._clock()+max(error.retry_after_s or 0,5)
                        if due is None:self._exhausted.add(token);self._pending.pop(token,None)
                        else:self._due[token]=due;self._retrying.add(token)
                    if token in self._retrying and token not in self._pending:
                        if len(self._pending)>=32:self._pending.popitem(last=True)
                        self._pending[token]=job
                    self._condition.notify_all()
                self.result_ready.emit(response)
        finally:
            if service is not None:service.close()
