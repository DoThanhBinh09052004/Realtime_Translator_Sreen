"""Tests for GameControls – the central coordinator for toolbar, tray, and shortcuts.

Covers:
 - Toolbar routing through controller methods (start_ocr, stop_ocr, region, open, quit).
 - Tray menu routing and text updates (Bắt đầu / Dừng lại).
 - Tray activation: single-click restore toolbar (without activating), double-click open main app.
 - Open app restores minimized controller window.
 - Hotkey routing and error logging.
 - Failed start leaves toolbar expanded, ring stopped, and reveals controller error/config view.
 - Internal restart (restart_pending) vs fatal finish lifecycle with queued GUI turns.
 - Synchronous revision_changed before restart_pending does not cause false stopped presentation.
 - Selection sets toolbar busy, ignores toggles, and clears busy on finish.
 - Direct shutdown rejects subsequent and queued actions.
 - Boolean state unchanged does not reset rotating ring animation.
 - Tray absence does not crash or strand user.
 - Capture exclusion failure fallback: automatically hides for active capture session, restores on stop.
 - Tray single-click does not reveal unexcluded rotating toolbar during active capture.
 - WinIdChange triggers capture exclusion reapplication.
 - EngineError.user_message used for reporting.
 - Save-position failure handling (ConfigError logged, no crash).
 - Screen position recovery (accessible kept, inaccessible recovered to primary work area).
 - Localized Vietnamese tooltips with shortcut hints (Ctrl+Alt+F8, Ctrl+Alt+F9).
"""
from __future__ import annotations

import pytest
from PyQt5.QtCore import QEvent, QObject, QPoint, QRect, Qt, pyqtSignal
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon

from core.config import ConfigError
from core.contracts import EngineError
from ui.game_toolbar import GameToolbar
from ui.global_hotkeys import GlobalHotkeys


# ---------------------------------------------------------------------------
# Mocks & Fakes
# ---------------------------------------------------------------------------

class MockWorker(QObject):
    finished = pyqtSignal()
    revision_changed = pyqtSignal(int)

    def __init__(self, running: bool = False, restart_pending: bool = False) -> None:
        super().__init__()
        self._running = running
        self.restart_pending = restart_pending

    def is_running(self) -> bool:
        return self._running

    def set_running(self, running: bool) -> None:
        self._running = running


class MockConsolePage:
    def __init__(self) -> None:
        self.logs: list[str] = []

    def append_log(self, msg: str) -> None:
        self.logs.append(msg)


class MockStatus:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def showMessage(self, msg: str, timeout: int = 0) -> None:
        self.messages.append(msg)


class MockController:
    def __init__(self, worker: MockWorker | None = None) -> None:
        self.worker = worker
        self.console_page = MockConsolePage()
        self.status = MockStatus()
        self.start_ocr_calls = 0
        self.stop_ocr_calls = 0
        self.shown = False
        self.raised = False
        self.activated = False
        self.closed = False
        self.show_normal_called = False
        self._minimized = False

    def isMinimized(self) -> bool:
        return self._minimized

    def showNormal(self) -> None:
        self.show_normal_called = True
        self._minimized = False

    def start_ocr(self) -> None:
        self.start_ocr_calls += 1

    def stop_ocr(self) -> None:
        self.stop_ocr_calls += 1

    def show(self) -> None:
        self.shown = True

    def raise_(self) -> None:
        self.raised = True

    def activateWindow(self) -> None:
        self.activated = True

    def close(self) -> None:
        self.closed = True


class FakeNativeApi:
    def __init__(self) -> None:
        self.registered: dict[tuple[int | None, int], tuple[int, int]] = {}
        self.unregistered: list[tuple[int | None, int]] = []

    def RegisterHotKey(self, hwnd: int | None, hk_id: int, fsModifiers: int, vk: int) -> bool:
        self.registered[(hwnd, hk_id)] = (fsModifiers, vk)
        return True

    def UnregisterHotKey(self, hwnd: int | None, hk_id: int) -> bool:
        key = (hwnd, hk_id)
        if key in self.registered:
            del self.registered[key]
            self.unregistered.append(key)
            return True
        return False


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

