from core.contracts import SubtitleFrame, EngineError
from core.dialogue.track import DialogueTrack
from core.dialogue.policy import DEFAULT_DIALOGUE_POLICY


class SubtitleDialogueSession:
    def __init__(self, *, policy=DEFAULT_DIALOGUE_POLICY):
        self.policy = policy
        self._revision = None

    def reset(self, revision, settings):
        self._revision, self._settings = revision, settings
        self.track = DialogueTrack(0,policy=self.policy)
        self._now = self._last_success = float('-inf')
        self._end_until = None
        self._oversized = None
        self._errors = []

    @property
    def active_turns(self):
        key = self.track.active_turn(self._revision)
        return frozenset({key}) if key else frozenset()

    @property
    def needs_scan(self):
        return self.track.has_pending or (not self.track.closed and self.track.missing_count > 0)

    def observe(self, text, *, now_s):
        self._expire_tail(now_s)
        self._now = self._last_success = now_s
        if text.strip():
            self._end_until = None
            self.track.observe(text,now_s=now_s)
        elif self.track.miss(now_s=now_s):
            self._end_until = now_s+self.policy.subtitle_end_hold_s
        key = (self.track.turn_id,self.track.text_version)
        if len(self.track.source_text)>2000 and key!=self._oversized:
            self._oversized=key
            self._errors=[EngineError('invalid_input','Đoạn thoại vượt quá 2000 ký tự.',False)]

    def translation_jobs(self, *, now_s):
        job=self.track.job(revision=self._revision,settings=self._settings,now_s=now_s)
        return (job,) if job and now_s-self._last_success < self.policy.subtitle_fresh_s else ()

    def mark_dispatched(self, job, *, now_s):
        if job.revision==self._revision: self.track.mark_dispatched(job,now_s=now_s)

    def apply_result(self, result, *, now_s):
        self._now=now_s
        if result.revision!=self._revision: return False
        accepted=self.track.apply_result(result,now_s=now_s)
        if accepted and result.result.error is None and not self.track.closed:
            self._end_until=None
        return accepted

    def tick(self, *, now_s):
        self._now=now_s
        self._expire_tail(now_s)
        self.track.advance(now_s=now_s)

    def _expire_tail(self, now_s):
        if self._end_until is not None and now_s >= self._end_until:
            self.track.presentation = None
            self._end_until = None

    def current_frame(self):
        if self._revision is None: return None
        p=self.track.presentation
        visible=(p is not None and self._now-self._last_success < self.policy.subtitle_fresh_s
                 and (self._end_until is None or self._now < self._end_until))
        return SubtitleFrame(self._revision,p.turn_id if p else self.track.turn_id,
                             p.source_text if visible else '',p.text if visible else '')

    def drain_errors(self):
        errors,self._errors=tuple(self._errors),[]
        return errors
