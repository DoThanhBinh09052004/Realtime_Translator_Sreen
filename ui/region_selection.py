"""Lifecycle and integration helper for region selection and application lifecycle.

Provides RegionSelectionLifecycle to manage region selection state,
worker pause/resume intent, selector window lifecycle, and main controller
visibility outside of main.py closures.
"""
from __future__ import annotations

import logging
from typing import Any, Callable
from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from core.capture.models import CaptureProfile
from ui.selector import RegionSelector

logger = logging.getLogger(__name__)


class RegionSelectionLifecycle(QObject):
    """Manages the region selection workflow, preserving running intent and UI state."""
    shutdown_finished = pyqtSignal()

    def __init__(
        self,
        controller: Any,
        worker: Any,
        overlay: Any,
        geometry_provider: Any,
        game_controls: Any = None,
        on_sync_geometry: Callable[[], None] | None = None,
        selector_factory: Callable[..., Any] | None = None,
        parent: QObject | None = None,
        preview_factory=None,
        editor_factory=None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.worker = worker
        self.overlay = overlay
        self.geometry_provider = geometry_provider
        self.game_controls = game_controls
        self.on_sync_geometry = on_sync_geometry
        self.selector_factory = selector_factory or RegionSelector

        self.current_selector: Any | None = None
        self._was_running = False
        self._was_controller_visible = False
        self._was_overlay_visible = False
        self._is_active = False
        self._is_closed = False
        self._session_generation = 0
        from ui.capture_preview import CapturePreviewWorker
        from ui.capture_regions_dialog import CaptureRegionsDialog
        self.preview_factory = preview_factory or CapturePreviewWorker
        self.editor_factory = editor_factory or CaptureRegionsDialog
        self.preview_worker = None
        self.current_editor = None
        self._preview_result = None
        self._latest_capture_context = None
        self._capture_phase = None
        self._shutdown_requested = False
        self._shutdown_emitted = False
        self._terminal_epoch = None
        self._drain_started = None
        self._poll = QTimer(self); self._poll.setInterval(30); self._poll.timeout.connect(self._advance_capture)
        if isinstance(worker, QObject) and hasattr(worker, 'shutdown_finished'):
            worker.shutdown_finished.connect(self._advance_capture)

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def is_closed(self) -> bool:
        return self._is_closed

    def set_game_controls(self, game_controls: Any) -> None:
        self.game_controls = game_controls

    def start_selection(self) -> None:
        """Start region selection process.

        Guards against duplicate calls or closed state, preserves running/pending-restart intent,
        preserves controller and overlay visibility, hides UI, and instantiates the selector.
        """
        if self._is_closed or self._is_active:
            return

        if isinstance(getattr(self.worker, 'capture_profile', None), CaptureProfile):
            self._start_capture_selection()
            return

        self._is_active = True
        self._session_generation += 1
        current_gen = self._session_generation

        # Preserve running or pending restart intent
        self._was_running = bool(
            (self.worker is not None and self.worker.is_running())
            or (self.worker is not None and getattr(self.worker, "restart_pending", False))
        )
        if self._was_running and self.worker is not None:
            self.worker.stop_worker(preserve_translation_session=True)

        # Preserve controller visibility
        self._was_controller_visible = bool(
            self.controller is not None
            and hasattr(self.controller, "isVisible")
            and self.controller.isVisible()
        )

        # Preserve overlay visibility
        self._was_overlay_visible = bool(
            self.overlay is not None
            and hasattr(self.overlay, "isVisible")
            and self.overlay.isVisible()
        )

        # Hide UI elements during selection
        if self.controller is not None and hasattr(self.controller, "hide"):
            self.controller.hide()

        if self.overlay is not None and hasattr(self.overlay, "hide"):
            self.overlay.hide()

        # Update GameControls using public set_selection_active
        if self.game_controls is not None and hasattr(self.game_controls, "set_selection_active"):
            self.game_controls.set_selection_active(True)

        # Create and display RegionSelector with error recovery
        try:
            selector = self.selector_factory(geometry_provider=self.geometry_provider)
            self.current_selector = selector

            # Connect callbacks with session generation guard
            selector.region_selected.connect(
                lambda new_region, gen=current_gen: self.on_region_selected(new_region, generation=gen)
            )
            selector.cancelled.connect(
                lambda gen=current_gen: self.on_selection_cancelled(generation=gen)
            )

            selector.show()
            if hasattr(selector, "raise_"):
                selector.raise_()
            if hasattr(selector, "activateWindow"):
                selector.activateWindow()
        except Exception as e:
            # Native creation or display failure: recover cleanly and report
            err_msg = f"Không thể mở màn hình chọn vùng quét: {e}"
            self._log_message(err_msg)
            self.current_selector = None
            self._cleanup_selection_and_restore()

    def on_region_selected(self, new_region: dict, generation: int | None = None) -> None:
        """Handle region selection completion."""
        if self._is_closed or not self._is_active:
            return
        if generation is not None and generation != self._session_generation:
            return

        selector = self.current_selector
        self.current_selector = None

        saved = False
        if self.controller is not None and hasattr(self.controller, "apply_region_selection"):
            saved = bool(self.controller.apply_region_selection(new_region))

        if saved:
            if callable(self.on_sync_geometry):
                self.on_sync_geometry()
            if self.controller is not None and hasattr(self.controller, "refresh_region"):
                self.controller.refresh_region()
        else:
            # Finding 6: Failed save must append clear log that region was retained
            self._log_message("Lưu vùng quét thất bại; đang giữ nguyên vùng quét cũ.")

        self._cleanup_selection_and_restore()

        if selector is not None and hasattr(selector, "close"):
            selector.close()

    def on_selection_cancelled(self, generation: int | None = None) -> None:
        """Handle region selection cancellation (e.g. Escape or click away)."""
        if self._is_closed or not self._is_active:
            return
        if generation is not None and generation != self._session_generation:
            return

        selector = self.current_selector
        self.current_selector = None

        self._cleanup_selection_and_restore()

        if selector is not None and hasattr(selector, "close"):
            selector.close()

    def _cleanup_selection_and_restore(self) -> None:
        """Restore previous UI visibility and resume worker if previously running."""
        self._is_active = False

        # Restore controller only if it was visible before selection
        if self._was_controller_visible and self.controller is not None:
            if hasattr(self.controller, "show"):
                self.controller.show()

        # Finding 5: Restore overlay only if it was visible before selection
        if self._was_overlay_visible and self.overlay is not None:
            if hasattr(self.overlay, "show"):
                self.overlay.show()

        # Restore GameControls selection state via public API
        if self.game_controls is not None and hasattr(self.game_controls, "set_selection_active"):
            self.game_controls.set_selection_active(False)

        # Finding 1: Resume through controller.start_ocr(preserve_translation_session=True)
        # to ensure controller status, starting_translation hook, and worker agree.
        should_resume = self._was_running
        if isinstance(getattr(self.worker, 'capture_profile', None), CaptureProfile):
            should_resume = should_resume and getattr(self.controller, 'capture_run_requested', False) is True
        if should_resume:
            if self.controller is not None and hasattr(self.controller, "start_ocr"):
                self.controller.start_ocr(preserve_translation_session=True)
            elif self.worker is not None and hasattr(self.worker, "start_worker"):
                self.worker.start_worker(preserve_translation_session=True)

            if self.game_controls is not None and hasattr(self.game_controls, "sync_state"):
                self.game_controls.sync_state()

    def _log_message(self, message: str) -> None:
        if hasattr(self.controller, "console_page") and hasattr(self.controller.console_page, "append_log"):
            self.controller.console_page.append_log(message)
        elif hasattr(self.controller, "status") and hasattr(self.controller.status, "showMessage"):
            self.controller.status.showMessage(message)
        else:
            logger.warning(message)

    def close(self) -> None:
        """Close selector and permanently cancel selection during shutdown without resuming worker."""
        self._is_closed = True
        self._is_active = False
        self._was_running = False

        if self.current_selector is not None:
            selector = self.current_selector
            self.current_selector = None
            try:
                selector.region_selected.disconnect()
            except Exception:
                pass
            try:
                selector.cancelled.disconnect()
            except Exception:
                pass
            if hasattr(selector, "close"):
                selector.close()

        if self.game_controls is not None and hasattr(self.game_controls, "set_selection_active"):
            self.game_controls.set_selection_active(False)

    def _runtime_drained(self):
        drained = getattr(self.worker, 'is_drained', None)
        return drained if type(drained) is bool else not self.worker.is_running()

    def _start_capture_selection(self):
        self._is_active = True
        self._latest_capture_context = self.worker.capture_context
        self._session_generation += 1
        self._was_running = (getattr(self.controller, 'capture_run_requested', False) is True
                             or self.worker.is_running() or self.worker.restart_pending)
        self._was_controller_visible = self.controller.isVisible()
        self._was_overlay_visible = self.overlay.isVisible()
        self.overlay.hide()
        if self.game_controls is not None: self.game_controls.set_selection_active(True)
        self._capture_phase = 'runtime_drain'
        self.worker.stop_worker(preserve_translation_session=True)
        self._poll.start(); self._advance_capture()

    @pyqtSlot()
    def _advance_capture(self):
        preview_drained = self.preview_worker is None or not self.preview_worker.isRunning()
        if self._shutdown_requested:
            if self._runtime_drained() and preview_drained and not self._shutdown_emitted:
                self._shutdown_emitted = True; self._poll.stop(); self.shutdown_finished.emit()
            return
        if self._is_closed: return
        if self._capture_phase == 'runtime_drain' and self._runtime_drained():
            self._capture_phase = 'preview'
            self._preview_result = None
            generation = self._session_generation
            self.preview_worker = self.preview_factory(self.worker.capture_profile, self.worker.capture_context)
            self.preview_worker.preview_ready.connect(lambda image, context: self._receive_preview(image, context, generation))
            self.preview_worker.error_occurred.connect(lambda error: self._log_message(error.user_message))
            self.preview_worker.shutdown_finished.connect(self._advance_capture)
            self.preview_worker.start()
            return
        if self._capture_phase == 'preview' and preview_drained:
            self.preview_worker = None
            if self._preview_result is None:
                self._capture_phase = None; self._poll.stop(); self._cleanup_selection_and_restore(); return
            image, context = self._preview_result
            self._capture_phase = 'editor'; self._poll.stop()
            self.current_editor = self.editor_factory(self.worker.capture_profile, image, context)
            if self._latest_capture_context is not None:
                self.current_editor.update_context(self._latest_capture_context)
            generation = self._session_generation
            self.current_editor.profile_selected.connect(lambda profile: self._apply_profile(profile, generation))
            self.current_editor.cancelled.connect(lambda: self._cancel_capture(generation))
            self.current_editor.refresh_requested.connect(self._refresh_preview)
            self.current_editor.show()

    def _receive_preview(self, image, context, generation):
        if not self._is_closed and generation == self._session_generation:
            self._preview_result = image, context

    def _apply_profile(self, profile, generation):
        if self._is_closed or generation != self._session_generation: return
        if not self.controller.settings_coordinator.apply_capture_profile(profile):
            self.current_editor.error_label.setText('Lưu thất bại; giữ nguyên cấu hình. Hãy thử lại hoặc Hủy.')
            return
        editor, self.current_editor = self.current_editor, None
        editor.accept(); self._capture_phase = None
        self._cleanup_selection_and_restore()

    def _cancel_capture(self, generation):
        if self._is_closed or generation != self._session_generation: return
        self.current_editor = None; self._capture_phase = None
        self._cleanup_selection_and_restore()

    def _refresh_preview(self):
        if self.current_editor is not None:
            editor, self.current_editor = self.current_editor, None
            editor.accept()
        self._capture_phase = 'runtime_drain'; self._poll.start(); self._advance_capture()

    def update_capture_context(self, context):
        self._latest_capture_context = context
        if self.current_editor is not None: self.current_editor.update_context(context)

    @pyqtSlot(object)
    def on_capture_terminal(self, status):
        context = getattr(self.worker, 'capture_context', None)
        if (context is None or status.binding_epoch != context.binding_epoch
                or self._terminal_epoch == status.binding_epoch or self._is_closed): return
        self._terminal_epoch = status.binding_epoch
        self.worker.stop_worker(preserve_translation_session=True)
        self.overlay.clear()
        if status.error is not None: self._log_message(status.error.user_message)
        if hasattr(self.controller, 'show_capture_waiting'): self.controller.show_capture_waiting(status.error)
        if self.game_controls is not None: self.game_controls.sync_state()

    def request_shutdown(self):
        if self._shutdown_requested: return
        self._shutdown_requested = True
        if hasattr(self.controller, 'capture_run_requested'): self.controller.capture_run_requested = False
        self.close()
        if self.current_editor is not None:
            self.current_editor.accept(); self.current_editor = None
        if self.preview_worker is not None: self.preview_worker.request_stop()
        self.worker.stop_worker()
        self._poll.start(); self._advance_capture()
