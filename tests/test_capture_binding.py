from types import SimpleNamespace
from unittest.mock import Mock
from PyQt5.QtCore import QObject, pyqtSignal
from test_capture_app_integration import capture_values


class Provider(QObject):
    context_changed = pyqtSignal(object)
    source_unavailable = pyqtSignal(object)
    def __init__(self): super().__init__(); self.bindings = []
    def set_binding(self, *args): self.bindings.append(args)
    def clear_binding(self): pass


def test_origin_update_and_restore_obey_controller_intent(qtbot, capture_geometry):
    from ui.capture_binding import CaptureApplicationBinding
    from core.capture.models import SourceStatus
    from core.contracts import EngineError
    from dataclasses import replace
    profile, context = capture_values(capture_geometry, 'window')
    provider = Provider(); worker = Mock(); worker.capture_context = context; worker.capture_profile = profile
    worker.is_drained = True
    controller = Mock(); controller.capture_run_requested = True
    controller.ocr_page.capture_settings.source_selected = Mock()
    lifecycle = Mock(); lifecycle.is_active = False
    binding = CaptureApplicationBinding(controller, worker, Mock(), Mock(), lifecycle, window_provider=provider)
    binding.profile = profile; binding.identity = context.window
    binding._context_changed(replace(context, geometry_sequence=2))
    worker.update_capture_geometry.assert_called_once(); controller.start_ocr.assert_not_called()
    controller.capture_run_requested = False
    binding._context_changed(replace(context, binding_epoch=2))
    controller.start_ocr.assert_not_called()
    controller.capture_run_requested = True
    binding._context_changed(replace(context, binding_epoch=3))
    controller.start_ocr.assert_called_once()

class Screens(QObject):
    changed = pyqtSignal()
    def __init__(self, mappings):
        super().__init__(); self.mappings = mappings
    def snapshot(self): return tuple(self.mappings)


def test_desktop_topology_loss_and_restore_respects_intent(qtbot, capture_geometry):
    from ui.capture_binding import CaptureApplicationBinding
    from ui.region_selection import RegionSelectionLifecycle
    profile, _ = capture_values(capture_geometry)
    screen = capture_geometry.screen
    from dataclasses import replace
    profile = replace(profile, monitor_name=screen.name)
    screens = Screens([screen]); worker = Mock(); worker.capture_context = None; worker.is_drained = True
    worker.configure_capture.side_effect = lambda p, c: setattr(worker, 'capture_context', c)
    controller = Mock(); controller.capture_run_requested = True
    controller.ocr_page.capture_settings.source_selected = Mock()
    overlay = Mock(); lifecycle = RegionSelectionLifecycle(controller, worker, overlay, screens)
    binding = CaptureApplicationBinding(controller, worker, overlay, screens, lifecycle, window_provider=Provider())
    binding.initialize(profile)
    initial = worker.capture_context
    controller.start_ocr.reset_mock()
    screens.mappings = []; screens.changed.emit()
    overlay.clear.assert_called_once()
    worker.stop_worker.assert_called()
    assert binding.ensure_ready() is False
    assert controller.capture_run_requested is True
    screens.mappings = [screen]; screens.changed.emit()
    assert worker.capture_context.binding_epoch > initial.binding_epoch
    controller.start_ocr.assert_called_once()
    controller.capture_run_requested = False
    screens.mappings = []; screens.changed.emit()
    screens.mappings = [screen]; screens.changed.emit()
    controller.start_ocr.assert_called_once()


def test_desktop_geometry_change_rebinds_and_clears(qtbot, capture_geometry):
    from ui.capture_binding import CaptureApplicationBinding
    from ui.region_selection import RegionSelectionLifecycle
    from core.blocks.models import Rect
    from dataclasses import replace
    profile, _ = capture_values(capture_geometry)
    screen = capture_geometry.screen
    profile = replace(profile, monitor_name=screen.name)
    screens = Screens([screen]); worker = Mock(); worker.capture_context = None; worker.is_drained = True
    worker.configure_capture.side_effect = lambda p, c: setattr(worker, 'capture_context', c)
    controller = Mock(); controller.capture_run_requested = True
    controller.ocr_page.capture_settings.source_selected = Mock()
    overlay = Mock(); lifecycle = RegionSelectionLifecycle(controller, worker, overlay, screens)
    binding = CaptureApplicationBinding(controller, worker, overlay, screens, lifecycle, window_provider=Provider())
    binding.initialize(profile); initial = worker.capture_context
    screens.mappings = [replace(screen, physical_rect=Rect(20, 30, 1024, 768))]
    screens.changed.emit()
    assert worker.capture_context.binding_epoch > initial.binding_epoch
    assert worker.capture_context.geometry.region_px == screens.mappings[0].physical_rect
    overlay.clear.assert_called_once()
