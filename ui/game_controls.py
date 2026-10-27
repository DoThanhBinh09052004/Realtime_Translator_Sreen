"""GameControls coordinator for floating toolbar, system tray, and global hotkeys.

Owns the GameToolbar, QSystemTrayIcon, and GlobalHotkeys instances.
Routes actions to the existing translation controller and region-selection
lifecycle. TranslationWorker remains authoritative for running and restart states.
"""
from __future__ import annotations

from typing import Any, Callable

from PyQt5.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QAction, QMenu, QSystemTrayIcon

from core.config import ConfigError, load_config, save_config_values
from core.contracts import EngineError
from ui.capture_exclusion import set_capture_excluded
from ui.game_toolbar import GameToolbar
from ui.global_hotkeys import GlobalHotkeys
from ui.icons import get_lucide_icon
from ui.styles import CYBER_PALETTE

_TRAY_TOOLTIP = "Translate HUD - Điều khiển game"
_TEXT_START = "Bắt đầu (Ctrl+Alt+F8)"
_TEXT_STOP = "Dừng lại (Ctrl+Alt+F8)"
_TEXT_REGION = "Chọn vùng (Ctrl+Alt+F9)"
_TEXT_OPEN = "Mở ứng dụng"
_TEXT_EXIT = "Thoát"


