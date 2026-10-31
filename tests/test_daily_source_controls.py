from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from PyQt5.QtCore import QObject, pyqtSignal

from core import config
from core.capture.models import CaptureProfile, WindowIdentity
from core.capture.profile import parse_capture_profile
from ui.capture_settings import CaptureSettings
from ui.capture_binding import CaptureApplicationBinding


def make_desktop_profile():
    return parse_capture_profile({
        'version': 1,
        'source_kind': 'desktop',
        'monitor_name': 'left',
        'window_hint': None,
        'regions': [{'id': '11111111-1111-4111-8111-111111111111', 'name': 'Subtitles',
                     'rect': {'x': .1, 'y': .2, 'width': .4, 'height': .3}, 'enabled': True}],
        'exclusions': [],
    })


def make_window_profile():
    return parse_capture_profile({
        'version': 1,
        'source_kind': 'window',
        'monitor_name': None,
        'window_hint': 'Game Window',
        'regions': [{'id': '11111111-1111-4111-8111-111111111111', 'name': 'Subtitles',
                     'rect': {'x': .1, 'y': .2, 'width': .4, 'height': .3}, 'enabled': True}],
        'exclusions': [],
    })


def test_daily_and_advanced_source_choose_call_binding_once(qtbot, monkeypatch):
    class FakeController(QObject):
        capture_source_selected = pyqtSignal(object, object)
        capture_stop_requested = pyqtSignal()
        daily_state_changed = pyqtSignal()

        def __init__(self):
            super().__init__()
            self.capture_run_requested = False
            self.settings_coordinator = Mock()
            self._capture_profile = None
            self._capture_bound = False

        def set_capture_profile_state(self, profile, *, bound):
            self._capture_profile, self._capture_bound = profile, bound

        def show_capture_waiting(self, error=None):
            pass

        def _show_save_error(self, err):
            pass

    controller = FakeController()
    worker = Mock()
    worker.capture_context = None
    worker.is_drained = True
    screens = Mock()
    screens.snapshot.return_value = ()
    screens.changed = Mock()
    screens.changed.connect = Mock()
    lifecycle = Mock()
    lifecycle.is_active = False

    calls = []
    monkeypatch.setattr(CaptureApplicationBinding, 'select_source', lambda self, *args: calls.append(args))
    binding = CaptureApplicationBinding(controller, worker, Mock(), screens, lifecycle)

    profile = make_desktop_profile()
    
    # Emit from a source control via controller signal
    controller.capture_source_selected.emit(profile, None)
    assert len(calls) == 1


def test_duplicate_titles_keep_distinct_identity_without_hwnd_label(qtbot):
    id1 = WindowIdentity(hwnd=101, pid=10, process_started_100ns=1)
    id2 = WindowIdentity(hwnd=202, pid=20, process_started_100ns=2)

    w1 = SimpleNamespace(title="Same Title", process_name="game.exe", identity=id1, available=True)
    w2 = SimpleNamespace(title="Same Title", process_name="game.exe", identity=id2, available=True)

    panel = CaptureSettings(screens=lambda: (), windows=lambda: [w1, w2])
    qtbot.addWidget(panel)
    panel.kind_combo.setCurrentIndex(1)  # Cửa sổ

    assert panel.source_combo.count() == 2
    label0 = panel.source_combo.itemText(0)
    label1 = panel.source_combo.itemText(1)

    assert label0 != label1
    assert "HWND" not in label0
    assert "HWND" not in label1
    assert panel.source_combo.itemData(0).identity == id1
    assert panel.source_combo.itemData(1).identity == id2


def test_saved_window_hint_is_unbound_after_launch(qtbot):
    controller = Mock()
    controller.capture_source_selected = Mock()
    controller.capture_stop_requested = Mock()
    controller.settings_coordinator = Mock()
    worker = Mock()
    worker.capture_context = None
    worker.is_drained = True
    screens = Mock()
    screens.snapshot.return_value = ()
    screens.changed = Mock()
    lifecycle = Mock()
    lifecycle.is_active = False

    binding = CaptureApplicationBinding(controller, worker, Mock(), screens, lifecycle)
    window_profile = make_window_profile()
    
    binding.initialize(window_profile)
    assert binding.is_bound is False
    assert binding.is_waiting is False


def test_failed_source_save_keeps_previous_binding(qtbot, monkeypatch):
    controller = Mock()
    controller.capture_source_selected = Mock()
    controller.capture_stop_requested = Mock()
    controller.settings_coordinator = Mock()
    worker = Mock()
    worker.capture_context = None
    worker.is_drained = True
    screens = Mock()
    screens.snapshot.return_value = ()
    screens.changed = Mock()
    lifecycle = Mock()
    lifecycle.is_active = False

    binding = CaptureApplicationBinding(controller, worker, Mock(), screens, lifecycle)
    initial_profile = make_desktop_profile()
    binding.profile = initial_profile
    binding.identity = None

    def refuse_save(*args, **kwargs):
        raise config.ConfigError("disk write failed")

    monkeypatch.setattr(config, "save_capture_profile", refuse_save)

    new_profile = make_window_profile()
    new_identity = WindowIdentity(hwnd=999, pid=88, process_started_100ns=77)

    binding.select_source(new_profile, new_identity)
    assert binding.profile == initial_profile
    assert binding.identity is None
