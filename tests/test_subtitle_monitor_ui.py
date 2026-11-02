from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QPoint, QRect
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QApplication
from ui.overlay import Overlay


@pytest.fixture
def overlay(qtbot):
    widget = Overlay()
    qtbot.addWidget(widget)
    return widget


def use_area(monkeypatch, overlay, area):
    monkeypatch.setattr(overlay, '_available_geometry', lambda: area, raising=False)


def test_secondary_monitor_preset(monkeypatch, overlay):
    use_area(monkeypatch, overlay, QRect(1920, 0, 1920, 1080))
    overlay.resize(300, 60)
    overlay.apply_preset('bottom_center')
    assert overlay.pos() == QPoint(2730, 940)


def test_update_keeps_negative_monitor(monkeypatch, overlay):
    area = QRect(-1920, -1080, 1920, 1080)
    use_area(monkeypatch, overlay, area)
    overlay.apply_preset('bottom_center')
    overlay.update_text('日本語の字幕と tiếng Việt ' * 25)
    assert area.contains(overlay.frameGeometry())
    assert overlay.maximumWidth() == 1440


def test_update_uses_new_monitor_width(monkeypatch, overlay):
    use_area(monkeypatch, overlay, QRect(1920, 0, 1920, 1080))
    overlay.apply_preset('bottom_center')
    area = QRect(-1280, 0, 1280, 720)
    use_area(monkeypatch, overlay, area)
    overlay.update_text('A translated sentence ' * 20)
    assert overlay.maximumWidth() == 960
    assert area.contains(overlay.frameGeometry())


def test_restore_offscreen_position_on_update_and_drag(monkeypatch, overlay):
    area = QRect(0, 0, 1920, 1080)
    use_area(monkeypatch, overlay, area)
    overlay.move(9000, 9000)
    overlay.update_text('Restored subtitle')
    assert area.contains(overlay.frameGeometry())
    overlay.move(9000, 9000)
    positions = []
    overlay.position_changed.connect(lambda *position: positions.append(position))
    overlay.set_drag_mode(True)
    assert area.contains(overlay.frameGeometry())
    assert positions == []


@pytest.mark.parametrize('ratio', [1.5, 2.0])
def test_monitor_selection_uses_pre_resize_center(monkeypatch, overlay, ratio):
    area = QRect(1920, 40, 1280, 680)
    screen = SimpleNamespace(availableGeometry=lambda: area, devicePixelRatio=lambda: ratio)
    points = []
    monkeypatch.setattr(QGuiApplication, 'screenAt', lambda point: points.append(QPoint(point)) or screen)
    before = overlay.frameGeometry().center()
    assert overlay._available_geometry() == area
    overlay.update_text('A long Japanese subtitle 日本語 ' * 12)
    assert points == [before, before]
    assert overlay.maximumWidth() == 960
    assert area.contains(overlay.frameGeometry())


def test_missing_monitor_falls_back_to_primary(monkeypatch, overlay):
    area = QRect(-1920, -1080, 1920, 1080)
    primary = SimpleNamespace(availableGeometry=lambda: area)
    monkeypatch.setattr(QGuiApplication, 'screenAt', lambda point: None)
    monkeypatch.setattr(overlay, 'screen', lambda: None)
    monkeypatch.setattr(QApplication, 'primaryScreen', lambda: primary)
    assert overlay._available_geometry() == area


def test_offscreen_center_uses_valid_widget_screen(monkeypatch, overlay):
    area = QRect(1920, 0, 1280, 720)
    screen = SimpleNamespace(availableGeometry=lambda: area)
    monkeypatch.setattr(QGuiApplication, 'screenAt', lambda point: None)
    monkeypatch.setattr(overlay, 'screen', lambda: screen)
    monkeypatch.setattr(QApplication, 'screens', lambda: [screen])
    assert overlay._available_geometry() == area


def test_removed_widget_screen_uses_primary(monkeypatch, overlay):
    area = QRect(-1920, 0, 1920, 1080)
    removed = SimpleNamespace(availableGeometry=lambda: QRect(9000, 0, 800, 600))
    primary = SimpleNamespace(availableGeometry=lambda: area)
    monkeypatch.setattr(QGuiApplication, 'screenAt', lambda point: None)
    monkeypatch.setattr(overlay, 'screen', lambda: removed)
    monkeypatch.setattr(QApplication, 'screens', lambda: [primary])
    monkeypatch.setattr(QApplication, 'primaryScreen', lambda: primary)
    assert overlay._available_geometry() == area
