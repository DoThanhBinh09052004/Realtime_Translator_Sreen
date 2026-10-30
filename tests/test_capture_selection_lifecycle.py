from types import SimpleNamespace
from PyQt5.QtCore import QObject, pyqtSignal
from core.capture.models import SourceStatus
from core.contracts import EngineError
from test_capture_app_integration import capture_values


class Runtime(QObject):
    shutdown_finished = pyqtSignal()
    def __init__(self, profile, context):
        super().__init__(); self.capture_profile = profile; self.capture_context = context
        self.is_drained = False; self.restart_pending = False; self.stops = 0
    def is_running(self): return True
    def stop_worker(self, **kwargs): self.stops += 1


class Preview(QObject):
    preview_ready = pyqtSignal(object, object)
    error_occurred = pyqtSignal(object)
    shutdown_finished = pyqtSignal()
    def __init__(self, *args): super().__init__(); self.running = False; self.stops = 0
    def start(self): self.running = True
    def isRunning(self): return self.running
    def request_stop(self): self.stops += 1


def test_selection_waits_for_runtime_and_preview_drain(qtbot, capture_geometry):
    from ui.region_selection import RegionSelectionLifecycle
    from unittest.mock import Mock
    profile, context = capture_values(capture_geometry)
    w = Runtime(profile, context); c = Mock(); c.capture_run_requested = True
    previews = []; editors = []
    def factory(*args): preview = Preview(); previews.append(preview); return preview
    lifecycle = RegionSelectionLifecycle(c, w, Mock(), Mock(), preview_factory=factory, editor_factory=lambda *a: editors.append(a))
    lifecycle.start_selection()
    assert not previews and w.stops == 1
    w.is_drained = True; w.shutdown_finished.emit()
    qtbot.waitUntil(lambda: bool(previews))
    p = previews[0]; p.preview_ready.emit('image', context)
    assert not editors
    lifecycle.request_shutdown()
    assert p.stops == 1


def test_quit_waits_for_preview_native_drain_when_runtime_already_finished(qtbot, capture_geometry):
    from ui.region_selection import RegionSelectionLifecycle
    from main import ShutdownBarrier
    from unittest.mock import Mock
    profile, context = capture_values(capture_geometry)
    w = Runtime(profile, context); w.is_drained = True
    p = Preview(); c = Mock(); c.capture_run_requested = True
    lifecycle = RegionSelectionLifecycle(c, w, Mock(), Mock(), preview_factory=lambda *a: p)
    lifecycle.start_selection(); assert p.running
    quits = []; barrier = ShutdownBarrier(lambda: quits.append(1)); barrier.begin(); barrier.finish('language_packs')
    lifecycle.shutdown_finished.connect(lambda: barrier.finish('translation'))
    lifecycle.request_shutdown(); qtbot.wait(60)
    assert not quits
    p.running = False; p.shutdown_finished.emit()
    qtbot.waitUntil(lambda: bool(quits))
    p.shutdown_finished.emit(); assert quits == [1]
    c.start_ocr.assert_not_called()


def test_terminal_epoch_guard_invalidates_without_losing_run_intent(qtbot, capture_geometry):
    from ui.region_selection import RegionSelectionLifecycle
    from unittest.mock import Mock
    profile, context = capture_values(capture_geometry)
    w = Runtime(profile, context); c = Mock(); c.capture_run_requested = True; overlay = Mock()
    lifecycle = RegionSelectionLifecycle(c, w, overlay, Mock())
    lifecycle.on_capture_terminal(SourceStatus(0, 'error'))
    assert w.stops == 0
    lifecycle.on_capture_terminal(SourceStatus(1, 'error', EngineError('capture', 'gone', True)))
    assert w.stops == 1 and c.capture_run_requested is True
    overlay.clear.assert_called_once()

