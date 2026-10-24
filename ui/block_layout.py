"""Shared GUI text measurement and clipped painting for overlay and preview."""
from dataclasses import dataclass
from math import ceil
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QFont, QTextLayout, QTextOption, QFontMetricsF
from core.blocks.models import Rect
from core.blocks.geometry import overlay_window_rect, ocr_rect_to_overlay


@dataclass(frozen=True)
class PlacedBlock:
    block_id: int
    text: str
    source_rect: Rect
    view_rect: Rect
    font_px: int
    clipped: bool


def _font(size, family='Segoe UI'):
    f = QFont(family)
    f.setPixelSize(size)
    return f


def _lines(text, font, width):
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    lines, y = [], 0.
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(1., width))
        line.setPosition(QPointF(0, y))
        lines.append(line)
        y += line.height()
    layout.endLayout()
    return layout, lines, y


def _subtract(rect, obstacle):
    if not rect.intersects(obstacle):
        return [rect]
    x, y, r, b = max(rect.x, obstacle.x), max(rect.y, obstacle.y), min(rect.right, obstacle.right), min(rect.bottom, obstacle.bottom)
    candidates = [(rect.x, rect.y, rect.width, y-rect.y), (rect.x, b, rect.width, rect.bottom-b),
                  (rect.x, y, x-rect.x, b-y), (r, y, rect.right-r, b-y)]
    return [Rect(*c) for c in candidates if c[2] > 0 and c[3] > 0]


def _available_rects(anchor, canvas, obstacles):
    """Free rectangles anchored at the source, including narrow/tall choices."""
    rights = {anchor.right, canvas.right}
    rights.update(o.x for o in obstacles if anchor.right <= o.x <= canvas.right)
    spaces = []
    for right in sorted(rights):
        bottom = canvas.bottom
        for obstacle in obstacles:
            if obstacle.x < right and obstacle.right > anchor.x and obstacle.bottom > anchor.y:
                bottom = min(bottom, obstacle.y)
        if right >= anchor.right and bottom >= anchor.bottom:
            spaces.append(Rect(anchor.x, anchor.y, right-anchor.x, bottom-anchor.y))
    return spaces


def _minimum_extent(lower, upper, fits):
    """Smallest fitting extension to within one logical pixel, retaining floats."""
    lo, hi = 0, ceil(upper-lower)
    while lo < hi:
        mid = (lo+hi)//2
        if fits(min(upper, lower+mid)):
            hi = mid
        else:
            lo = mid+1
    return min(upper, lower+lo)


def _compact_layout(text, source, canvas, obstacles, preferred, font_family):
    # A one-pixel gap is desirable, but must not cut a nonoverlapping source.
    reserved = []
    for obstacle in obstacles:
        padded = Rect(obstacle.x-1, obstacle.y-1, obstacle.width+2, obstacle.height+2)
        reserved.append(obstacle if not source.intersects(obstacle) and source.intersects(padded) else padded)
    anchor = source
    if any(anchor.intersects(o) for o in reserved):
        # Intrinsically overlapping OCR boxes cannot both be fully covered.
        pieces = [anchor]
        for obstacle in reserved:
            pieces = [p for piece in pieces for p in _subtract(piece, obstacle)]
        if not pieces:
            return None
        anchor = min(pieces, key=lambda r: (-r.width*r.height, r.y, r.x))
    spaces = _available_rects(anchor, canvas, reserved)
    measurements, fonts = {}, {}

    def fits(rect, size):
        key = size, rect.width
        if key not in measurements:
            font = fonts.setdefault(size, _font(size, font_family))
            _, lines, height = _lines(text, font, rect.width-4)
            measurements[key] = height, max((line.naturalTextWidth() for line in lines), default=0)
        height, width = measurements[key]
        return height <= rect.height-4 and width <= rect.width-4

    def fit_size(size):
        if fits(anchor, size):
            return anchor
        horizontal, wrapped = [], []
        for space in spaces:
            row = Rect(anchor.x, anchor.y, space.width, anchor.height)
            if fits(row, size):
                width = _minimum_extent(anchor.width, row.width,
                    lambda w: fits(Rect(row.x, row.y, w, row.height), size))
                horizontal.append(Rect(row.x, row.y, width, row.height))
            elif fits(space, size):
                height = _minimum_extent(anchor.height, space.height,
                    lambda h: fits(Rect(space.x, space.y, space.width, h), size))
                width = _minimum_extent(anchor.width, space.width,
                    lambda w: fits(Rect(space.x, space.y, w, height), size))
                wrapped.append(Rect(space.x, space.y, width, height))
        if horizontal:
            return min(horizontal, key=lambda r: r.width)
        return min(wrapped, key=lambda r: (r.height, r.width)) if wrapped else None

    view = fit_size(preferred)
    if view is not None:
        return view, preferred, False
    lo, hi, best = 10, preferred-1, None
    while lo <= hi:
        size = (lo+hi)//2
        view = fit_size(size)
        if view is None:
            hi = size-1
        else:
            best = view, size, False
            lo = size+1
    if best is not None:
        return best
    view = max(spaces, key=lambda r: r.width*r.height, default=anchor)
    return view, 10, not fits(view, 10)


def layout_blocks(frame, *, max_font_px, font_family='Segoe UI'):
    window = overlay_window_rect(frame.geometry)
    canvas = Rect(0, 0, window.width, window.height)
    sources = [(b, ocr_rect_to_overlay(b.source_rect, frame.geometry)) for b in frame.blocks]
    placed = []
    for block, source in sorted(sources, key=lambda p: (p[1].y, p[1].x, p[0].block_id)):
        x, y, right, bottom = max(0, source.x), max(0, source.y), min(canvas.right, source.right), min(canvas.bottom, source.bottom)
        if right <= x or bottom <= y:
            continue
        obstacles = [r for other, r in sources if other.block_id != block.block_id]+[b.view_rect for b in placed]
        preferred = max(10, min(max_font_px, round(.8*source.height)))
        result = _compact_layout(block.translated_text, Rect(x, y, right-x, bottom-y),
                                 canvas, obstacles, preferred, font_family)
        if result is None:
            continue
        view, size, clipped = result
        placed.append(PlacedBlock(block.block_id, block.translated_text, source, view, size, clipped))
    return tuple(placed)


def paint_blocks(painter, blocks, *, bg_color, text_color):
    for block in blocks:
        r = block.view_rect
        painter.save()
        painter.setClipRect(QRectF(r.x, r.y, r.width, r.height))
        painter.fillRect(QRectF(r.x, r.y, r.width, r.height), bg_color)
        painter.setPen(text_color)
        font = _font(block.font_px)
        painter.setFont(font)
        layout, lines, _ = _lines(block.text, font, r.width-4)
        visible = [line for line in lines if line.y()+line.height() <= r.height-4]
        for index, line in enumerate(visible):
            if block.clipped and index == len(visible)-1:
                text = block.text[line.textStart():]
                elided = QFontMetricsF(font).elidedText(text, Qt.ElideRight, max(0, r.width-4))
                painter.drawText(QPointF(r.x+2, r.y+2+line.y()+line.ascent()), elided)
            else:
                line.draw(painter, QPointF(r.x+2, r.y+2))
        painter.restore()