class TestToolbarAndTrayRouting:
    """Toolbar and tray actions route cleanly to controller methods."""

    def test_toolbar_toggle_routes_to_start_stop(self, qtbot):
        from ui.game_controls import GameControls

        worker = MockWorker(running=False)
        controller = MockController(worker=worker)
        tb = GameToolbar()
        qtbot.addWidget(tb)

        gc = GameControls(
            controller=controller,
            worker=worker,
            toolbar=tb,
            tray_available=True,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            config_loader=lambda: {},
            config_saver=lambda d: None,
            capture_excluder=lambda hwnd, exc=True: None,
        )

        # 1. When stopped, toggle starts OCR
        tb.toggle_requested.emit()
        assert controller.start_ocr_calls == 1
        assert controller.stop_ocr_calls == 0

        # Simulate worker running now
        worker.set_running(True)
        gc.sync_state()

        # 2. When running, toggle stops OCR
        tb.toggle_requested.emit()
        assert controller.stop_ocr_calls == 1

        gc.shutdown()

    def test_toolbar_region_open_quit_routing(self, qtbot):
        from ui.game_controls import GameControls

        controller = MockController()
        tb = GameToolbar()
        qtbot.addWidget(tb)

        region_called = []
        quit_called = []

        gc = GameControls(
            controller=controller,
            toolbar=tb,
            on_select_region=lambda: region_called.append(True),
            on_quit=lambda: quit_called.append(True),
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            config_loader=lambda: {},
            config_saver=lambda d: None,
            capture_excluder=lambda hwnd, exc=True: None,
        )

        # Region request
        tb.region_requested.emit()
        assert len(region_called) == 1

        # Open request
        tb.open_requested.emit()
        assert controller.shown is True
        assert controller.raised is True
        assert controller.activated is True

        # Quit request
        tb.quit_requested.emit()
        assert len(quit_called) == 1

        gc.shutdown()

    def test_tray_menu_routing_and_text_updates(self, qtbot):
        from ui.game_controls import GameControls

        worker = MockWorker(running=False)
        controller = MockController(worker=worker)
        tb = GameToolbar()
        qtbot.addWidget(tb)

        gc = GameControls(
            controller=controller,
            worker=worker,
            toolbar=tb,
            tray_available=True,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            config_loader=lambda: {},
            config_saver=lambda d: None,
            capture_excluder=lambda hwnd, exc=True: None,
        )

        # Check tray actions exist
        assert gc.tray_icon is not None
        assert gc._tray_toggle_action is not None
        assert "Bắt đầu" in gc._tray_toggle_action.text()
        assert "Ctrl+Alt+F8" in gc._tray_toggle_action.text()
        assert "Ctrl+Alt+F9" in gc._tray_region_action.text()

        # Trigger tray toggle when stopped -> start_ocr
        gc._tray_toggle_action.trigger()
        assert controller.start_ocr_calls == 1

        # Switch to running
        worker.set_running(True)
        gc.sync_state()
        assert "Dừng" in gc._tray_toggle_action.text()

        # Trigger tray toggle when running -> stop_ocr
        gc._tray_toggle_action.trigger()
        assert controller.stop_ocr_calls == 1

        gc.shutdown()

    def test_tray_clicks_restore_without_activating_and_open_restores_minimized(self, qtbot):
        from ui.game_controls import GameControls

        controller = MockController()
        controller._minimized = True
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.hide()

        gc = GameControls(
            controller=controller,
            toolbar=tb,
            tray_available=True,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            config_loader=lambda: {},
            config_saver=lambda d: None,
            capture_excluder=lambda hwnd, exc=True: None,
        )

        # Single click (Trigger) restores toolbar WITHOUT activateWindow
        gc._on_tray_activated(QSystemTrayIcon.Trigger)
        assert tb.isVisible() is True

        # Double click opens main app and restores minimized state
        gc._on_tray_activated(QSystemTrayIcon.DoubleClick)
        assert controller.show_normal_called is True
        assert controller.shown is True
        assert controller.activated is True

        gc.shutdown()

    def test_hotkey_routing_and_error_logging(self, qtbot):
        from ui.game_controls import GameControls

        worker = MockWorker(running=False)
        controller = MockController(worker=worker)
        fake_api = FakeNativeApi()
        hotkeys = GlobalHotkeys(native_api=fake_api, platform="win32")
        region_called = []

        gc = GameControls(
            controller=controller,
            worker=worker,
            hotkeys=hotkeys,
            on_select_region=lambda: region_called.append(True),
            config_loader=lambda: {},
            config_saver=lambda d: None,
            capture_excluder=lambda hwnd, exc=True: None,
        )

        # Hotkeys trigger actions
        hotkeys.toggle_requested.emit()
        assert controller.start_ocr_calls == 1

        hotkeys.region_requested.emit()
        assert len(region_called) == 1

        # Hotkey error is logged to controller console
        hotkeys.error_occurred.emit("Lỗi phím tắt trùng")
        assert any("Lỗi phím tắt trùng" in log for log in controller.console_page.logs)

        gc.shutdown()