class FakeWindowProvider(QObject):
    context_changed = pyqtSignal(object)
    source_unavailable = pyqtSignal(object)
    def __init__(self, context): super().__init__(); self.context = context; self.bindings = []; self.clears = 0
    def set_binding(self, profile, identity, epoch):
        from dataclasses import replace
        self.bindings.append(identity)
        self.context_changed.emit(replace(self.context, binding_epoch=epoch, window=identity))
    def clear_binding(self): self.clears += 1


def test_binding_routes_selection_move_and_restore_through_controller(qtbot, capture_geometry):
    from ui.capture_binding import CaptureApplicationBinding
    from unittest.mock import Mock
    from dataclasses import replace
    profile, context = capture_values(capture_geometry, 'window')
    w = Mock(); w.capture_context = None; w.capture_profile = None; w.is_drained = True
    w.configure_capture.side_effect = lambda p, c: (setattr(w, 'capture_profile', p), setattr(w, 'capture_context', c))
    c = Mock(); c.capture_run_requested = False
    picker = FakeWindowProvider(context)
    c.ocr_page.capture_settings.source_selected = picker.context_changed
    provider = FakeWindowProvider(context); lifecycle = Mock(); lifecycle.is_active = False
    binding = CaptureApplicationBinding(c, w, Mock(), Mock(), lifecycle, window_provider=provider)
    binding.select_source(profile, context.window)
    assert w.capture_context.window == context.window
    assert provider.bindings == [context.window]
    c.capture_run_requested = True
    moved = replace(w.capture_context, geometry_sequence=2, geometry=replace(capture_geometry, region_px=replace(capture_geometry.region_px, x=90)))
    provider.context_changed.emit(moved)
    w.update_capture_geometry.assert_called_once_with(moved)
    provider.source_unavailable.emit(EngineError('window_unavailable', 'minimized', True))
    lifecycle.on_capture_terminal.assert_called_once()
    provider.context_changed.emit(replace(moved, binding_epoch=moved.binding_epoch+1))
    c.start_ocr.assert_called_once_with(preserve_translation_session=True)
    binding.stop()
    assert provider.clears == 2


def test_start_is_blocked_until_preview_and_editor_cleanup(qtbot, ui_window, capture_geometry, monkeypatch):
    from ui.capture_binding import CaptureApplicationBinding
    from ui.region_selection import RegionSelectionLifecycle
    from unittest.mock import Mock
    from test_capture_binding import Provider, Screens
    profile, context = capture_values(capture_geometry)
    c = ui_window; w = c.worker
    w.capture_profile = profile; w.capture_context = context; w.is_drained = True
    w.is_running.return_value = False; w.restart_pending = False
    c.capture_run_requested = True
    c.set_capture_profile_state(profile, bound=True)
    monkeypatch.setattr(c.settings_coordinator, 'source_ready', lambda: True)
    p = Preview(); overlay = Mock(); overlay.isVisible.return_value = False
    lifecycle = RegionSelectionLifecycle(c, w, overlay, Mock(), preview_factory=lambda *a: p)
    binding = CaptureApplicationBinding(c, w, overlay, Screens([]), lifecycle, window_provider=Provider())
    binding.profile = profile
    lifecycle.start_selection()
    assert p.running
    c.start_ocr()
    w.start_worker.assert_not_called()
    p.preview_ready.emit(None, context)
    p.request_stop(); c.start_ocr()
    w.start_worker.assert_not_called()
    p.running = False; p.shutdown_finished.emit()
    qtbot.waitUntil(lambda: lifecycle.current_editor is not None)
    editor = lifecycle.current_editor; qtbot.addWidget(editor)
    c.start_ocr(); w.start_worker.assert_not_called()
    editor.reject()
    qtbot.waitUntil(lambda: not lifecycle.is_active)
    w.start_worker.assert_called_once()


