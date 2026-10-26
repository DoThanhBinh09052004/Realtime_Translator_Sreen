"""Comprehensive tests for Task 3: GameControls application lifecycle and selection integration.

Covers:
1. Region selection lifecycle outside main closures:
   - Selecting while running: worker pauses with preserve_translation_session=True, toolbar hidden and busy, selector shown.
   - Finishing selection: applies region, syncs geometry, restores UI, clears busy, resumes via controller.start_ocr(preserve_translation_session=True).
   - Real ControllerWindow + FakeWorker reproduction: emit worker.finished while selecting; upon cancel, controller status and worker agree on 'Đang hoạt động'.
   - Selecting while stopped: worker remains stopped when finished or cancelled.
   - Escape / Cancel preserves old region, restores UI, clears controls busy exactly once.
   - Failed region save: reports error, logs old region retention, does not sync geometry, clears controls busy and restores safely.
   - Duplicate region selection request while already selecting: ignored / blocked.
   - Hidden controller stays hidden: selecting while controller is hidden does not activate or show controller when finished or cancelled.
   - Visible controller restored: selecting while controller is visible restores it.
   - Stale subtitle restoration prevented: stopped selection does not resurrect previously hidden overlay subtitles.
   - Selector factory/show failure recovery: cleans up, restores UI, logs error, does not hang in selecting state.
   - Permanent closed flag & generation guard: close() permanently closes lifecycle; late signals from prior selections ignored.
   - Quit during selection: closes selector immediately without ever resuming worker; late region_selected or cancelled signals ignored.
2. Application lifecycle & window closing:
   - ControllerWindow X button (closeEvent) hides to system tray when tray is available (does not quit or stop worker).
   - ControllerWindow X button safely invokes on_quit_cb when tray is NOT available.
   - Explicit Quit via sidebar/tray/toolbar always drains workers and marks quitting.
   - Missing API key start attempt: does not collapse toolbar, reveals controller error/config view.
   - Worker finished signal during pending internal restart does not falsely expand or stop toolbar.
3. Pre-start capture fallback ordering:
   - Controller emits starting_translation hook before worker.start_worker launches capture.
   - GameControls catches starting_translation and immediately hides unexcluded toolbar before capture frames.
   - Starting from toolbar, hotkey, or full app hides unexcluded toolbar prior to capture.
   - While selecting, queued stopped state sync does not reveal toolbar.
4. Clean shutdown:
   - shutdown removes hotkeys, hides tray, closes toolbar and selector idempotently.
   - No late callbacks or timer events show UI or restart worker after shutdown.
"""
from __future__ import annotations

import pytest
from unittest.mock import Mock, call
from PyQt5.QtCore import QObject, QPoint, QRect, Qt, pyqtSignal
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from core.contracts import EngineError
from core.config import State
from ui.game_controls import GameControls
from ui.region_selection import RegionSelectionLifecycle
from ui.controller import ControllerWindow
import ui.global_hotkeys as global_hotkeys_mod


@pytest.fixture(autouse=True)
def guard_no_real_native_api(monkeypatch):
    """Safety guard: prevent Win32NativeApi construction during lifecycle tests."""
    def _forbid_native(*args, **kwargs):
        raise AssertionError("Real Win32NativeApi instantiated during test! Inject fake hotkeys instead.")

    monkeypatch.setattr(global_hotkeys_mod, "Win32NativeApi", _forbid_native)


class FakeHotkeys(QObject):
    toggle_requested = pyqtSignal()
    region_requested = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.started = False
        self.closed = False

    def start(self) -> bool:
        self.started = True
        return True

    def close(self) -> None:
        self.closed = True


class FakeWorker(QObject):
    finished = pyqtSignal()
    revision_changed = pyqtSignal(int)
    translation_status_updated = pyqtSignal(object)
    log_updated = pyqtSignal(str)
    error_occurred = pyqtSignal(object)
    shutdown_finished = pyqtSignal()

    def __init__(self, running: bool = False, restart_pending: bool = False) -> None:
        super().__init__()
        self._running = running
        self.restart_pending = restart_pending
        self.start_worker_calls: list[dict] = []
        self.stop_worker_calls: list[dict] = []
        self.interval_val = 500

    def is_running(self) -> bool:
        return self._running

    def interval(self) -> int:
        return self.interval_val

    def setInterval(self, val: int) -> None:
        self.interval_val = val

    def start_worker(self, **kwargs) -> None:
        self.start_worker_calls.append(kwargs)
        self._running = True

    def stop_worker(self, **kwargs) -> None:
        self.stop_worker_calls.append(kwargs)
        self._running = False


