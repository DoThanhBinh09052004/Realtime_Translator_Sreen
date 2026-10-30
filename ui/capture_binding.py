"""GUI owner wiring source selection, geometry, drain and controller run intent."""
from PyQt5.QtCore import QObject, QTimer
from core.capture.models import CaptureContext, SourceStatus
from core.blocks.models import CaptureGeometry
from core.config import ConfigError, save_capture_profile
from ui.window_geometry import WindowGeometryProvider


class CaptureApplicationBinding(QObject):
    def __init__(self, controller, worker, overlay, screens, lifecycle, *, window_provider=None, parent=None):
        super().__init__(parent)
        self.controller, self.worker, self.overlay = controller, worker, overlay
        self.screens, self.lifecycle = screens, lifecycle
        self.windows = window_provider or WindowGeometryProvider(self, screen_provider=screens)
        self.profile = self.identity = None
        self._epoch = 0
        self._pending = None
        self._waiting = False
        self._stopped = False
        self._timer = QTimer(self); self._timer.setInterval(30); self._timer.timeout.connect(self._apply_pending)
        self.windows.context_changed.connect(self._context_changed)
        self.windows.source_unavailable.connect(self._unavailable)
        screens.changed.connect(self._screens_changed)
        controller.ocr_page.capture_settings.source_selected.connect(self.select_source)
        controller.capture_stop_requested.connect(self.stop)
        controller.settings_coordinator.settings_changed.connect(self._settings_changed)
        controller.ensure_capture_ready = self.ensure_ready

    def _settings_changed(self, snapshot, field):
        if field == 'capture_profile':
            self.profile = self.worker.capture_profile
            self.controller.set_capture_profile_state(self.profile, bound=True)

    def initialize(self, profile):
        self.profile = profile
        self.controller.set_capture_profile_state(profile, bound=profile is None or profile.source_kind == 'desktop')
        if profile is not None and profile.source_kind == 'desktop':
            self._bind_desktop()

    def select_source(self, profile, identity):
        if self.lifecycle.is_active is True:
            self.controller.show_capture_waiting()
            return
        try:
            save_capture_profile(profile)
        except ConfigError as error:
            self.controller._show_save_error(str(error)); return
        self.worker.stop_worker(preserve_translation_session=True)
        self.windows.clear_binding()
        self.profile, self.identity = profile, identity
        self._stopped = False
        self._epoch = max(self._epoch, getattr(self.worker.capture_context, 'binding_epoch', 0)) + 1
        self.controller.set_capture_profile_state(profile, bound=profile.source_kind == 'desktop' or identity is not None)
        if profile.source_kind == 'window':
            self.windows.set_binding(profile, identity, self._epoch)
        else:
            self._bind_desktop()

    def _bind_desktop(self):
        matching = [screen for screen in self.screens.snapshot() if screen.name == self.profile.monitor_name]
        if len(matching) != 1:
            self.controller.set_capture_profile_state(self.profile, bound=False)
            self._unavailable(None); return
        screen = matching[0]; rect = screen.physical_rect
        self._epoch += 1
        self._context_changed(CaptureContext(self._epoch, 1, 'desktop', None,
            CaptureGeometry(rect, screen, (int(rect.width), int(rect.height)))))

    def _screens_changed(self):
        if self._stopped or self.profile is None or self.profile.source_kind != 'desktop':
            return
        matching = [screen for screen in self.screens.snapshot() if screen.name == self.profile.monitor_name]
        current = self._pending or self.worker.capture_context
        if len(matching) != 1:
            if not self._waiting:
                self._unavailable(None)
            return
        if (not self._waiting and current is not None and current.source_kind == 'desktop'
                and current.geometry.screen == matching[0]):
            return
        if not self._waiting and current is not None:
            self._unavailable(None)
        self._bind_desktop()

    def _context_changed(self, context):
        if self._stopped: return
        old = self.worker.capture_context
        self.lifecycle.update_capture_context(context)
        if old is not None and old.binding_epoch == context.binding_epoch and old.source_kind == context.source_kind and old.window == context.window:
            self.worker.update_capture_geometry(context)
            return
        self._epoch = max(self._epoch, context.binding_epoch)
        self._pending = context
        if self.worker.is_drained is not True:
            self.worker.stop_worker(preserve_translation_session=True)
        self._timer.start(); self._apply_pending()

    def _apply_pending(self):
        if self._pending is None or self._stopped: self._timer.stop(); return
        if self.worker.is_drained is not True: return
        context, self._pending = self._pending, None
        self._timer.stop()
        self.worker.configure_capture(self.profile, context)
        self.controller.set_capture_profile_state(self.profile, bound=True)
        self._waiting = False
        if self.controller.capture_run_requested is True and self.lifecycle.is_active is not True:
            self.controller.start_ocr(preserve_translation_session=True)

    def _unavailable(self, error):
        self._pending = None
        self._waiting = True
        context = self.worker.capture_context
        if context is not None:
            self.lifecycle.on_capture_terminal(SourceStatus(context.binding_epoch, 'unavailable', error))
        else:
            self.controller.show_capture_waiting(error)

    def ensure_ready(self):
        if self.lifecycle.is_active is True:
            return False
        if self.profile is None: return True
        if self._stopped:
            self._stopped = False
            if self.profile.source_kind == 'window':
                self._epoch += 1
                self.windows.set_binding(self.profile, self.identity, self._epoch)
            else: self._bind_desktop()
        return not self._waiting and self._pending is None

    def stop(self):
        self._stopped = True
        self._pending = None
        self._timer.stop()
        self.windows.clear_binding()
