from core.blocks.models import OverlayFrame, OverlayBlock, Rect
from core.contracts import EngineError
from PyQt5.QtCore import Qt, QEvent


def test_compact_background_pixels_and_relayout(qtbot, monkeypatch, capture_geometry):
    from PyQt5.QtGui import QImage, QColor, QPainter
    from ui.block_layout import layout_blocks, paint_blocks
    import ui.block_overlay as module
    monkeypatch.setattr(module, 'set_capture_excluded', lambda *args: None)
    source = Rect(20, 20, 320, 40)
    def frame(text, frame_id=1):
        return OverlayFrame(1, frame_id, capture_geometry, (OverlayBlock(1, 'Original', text, source),))
    short = frame('Xin chào')
    blocks = layout_blocks(short, max_font_px=22)
    image = QImage(800, 600, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    paint_blocks(painter, blocks, bg_color=QColor(20, 20, 20, 200), text_color=QColor('white'))
    painter.end()
    assert image.pixelColor(338, 58).alpha() == 200
    assert image.pixelColor(345, 40).alpha() == 0
    canvas = module.BlockOverlay()
    qtbot.addWidget(canvas)
    canvas.set_frame(frame('Paimon sẽ đưa bạn đến nơi ở của Thần Anemo trước, và có lý do cho điều đó.'))
    long_right = canvas.placed_blocks[0].view_rect.right
    assert long_right > source.right
    canvas.set_frame(frame('Xin chào', 2))
    canvas.apply_style(font_size=14, bg_hex='#203040', opacity_pct=65)
    qtbot.waitUntil(lambda: canvas.placed_blocks[0].font_px == 14)
    assert canvas.placed_blocks[0].view_rect == source
    painted = canvas.grab().toImage()
    assert painted.pixelColor(338, 58).alpha() > 0
    assert painted.pixelColor(345, 40).alpha() == 0


def test_policy_failure_or_recreated_handle_never_paints_unprotected_blocks(qtbot, monkeypatch, capture_geometry):
    import ui.block_overlay as module
    monkeypatch.setattr(module, 'set_capture_excluded', lambda *a: EngineError('capture_exclusion', 'fail', False))
    canvas = module.BlockOverlay()
    qtbot.addWidget(canvas)
    frame = OverlayFrame(1, 1, capture_geometry, (OverlayBlock(1, 'a', 'b', Rect(0, 0, 100, 20)),))
    canvas.set_frame(frame)
    assert not canvas.isVisible() and not canvas.placed_blocks
    monkeypatch.setattr(module, 'set_capture_excluded', lambda *a: None)
    canvas.set_frame(frame)
    assert canvas.placed_blocks
    monkeypatch.setattr(module, 'set_capture_excluded', lambda *a: EngineError('capture_exclusion', 'fail', False))
    canvas.event(QEvent(QEvent.WinIdChange))
    assert not canvas.isVisible() and not canvas.placed_blocks


def test_blocks_are_click_through_and_older_frames_are_dropped(qtbot, monkeypatch, capture_geometry):
    import ui.block_overlay as module
    from ui.overlay import Overlay
    monkeypatch.setattr(module, 'set_capture_excluded', lambda *a: None)
    overlay = Overlay()
    qtbot.addWidget(overlay)
    overlay.set_mode('blocks', 2)
    def frame(revision, frame_id, text):
        return OverlayFrame(revision, frame_id, capture_geometry, (OverlayBlock(1, 'a', text, Rect(0, 0, 100, 20)),))
    overlay.update_blocks(frame(2, 3, 'new'))
    overlay.update_blocks(frame(1, 4, 'old'))
    overlay.update_blocks(frame(2, 2, 'old'))
    assert overlay.block_overlay.placed_blocks[0].text == 'new'
    overlay.update_blocks(frame(2, 3, 'updated'))
    assert overlay.block_overlay.placed_blocks[0].text == 'updated'
    overlay.update_text('legacy')
    overlay.refresh()
    assert not overlay.isVisible()
    assert overlay.get_geometry_rect() is None
    assert overlay.block_overlay.windowFlags() & Qt.WindowTransparentForInput
    assert overlay.block_overlay.testAttribute(Qt.WA_TransparentForMouseEvents)


def test_leaving_drag_mode_restores_click_through_after_mode_switch(qtbot):
    from ui.overlay import Overlay
    overlay = Overlay()
    qtbot.addWidget(overlay)
    overlay.set_drag_mode(True)
    assert not overlay.testAttribute(Qt.WA_TransparentForMouseEvents)
    overlay.set_mode('blocks', 1)
    overlay.set_mode('subtitle', 2)
    overlay.update_text('New subtitle')
    assert not overlay.is_drag_mode
    assert overlay.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert overlay.cursor().shape() != Qt.SizeAllCursor
