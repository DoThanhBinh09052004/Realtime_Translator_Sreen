from core.blocks.models import OverlayFrame, OverlayBlock, Rect


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