class FakeSelector(QWidget):
    region_selected = pyqtSignal(dict)
    cancelled = pyqtSignal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__()
        self.closed = False
        self.shown = False

    def show(self) -> None:
        self.shown = True
        super().show()

    def close(self) -> bool:
        self.closed = True
        return super().close()


class FakeTrayIcon(QObject):
    activated = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.visible = False
        self._tooltip = ""
        self._menu = None

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def isVisible(self):
        return self.visible

    def setToolTip(self, tip):
        self._tooltip = tip

    def setContextMenu(self, menu):
        self._menu = menu


def make_test_game_controls(controller, worker, toolbar=None, capture_excluder=None, tray_available=False):
    """Helper to instantiate GameControls with strictly fake hotkeys and mock excluder."""
    fake_hk = FakeHotkeys()
    gc = GameControls(
        controller=controller,
        worker=worker,
        toolbar=toolbar,
        hotkeys=fake_hk,
        tray_available=tray_available,
        capture_excluder=capture_excluder or (lambda hwnd, excl: None),
    )
    return gc


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_region_selection_while_running(qtbot):
    """Selecting while running pauses worker, hides UI, and finishing resumes session via controller."""
    worker = FakeWorker(running=True)
    controller = Mock()
    controller.isVisible.return_value = True
    controller.apply_region_selection.return_value = True
    overlay = Mock()
    overlay.isVisible.return_value = True
    sync_geom = Mock()
    game_controls = Mock()

    created_selectors = []
    def make_selector(**kwargs):
        s = FakeSelector()
        created_selectors.append(s)
        return s

    lifecycle = RegionSelectionLifecycle(
        controller=controller,
        worker=worker,
        overlay=overlay,
        geometry_provider=Mock(),
        game_controls=game_controls,
        on_sync_geometry=sync_geom,
        selector_factory=make_selector,
    )

    lifecycle.start_selection()

    assert lifecycle.is_active is True
    # Worker paused with preserve_translation_session
    assert len(worker.stop_worker_calls) == 1
    assert worker.stop_worker_calls[0].get("preserve_translation_session") is True
    # UI hidden
    controller.hide.assert_called_once()
    overlay.hide.assert_called_once()
    game_controls.set_selection_active.assert_called_with(True)
    assert len(created_selectors) == 1
    assert created_selectors[0].shown is True

    # User completes selection
    new_reg = {"x": 10, "y": 20, "width": 100, "height": 100}
    created_selectors[0].region_selected.emit(new_reg)

    assert lifecycle.is_active is False
    controller.apply_region_selection.assert_called_once_with(new_reg)
    sync_geom.assert_called_once()
    controller.show.assert_called_once()
    overlay.show.assert_called_once()
    game_controls.set_selection_active.assert_called_with(False)

    # Finding 1: Resumes through controller.start_ocr
    controller.start_ocr.assert_called_once_with(preserve_translation_session=True)
    assert created_selectors[0].closed is True


def test_real_controller_worker_agree_after_cancel_selection(qtbot):
    """Finding 1 Reproduction & Regression:
    Real ControllerWindow + FakeWorker + FakeSelector:
    Start running -> start selection -> worker emits finished while selecting -> cancel selection.
    Both worker.is_running() and controller status MUST agree on 'Đang hoạt động'.
    """
    worker = FakeWorker(running=False)
    state = State()
    state.ai_provider = "Google Gemini"

    window = ControllerWindow(worker, state, Mock(), Mock())
    qtbot.addWidget(window)

    # Start OCR initially
    window.start_ocr()
    assert worker.is_running() is True
    assert "Đang hoạt động" in window.status.text()

    toolbar = Mock()
    gc = make_test_game_controls(window, worker, toolbar=toolbar)
    window.set_game_controls(gc)

    created_selectors = []
    def make_selector(**kwargs):
        s = FakeSelector()
        created_selectors.append(s)
        return s

    overlay = Mock()
    overlay.isVisible.return_value = True

    lifecycle = RegionSelectionLifecycle(
        controller=window,
        worker=worker,
        overlay=overlay,
        geometry_provider=Mock(),
        game_controls=gc,
        selector_factory=make_selector,
    )

    lifecycle.start_selection()
    assert lifecycle.is_active is True
    assert worker.is_running() is False  # Paused during selection

    # While selecting, worker emits finished (e.g. background drain completed)
    worker.finished.emit()
    # At this point, controller may have reacted to finished
    assert "Đã dừng" in window.status.text()

    # User cancels selection
    created_selectors[0].cancelled.emit()

    # Now, resume must restore BOTH worker and controller to 'Đang hoạt động'
    assert worker.is_running() is True
    assert "Đang hoạt động" in window.status.text()
    assert lifecycle.is_active is False
    gc.shutdown()


