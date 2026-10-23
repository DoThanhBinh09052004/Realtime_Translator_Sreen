from core.blocks.models import OverlayFrame, OverlayBlock, Rect
from core.contracts import EngineError
from PyQt5.QtCore import Qt, QEvent


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
