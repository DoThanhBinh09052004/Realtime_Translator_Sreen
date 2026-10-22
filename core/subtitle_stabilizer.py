"""Temporal subtitle decisions, independent of OCR, translation and the UI."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class StabilizationDecision:
    action: Literal['wait', 'translate', 'unchanged']
    text: str = ''


class SubtitleStabilizer:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self._pending = ''
        self._sequence_started = 0.0
        self._committed = ''
        self._suppress_suffix = False

    @property
    def has_pending(self) -> bool:
        return bool(self._pending)

    def commit(self, text: str) -> None:
        self._committed = ' '.join(text.split())
        self._pending = ''
        self._suppress_suffix = bool(self._committed)

    def observe(self, text: str, now_s: float) -> StabilizationDecision:
        text = ' '.join(text.split())
        if not text:
            self._suppress_suffix = False
            if self.has_pending:
                return StabilizationDecision('translate', self._pending)
            return StabilizationDecision('wait')

        tokens = text.split()
        committed_tokens = self._committed.split()
        is_suffix = (len(tokens) < len(committed_tokens)
                     and committed_tokens[-len(tokens):] == tokens)
        if text == self._committed or (self._suppress_suffix and is_suffix):
            self._pending = ''
            return StabilizationDecision('unchanged', text)

        self._suppress_suffix = False
        if text == self._pending:
            return StabilizationDecision('translate', text)

        related = self.has_pending and (
            text.startswith(self._pending) or self._pending.startswith(text))
        if not related:
            self._sequence_started = now_s
        self._pending = text
        if now_s - self._sequence_started >= 2.0:
            return StabilizationDecision('translate', text)
        return StabilizationDecision('wait')