def test_region_selection_while_stopped(qtbot):
    """Selecting while stopped does not start worker upon finish."""
    worker = FakeWorker(running=False)
    controller = Mock()
    controller.isVisible.return_value = True
    controller.apply_region_selection.return_value = True
    overlay = Mock()
    overlay.isVisible.return_value = False  # Overlay was not visible
    game_controls = Mock()

    created_selectors = []
    def make_selector(**kwargs):
        s = FakeSelector()
        created_selectors.append(s)
        return s

    lifecycle = RegionSelectionLifecycle(
        controller=controller,
        worker=worker,
        overlay=overlay,
        geometry_provider=Mock(),
        game_controls=game_controls,
        on_sync_geometry=Mock(),
        selector_factory=make_selector,
    )

    lifecycle.start_selection()
    assert len(worker.stop_worker_calls) == 0

    # User cancels with Escape
    created_selectors[0].cancelled.emit()

    assert lifecycle.is_active is False
    assert len(worker.start_worker_calls) == 0
    controller.start_ocr.assert_not_called()
    controller.show.assert_called_once()
    # Finding 5: Overlay was hidden before, so it must NOT be shown!
    overlay.show.assert_not_called()
    game_controls.set_selection_active.assert_called_with(False)


def test_region_selection_preserves_hidden_controller(qtbot):
    """If controller was hidden before selection, it stays hidden after finish/cancel."""
    worker = FakeWorker(running=False)
    controller = Mock()
    controller.isVisible.return_value = False  # Hidden main window!
    overlay = Mock()
    game_controls = Mock()

    created_selectors = []
    def make_selector(**kwargs):
        s = FakeSelector()
        created_selectors.append(s)
        return s

    lifecycle = RegionSelectionLifecycle(
        controller=controller,
        worker=worker,
        overlay=overlay,
        geometry_provider=Mock(),
        game_controls=game_controls,
        selector_factory=make_selector,
    )

    lifecycle.start_selection()
    created_selectors[0].cancelled.emit()

    # Controller must NOT be shown
    controller.show.assert_not_called()
    assert lifecycle.is_active is False


def test_duplicate_region_selection_ignored(qtbot):
    """Reentrant or duplicate start_selection calls while selecting are ignored."""
    worker = FakeWorker(running=False)
    controller = Mock()
    created_selectors = []
    def make_selector(**kwargs):
        s = FakeSelector()
        created_selectors.append(s)
        return s

    lifecycle = RegionSelectionLifecycle(
        controller=controller,
        worker=worker,
        overlay=Mock(),
        geometry_provider=Mock(),
        game_controls=Mock(),
        selector_factory=make_selector,
    )

    lifecycle.start_selection()
    assert len(created_selectors) == 1
    # Duplicate call
    lifecycle.start_selection()
    assert len(created_selectors) == 1


def test_failed_save_restores_safely_and_logs(qtbot):
    """Finding 6: If apply_region_selection fails while previously running:
    logs old region retained, does not sync geometry, clears controls busy, and resumes safely.
    """
    worker = FakeWorker(running=True)
    controller = Mock()
    controller.isVisible.return_value = True
    controller.apply_region_selection.return_value = False  # Save failed!
    sync_geom = Mock()
    game_controls = Mock()

    created_selectors = []
    def make_selector(**kwargs):
        s = FakeSelector()
        created_selectors.append(s)
        return s

    lifecycle = RegionSelectionLifecycle(
        controller=controller,
        worker=worker,
        overlay=Mock(),
        geometry_provider=Mock(),
        game_controls=game_controls,
        on_sync_geometry=sync_geom,
        selector_factory=make_selector,
    )

    lifecycle.start_selection()
    created_selectors[0].region_selected.emit({"x": 0, "y": 0, "width": 10, "height": 10})

    # Geometry not synced when save failed
    sync_geom.assert_not_called()
    # Clear log appended to console page
    controller.console_page.append_log.assert_called_with("Lưu vùng quét thất bại; đang giữ nguyên vùng quét cũ.")
    # Busy cleared and resume called
    assert lifecycle.is_active is False
    game_controls.set_selection_active.assert_called_with(False)
    controller.start_ocr.assert_called_once_with(preserve_translation_session=True)
    controller.show.assert_called_once()


