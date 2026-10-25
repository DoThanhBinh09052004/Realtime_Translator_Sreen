"""One current subtitle candidate, using the existing temporal stabilizer."""
from core.subtitle_stabilizer import SubtitleStabilizer
from core.contracts import SubtitleFrame
from core.blocks.models import BlockJob


class GoogleSubtitleSession:
    def __init__(self):
        self.reset()

    def reset(self):
        self._revision = None
        self._candidate_id = 0
        self._text = ''
        self._translated = ''
        self._ready = False
        self._settings = None
        self._stabilizer = SubtitleStabilizer()

    @property
    def active_keys(self):
        return frozenset({(self._candidate_id,self._text)}) if self._text else frozenset()

    @property
    def has_pending(self):
        return self._stabilizer.has_pending

    def observe(self, text, *, settings, revision, now_s):
        if revision != self._revision:
            self.reset()
            self._revision = revision
        self._settings = settings
        text = ' '.join(text.split())
        if text != self._text:
            if self._translated:
                self._stabilizer.reset()
            self._candidate_id += 1
            self._text, self._translated, self._ready = text, '', False
        if not text:
            self._stabilizer.reset()
            self._ready = False
        else:
            self._ready = self._stabilizer.observe(text,now_s).action == 'translate'
        return self.current_frame()

    def translation_jobs(self):
        if self._ready and self._text and not self._translated:
            return (BlockJob(self._revision,self._candidate_id,self._text,self._settings),)
        return ()

    def apply_result(self, result):
        if result.revision != self._revision or (result.block_id,result.source_text) not in self.active_keys:
            return False
        if result.result.error is None and result.result.text:
            self._translated = result.result.text
            self._stabilizer.commit(self._text)
        return True

    def current_frame(self):
        if self._revision is None:
            return None
        return SubtitleFrame(self._revision,self._candidate_id,self._text,self._translated)
