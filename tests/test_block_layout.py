from core.blocks.models import OverlayFrame, OverlayBlock, Rect
from dataclasses import replace
import pytest


def measured_text(text, size, width):
    """Independent Qt measurement for observable fit/minimality assertions."""
    from PyQt5.QtGui import QFont, QTextLayout, QTextOption
    font = QFont('Segoe UI')
    font.setPixelSize(size)
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    height, widest = 0., 0.
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(1., width))
        height += line.height()
        widest = max(widest, line.naturalTextWidth())
    layout.endLayout()
    return height, widest


def text_fits(text, size, rect):
    height, width = measured_text(text, size, rect.width-4)
    return height <= rect.height-4 and width <= rect.width-4


def test_short_translation_keeps_source_box(qapp, capture_geometry):
    from ui.block_layout import layout_blocks
    source = Rect(20, 20, 320, 40)
    block, = layout_blocks(OverlayFrame(1, 1, capture_geometry, (
        OverlayBlock(1, 'Among the seven gods', 'Xin chào', source),)), max_font_px=22)
    assert block.view_rect == source
    assert block.font_px == 22 and not block.clipped


def test_horizontal_growth_is_minimal(qapp, capture_geometry):
    from ui.block_layout import layout_blocks
    source = Rect(10, 10, 30, 40)
    text = 'Vị thần điều khiển gió'
    block, = layout_blocks(OverlayFrame(1, 1, capture_geometry, (
        OverlayBlock(1, 'The wind god', text, source),)), max_font_px=22)
    view = block.view_rect
    assert (view.x, view.y, view.height) == (10, 10, 40)
    assert 30 < view.width < 790
    assert block.font_px == 22 and not block.clipped
    assert text_fits(text, 22, view)
    assert not text_fits(text, 22, Rect(view.x, view.y, view.width-1, view.height))


def test_wraps_and_grows_height_before_shrinking(qapp, capture_geometry):
    from ui.block_layout import layout_blocks
    source = Rect(660, 10, 130, 40)
    text = 'Paimon sẽ đưa bạn đến nơi ở của Thần Anemo trước, và có lý do cho điều đó.'
    block, = layout_blocks(OverlayFrame(1, 1, capture_geometry, (
        OverlayBlock(1, 'Follow Paimon', text, source),)), max_font_px=22)
    view = block.view_rect
    assert (view.x, view.y) == (660, 10)
    assert view.contains(source) and view.right <= 800
    assert 40 < view.height < 590
    assert block.font_px == 22 and not block.clipped
    assert text_fits(text, block.font_px, view)
    assert not text_fits(text, block.font_px, Rect(view.x, view.y, view.width, view.height-1))


def test_shallow_source_grows_height_without_full_width(qapp, capture_geometry):
    from ui.block_layout import layout_blocks
    source = Rect(20, 20, 320, 8)
    block, = layout_blocks(OverlayFrame(1, 1, capture_geometry, (
        OverlayBlock(1, 'Hello', 'Xin chào', source),)), max_font_px=22)
    assert block.view_rect.width == 320
    assert block.view_rect.contains(source)
    assert 8 < block.view_rect.height < 40
    assert block.font_px == 10 and not block.clipped


@pytest.mark.parametrize('obstacle', [Rect(180, 60, 100, 80), Rect(250, 10, 50, 50), Rect(0, 150, 800, 30)])
def test_diagonal_obstacle_preserves_source_and_readable_font(qapp, capture_geometry, obstacle):
    from ui.block_layout import layout_blocks
    source = Rect(10, 10, 100, 40)
    text = 'Paimon sẽ đưa bạn đến nơi ở của Thần Anemo. ' * 3
    blocks = layout_blocks(OverlayFrame(1, 1, capture_geometry, (
        OverlayBlock(1, 'Dialogue', text, source),
        OverlayBlock(2, 'Other', 'OK', obstacle))), max_font_px=22)
    block = next(b for b in blocks if b.block_id == 1)
    assert (block.view_rect.x, block.view_rect.y) == (10, 10)
    assert block.view_rect.contains(source)
    assert not block.view_rect.intersects(obstacle)
    assert block.font_px == 22 and not block.clipped
    assert text_fits(text, 22, block.view_rect)
    assert all(not a.view_rect.intersects(b.view_rect) for i, a in enumerate(blocks) for b in blocks[i+1:])