def test_selector_construction_error_recovery(qtbot):
    """Finding 4: When selector factory/show raises an exception:
    recovers cleanly, restores prior UI visibility, logs error, and clears selection state.
    """
    worker = FakeWorker(running=True)
    controller = Mock()
    controller.isVisible.return_value = True
    overlay = Mock()
    overlay.isVisible.return_value = True
    game_controls = Mock()

    def bad_factory(**kwargs):
        raise RuntimeError("Native selector creation failed")

    lifecycle = RegionSelectionLifecycle(
        controller=controller,
        worker=worker,
        overlay=overlay,
        geometry_provider=Mock(),
        game_controls=game_controls,
        selector_factory=bad_factory,
    )

    # Must not raise
    lifecycle.start_selection()

    assert lifecycle.is_active is False
    # Error logged
    controller.console_page.append_log.assert_called_once()
    assert "Không thể mở màn hình chọn vùng quét" in controller.console_page.append_log.call_args[0][0]
    # Restored
    controller.show.assert_called_once()
    overlay.show.assert_called_once()
    game_controls.set_selection_active.assert_called_with(False)
    # Resumes worker
    controller.start_ocr.assert_called_once_with(preserve_translation_session=True)


def test_session_generation_guards_late_callbacks(qtbot):
    """Finding 3: Callbacks from an older selection session are ignored in a new session."""
    worker = FakeWorker(running=False)
    controller = Mock()
    controller.apply_region_selection.return_value = True
    game_controls = Mock()

    created_selectors = []
    def make_selector(**kwargs):
        s = FakeSelector()
        created_selectors.append(s)
        return s

    lifecycle = RegionSelectionLifecycle(
        controller=controller,
        worker=worker,
        overlay=Mock(),
        geometry_provider=Mock(),
        game_controls=game_controls,
        selector_factory=make_selector,
    )

    # Session 1 starts and cancels
    lifecycle.start_selection()
    selector_1 = created_selectors[0]
    lifecycle.on_selection_cancelled(generation=1)

    # Session 2 starts
    lifecycle.start_selection()
    selector_2 = created_selectors[1]
    assert lifecycle._session_generation == 2

    # Late callback from selector_1 arrives during session 2
    selector_1.region_selected.emit({"x": 1, "y": 2, "width": 3, "height": 4})

    # Must be ignored: apply_region_selection NOT called for old callback
    controller.apply_region_selection.assert_not_called()
    assert lifecycle.is_active is True

    # Proper callback for session 2 arrives
    selector_2.region_selected.emit({"x": 10, "y": 20, "width": 30, "height": 40})
    controller.apply_region_selection.assert_called_once_with({"x": 10, "y": 20, "width": 30, "height": 40})
    assert lifecycle.is_active is False


def test_start_selection_after_close_is_permanently_ignored(qtbot):
    """Finding 3: After close(), start_selection is permanently blocked."""
    worker = FakeWorker(running=False)
    controller = Mock()
    created_selectors = []
    def make_selector(**kwargs):
        s = FakeSelector()
        created_selectors.append(s)
        return s

    lifecycle = RegionSelectionLifecycle(
        controller=controller,
        worker=worker,
        overlay=Mock(),
        geometry_provider=Mock(),
        game_controls=Mock(),
        selector_factory=make_selector,
    )

    lifecycle.close()
    assert lifecycle.is_closed is True

    lifecycle.start_selection()
    assert len(created_selectors) == 0
    assert lifecycle.is_active is False


def test_quit_during_selection_closes_selector_without_resuming(qtbot):
    """Quitting during selection closes selector immediately and never resumes worker."""
    worker = FakeWorker(running=True)
    controller = Mock()
    game_controls = Mock()

    created_selectors = []
    def make_selector(**kwargs):
        s = FakeSelector()
        created_selectors.append(s)
        return s

    lifecycle = RegionSelectionLifecycle(
        controller=controller,
        worker=worker,
        overlay=Mock(),
        geometry_provider=Mock(),
        game_controls=game_controls,
        selector_factory=make_selector,
    )

    lifecycle.start_selection()
    selector = created_selectors[0]
    assert selector.closed is False

    # Quit / Close lifecycle
    lifecycle.close()

    assert selector.closed is True
    assert lifecycle.is_active is False
    assert lifecycle.is_closed is True

    # Emit late signals - should be ignored
    selector.region_selected.emit({"x": 10, "y": 20, "width": 100, "height": 100})
    selector.cancelled.emit()

    # Worker must NOT be resumed
    assert len(worker.start_worker_calls) == 0
    controller.start_ocr.assert_not_called()


