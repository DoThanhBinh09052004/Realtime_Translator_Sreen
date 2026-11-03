"""GUI-thread translation output policy, independent of Qt and run ownership.

The facade must reject stale publications before calling these methods: only
accepted output may advance duplicate suppression state.
"""
from core.contracts import TranslationStatus


class TranslationOutputPolicy:
    def __init__(self):
        self._last_text = ''
        self._last_status = None

    def reset_subtitle(self):
        self._last_text = ''

    def accept_text(self, text):
        # Empty frames clear the subtitle overlay, but retain plain-text dedup.
        if not text or text == self._last_text:
            return False
        self._last_text = text
        return True

    def next_status(self, provider, revision, session_id, recovery=None):
        if provider == 'Google Translate':
            phase = 'active' if recovery.phase == 'ready' else recovery.phase
            status = TranslationStatus(provider, revision, session_id, phase,
                recovery.retries_issued, recovery.not_before_s if phase == 'retry_wait' else None)
        else:
            status = TranslationStatus(provider, revision, session_id, 'active')
        if status == self._last_status:
            return None
        self._last_status = status
        return status