@pytest.mark.parametrize('ratio', [1., 1.25])
@pytest.mark.parametrize('text', ['Tiếng Việt rất dài '*20, '日本語漢字'*100])
def test_fractional_geometry_and_tiny_canvas_stay_safe(qapp, capture_geometry, ratio, text):
    from ui.block_layout import layout_blocks
    screen = replace(capture_geometry.screen, logical_rect=Rect(0, 0, 1920/ratio, 1080/ratio))
    geometry = replace(capture_geometry, region_px=Rect(0, 0, 30, 12), image_size_px=(30, 12), screen=screen)
    block, = layout_blocks(OverlayFrame(1, 1, geometry, (
        OverlayBlock(1, 'text', text, Rect(-4, -3, 34, 15)),)), max_font_px=22)
    assert Rect(0, 0, 30/ratio, 12/ratio).contains(block.view_rect)
    assert block.view_rect.x == block.view_rect.y == 0
    assert 10 <= block.font_px <= 22
    assert block.clipped


def test_overlapping_sources_keep_safe_fallback(qapp, capture_geometry):
    from ui.block_layout import layout_blocks
    blocks = layout_blocks(OverlayFrame(1, 1, capture_geometry, (
        OverlayBlock(1, 'a', 'Một câu dịch', Rect(10, 10, 150, 40)),
        OverlayBlock(2, 'b', 'Một câu khác', Rect(100, 20, 100, 40)))), max_font_px=22)
    assert blocks
    assert all(Rect(0, 0, 800, 600).contains(b.view_rect) for b in blocks)
    assert all(not a.view_rect.intersects(b.view_rect) for i, a in enumerate(blocks) for b in blocks[i+1:])


@pytest.mark.parametrize('inner', [Rect(20, 20, 50, 40), Rect(10, 10, 200, 80)])
def test_nested_source_translation_is_not_discarded_when_free_space_exists(qapp, capture_geometry, inner):
    from ui.block_layout import layout_blocks
    blocks = layout_blocks(OverlayFrame(1, 1, capture_geometry, (
        OverlayBlock(0, 'Outer', 'Hello world', Rect(10, 10, 200, 80)),
        OverlayBlock(1, 'Inner', 'Hello world', inner))), max_font_px=22)
    assert {b.block_id for b in blocks} == {0, 1}
    assert not blocks[0].view_rect.intersects(blocks[1].view_rect)
    assert all(Rect(0, 0, 800, 600).contains(b.view_rect) for b in blocks)
    assert all(not b.clipped for b in blocks)


def test_long_vietnamese_and_cjk_fit_or_clip_inside_canvas(qapp, capture_geometry):
    from ui.block_layout import layout_blocks
    frame = OverlayFrame(1, 1, capture_geometry, (
        OverlayBlock(1, 'one', 'Tiếng Việt rất dài '*50, Rect(10, 10, 100, 20)),
        OverlayBlock(2, 'two', '日本語漢字'*100, Rect(140, 10, 100, 20))))
    placed = layout_blocks(frame, max_font_px=22)
    assert len(placed) == 2
    for b in placed:
        assert 10 <= b.font_px <= 22
        assert Rect(0, 0, 800, 600).contains(b.view_rect)
    assert not placed[0].view_rect.intersects(placed[1].view_rect)
    assert placed[0].source_rect == Rect(10, 10, 100, 20)


def test_tiny_canvas_clips_and_expands_right_first(qapp, capture_geometry):
    from dataclasses import replace
    from ui.block_layout import layout_blocks
    g = replace(capture_geometry, region_px=Rect(0, 0, 30, 12), image_size_px=(30, 12))
    b, = layout_blocks(OverlayFrame(1, 1, g, (OverlayBlock(1, 'a', 'very long words', Rect(0, 0, 10, 10)),)), max_font_px=22)
    assert b.clipped and b.view_rect.right <= 30
    frame = OverlayFrame(1, 1, capture_geometry, (OverlayBlock(1, 'a', 'This can fit in one expanded line', Rect(10, 10, 30, 20)),))
    b, = layout_blocks(frame, max_font_px=22)
    assert b.view_rect.width > 30
    assert b.font_px == 16
