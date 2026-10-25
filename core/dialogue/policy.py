"""Recognition identity is deliberately narrower than semantic similarity."""
from dataclasses import dataclass
import re
import unicodedata
from typing import Literal


@dataclass(frozen=True)
class DialoguePolicy:
    quiet_s: float = .5
    continuous_s: float = 1.5
    min_dispatch_gap_s: float = .5
    min_read_s: float = 1.
    subtitle_end_hold_s: float = 3.
    absent_scans: int = 2
    subtitle_fresh_s: float = 6.
    block_fresh_s: float = 3.
    tick_ms: int = 25


DEFAULT_DIALOGUE_POLICY = DialoguePolicy()


def identity_text(text: str) -> str:
    text = ' '.join(unicodedata.normalize('NFC', text).split())
    text = text.translate(str.maketrans({'’': "'", '‘': "'", '“':'"', '”':'"'}))
    text = re.sub(r'\s*([,.;:!?])\s*', r'\1', text)
    return text.rstrip('.…').rstrip()


def classify_text(previous: str, current: str) -> Literal['same','append','regression','different']:
    a,b = identity_text(previous), identity_text(current)
    if a == b: return 'same'
    if a and b.startswith(a): return 'append'
    if b and a.startswith(b): return 'regression'
    return 'different'
