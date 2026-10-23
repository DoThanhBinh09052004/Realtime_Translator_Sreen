"""Capture-thread-owned tracks and per-block text stabilization."""
from dataclasses import dataclass
from math import hypot
from core.contracts import EngineError
from core.blocks.models import BlockJob, OverlayBlock, OverlayFrame


@dataclass
class _Track:
    block_id: int
    text: str
    rect: object
    since: float
    observations: int = 1
    ready: bool = False
    translated: str = ''


def _distance(a, b):
    return hypot(a.x+a.width/2-b.x-b.width/2, a.y+a.height/2-b.y-b.height/2)


def _iou(a, b):
    intersection = max(0, min(a.right, b.right)-max(a.x, b.x))*max(0, min(a.bottom, b.bottom)-max(a.y, b.y))
    return intersection / (a.width*a.height+b.width*b.height-intersection)


class BlockSession:
    def __init__(self):
        self.reset()

    def reset(self):
        self._tracks = {}
        self._next_id = 0
        self._revision = None
        self._frame = None
        self._errors = []
        self._oversized = set()

    @property
    def active_keys(self):
        return frozenset((t.block_id, t.text) for t in self._tracks.values())

    @property
    def has_pending(self):
        return any(not t.ready for t in self._tracks.values())

    def observe(self, blocks, *, settings, revision, frame_id, geometry, now_s):
        if revision != self._revision:
            self.reset()
            self._revision = revision
        self._settings = settings
        blocks = tuple(sorted(blocks, key=lambda b: (b.source_rect.y, b.source_rect.x, b.source_text)))[:32]
        matches, used = {}, set()
        for exact in (True, False):
            pairs = []
            for i, b in enumerate(blocks):
                if i in matches:
                    continue
                text = ' '.join(b.source_text.split())
                for key, track in self._tracks.items():
                    if key in used:
                        continue
                    distance = _distance(b.source_rect, track.rect)
                    score = _iou(b.source_rect, track.rect)
                    valid = (text == track.text and distance <= max(64, 4*max(b.source_rect.height, track.rect.height))) if exact else score >= .30
                    if valid:
                        pairs.append((0 if exact else -score, distance, key, i))
            for _, _, key, i in sorted(pairs):
                if key not in used and i not in matches:
                    matches[i] = key
                    used.add(key)
        tracks = {}
        for i, block in enumerate(blocks):
            text = ' '.join(block.source_text.split())
            if not text:
                continue
            track = self._tracks.get(matches.get(i))
            if track is None:
                track = _Track(self._next_id, text, block.source_rect, now_s)
                self._next_id += 1
            elif text == track.text:
                track.observations += 1
            else:
                if not (text.startswith(track.text) or track.text.startswith(text)):
                    track.since = now_s
                track.text = text
                track.observations = 1
                track.ready = False
                track.translated = ''
            track.rect = block.source_rect
            track.ready = track.observations >= 2 or now_s-track.since >= 2
            if len(text) > 2000 and text not in self._oversized:
                self._oversized.add(text)
                self._errors = (self._errors + [EngineError('invalid_input', 'Khối chữ vượt quá 2000 ký tự.', False)])[-32:]
            tracks[track.block_id] = track
        self._tracks = tracks
        self._frame = OverlayFrame(revision, frame_id, geometry, ())
        return self.current_frame()

    def translation_jobs(self):
        return tuple(BlockJob(self._revision, t.block_id, t.text, self._settings)
                     for t in self._tracks.values() if t.ready and not t.translated and len(t.text) <= 2000)

    def apply_result(self, result):
        track = self._tracks.get(result.block_id)
        if result.revision != self._revision or track is None or track.text != result.source_text:
            return False
        if result.result.error is None:
            track.translated = result.result.text
        return True

    def current_frame(self):
        if self._frame is None:
            return None
        f = self._frame
        return OverlayFrame(f.revision, f.frame_id, f.geometry, tuple(
            OverlayBlock(t.block_id, t.text, t.translated, t.rect) for t in self._tracks.values() if t.translated))

    def drain_errors(self):
        errors, self._errors = tuple(self._errors), []
        return errors
