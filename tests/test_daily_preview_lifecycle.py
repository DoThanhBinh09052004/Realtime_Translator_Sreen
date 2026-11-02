from dataclasses import replace
from unittest.mock import Mock
from PyQt5.QtCore import QObject, pyqtSignal
import pytest

from core.capture.models import CaptureProfile
from test_capture_app_integration import capture_values


class Runtime(QObject):
    shutdown_finished = pyqtSignal()

    def __init__(self, profile, context):
        super().__init__()
        self.capture_profile = profile
        self.capture_context = context
        self.is_drained = True
        self.restart_pending = False
        self.stops = 0

    def is_running(self):
        return False

    def stop_worker(self, **kwargs):
        self.stops += 1


class Preview(QObject):
    preview_ready = pyqtSignal(object, object)
    error_occurred = pyqtSignal(object)
    shutdown_finished = pyqtSignal()

    def __init__(self, *args):
        super().__init__()
        self.running = False
        self.stops = 0

    def start(self):
        self.running = True

    def isRunning(self):
        return self.running

    def request_stop(self):
        self.stops += 1


def test_dashboard_preview_does_not_open_editor_or_start_ocr(qtbot, capture_geometry):
    from ui.region_selection import RegionSelectionLifecycle

    profile, context = capture_values(capture_geometry)
    w = Runtime(profile, context)
    c = Mock()
    c.capture_run_requested = False
    p = Preview()
    editors = []

    lifecycle = RegionSelectionLifecycle(
        c, w, Mock(), Mock(),
        preview_factory=lambda *a: p,
        editor_factory=lambda *a: editors.append(a),
    )

    ready_results = []
    lifecycle.dashboard_preview_ready.connect(lambda img, ctx: ready_results.append((img, ctx)))

    success = lifecycle.request_dashboard_preview()
    assert success is True
    assert p.running is True

    p.preview_ready.emit("fake_image", context)
    p.running = False
    p.shutdown_finished.emit()

    assert not editors
    c.start_ocr.assert_not_called()
    assert len(ready_results) == 1
    assert ready_results[0] == ("fake_image", context)


def test_preview_result_waits_for_owner_drain(qtbot, capture_geometry):
    from ui.region_selection import RegionSelectionLifecycle

    profile, context = capture_values(capture_geometry)
    w = Runtime(profile, context)
    c = Mock()
    c.capture_run_requested = False
    p = Preview()

    lifecycle = RegionSelectionLifecycle(c, w, Mock(), Mock(), preview_factory=lambda *a: p)
    ready_results = []
    lifecycle.dashboard_preview_ready.connect(lambda img, ctx: ready_results.append((img, ctx)))

    lifecycle.request_dashboard_preview()
    p.preview_ready.emit("fake_image", context)
    
    # Still running -> not published yet
    assert len(ready_results) == 0

    # Once drained -> published
    p.running = False
    p.shutdown_finished.emit()
    assert len(ready_results) == 1


def test_old_epoch_preview_is_discarded(qtbot, capture_geometry):
    from ui.region_selection import RegionSelectionLifecycle

    profile, context = capture_values(capture_geometry)
    w = Runtime(profile, context)
    c = Mock()
    c.capture_run_requested = False
    p = Preview()

    lifecycle = RegionSelectionLifecycle(c, w, Mock(), Mock(), preview_factory=lambda *a: p)
    ready_results = []
    lifecycle.dashboard_preview_ready.connect(lambda img, ctx: ready_results.append((img, ctx)))

    lifecycle.request_dashboard_preview()
    
    # Change epoch on worker context before preview delivers
    w.capture_context = replace(context, binding_epoch=context.binding_epoch + 1)

    p.preview_ready.emit("fake_image", context)  # context has old epoch
    p.running = False
    p.shutdown_finished.emit()

    assert len(ready_results) == 0


def test_source_resize_invalidates_snapshot(qtbot, capture_geometry):
    from ui.region_selection import RegionSelectionLifecycle

    profile, context = capture_values(capture_geometry)
    w = Runtime(profile, context)
    c = Mock()
    c.capture_run_requested = False
    p = Preview()

    lifecycle = RegionSelectionLifecycle(c, w, Mock(), Mock(), preview_factory=lambda *a: p)
    invalidated_calls = []
    lifecycle.dashboard_preview_invalidated.connect(lambda: invalidated_calls.append(True))

    lifecycle.request_dashboard_preview()
    p.preview_ready.emit("fake_image", context)
    p.running = False
    p.shutdown_finished.emit()

    # Resize source
    new_geometry = replace(capture_geometry, image_size_px=(1024, 768))
    new_context = replace(context, geometry=new_geometry)
    lifecycle.update_capture_context(new_context)

    assert len(invalidated_calls) == 1


