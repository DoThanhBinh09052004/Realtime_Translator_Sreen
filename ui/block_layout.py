"""Shared GUI text measurement and clipped painting for overlay and preview."""
from dataclasses import dataclass
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
        # Start with the source anchor, expand right first and then down. Reserve
        # all other anchors, even those whose text has not been laid out yet.
        r_limit = min([r.x-2 for r in obstacles if r.x >= right and r.y < bottom and r.bottom > y]+[canvas.right])
        view = Rect(x, y, max(right, r_limit)-x, bottom-y)
        preferred = max(10, min(max_font_px, round(.8*source.height)))
        def fits(rect, size):
            _, lines, h = _lines(block.translated_text, _font(size, font_family), rect.width-4)
            return h <= rect.height-4 and all(line.naturalTextWidth() <= rect.width-4 for line in lines)
        if not fits(view, preferred):
            b_limit = min([r.y-2 for r in obstacles if r.y >= bottom and r.x < view.right and r.right > x]+[canvas.bottom])
            view = Rect(x, y, view.width, max(bottom, b_limit)-y)
        pieces = [view]
        for obstacle in obstacles:
            padded = Rect(obstacle.x-1, obstacle.y-1, obstacle.width+2, obstacle.height+2)
            pieces = [part for piece in pieces for part in _subtract(piece, padded)]
        if not pieces:
            continue
        view = min(pieces, key=lambda r: (-r.width*r.height, r.y, r.x))
        lo, hi, size = 10, preferred, 10
        while lo <= hi:
            mid = (lo+hi)//2
            if fits(view, mid):
                size, lo = mid, mid+1
            else:
                hi = mid-1
        placed.append(PlacedBlock(block.block_id, block.translated_text, source, view, size, not fits(view, size)))
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