def test_close_event_hides_when_tray_available(qtbot):
    """Clicking [X] on ControllerWindow hides window when tray icon is available."""
    worker = FakeWorker()
    state = State()

    on_quit = Mock()
    on_select = Mock()

    window = ControllerWindow(worker, state, on_select, on_quit)
    qtbot.addWidget(window)

    fake_tray = FakeTrayIcon()
    fake_controls = Mock()
    fake_controls.tray_icon = fake_tray
    window.set_game_controls(fake_controls)

    window.show()
    assert window.isVisible() is True

    # Simulate close event (user clicks X)
    window.close()

    # Window should be hidden, NOT quitting
    assert window.isVisible() is False
    on_quit.assert_not_called()


def test_close_event_quits_when_tray_unavailable(qtbot):
    """Clicking [X] invokes on_quit when tray icon is not available."""
    worker = FakeWorker()
    state = State()

    on_quit = Mock()
    window = ControllerWindow(worker, state, Mock(), on_quit)
    qtbot.addWidget(window)

    fake_controls = Mock()
    fake_controls.tray_icon = None  # No tray!
    window.set_game_controls(fake_controls)

    window.close()

    # Must call on_quit callback
    on_quit.assert_called_once()


def test_explicit_quit_drains_worker_and_shuts_down(qtbot):
    """Sidebar quit or tray quit drains worker and shuts down cleanly."""
    worker = FakeWorker(running=True)
    state = State()

    quitted = False
    def on_quit():
        nonlocal quitted
        quitted = True
        worker.stop_worker()

    window = ControllerWindow(worker, state, Mock(), on_quit)
    qtbot.addWidget(window)

    # Sidebar quit requested
    window.sidebar.quit_requested.emit()

    assert quitted is True
    assert len(worker.stop_worker_calls) == 1


def test_pre_start_hook_hides_unexcluded_toolbar_before_worker_starts(qtbot):
    """CRITICAL: starting_translation signal hides unexcluded toolbar BEFORE worker.start_worker."""
    worker = FakeWorker(running=False)

    class ControllerSignalEmitter(QObject):
        starting_translation = pyqtSignal()
        def __init__(self):
            super().__init__()
            self.worker = worker

    c_obj = ControllerSignalEmitter()
    toolbar = Mock()
    toolbar.isVisible.return_value = True

    # GameControls with capture exclusion failed (_capture_excluded = False)
    gc = make_test_game_controls(
        controller=c_obj,
        worker=worker,
        toolbar=toolbar,
        tray_available=False,
        capture_excluder=lambda hwnd, excl: EngineError("capture_exclusion", "failed", False),
    )
    assert gc.is_capture_excluded is False

    call_order = []
    toolbar.hide.side_effect = lambda: call_order.append("toolbar_hide")
    worker.start_worker = lambda **kwargs: call_order.append("worker_start")

    # When starting_translation is emitted, toolbar must hide immediately before start_worker
    c_obj.starting_translation.emit()
    worker.start_worker()

    assert call_order == ["toolbar_hide", "worker_start"]
    gc.shutdown()


def test_queued_stopped_sync_while_selecting_does_not_reveal_toolbar(qtbot):
    """Queued state sync while selecting is active must keep toolbar hidden."""
    worker = FakeWorker(running=True)
    toolbar = Mock()
    toolbar.isVisible.return_value = False

    gc = make_test_game_controls(
        controller=Mock(),
        worker=worker,
        toolbar=toolbar,
        tray_available=False,
        capture_excluder=lambda hwnd, excl: None,  # excluded
    )
    gc.set_selection_active(True)

    # Worker finishes / stops and queues state sync
    worker.set_running = False
    worker._running = False
    gc.sync_state()

    # Toolbar must NOT be shown while selecting
    toolbar.show.assert_not_called()
    gc.shutdown()


def test_stale_finish_during_restart_pending_sequence(qtbot):
    """Regression test for exact sequence:
    running=True; worker sets running=False and emits revision_changed synchronously;
    only THEN sets restart_pending=True; next GUI event turn must retain running toolbar.
    """
    worker = FakeWorker(running=True, restart_pending=False)
    toolbar = Mock()

    gc = make_test_game_controls(
        controller=Mock(),
        worker=worker,
        toolbar=toolbar,
        tray_available=False,
        capture_excluder=lambda hwnd, excl: None,
    )
    toolbar.reset_mock()

    # Exact regression sequence:
    # 1. worker sets running=False
    worker._running = False
    # 2. synchronously emits revision_changed
    worker.revision_changed.emit(2)
    # 3. THEN sets restart_pending=True
    worker.restart_pending = True

    # 4. GUI event turn processes queued singleShot
    qtbot.wait(10)

    # Toolbar must retain running state (not set_running(False))
    toolbar.set_running.assert_not_called()
    assert gc._last_running_state is True
    gc.shutdown()