def test_start_during_preview_waits_for_drain(qtbot, capture_geometry):
    from ui.region_selection import RegionSelectionLifecycle

    profile, context = capture_values(capture_geometry)
    w = Runtime(profile, context)
    c = Mock()
    c.capture_run_requested = False
    c.start_ocr = Mock()
    c.daily_coordinator = Mock()
    c.daily_coordinator.readiness.return_value = Mock(ready=True)
    p = Preview()

    lifecycle = RegionSelectionLifecycle(c, w, Mock(), Mock(), preview_factory=lambda *a: p)
    lifecycle.request_dashboard_preview()
    assert p.running is True

    # Start intent during preview
    lifecycle.queue_start_intent()
    assert p.stops == 1
    c.start_ocr.assert_not_called()

    p.running = False
    p.shutdown_finished.emit()
    c.start_ocr.assert_called_once()


def test_quit_during_preview_waits_for_shutdown_finished(qtbot, capture_geometry):
    from ui.region_selection import RegionSelectionLifecycle

    profile, context = capture_values(capture_geometry)
    w = Runtime(profile, context)
    c = Mock()
    c.capture_run_requested = False
    p = Preview()

    lifecycle = RegionSelectionLifecycle(c, w, Mock(), Mock(), preview_factory=lambda *a: p)
    lifecycle.request_dashboard_preview()

    shutdowns = []
    lifecycle.shutdown_finished.connect(lambda: shutdowns.append(True))

    lifecycle.request_shutdown()
    assert p.stops == 1
    assert len(shutdowns) == 0

    p.running = False
    p.shutdown_finished.emit()
    assert len(shutdowns) == 1


def test_cancel_region_editor_preserves_saved_regions(qtbot, capture_geometry):
    from ui.region_selection import RegionSelectionLifecycle

    profile, context = capture_values(capture_geometry)
    w = Runtime(profile, context)
    c = Mock()
    c.settings_coordinator = Mock()
    p = Preview()

    class FakeEditor(QObject):
        profile_selected = pyqtSignal(object)
        cancelled = pyqtSignal()
        refresh_requested = pyqtSignal()
        def show(self): pass
        def update_context(self, ctx): pass
        def accept(self): pass

    editor = FakeEditor()
    lifecycle = RegionSelectionLifecycle(
        c, w, Mock(), Mock(),
        preview_factory=lambda *a: p,
        editor_factory=lambda *a: editor,
    )

    lifecycle.start_selection()
    p.preview_ready.emit("fake_image", context)
    p.running = False
    p.shutdown_finished.emit()

    lifecycle.on_selection_cancelled()
    c.settings_coordinator.apply_capture_profile.assert_not_called()


def test_shared_preview_rejects_late_frame_after_source_change(ui_window, capture_geometry):
    from PyQt5.QtGui import QImage
    profile, context = capture_values(capture_geometry)
    ui_window.worker.capture_context = context
    ui_window.set_capture_profile_state(profile, bound=True)
    image = QImage(100, 80, QImage.Format_RGB32)
    assert ui_window.accept_capture_snapshot(image, context)
    from ui.controller_state import PresentedTranslation, PresentedPair
    ui_window._on_translation_presented(PresentedTranslation(1, 'subtitle', 1, (PresentedPair('old', 'cũ'),)))
    ui_window.clear_capture_snapshot()
    ui_window.capture_context_changed(replace(context, geometry_sequence=context.geometry_sequence+1))
    assert ui_window.subtitle_page._presentation is None
    ui_window.set_capture_profile_state(profile, bound=False)
    views = (ui_window.console_page, ui_window.ocr_page, ui_window.subtitle_page)
    assert all(view.snapshot_widget._image is None for view in views)
    assert not ui_window.accept_capture_snapshot(image, context)
    ui_window.worker.capture_context = replace(context, binding_epoch=context.binding_epoch+1)
    ui_window.set_capture_profile_state(profile, bound=True)
    assert not ui_window.accept_capture_snapshot(image, context)
    assert all(view.snapshot_widget._image is None for view in views)


def test_preview_cache_is_shared_without_capture_on_navigation(ui_window, capture_geometry):
    from PyQt5.QtGui import QImage
    profile, context = capture_values(capture_geometry)
    ui_window.worker.capture_context = context
    ui_window.set_capture_profile_state(profile, bound=True)
    ui_window.daily_coordinator.lifecycle = Mock()
    image = QImage(100, 80, QImage.Format_RGB32)
    assert ui_window.accept_capture_snapshot(image, context)
    for index in range(4):
        ui_window._switch_to_page(index)
    lifecycle = ui_window.daily_coordinator.lifecycle
    lifecycle.request_dashboard_preview.assert_not_called()
    for page in (ui_window.console_page, ui_window.ocr_page, ui_window.subtitle_page):
        assert page.snapshot_widget._image == image
        assert page.snapshot_widget._context == context
        page.refresh_preview_btn.setEnabled(True)
        page.refresh_preview_btn.click()
    assert lifecycle.request_dashboard_preview.call_count == 3
    ui_window.worker.start_worker.assert_not_called()
