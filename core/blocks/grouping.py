"""Deterministic horizontal text grouping, independent of OCR and Qt."""
import re
from math import isfinite
from core.blocks.models import Rect, TextBlock


def union(a, b):
    return Rect(min(a.x, b.x), min(a.y, b.y), max(a.right, b.right)-min(a.x, b.x), max(a.bottom, b.bottom)-min(a.y, b.y))


def group_spans(spans, image_size_px):
    width, height = image_size_px
    pieces = []
    for span in spans:
        text = ' '.join(span.text.split())
        if not text or not isfinite(span.confidence) or span.confidence < .50:
            continue
        try:
            if len(span.polygon) != 4 or not all(isfinite(v) for p in span.polygon for v in p):
                continue
            xs, ys = zip(*span.polygon)
            x, y = max(0, min(xs)), max(0, min(ys))
            r, b = min(width, max(xs)), min(height, max(ys))
            rect = Rect(x, y, r-x, b-y)
        except (ValueError, TypeError):
            continue
        pieces.append((text, rect))
    pieces.sort(key=lambda p: (p[1].y, p[1].x, p[0]))
    # Merge nearest horizontal fragments first, then adjacent text lines.
    for horizontal in (True, False):
        while True:
            candidates = []
            for i, (ta, a) in enumerate(pieces):
                for j, (tb, b) in enumerate(pieces):
                    if i == j:
                        continue
                    ratio = max(a.height, b.height) / min(a.height, b.height)
                    if horizontal:
                        overlap = max(0, min(a.bottom, b.bottom)-max(a.y, b.y)) / min(a.height, b.height)
                        gap = b.x-a.right
                        valid = 0 <= gap <= 1.5*min(a.height, b.height) and overlap >= .60 and ratio <= 1.30
                    else:
                        overlap = max(0, min(a.right, b.right)-max(a.x, b.x)) / min(a.width, b.width)
                        gap = b.y-a.bottom
                        valid = (0 <= gap <= .75*max(a.height, b.height) and ratio <= 1.20
                                 and (overlap >= .50 or abs(a.x-b.x) <= max(a.height, b.height))
                                 and not re.match(r'^(?:[•●▪\-–—]|\d+[.)])', tb)
                                 and not ta.endswith(('.', '!', '?', '。', '！', '？')))
                    if valid:
                        candidates.append((gap, a.y, a.x, b.y, b.x, i, j))
            if not candidates:
                break
            *_, i, j = min(candidates)
            ta, a = pieces[i]
            tb, b = pieces[j]
            # Keep line metrics while collecting paragraphs (paragraph height is
            # not a font size); vertical chaining is done separately below.
            pieces[i] = (ta+' '+tb, union(a, b))
            pieces.pop(j)
        if horizontal:
            continue
    pieces.sort(key=lambda p: (p[1].y, p[1].x, p[0]))
    return tuple(TextBlock(i, text, rect) for i, (text, rect) in enumerate(pieces[:32]))