class TestLifecycleAndStateSync:
    """Worker failures, restart intent, queued sync, and animation consistency."""

    def test_failed_start_remains_expanded_and_reveals_error_view(self, qtbot):
        from ui.game_controls import GameControls

        worker = MockWorker(running=False)
        controller = MockController(worker=worker)
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()

        gc = GameControls(
            controller=controller,
            worker=worker,
            toolbar=tb,
            tray_available=True,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            config_loader=lambda: {},
            config_saver=lambda d: None,
            capture_excluder=lambda hwnd, exc=True: None,
        )

        # Trigger toggle to start, but worker does not transition to running
        gc.toggle_translation()
        assert controller.start_ocr_calls == 1
        # Toolbar should remain expanded
        assert tb._running is False
        assert not tb._ring_timer.isActive()
        # Main app is shown/activated to make error view discoverable
        assert controller.shown is True
        assert controller.activated is True

        gc.shutdown()

    def test_internal_restart_and_fatal_finish(self, qtbot):
        from ui.game_controls import GameControls

        worker = MockWorker(running=True, restart_pending=False)
        controller = MockController(worker=worker)
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()

        gc = GameControls(
            controller=controller,
            worker=worker,
            toolbar=tb,
            tray_available=True,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            config_loader=lambda: {},
            config_saver=lambda d: None,
            capture_excluder=lambda hwnd, exc=True: None,
        )
        gc.sync_state()
        assert tb._running is True
        assert tb._ring_timer.isActive()

        # 1. Internal restart: worker emits finished while restart_pending is True
        worker.set_running(False)
        worker.restart_pending = True
        worker.finished.emit()
        QApplication.processEvents()

        # Must NOT collapse or show stopped; remains running
        assert tb._running is True
        assert tb._ring_timer.isActive()

        # 2. Fatal finish: worker stopped and restart_pending is False
        worker.restart_pending = False
        worker.finished.emit()
        QApplication.processEvents()

        # Must expand to stopped state, ring stops
        assert tb._running is False
        assert not tb._ring_timer.isActive()

        gc.shutdown()

    def test_synchronous_revision_changed_queued_sync(self, qtbot):
        """Worker emits revision_changed synchronously before setting restart_pending=True."""
        from ui.game_controls import GameControls

        worker = MockWorker(running=True, restart_pending=False)
        controller = MockController(worker=worker)
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()

        gc = GameControls(
            controller=controller,
            worker=worker,
            toolbar=tb,
            tray_available=True,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            config_loader=lambda: {},
            config_saver=lambda d: None,
            capture_excluder=lambda hwnd, exc=True: None,
        )
        gc.sync_state()
        assert tb._running is True

        # Simulate configure(): stops worker, emits revision_changed synchronously,
        # then sets restart_pending = True
        worker.set_running(False)
        worker.revision_changed.emit(2)
        worker.restart_pending = True

        # Process the queued singleShot event
        QApplication.processEvents()

        # Because sync was queued to next turn, it observed restart_pending=True
        assert tb._running is True
        assert tb._ring_timer.isActive()

        gc.shutdown()

    def test_unchanged_running_state_does_not_reset_animation(self, qtbot):
        from ui.game_controls import GameControls

        worker = MockWorker(running=True)
        controller = MockController(worker=worker)
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()

        gc = GameControls(
            controller=controller,
            worker=worker,
            toolbar=tb,
            tray_available=True,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            config_loader=lambda: {},
            config_saver=lambda d: None,
            capture_excluder=lambda hwnd, exc=True: None,
        )
        gc.sync_state()
        assert tb._running is True

        # Advance ring angle
        tb._advance_ring()
        angle_before = tb._ring_angle
        assert angle_before > 0.0

        # Sync state again while still running
        gc.sync_state()
        gc.sync_state()

        # Ring angle should NOT have been reset to 0.0
        assert tb._ring_angle == angle_before

        gc.shutdown()


