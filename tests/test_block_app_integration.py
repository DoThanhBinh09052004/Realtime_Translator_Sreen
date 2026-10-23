from core.blocks.models import Rect, ScreenMapping, CaptureGeometry


def test_subtitle_mask_converts_logical_rect_to_physical_at_150_percent():
    from core.blocks.geometry import subtitle_mask_rect
    screen = ScreenMapping('left', Rect(-1280, 0, 1280, 720), Rect(-1920, 0, 1920, 1080))
    geometry = CaptureGeometry(Rect(-1770, 150, 600, 300), screen, (600, 300))
    assert subtitle_mask_rect((-1180, 100, 100, 20), geometry) == (-1770, 150, 150, 30)
    assert subtitle_mask_rect((100, 100, 100, 20), geometry) is None