def test_preview_resize_before_editor_disables_apply_until_refresh(qtbot, capture_geometry):
    from ui.region_selection import RegionSelectionLifecycle
    from ui.capture_regions_dialog import CaptureRegionsDialog
    from dataclasses import replace
    from unittest.mock import Mock
    profile, context = capture_values(capture_geometry, 'window')
    w = Runtime(profile, context); w.is_drained = True
    c = Mock(); c.capture_run_requested = False
    previews = []
    def preview_factory(*args):
        preview = Preview(); previews.append(preview); return preview
    lifecycle = RegionSelectionLifecycle(c, w, Mock(), Mock(), preview_factory=preview_factory)
    lifecycle.start_selection(); p = previews[0]
    p.preview_ready.emit(None, context)
    moved = replace(context, geometry_sequence=2, geometry=replace(context.geometry, region_px=replace(context.geometry.region_px, x=50)))
    lifecycle.update_capture_context(moved)
    resized = replace(moved, binding_epoch=2, geometry=replace(moved.geometry, image_size_px=(900, 600)))
    lifecycle.update_capture_context(resized)
    p.running = False; p.shutdown_finished.emit()
    qtbot.waitUntil(lambda: lifecycle.current_editor is not None)
    editor = lifecycle.current_editor; qtbot.addWidget(editor)
    assert not editor.apply_btn.isEnabled()
    assert 'ảnh' in editor.error_label.text().lower()
    w.capture_context = resized
    editor.refresh_requested.emit()
    fresh = previews[1]; fresh.preview_ready.emit(None, resized)
    fresh.running = False; fresh.shutdown_finished.emit()
    qtbot.waitUntil(lambda: lifecycle.current_editor is not None)
    refreshed = lifecycle.current_editor; qtbot.addWidget(refreshed)
    assert refreshed.apply_btn.isEnabled()
    refreshed.reject()


def test_preview_origin_move_does_not_invalidate_image(qtbot, capture_geometry):
    from ui.region_selection import RegionSelectionLifecycle
    from dataclasses import replace
    from unittest.mock import Mock
    profile, context = capture_values(capture_geometry, 'window')
    w = Runtime(profile, context); w.is_drained = True
    p = Preview(); lifecycle = RegionSelectionLifecycle(Mock(), w, Mock(), Mock(), preview_factory=lambda *a: p)
    lifecycle.start_selection(); p.preview_ready.emit(None, context)
    lifecycle.update_capture_context(replace(context, geometry_sequence=2, geometry=replace(context.geometry, region_px=replace(context.geometry.region_px, x=50))))
    p.running = False; p.shutdown_finished.emit()
    qtbot.waitUntil(lambda: lifecycle.current_editor is not None)
    editor = lifecycle.current_editor; qtbot.addWidget(editor)
    assert editor.apply_btn.isEnabled()
    editor.reject()


import pytest
@pytest.mark.parametrize('finish', ['preview_failure', 'cancel', 'apply'])
def test_stop_during_selection_prevents_cleanup_restart(qtbot, capture_geometry, finish):
    from ui.region_selection import RegionSelectionLifecycle
    from unittest.mock import Mock
    profile, context = capture_values(capture_geometry)
    w = Runtime(profile, context); w.is_drained = True
    c = Mock(); c.capture_run_requested = True
    c.settings_coordinator.apply_capture_profile.return_value = True
    p = Preview(); lifecycle = RegionSelectionLifecycle(c, w, Mock(), Mock(), preview_factory=lambda *a: p)
    lifecycle.start_selection()
    c.capture_run_requested = False
    if finish != 'preview_failure': p.preview_ready.emit(None, context)
    p.running = False; p.shutdown_finished.emit()
    if finish != 'preview_failure':
        qtbot.waitUntil(lambda: lifecycle.current_editor is not None)
        editor = lifecycle.current_editor; qtbot.addWidget(editor)
        if finish == 'cancel': editor.reject()
        else: editor.apply_btn.click()
    assert not lifecycle.is_active
    c.start_ocr.assert_not_called()
