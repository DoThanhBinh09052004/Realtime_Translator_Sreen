import pytest
from core.blocks.models import Rect, ScreenMapping, CaptureGeometry


def test_negative_origin_resized_ocr_mapping():
    from core.blocks.geometry import overlay_window_rect, ocr_rect_to_overlay
    screen = ScreenMapping('left', Rect(-1280, 0, 1280, 720), Rect(-1920, 0, 1920, 1080))
    g = CaptureGeometry(Rect(-1770, 150, 600, 300), screen, (1200, 600))
    assert overlay_window_rect(g) == Rect(-1180, 100, 400, 200)
    assert ocr_rect_to_overlay(Rect(60, 30, 240, 60), g) == Rect(20, 10, 80, 20)


@pytest.mark.parametrize('scale', [1, 1.25, 1.5, 2])
def test_selection_rounds_outwards_and_rejects_cross_screen(scale):
    from core.blocks.geometry import qt_selection_to_physical, resolve_capture_geometry
    screen = ScreenMapping('left', Rect(-800, 0, 800, 600), Rect(-800*scale, 0, 800*scale, 600*scale))
    region = qt_selection_to_physical(Rect(-700, 100, 200, 100), screen)
    assert region == dict(left=int(-700*scale), top=int(100*scale), width=int(200*scale), height=int(100*scale))
    assert resolve_capture_geometry(dict(left=-10, top=0, width=20, height=20), (screen,), (20, 20)) is None
