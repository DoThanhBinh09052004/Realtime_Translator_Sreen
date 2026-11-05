"""A bounded progressive-text state machine; clocks and I/O are supplied by callers."""
import unicodedata
from core.blocks.models import BlockJob
from core.dialogue.models import TrackPresentation
from core.dialogue.policy import DEFAULT_DIALOGUE_POLICY, classify_text
from core.dialogue.context_models import OcrEvidence, OcrLine, StableTurn, PresentationReceipt


class DialogueTrack:
    def __init__(self, track_id: int, *, policy=DEFAULT_DIALOGUE_POLICY):
        self.track_id, self.policy = track_id, policy
        self.turn_id = self.text_version = 0
        self.source_text = ''
        self.closed = True
        self.missing_count = 0
        self._missing_since = None
        self.last_seen_s = float('-inf')
        self.presentation = None
        self._shown_at = float('-inf')
        self._pending = self._deferred = self._challenger = None
        self._issued = None
        self._last_dispatch = float('-inf')
        self._dispatched_version = self._applied_version = 0
        self._observations = 0
        self.evidence = OcrEvidence()
        self._stable_emitted = None
        self._receipts = []

    def _begin(self, text, now_s, observations=1, evidence=None, captured_at_s=None):
        self.turn_id += 1
        self.text_version = 1
        self.source_text, self.closed = text, False
        self._started = self._changed_at = now_s
        self._last_dispatch = float('-inf')
        self._dispatched_version = self._applied_version = 0
        self._observations = observations
        self._issued = self._challenger = self._deferred = self._pending = None
        self.evidence = evidence or OcrEvidence((OcrLine(text),)) if len(text)<=2000 else OcrEvidence()
        self._captured_at = now_s if captured_at_s is None else captured_at_s
        self._receipts.clear()

    def observe(self, text: str, *, now_s: float, evidence=None, captured_at_s=None) -> None:
        text = ' '.join(unicodedata.normalize('NFC', text).split())
        if not text:
            self.miss(now_s=now_s)
            return
        self.last_seen_s, self.missing_count = now_s, 0
        self._missing_since = None
        if self.closed:
            self._begin(text, now_s, evidence=evidence, captured_at_s=captured_at_s)
            return
        relation = classify_text(self.source_text, text)
        semantic = lambda value: tuple(line.text for line in value.lines) if value else ()
        if relation == 'same' and evidence is not None and semantic(evidence)!=semantic(self.evidence):
            relation = 'evidence'
        if relation in ('same','append'):
            self._challenger = None
            self._observations += 1
            if relation == 'append':
                self.source_text = text
                self.text_version += 1
                self._changed_at = now_s
                self.evidence = evidence or OcrEvidence((OcrLine(text),)) if len(text)<=2000 else OcrEvidence()
                self._captured_at = now_s if captured_at_s is None else captured_at_s
            if self._deferred is not None:
                value, self._deferred = self._deferred, None
                self._offer(value, now_s)
            self.advance(now_s=now_s)
            return
        old = self._challenger
        if old and classify_text(old[0],text) in ('same','append') and old[3] == relation:
            challenger = (text, old[1], old[2]+1, relation, evidence, captured_at_s)
        else:
            challenger = (text, now_s, 1, relation, evidence, captured_at_s)
        self._challenger = challenger
        minimum = self.policy.quiet_s if relation == 'regression' else 0.
        if challenger[2] >= 2 and now_s-challenger[1] >= minimum:
            if relation == 'evidence':
                self.text_version += 1
                self.evidence = evidence
                self._changed_at = now_s
                self._challenger = self._deferred = self._pending = None
                self._captured_at = now_s if captured_at_s is None else captured_at_s
            else:
                self._begin(text, now_s, observations=challenger[2], evidence=evidence, captured_at_s=captured_at_s)

    def miss(self, *, now_s: float, minimum_scans=None, minimum_absence_s=0.) -> bool:
        if self.closed: return False
        self._challenger = None
        self.missing_count += 1
        if self._missing_since is None:
            self._missing_since = now_s
        required = self.policy.absent_scans if minimum_scans is None else minimum_scans
        if (self.missing_count < required
                or now_s-self._missing_since < minimum_absence_s): return False
        self.closed = True
        self._issued = self._pending = self._deferred = self._challenger = None
        return True

    @property
    def has_pending(self):
        return not self.closed and bool(self._challenger or self._observations < 2
                                       or self.text_version > self._dispatched_version)

    def active_turn(self, revision):
        return None if self.closed else (revision,self.track_id,self.turn_id)

    def job(self, *, revision, settings, now_s):
        if (not self._source_ready(now_s) or self.text_version <= self._dispatched_version
                or now_s-self._last_dispatch < self.policy.min_dispatch_gap_s):
            return None
        return BlockJob(revision,self.track_id,self.source_text,settings,self.turn_id,self.text_version,self.evidence)

    def _source_ready(self,now_s):
        if self.closed or self._challenger or self._observations<2 or not self.source_text or len(self.source_text)>2000:return False
        baseline = self._started if self._last_dispatch == float('-inf') else self._last_dispatch
        return now_s-self._changed_at>=self.policy.quiet_s or now_s-baseline>=self.policy.continuous_s

    def drain_stable_turns(self, *, revision):
        if not self._source_ready(getattr(self,'_now',self.last_seen_s)) or (self.turn_id,self.text_version)==self._stable_emitted:return ()
        self._stable_emitted=(self.turn_id,self.text_version)
        return (StableTurn(revision,self.track_id,self.turn_id,self.text_version,self.source_text,self.evidence,self._captured_at,getattr(self,'_now',self.last_seen_s)),)

    def drain_presentations(self):
        receipts,self._receipts=tuple(self._receipts),[]
        return receipts if not self.closed else ()

    def mark_dispatched(self, job, *, now_s):
        if not self.closed and job.block_id == self.track_id and job.turn_id == self.turn_id:
            self._issued = job
            self._last_dispatch = now_s
            self._dispatched_version = max(self._dispatched_version, job.text_version)

    def apply_result(self, result, *, now_s, defer_when_missing=False):
        job = self._issued
        if (self.closed or job is None or result.request_key != job.request_key
                or result.source_text != job.source_text): return False
        self._issued = None
        if result.result.error is not None: return True
        if not result.result.text or result.text_version <= self._applied_version: return False
        receipt=PresentationReceipt(result.request_key,result.source_text,result.result.text,result.result.context)
        value = TrackPresentation(result.turn_id,result.text_version,result.source_text,result.result.text,receipt)
        if self._challenger or (defer_when_missing and self.missing_count):
            self._deferred = value
        else:
            self._offer(value, now_s)
        return True

    def _offer(self, value, now_s):
        self._applied_version = max(self._applied_version, value.text_version)
        current = self.presentation
        if current and current.turn_id == value.turn_id and now_s-self._shown_at < self.policy.min_read_s:
            self._pending = value
        else:
            self._present(value, now_s)

    def _present(self, value, now_s):
        if self.presentation is None or self.presentation.text != value.text:
            self._shown_at = now_s
        self.presentation = value
        self._pending = None
        if value.receipt is not None: self._receipts=[value.receipt]

    def advance(self, *, now_s):
        self._now = now_s
        if self._pending and not self._challenger and now_s-self._shown_at >= self.policy.min_read_s:
            self._present(self._pending, now_s)
            return True
        return False