class TestTrayAbsenceAndCaptureFallback:
    """Coordinator handles tray absence, automatic capture fallback, and save failure."""

    def test_tray_absence_does_not_crash_or_strand_user(self, qtbot):
        from ui.game_controls import GameControls

        controller = MockController()
        tb = GameToolbar()
        qtbot.addWidget(tb)

        gc = GameControls(
            controller=controller,
            toolbar=tb,
            tray_icon=None,
            tray_available=False,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            config_loader=lambda: {},
            config_saver=lambda d: None,
            capture_excluder=lambda hwnd, exc=True: None,
        )

        assert gc.tray_icon is None
        assert tb is not None
        assert any("khay hệ thống không khả dụng" in log.lower() for log in controller.console_page.logs)

        gc.shutdown()

    def test_automatic_capture_exclusion_fallback(self, qtbot):
        """If exclusion fails, hide toolbar during active capture session, restore when stopped."""
        from ui.game_controls import GameControls

        worker = MockWorker(running=False)
        controller = MockController(worker=worker)
        tb = GameToolbar()
        qtbot.addWidget(tb)
        tb.show()

        # Excluder fails with EngineError.user_message
        def failing_excluder(hwnd, exc=True):
            return EngineError("capture_exclusion", "Display affinity rejected by system", False)

        gc = GameControls(
            controller=controller,
            worker=worker,
            toolbar=tb,
            tray_available=True,
            capture_excluder=failing_excluder,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            config_loader=lambda: {},
            config_saver=lambda d: None,
        )

        assert gc.is_capture_excluded is False
        # Uses user_message from EngineError
        assert any("Display affinity rejected by system" in log for log in controller.console_page.logs)

        # Toolbar is visible while stopped
        assert tb.isVisible() is True

        # Start active capture session
        worker.set_running(True)
        gc.sync_state()

        # Automatically hidden during active capture session
        assert tb.isVisible() is False

        # Tray single click during active capture under exclusion failure does NOT reveal toolbar
        gc._on_tray_activated(QSystemTrayIcon.Trigger)
        assert tb.isVisible() is False
        assert any("tạm ẩn để tránh tự chụp" in log for log in controller.console_page.logs)

        # Session stops: toolbar is restored
        worker.set_running(False)
        gc.sync_state()
        assert tb.isVisible() is True

        gc.shutdown()

    def test_win_id_change_reapplies_exclusion(self, qtbot):
        from ui.game_controls import GameControls

        calls = []

        def tracking_excluder(hwnd, exc=True):
            calls.append(hwnd)
            return None

        controller = MockController()
        tb = GameToolbar()
        qtbot.addWidget(tb)

        gc = GameControls(
            controller=controller,
            toolbar=tb,
            capture_excluder=tracking_excluder,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            config_loader=lambda: {},
            config_saver=lambda d: None,
        )
        initial_count = len(calls)
        assert initial_count >= 1

        # Simulate QEvent.WinIdChange on toolbar
        event = QEvent(QEvent.WinIdChange)
        QApplication.sendEvent(tb, event)

        # Reapplied capture exclusion
        assert len(calls) == initial_count + 1

        gc.shutdown()

    def test_save_position_failure_logs_error_without_crash(self, qtbot):
        from ui.game_controls import GameControls

        controller = MockController()
        tb = GameToolbar()
        qtbot.addWidget(tb)

        def failing_saver(data):
            raise ConfigError("Disk is full")

        gc = GameControls(
            controller=controller,
            toolbar=tb,
            config_saver=failing_saver,
            config_loader=lambda: {},
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            capture_excluder=lambda hwnd, exc=True: None,
        )

        tb.position_released.emit(300, 400)
        assert any("Disk is full" in log or "không thể lưu" in log.lower() for log in controller.console_page.logs)

        gc.shutdown()


