from unittest.mock import Mock
from PyQt5.QtCore import QObject, pyqtSignal
from core import config


def test_public_region_api_and_refresh_apply_once(ui_window):
    from main import apply_selected_region
    region = {'left': -10, 'top': 0, 'width': 200, 'height': 100}
    ui_window.worker.reset_mock()
    assert ui_window.apply_region_selection(region)
    assert config.load_region() == region
    ui_window.worker.set_region.assert_called_once_with(region)
    ui_window.worker.reset_mock()
    ui_window.refresh_region()
    ui_window.worker.set_region.assert_not_called()
    assert apply_selected_region(ui_window, ui_window.worker, region)
    ui_window.worker.set_region.assert_called_once_with(region)


def test_repeated_navigation_does_not_multiply_saves(ui_window, monkeypatch):
    replace = Mock(wraps=config.os.replace)
    monkeypatch.setattr(config.os, 'replace', replace)
    for index in (3, 1, 2, 0) * 5:
        ui_window.nav_buttons[index].click()
    ui_window.worker.reset_mock()
    ui_window.src_combo.setCurrentText('Japanese')
    assert replace.call_count == 1
    ui_window.worker.configure.assert_called_once()


def test_replacing_qobject_overlay_disconnects_old_signal(ui_window, monkeypatch):
    class FakeOverlay(QObject):
        position_changed = pyqtSignal(int, int)
    old = FakeOverlay()
    new = FakeOverlay()
    ui_window.overlay = old
    ui_window.overlay = new
    ui_window.overlay = new
    replace = Mock(wraps=config.os.replace)
    monkeypatch.setattr(config.os, 'replace', replace)
    old.position_changed.emit(-300, 10)
    assert replace.call_count == 0
    new.position_changed.emit(-200, 40)
    assert replace.call_count == 1
    assert (ui_window.state.overlay_x, ui_window.state.overlay_y) == (-200, 40)
