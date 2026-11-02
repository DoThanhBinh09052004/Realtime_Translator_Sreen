import pytest
from ui.overlay import Overlay
from PyQt5.QtGui import QFontDatabase


@pytest.mark.parametrize('opacity, alpha', [(0, 0), (50, 128), (100, 255)])
def test_subtitle_background_pixels_follow_opacity(qtbot, opacity, alpha):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/arial.ttf')
    overlay = Overlay('#000000', opacity, '#ffffff')
    qtbot.addWidget(overlay)
    overlay.resize(400, 100)
    overlay.show()
    image = overlay.grab().toImage()
    background = image.pixelColor(25, 25)
    assert abs(background.alpha() - alpha) <= 1
    assert background.red() == background.green() == background.blue() == 0
    assert any(image.pixelColor(x, y).red() > 200
               and image.pixelColor(x, y).alpha() > 240
               for x in range(80, 320) for y in range(30, 70))


def test_subtitle_background_updates_without_recreating_window(qtbot):
    overlay = Overlay('#000000', 0)
    qtbot.addWidget(overlay)
    overlay.resize(400, 100)
    overlay.show()
    for opacity, alpha in [(100, 255), (50, 128), (0, 0)]:
        overlay.apply_style(opacity_pct=opacity)
        assert abs(overlay.grab().toImage().pixelColor(25, 25).alpha() - alpha) <= 1
