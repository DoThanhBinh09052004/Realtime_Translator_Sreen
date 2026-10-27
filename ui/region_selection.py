"""Lifecycle and integration helper for region selection and application lifecycle.

Provides RegionSelectionLifecycle to manage region selection state,
worker pause/resume intent, selector window lifecycle, and main controller
visibility outside of main.py closures.
"""
from __future__ import annotations

import logging
from typing import Any, Callable
from PyQt5.QtCore import QObject
from ui.selector import RegionSelector

logger = logging.getLogger(__name__)


class RegionSelectionLifecycle(QObject):
    """Manages the region selection workflow, preserving running intent and UI state."""

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
        if self._was_running:
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
