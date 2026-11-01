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
    dashboard_preview_ready = pyqtSignal(object, object)
    dashboard_preview_invalidated = pyqtSignal()
    activity_changed = pyqtSignal()
    dashboard_preview_error = pyqtSignal(object)

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
        self._preview_purpose = None
        self._start_intent = False
        self._window_image_selection = False
        self._screen_fallback_context = None
        self._poll = QTimer(self); self._poll.setInterval(30); self._poll.timeout.connect(self._advance_capture)
        if isinstance(worker, QObject) and hasattr(worker, 'shutdown_finished'):
            worker.shutdown_finished.connect(self._advance_capture)

    @property
    def preview_is_drained(self) -> bool:
        return self.preview_worker is None or not self.preview_worker.isRunning()

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def is_closed(self) -> bool:
        return self._is_closed

    def set_game_controls(self, game_controls: Any) -> None:
        self.game_controls = game_controls

    def start_quick_selection(self) -> None:
        """Use a source-bounded drag selector; keep start_selection for advanced editing."""
        if self._is_closed or self._is_active:
            return
        profile = getattr(self.worker, 'capture_profile', None)
        context = getattr(self.worker, 'capture_context', None)
        if not isinstance(profile, CaptureProfile):
            self.start_selection()
            return
        if context is None or getattr(self.controller, '_capture_bound', True) is False:
            self._log_message('Hãy chọn nguồn đang hiển thị trước khi khoanh vùng đọc.')
            return
        self.cancel_dashboard_preview()
        self._start_capture_selection(quick=profile.source_kind != 'window',
                                      window_image=profile.source_kind == 'window')


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
        self._screen_fallback_context = None

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

        self._preview_purpose = None
        self.activity_changed.emit()

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

    def request_dashboard_preview(self) -> bool:
        if self._is_closed or self._shutdown_requested:
            return False
        if self._is_active or self._preview_purpose is not None:
            return False
        if getattr(self.controller, 'capture_run_requested', False) or (self.worker is not None and self.worker.is_running()):
            return False
        profile = getattr(self.worker, 'capture_profile', None)
        context = getattr(self.worker, 'capture_context', None)
        if profile is None or context is None:
            return False
        if not self.preview_is_drained:
            return False

        self._preview_purpose = 'dashboard'
        self._latest_capture_context = context
        self._session_generation += 1
        self._capture_phase = 'preview'
        self._preview_result = None
        self.activity_changed.emit()

        generation = self._session_generation
        self.preview_worker = self.preview_factory(profile, context)
        self.preview_worker.preview_ready.connect(lambda image, ctx: self._receive_preview(image, ctx, generation))
        self.preview_worker.error_occurred.connect(self._on_dashboard_preview_error)
        self.preview_worker.shutdown_finished.connect(self._advance_capture)
        self.preview_worker.start()
        self._poll.start()
        return True

    def cancel_dashboard_preview(self) -> None:
        if self._preview_purpose == 'dashboard':
            self._start_intent = False
            self._preview_result = None
            if self.preview_worker is not None:
                self.preview_worker.request_stop()
            self._preview_purpose = None
            self._capture_phase = None
            self.dashboard_preview_invalidated.emit()
            self.activity_changed.emit()

    def queue_start_intent(self) -> None:
        if self._preview_purpose == 'dashboard':
            self._start_intent = True
            if self.preview_worker is not None:
                self.preview_worker.request_stop()
            self.activity_changed.emit()

    def _on_dashboard_preview_error(self, error):
        self.dashboard_preview_error.emit(error)

    def _start_capture_selection(self, *, quick=False, window_image=False):
        self._window_image_selection = window_image
        self._is_active = True
        self._preview_purpose = 'editor'
        self._latest_capture_context = self.worker.capture_context
        self._session_generation += 1
        self._was_running = (getattr(self.controller, 'capture_run_requested', False) is True
                             or self.worker.is_running() or self.worker.restart_pending)
        self._was_controller_visible = self.controller.isVisible()
        self._was_overlay_visible = self.overlay.isVisible()
        self.overlay.hide()
        if self.game_controls is not None: self.game_controls.set_selection_active(True)
        self._capture_phase = 'quick_drain' if quick else 'runtime_drain'
        if quick:
            self.controller.hide()
        self.activity_changed.emit()
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
        if self._capture_phase == 'quick_drain' and self._runtime_drained() and preview_drained:
            from ui.direct_region_selector import DirectRegionSelector
            self.preview_worker = None
            self._capture_phase = 'editor'
            self._poll.stop()
            context = self.worker.capture_context
            if context is None or context != self._latest_capture_context:
                self._capture_phase = None
                self._cleanup_selection_and_restore()
                return
            self.current_editor = DirectRegionSelector(self.worker.capture_profile, context)
            generation = self._session_generation
            self.current_editor.profile_selected.connect(lambda profile: self._apply_profile(profile, generation))
            self.current_editor.cancelled.connect(lambda: self._cancel_capture(generation))
            self.current_editor.show()
            self.current_editor.raise_()
            self.current_editor.activateWindow()
            return
        if self._capture_phase == 'runtime_drain' and self._runtime_drained() and preview_drained:
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
            if self._preview_purpose == 'dashboard':
                self._capture_phase = None
                self._preview_purpose = None
                self._poll.stop()
                if self._preview_result is not None:
                    image, context = self._preview_result
                    self._preview_result = None
                    current_context = getattr(self.worker, 'capture_context', None)
                    if (current_context is not None
                            and context.binding_epoch == current_context.binding_epoch
                            and context.geometry.region_px == current_context.geometry.region_px):
                        self.dashboard_preview_ready.emit(image, context)
                self.activity_changed.emit()
                if self._start_intent:
                    self._start_intent = False
                    if hasattr(self.controller, 'daily_coordinator'):
                        if self.controller.daily_coordinator.readiness().ready:
                            self.controller.start_ocr()
                    elif hasattr(self.controller, 'start_ocr'):
                        self.controller.start_ocr()
                return

            if self._preview_result is None and self._window_image_selection:
                self._preview_result = (None, self.worker.capture_context)
            if self._preview_result is None:
                self._capture_phase = None; self._poll.stop(); self._cleanup_selection_and_restore(); return
            image, context = self._preview_result
            self._capture_phase = 'editor'; self._poll.stop()
            if self._window_image_selection:
                from ui.window_region_picker import WindowRegionPicker
                self.current_editor = WindowRegionPicker(self.worker.capture_profile, image, context)
                self.current_editor.screen_fallback_requested.connect(self._start_screen_fallback)
            else:
                self.current_editor = self.editor_factory(self.worker.capture_profile, image, context)
            self._apply_editor_theme(self.current_editor)
            if self._latest_capture_context is not None:
                self.current_editor.update_context(self._latest_capture_context)
            generation = self._session_generation
            self.current_editor.profile_selected.connect(lambda profile: self._apply_profile(profile, generation))
            self.current_editor.cancelled.connect(lambda: self._cancel_capture(generation))
            self.current_editor.refresh_requested.connect(self._refresh_preview)
            self.current_editor.show()

    def _apply_editor_theme(self, editor):
        from PyQt5.QtWidgets import QWidget
        if not isinstance(editor, QWidget) or not hasattr(editor, 'apply_theme'):
            return
        editor.apply_theme(getattr(self.controller, 'ui_theme', 'light'))
        signal = getattr(getattr(self.controller, 'settings_coordinator', None), 'ui_theme_changed', None)
        if signal is not None:
            signal.connect(editor.apply_theme)

    def _receive_preview(self, image, context, generation):
        if not self._is_closed and generation == self._session_generation:
            self._preview_result = image, context

    def _start_screen_fallback(self):
        """Draft a desktop selection; do not mutate the active source on cancel."""
        if self._is_closed or not self._is_active or not self._runtime_drained() or not self.preview_is_drained:
            return
        from core.capture.models import CaptureContext
        from core.capture.profile import migrate_legacy_region
        from core.blocks.models import CaptureGeometry
        from ui.direct_region_selector import DirectRegionSelector
        old = self.worker.capture_context
        screens = tuple(self.geometry_provider.snapshot())
        screen = next((s for s in screens if s.name == old.geometry.screen.name), None)
        if screen is None:
            self.current_editor.error_label.setText('Màn hình nguồn không còn kết nối. Hủy và chọn lại nguồn.')
            return
        rect = screen.physical_rect
        profile = migrate_legacy_region(dict(left=int(rect.x), top=int(rect.y),
            width=int(rect.width), height=int(rect.height)), screens)
        if profile is None:
            return
        binding = self.controller.daily_coordinator.binding
        epoch = max(old.binding_epoch, getattr(binding, '_epoch', 0)) + 1
        context = CaptureContext(epoch, 1, 'desktop', None, CaptureGeometry(rect, screen, (int(rect.width), int(rect.height))))
        previous, self.current_editor = self.current_editor, None
        previous.accept()
        self.controller.hide()
        editor = DirectRegionSelector(profile, context)
        self._screen_fallback_context = context
        self.current_editor = editor
        generation = self._session_generation
        editor.profile_selected.connect(lambda draft: self._apply_screen_fallback(draft, context, generation))
        editor.cancelled.connect(lambda: self._cancel_capture(generation))
        editor.show()
        editor.raise_()
        editor.activateWindow()

    def _apply_screen_fallback(self, profile, context, generation):
        if self._is_closed or generation != self._session_generation:
            return
        binding = self.controller.daily_coordinator.binding
        if not binding.apply_screen_selection(profile, context):
            self.current_editor.error_label.setText('Chưa lưu được vùng màn hình. Nguồn cũ được giữ; thử lại hoặc Hủy.')
            return
        editor, self.current_editor = self.current_editor, None
        editor.accept()
        self._capture_phase = None
        self._cleanup_selection_and_restore()

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
        old = self._latest_capture_context
        self._latest_capture_context = context
        if self.current_editor is not None and self._screen_fallback_context is None:
            self.current_editor.update_context(context)
        if old is not None and (
            old.binding_epoch != context.binding_epoch
            or getattr(old.geometry, 'region_px', None) != getattr(context.geometry, 'region_px', None)
            or getattr(old.geometry, 'image_size_px', None) != getattr(context.geometry, 'image_size_px', None)
        ):
            self.cancel_dashboard_preview()
            self.dashboard_preview_invalidated.emit()

    @pyqtSlot(object)
    def on_capture_terminal(self, status):
        context = getattr(self.worker, 'capture_context', None)
        if (context is None or status.binding_epoch != context.binding_epoch
                or self._terminal_epoch == status.binding_epoch or self._is_closed): return
        self.cancel_dashboard_preview()
        self.dashboard_preview_invalidated.emit()
        self._terminal_epoch = status.binding_epoch
        if (self.current_editor is not None and self._screen_fallback_context is None
                and hasattr(self.current_editor, 'invalidate_source')):
            self.current_editor.invalidate_source()
        self.worker.stop_worker(preserve_translation_session=True)
        self.overlay.clear()
        if status.error is not None: self._log_message(status.error.user_message)
        if hasattr(self.controller, 'show_capture_waiting'): self.controller.show_capture_waiting(status.error)
        if self.game_controls is not None: self.game_controls.sync_state()

    def request_shutdown(self):
        if self._shutdown_requested: return
        self._shutdown_requested = True
        self._start_intent = False
        if self._preview_purpose == 'dashboard':
            self.cancel_dashboard_preview()
        elif self.preview_worker is not None:
            self.preview_worker.request_stop()
        if hasattr(self.controller, 'capture_run_requested'): self.controller.capture_run_requested = False
        self.close()
        if self.current_editor is not None:
            self.current_editor.accept(); self.current_editor = None
        self.worker.stop_worker()
        self._poll.start(); self._advance_capture()