class TestSelectionAndDirectShutdown:
    """Selection busy/blocking state and direct shutdown guarding."""

    def test_selection_sets_busy_and_blocks_toggle(self, qtbot):
        from ui.game_controls import GameControls

        worker = MockWorker(running=False)
        controller = MockController(worker=worker)
        tb = GameToolbar()
        qtbot.addWidget(tb)

        gc = GameControls(
            controller=controller,
            worker=worker,
            toolbar=tb,
            config_loader=lambda: {},
            config_saver=lambda d: None,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            capture_excluder=lambda hwnd, exc=True: None,
        )

        assert gc.is_selecting is False

        # Request region selection
        gc.request_region_selection()
        assert gc.is_selecting is True
        assert tb._busy is True

        # Toggle while selecting must be ignored
        gc.toggle_translation()
        assert controller.start_ocr_calls == 0

        # Duplicate selection ignored
        gc.request_region_selection()
        assert gc.is_selecting is True

        # Finish selection clears busy and allows toggle
        gc.finish_region_selection()
        assert gc.is_selecting is False
        assert tb._busy is False

        gc.toggle_translation()
        assert controller.start_ocr_calls == 1

        gc.shutdown()

    def test_direct_shutdown_rejects_queued_and_subsequent_actions(self, qtbot):
        from ui.game_controls import GameControls

        worker = MockWorker(running=False)
        controller = MockController(worker=worker)
        tb = GameToolbar()
        qtbot.addWidget(tb)

        region_called = []
        gc = GameControls(
            controller=controller,
            worker=worker,
            toolbar=tb,
            on_select_region=lambda: region_called.append(True),
            config_loader=lambda: {},
            config_saver=lambda d: None,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            capture_excluder=lambda hwnd, exc=True: None,
        )

        # Direct shutdown
        gc.shutdown()
        assert gc._is_shutdown is True
        assert gc._is_quitting is True

        # Any queued or subsequent calls are completely rejected
        gc.toggle_translation()
        assert controller.start_ocr_calls == 0

        gc.request_region_selection()
        assert len(region_called) == 0

        gc.open_main_app()
        assert controller.shown is False

        gc.sync_state()
        assert tb.isVisible() is False

    def test_localized_tooltips_with_shortcuts(self, qtbot):
        from ui.game_controls import GameControls

        controller = MockController()
        tb = GameToolbar()
        qtbot.addWidget(tb)

        gc = GameControls(
            controller=controller,
            toolbar=tb,
            config_loader=lambda: {},
            config_saver=lambda d: None,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            capture_excluder=lambda hwnd, exc=True: None,
        )

        buttons = tb._buttons
        assert "Ctrl+Alt+F8" in buttons[0].toolTip()
        assert "Bắt đầu" in buttons[0].toolTip()
        assert "Ctrl+Alt+F9" in buttons[1].toolTip()
        assert "Chọn vùng" in buttons[1].toolTip()
        assert "Mở ứng dụng" in buttons[2].toolTip()
        assert "Thoát" in buttons[3].toolTip()

        gc.shutdown()