class GameControls(QObject):
    """Central coordinator for floating game controls, tray, and global hotkeys."""

    def __init__(
        self,
        controller: Any,
        worker: Any = None,
        app: QApplication | None = None,
        on_select_region: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        toolbar: GameToolbar | None = None,
        hotkeys: GlobalHotkeys | None = None,
        tray_icon: QSystemTrayIcon | None = None,
        tray_available: bool | None = None,
        config_loader: Callable[[], dict] | None = None,
        config_saver: Callable[[dict], None] | None = None,
        capture_excluder: Callable[[int, bool], Any] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)

        self._controller = controller
        self._worker = worker
        self._app = app or QApplication.instance()
        self._on_select_region = on_select_region
        self._on_quit = on_quit

        self._config_loader = config_loader or load_config
        self._config_saver = config_saver or save_config_values
        self._capture_excluder = capture_excluder or set_capture_excluded

        self._is_selecting = False
        self._is_quitting = False
        self._is_shutdown = False
        self._last_running_state: bool | None = None

        # Capture exclusion state
        self._capture_excluded = False

        # 1. Setup Toolbar
        self.toolbar: GameToolbar = toolbar if toolbar is not None else GameToolbar()
        self.toolbar.installEventFilter(self)
        self._init_toolbar()

        # 2. Setup Hotkeys
        self.hotkeys: GlobalHotkeys = hotkeys if hotkeys is not None else GlobalHotkeys()
        self._init_hotkeys()

        # 3. Setup Tray
        self.tray_icon: QSystemTrayIcon | None = tray_icon
        self._tray_menu: QMenu | None = None
        self._tray_toggle_action: QAction | None = None
        self._tray_region_action: QAction | None = None
        self._tray_open_action: QAction | None = None
        self._tray_quit_action: QAction | None = None
        self._init_tray(tray_available)

        # 4. Subscribe to worker signals and controller hooks
        self._bind_worker()
        self._bind_controller()

        # 5. Position & Capture Exclusion
        self._restore_position()
        self.apply_capture_exclusion()

        # 6. Initial state sync & localized tooltips
        self._localize_toolbar(False)
        self.sync_state()

    # -- Event filter (WinIdChange monitoring) ------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.toolbar and event.type() == QEvent.WinIdChange:
            self.apply_capture_exclusion()
        return super().eventFilter(watched, event)

    # -- Toolbar initialization & localization -----------------------------

    def _init_toolbar(self) -> None:
        self.toolbar.toggle_requested.connect(self.toggle_translation)
        self.toolbar.region_requested.connect(self.request_region_selection)
        self.toolbar.open_requested.connect(self.open_main_app)
        self.toolbar.quit_requested.connect(self.request_quit)
        self.toolbar.position_released.connect(self.on_toolbar_position_released)

    def _localize_toolbar(self, is_running: bool) -> None:
        """Set Vietnamese action tooltips and accessible names with shortcuts."""
        buttons = getattr(self.toolbar, "_buttons", None)
        if not isinstance(buttons, (list, tuple)) or len(buttons) < 4:
            return
        b0 = buttons[0]
        if is_running:
            b0.setToolTip("Dừng dịch (Ctrl+Alt+F8)")
            b0.setAccessibleName("Dừng dịch")
        else:
            b0.setToolTip("Bắt đầu dịch (Ctrl+Alt+F8)")
            b0.setAccessibleName("Bắt đầu dịch")

        buttons[1].setToolTip("Chọn vùng (Ctrl+Alt+F9)")
        buttons[1].setAccessibleName("Chọn vùng")

        buttons[2].setToolTip("Mở ứng dụng")
        buttons[2].setAccessibleName("Mở ứng dụng")

        buttons[3].setToolTip("Thoát")
        buttons[3].setAccessibleName("Thoát")

    # -- Hotkeys initialization --------------------------------------------

    def _init_hotkeys(self) -> None:
        self.hotkeys.toggle_requested.connect(self.toggle_translation)
        self.hotkeys.region_requested.connect(self.request_region_selection)
        self.hotkeys.error_occurred.connect(self._log_error)
        self.hotkeys.start()

    # -- System Tray initialization -----------------------------------------

    def _init_tray(self, tray_available: bool | None) -> None:
        if tray_available is not None:
            is_avail = tray_available
        elif self.tray_icon is not None:
            is_avail = True
        else:
            is_avail = QSystemTrayIcon.isSystemTrayAvailable()

        if not is_avail:
            self.tray_icon = None
            self._log_error("Khay hệ thống không khả dụng trên môi trường này.")
            return

        if self.tray_icon is None:
            tray_icon = get_lucide_icon(
                "languages", color=CYBER_PALETTE.get("neon_indigo", "#6366f1"), size=22
            )
            self.tray_icon = QSystemTrayIcon(tray_icon, self)

        self.tray_icon.setToolTip(_TRAY_TOOLTIP)

        # Context menu
        menu = QMenu()
        self._tray_toggle_action = menu.addAction(_TEXT_START)
        self._tray_toggle_action.triggered.connect(self.toggle_translation)

        self._tray_region_action = menu.addAction(_TEXT_REGION)
        self._tray_region_action.triggered.connect(self.request_region_selection)

        menu.addSeparator()

        self._tray_open_action = menu.addAction(_TEXT_OPEN)
        self._tray_open_action.triggered.connect(self.open_main_app)

        self._tray_quit_action = menu.addAction(_TEXT_EXIT)
        self._tray_quit_action.triggered.connect(self.request_quit)

        self._tray_menu = menu
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if self._is_shutdown or self._is_quitting:
            return

        if reason == QSystemTrayIcon.Trigger:
            # Single click restores/shows toolbar without activating it
            if not self._capture_excluded and self._last_running_state:
                # Do not reveal an unexcluded rotating toolbar during capture
                self._log_error(
                    "Thanh điều khiển đang tạm ẩn để tránh tự chụp màn hình trong phiên dịch."
                )
                return

            if not self.toolbar.isVisible():
                self.toolbar.show()
            self.toolbar.raise_()
        elif reason == QSystemTrayIcon.DoubleClick:
            # Double click opens main application
            self.open_main_app()

    def _update_tray_state(self, is_running: bool) -> None:
        if self._tray_toggle_action is not None:
            self._tray_toggle_action.setText(_TEXT_STOP if is_running else _TEXT_START)

    # -- Worker Binding & State Synchronization ----------------------------

    def _bind_worker(self) -> None:
        worker = self._worker or getattr(self._controller, "worker", None)
        if worker is not None:
            if hasattr(worker, "finished"):
                try:
                    worker.finished.disconnect(self._queue_state_sync)
                except (TypeError, RuntimeError):
                    pass
                worker.finished.connect(self._queue_state_sync)
            if hasattr(worker, "revision_changed"):
                try:
                    worker.revision_changed.disconnect(self._queue_state_sync)
                except (TypeError, RuntimeError):
                    pass
                worker.revision_changed.connect(self._queue_state_sync)

    def _bind_controller(self) -> None:
        if self._controller is not None and hasattr(self._controller, "starting_translation"):
            try:
                self._controller.starting_translation.disconnect(self._on_pre_start)
            except (TypeError, RuntimeError):
                pass
            self._controller.starting_translation.connect(self._on_pre_start)

    def _on_pre_start(self) -> None:
        """Emitted before worker.start_worker launches capture.

        Hides unexcluded toolbar immediately to prevent self-capture.
        """
        if self._is_shutdown or self._is_quitting:
            return
        if not self._capture_excluded:
            self.toolbar.hide()

    def _queue_state_sync(self, *args: Any) -> None:
        """Queue state sync to next GUI event-loop turn to observe pending restart."""
        if self._is_shutdown or self._is_quitting:
            return
        QTimer.singleShot(0, self.sync_state)

    def set_worker(self, worker: Any) -> None:
        """Update worker reference and reconnect state signals."""
        self._worker = worker
        self._bind_worker()
        self.sync_state()

    def sync_state(self) -> None:
        """Synchronize UI with worker state without resetting running animations."""
        if self._is_shutdown or self._is_quitting:
            return

        worker = self._worker or getattr(self._controller, "worker", None)
        is_running = False
        if worker is not None:
            # Authoritative worker running or pending restart state
            is_running = bool(worker.is_running() or getattr(worker, "restart_pending", False))

        if is_running != self._last_running_state:
            self._last_running_state = is_running
            self.toolbar.set_running(is_running)
            self._localize_toolbar(is_running)
            self._update_tray_state(is_running)

            # Automatic capture exclusion fallback:
            # Hide floating toolbar during active capture if unexcluded; restore when stopped.
            if not self._capture_excluded:
                if is_running:
                    self.toolbar.hide()
                elif not self._is_quitting and not self._is_shutdown and not self._is_selecting:
                    self.toolbar.show()

    # -- Action Dispatchers -------------------------------------------------

    @property
    def is_selecting(self) -> bool:
        return self._is_selecting

    def set_selection_active(self, active: bool) -> None:
        """Update selection active state, toolbar visibility and busy status. Idempotent."""
        if self._is_shutdown or self._is_quitting:
            self._is_selecting = False
            return

        if self._is_selecting == active:
            return

        self._is_selecting = active
        if self.toolbar is not None:
            if active:
                self.toolbar.hide()
                self.toolbar.set_busy(True)
            else:
                self.toolbar.set_busy(False)
                # If unexcluded and actively running, stay hidden; otherwise show
                if self._capture_excluded or not self._last_running_state:
                    self.toolbar.show()

    def toggle_translation(self) -> None:
        """Toggle translation on/off through canonical controller methods."""
        if self._is_quitting or self._is_shutdown or self._is_selecting:
            return

        worker = self._worker or getattr(self._controller, "worker", None)
        running = bool(worker.is_running() or getattr(worker, "restart_pending", False)) if worker else False

        if running:
            if hasattr(self._controller, "stop_ocr") and callable(self._controller.stop_ocr):
                self._controller.stop_ocr()
            self.sync_state()
        else:
            if hasattr(self._controller, "start_ocr") and callable(self._controller.start_ocr):
                self._controller.start_ocr()
            self.sync_state()

            # If start failed to establish running or restart intent, reveal configuration/error view
            worker_after = self._worker or getattr(self._controller, "worker", None)
            now_running = (
                bool(worker_after.is_running() or getattr(worker_after, "restart_pending", False))
                if worker_after
                else False
            )
            if not now_running:
                self.open_main_app()

    def request_region_selection(self) -> None:
        """Trigger region selection if not already selecting or quitting."""
        if self._is_quitting or self._is_shutdown or self._is_selecting:
            return

        self.set_selection_active(True)

        if callable(self._on_select_region):
            self._on_select_region()
        elif hasattr(self._controller, "on_select_region_cb") and callable(self._controller.on_select_region_cb):
            self._controller.on_select_region_cb()

    def finish_region_selection(self) -> None:
        """Mark region selection as complete and restore controls."""
        if not self._is_selecting:
            return
        self.set_selection_active(False)

    def cancel_region_selection(self) -> None:
        """Alias for finish_region_selection on cancellation."""
        self.finish_region_selection()

    def open_main_app(self) -> None:
        """Show and activate the main controller window, restoring if minimized."""
        if self._is_quitting or self._is_shutdown:
            return

        # Restore minimized window if needed
        if hasattr(self._controller, "isMinimized") and self._controller.isMinimized():
            if hasattr(self._controller, "showNormal") and callable(self._controller.showNormal):
                self._controller.showNormal()
        elif hasattr(self._controller, "windowState") and hasattr(self._controller, "setWindowState"):
            try:
                state = int(self._controller.windowState())
                if state & Qt.WindowMinimized:
                    self._controller.setWindowState(
                        (state & ~Qt.WindowMinimized) | Qt.WindowActive
                    )
            except Exception:
                pass

        if hasattr(self._controller, "show") and callable(self._controller.show):
            self._controller.show()
        if hasattr(self._controller, "raise_") and callable(self._controller.raise_):
            self._controller.raise_()
        if hasattr(self._controller, "activateWindow") and callable(self._controller.activateWindow):
            self._controller.activateWindow()

    def request_quit(self) -> None:
        """Cleanly shutdown and exit the application."""
        if self._is_quitting or self._is_shutdown:
            return

        self._is_quitting = True
        self._is_selecting = False
        self.shutdown()

        if callable(self._on_quit):
            self._on_quit()
        elif hasattr(self._controller, "close") and callable(self._controller.close):
            self._controller.close()
        elif self._app is not None:
            self._app.quit()

    # -- Capture Exclusion --------------------------------------------------

    @property
    def is_capture_excluded(self) -> bool:
        return self._capture_excluded

    def apply_capture_exclusion(self) -> None:
        """Exclude toolbar from desktop capture or enable hide-fallback on failure."""
        try:
            error = self._capture_excluder(int(self.toolbar.winId()), True)
            if error is None:
                self._capture_excluded = True
            else:
                self._capture_excluded = False
                msg = getattr(error, "user_message", getattr(error, "message", str(error)))
                self._log_error(f"Loại trừ chụp màn hình không thành công: {msg}")
        except Exception as e:
            self._capture_excluded = False
            self._log_error(f"Lỗi thiết lập loại trừ chụp màn hình: {e}")

        # Update visibility if already in an active session
        if not self._capture_excluded and self._last_running_state:
            self.toolbar.hide()

    # -- Position Persistence & Recovery -----------------------------------

    def _restore_position(self) -> None:
        try:
            cfg = self._config_loader()
            pos = cfg.get("game_toolbar_pos")
            if isinstance(pos, dict) and "x" in pos and "y" in pos:
                x = int(pos["x"])
                y = int(pos["y"])
                if self._is_position_accessible(x, y):
                    self.toolbar.move(x, y)
                    return
        except Exception:
            pass

        # Inaccessible or unconfigured: recover to visible primary work area
        default_pos = self._get_default_position()
        self.toolbar.move(default_pos)

    def _is_position_accessible(self, x: int, y: int) -> bool:
        """Check if position intersects any connected screen's available geometry."""
        app = self._app or QApplication.instance()
        if not app:
            return True
        screens = app.screens()
        if not screens:
            return True

        tb_rect = QRect(x, y, max(self.toolbar.width(), 44), max(self.toolbar.height(), 44))
        for screen in screens:
            if screen.availableGeometry().intersects(tb_rect):
                return True
        return False

    def _get_default_position(self) -> QPoint:
        """Near the primary work area's upper-right corner."""
        app = self._app or QApplication.instance()
        tb_w = 180
        if self.toolbar is not None and hasattr(self.toolbar, "width"):
            try:
                w_val = self.toolbar.width()
                if isinstance(w_val, (int, float)):
                    tb_w = max(int(w_val), 180)
            except Exception:
                pass
        if app:
            screen = app.primaryScreen()
            if screen:
                geom = screen.availableGeometry()
                return QPoint(geom.right() - tb_w - 20, geom.top() + 20)
        return QPoint(100, 100)

    def on_toolbar_position_released(self, x: int, y: int) -> None:
        """Atomically persist last released global logical position."""
        if self._is_quitting or self._is_shutdown:
            return
        try:
            self._config_saver({"game_toolbar_pos": {"x": x, "y": y}})
        except (ConfigError, Exception) as e:
            self._log_error(f"Không thể lưu vị trí thanh điều khiển game: {e}")

    # -- Logging & Teardown -------------------------------------------------

    def _log_error(self, message: str) -> None:
        if hasattr(self._controller, "console_page") and hasattr(self._controller.console_page, "append_log"):
            self._controller.console_page.append_log(message)
        elif hasattr(self._controller, "status") and hasattr(self._controller.status, "showMessage"):
            self._controller.status.showMessage(message)

    def shutdown(self) -> None:
        """Teardown toolbar, hotkeys, and tray icon cleanly. Idempotent."""
        if self._is_shutdown:
            return
        self._is_shutdown = True
        self._is_quitting = True
        self._is_selecting = False

        if self.toolbar is not None:
            self.toolbar.removeEventFilter(self)
            self.toolbar.hide()
            self.toolbar.close()

        if self.hotkeys is not None:
            self.hotkeys.close()

        if self.tray_icon is not None:
            self.tray_icon.hide()
            self.tray_icon.setParent(None)
            self.tray_icon = None
