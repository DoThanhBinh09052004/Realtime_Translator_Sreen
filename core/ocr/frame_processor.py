"""Capture-thread-owned change detection and legacy dialogue OCR scheduling."""
import cv2
import numpy as np

from core.dialogue.models import DialogueObservation
from core.retry import RetryState


class FrameOcrProcessor:
    """Process frames using explicit OCR, revision, publication and clock ports.

    The capture owner calls ``reset`` when consuming runtime invalidation.
    No settings thread may reset this processor's in-flight state.
    """

    def __init__(self, *, read_ocr, is_current, publish, clock):
        self._read_ocr = read_ocr
        self._is_current = is_current
        self._publish = publish
        self._clock = clock
        self._retry = RetryState()
        self.reset()

    def reset(self):
        self.previous_thumbnail = None
        self.last_ocr = float('-inf')
        self._retry.reset()
        self._due = 0.
        self._exhausted = False
        self._scan_id = 0

    def is_frame_changed(self, image, threshold=1.2):
        try:
            thumb = cv2.resize(image, (100, 40), interpolation=cv2.INTER_LINEAR)
            if self.previous_thumbnail is None:
                self.previous_thumbnail = thumb
                return True
            difference = cv2.absdiff(self.previous_thumbnail, thumb)
            if float(np.mean(difference)) > threshold:
                self.previous_thumbnail = thumb
                return True
            return False
        except Exception:
            return True

    def process(self, image, settings, revision, geometry=None, *, captured_at_s=None,
                force_scan=False, change_detector=None):
        """Return True for an idle frame, False for scanned or stale frames.

        ``force_scan`` may be a deferred policy read for legacy direct callers;
        runners pass the boolean captured in their atomic runtime snapshot.
        """
        if not self._is_current(revision):
            return False
        now = self._clock()
        changed = (change_detector or self.is_frame_changed)(image)
        if changed:
            self._exhausted = False
            self._retry.reset()
        if callable(force_scan):
            force_scan = force_scan()
        scan = changed or force_scan or now - self.last_ocr >= max(1000, settings.interval_ms) / 1000
        if not scan or now < self._due or self._exhausted:
            return True
        result = self._read_ocr(image, settings.source_lang, settings=settings)
        completed = self._clock()
        if not self._is_current(revision):
            return False
        self.last_ocr = now
        if result.error is None:
            self._retry.reset()
            self._due = 0.
        else:
            due = self._retry.next_due(completed, result.error)
            self._due = due or 0.
            self._exhausted = due is None
        self._scan_id += 1
        self._publish(DialogueObservation(revision, self._scan_id,
            now if captured_at_s is None else captured_at_s, completed, settings, result, geometry))
        return False