class TestScreenPositionRecovery:
    """Screen recovery and position persistence."""

    def test_saved_accessible_position_applied(self, qtbot):
        from ui.game_controls import GameControls

        controller = MockController()
        tb = GameToolbar()
        qtbot.addWidget(tb)

        gc = GameControls(
            controller=controller,
            toolbar=tb,
            config_loader=lambda: {"game_toolbar_pos": {"x": 150, "y": 150}},
            config_saver=lambda d: None,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            capture_excluder=lambda hwnd, exc=True: None,
        )

        assert tb.pos().x() == 150
        assert tb.pos().y() == 150

        gc.shutdown()

    def test_inaccessible_position_recovered_to_primary(self, qtbot):
        from ui.game_controls import GameControls

        controller = MockController()
        tb = GameToolbar()
        qtbot.addWidget(tb)

        gc = GameControls(
            controller=controller,
            toolbar=tb,
            config_loader=lambda: {"game_toolbar_pos": {"x": 99999, "y": 99999}},
            config_saver=lambda d: None,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            capture_excluder=lambda hwnd, exc=True: None,
        )

        assert tb.pos().x() < 90000
        assert tb.pos().y() < 90000

        gc.shutdown()


class TestToolbarWindowVisibilityRules:
    """Visibility rules connecting main application window state with the game toolbar."""

    def test_app_visible_not_minimized_hides_toolbar(self, qtbot):
        from PyQt5.QtWidgets import QWidget
        from ui.game_controls import GameControls

        controller_widget = QWidget()
        qtbot.addWidget(controller_widget)
        controller_widget.show()

        tb = GameToolbar()
        qtbot.addWidget(tb)

        gc = GameControls(
            controller=controller_widget,
            toolbar=tb,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            capture_excluder=lambda hwnd, exc=True: None,
        )

        assert not tb.isVisible()
        gc.shutdown()

    def test_app_minimized_or_hidden_shows_toolbar(self, qtbot):
        from PyQt5.QtWidgets import QWidget
        from ui.game_controls import GameControls

        controller_widget = QWidget()
        qtbot.addWidget(controller_widget)
        controller_widget.show()

        tb = GameToolbar()
        qtbot.addWidget(tb)

        gc = GameControls(
            controller=controller_widget,
            toolbar=tb,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            capture_excluder=lambda hwnd, exc=True: None,
        )

        assert not tb.isVisible()

        # Hide to tray
        controller_widget.hide()
        assert tb.isVisible()

        # Show again
        controller_widget.show()
        assert not tb.isVisible()

        # Minimize
        controller_widget.showMinimized()
        assert tb.isVisible()

        # Restore
        controller_widget.showNormal()
        assert not tb.isVisible()

        gc.shutdown()

    def test_visibility_change_does_not_trigger_start_stop_worker(self, qtbot):
        from PyQt5.QtWidgets import QWidget
        from ui.game_controls import GameControls

        worker = MockWorker(running=False)
        controller_widget = QWidget()
        qtbot.addWidget(controller_widget)
        controller_widget.show()

        tb = GameToolbar()
        qtbot.addWidget(tb)

        gc = GameControls(
            controller=controller_widget,
            worker=worker,
            toolbar=tb,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            capture_excluder=lambda hwnd, exc=True: None,
        )

        # Minimize, restore, hide multiple times
        controller_widget.showMinimized()
        controller_widget.showNormal()
        controller_widget.hide()
        controller_widget.show()

        assert not worker.is_running()
        gc.shutdown()

    def test_worker_stop_or_error_when_app_open_does_not_resurrect_toolbar(self, qtbot):
        from PyQt5.QtWidgets import QWidget
        from ui.game_controls import GameControls

        worker = MockWorker(running=True)
        controller_widget = QWidget()
        qtbot.addWidget(controller_widget)
        controller_widget.show()

        tb = GameToolbar()
        qtbot.addWidget(tb)

        gc = GameControls(
            controller=controller_widget,
            worker=worker,
            toolbar=tb,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            capture_excluder=lambda hwnd, exc=True: None,
        )

        assert not tb.isVisible()

        # Worker stops or encounters error
        worker.set_running(False)
        gc.sync_state()

        # Toolbar must remain hidden because app is open
        assert not tb.isVisible()
        gc.shutdown()

    def test_region_selection_finish_or_cancel_obeys_restored_controller_state(self, qtbot):
        from PyQt5.QtWidgets import QWidget
        from ui.game_controls import GameControls

        controller_widget = QWidget()
        qtbot.addWidget(controller_widget)
        controller_widget.show()

        tb = GameToolbar()
        qtbot.addWidget(tb)

        gc = GameControls(
            controller=controller_widget,
            toolbar=tb,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            capture_excluder=lambda hwnd, exc=True: None,
        )

        # Start selection
        gc.set_selection_active(True)
        assert not tb.isVisible()

        # Finish selection while controller is visible
        gc.set_selection_active(False)
        assert not tb.isVisible()

        # If controller was hidden/tray when selection finished
        controller_widget.hide()
        gc.set_selection_active(True)
        gc.set_selection_active(False)
        assert tb.isVisible()

        gc.shutdown()

    def test_tray_single_click_does_not_show_toolbar_over_open_app(self, qtbot):
        from PyQt5.QtWidgets import QWidget
        from ui.game_controls import GameControls

        controller_widget = QWidget()
        qtbot.addWidget(controller_widget)
        controller_widget.show()

        tb = GameToolbar()
        qtbot.addWidget(tb)

        gc = GameControls(
            controller=controller_widget,
            toolbar=tb,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            capture_excluder=lambda hwnd, exc=True: None,
            tray_available=True,
        )

        assert not tb.isVisible()

        # Tray single click
        gc._on_tray_activated(QSystemTrayIcon.Trigger)
        assert not tb.isVisible()

        # But if controller is hidden, tray single click reveals toolbar
        controller_widget.hide()
        gc._on_tray_activated(QSystemTrayIcon.Trigger)
        assert tb.isVisible()

        gc.shutdown()

    def test_capture_exclusion_failure_keeps_toolbar_hidden_when_running_even_if_minimized(self, qtbot):
        from PyQt5.QtWidgets import QWidget
        from ui.game_controls import GameControls

        worker = MockWorker(running=True)
        controller_widget = QWidget()
        qtbot.addWidget(controller_widget)
        controller_widget.hide()

        tb = GameToolbar()
        qtbot.addWidget(tb)

        # capture_excluder fails
        gc = GameControls(
            controller=controller_widget,
            worker=worker,
            toolbar=tb,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            capture_excluder=lambda hwnd, exc=True: EngineError("capture", "failed"),
            tray_available=True,
        )

        # Even though controller is hidden, capture exclusion failed and worker is running -> toolbar MUST be hidden
        assert not tb.isVisible()

        # Tray single click also cannot reveal it
        gc._on_tray_activated(QSystemTrayIcon.Trigger)
        assert not tb.isVisible()

        # Worker stops -> toolbar can now be shown
        worker.set_running(False)
        gc.sync_state()
        assert tb.isVisible()

        gc.shutdown()

    def test_shutdown_detaches_event_filter_and_prevents_resurrection(self, qtbot):
        from PyQt5.QtWidgets import QWidget
        from ui.game_controls import GameControls

        controller_widget = QWidget()
        qtbot.addWidget(controller_widget)
        controller_widget.show()

        tb = GameToolbar()
        qtbot.addWidget(tb)

        gc = GameControls(
            controller=controller_widget,
            toolbar=tb,
            hotkeys=GlobalHotkeys(native_api=FakeNativeApi(), platform="win32"),
            capture_excluder=lambda hwnd, exc=True: None,
        )

        gc.shutdown()
        assert not tb.isVisible()

        # Subsequent controller hide/minimize should not resurrect toolbar
        controller_widget.hide()
        controller_widget.showMinimized()
        assert not tb.isVisible()
