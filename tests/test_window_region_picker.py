from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QImage
from PyQt5.QtTest import QSignalSpy
from test_capture_app_integration import capture_values
import pytest


def test_select_entire_window_is_a_draft_until_confirmed(qtbot, capture_geometry):
    from ui.window_region_picker import WindowRegionPicker
    profile, context = capture_values(capture_geometry, 'window')
    dialog = WindowRegionPicker(profile, QImage(800, 600, QImage.Format_RGB32), context)
    qtbot.addWidget(dialog)
    saved = QSignalSpy(dialog.profile_selected)
    dialog.select_all_btn.click()
    assert len(saved) == 0
    dialog._zoom(.8)
    dialog.apply_btn.click()
    assert len(saved) == 1
    rect = saved[0][0].regions[0].rect
    assert (rect.x, rect.y, rect.width, rect.height) == (0, 0, 1, 1)
    assert saved[0][0].source_kind == 'window'


def test_full_window_button_disabled_without_image(qtbot, capture_geometry):
    from ui.window_region_picker import WindowRegionPicker
    profile, context = capture_values(capture_geometry, 'window')
    dialog = WindowRegionPicker(profile, None, context)
    qtbot.addWidget(dialog)
    assert not dialog.select_all_btn.isEnabled()


def test_window_image_picker_confirms_drag_with_visible_button(qtbot, capture_geometry):
    from ui.window_region_picker import WindowRegionPicker
    profile, context = capture_values(capture_geometry, 'window')
    image = QImage(800, 600, QImage.Format_RGB32)
    image.fill(Qt.white)
    dialog = WindowRegionPicker(profile, image, context)
    qtbot.addWidget(dialog)
    dialog.show()
    canvas = dialog.canvas
    qtbot.mousePress(canvas, Qt.LeftButton, pos=QPoint(40, 30))
    qtbot.mouseRelease(canvas, Qt.LeftButton, pos=QPoint(240, 130))
    saved = QSignalSpy(dialog.profile_selected)
    assert len(saved) == 0
    dialog.apply_btn.click()
    assert len(saved) == 1
    assert saved[0][0].source_kind == 'window'
    assert 0 < saved[0][0].regions[0].rect.width < 1


def test_missing_video_still_offers_explicit_screen_fallback(qtbot, capture_geometry):
    from ui.window_region_picker import WindowRegionPicker
    profile, context = capture_values(capture_geometry, 'window')
    dialog = WindowRegionPicker(profile, None, context)
    qtbot.addWidget(dialog)
    assert not dialog.apply_btn.isEnabled()
    fallback = QSignalSpy(dialog.screen_fallback_requested)
    dialog.fallback_btn.click()
    assert len(fallback) == 1


def test_screen_fallback_commit_changes_real_capture_source(qtbot, ui_window, capture_geometry, monkeypatch):
    from ui.capture_binding import CaptureApplicationBinding
    from test_capture_binding import Screens, Provider
    from types import SimpleNamespace
    from core import config
    profile, context = capture_values(capture_geometry)
    from dataclasses import replace
    profile = replace(profile, monitor_name=capture_geometry.screen.name)
    worker = ui_window.worker
    worker.is_drained = True
    lifecycle = SimpleNamespace(is_active=True, preview_is_drained=True)
    binding = CaptureApplicationBinding(ui_window, worker, None, Screens([capture_geometry.screen]),
                                        lifecycle, window_provider=Provider())
    assert binding.apply_screen_selection(profile, context)
    worker.configure_capture.assert_called_once_with(profile, context)
    assert config.load_capture_setup_complete()
    assert binding.is_bound
    worker.configure_capture.reset_mock()
    monkeypatch.setattr(config, 'save_capture_profile', lambda *a, **kw: (_ for _ in ()).throw(config.ConfigError('full')))
    monkeypatch.setattr(ui_window, '_show_save_error', lambda message: None)
    assert not binding.apply_screen_selection(profile, context)
    worker.configure_capture.assert_not_called()


@pytest.mark.parametrize('confirm', [False, True])
def test_missing_window_frame_can_switch_or_cancel_screen_capture(qtbot, ui_window, capture_geometry, confirm):
    from ui.region_selection import RegionSelectionLifecycle
    from ui.capture_binding import CaptureApplicationBinding
    from test_capture_binding import Screens
    from test_capture_selection_lifecycle import Preview, FakeWindowProvider
    from unittest.mock import Mock
    from core import config
    profile, context = capture_values(capture_geometry, 'window')
    screens = Screens([capture_geometry.screen])
    worker = ui_window.worker
    worker.capture_profile, worker.capture_context = profile, context
    worker.is_drained, worker.restart_pending = True, False
    worker.is_running.return_value = False
    def configure(p, c):
        worker.capture_profile, worker.capture_context = p, c
    worker.configure_capture.side_effect = configure
    preview = Preview()
    lifecycle = RegionSelectionLifecycle(ui_window, worker, Mock(), screens, preview_factory=lambda *a: preview)
    binding = CaptureApplicationBinding(ui_window, worker, Mock(), screens, lifecycle,
                                        window_provider=FakeWindowProvider(context))
    ui_window.daily_coordinator.attach_capture(binding, lifecycle)
    binding.select_source(profile, context.window)
    before = config.load_config()['capture_profile']
    lifecycle.start_quick_selection()
    preview.running = False
    preview.shutdown_finished.emit()  # no usable image, e.g. failed WGC preview
    picker = lifecycle.current_editor
    qtbot.addWidget(picker)
    picker.fallback_btn.click()
    editor = lifecycle.current_editor
    qtbot.addWidget(editor)
    assert config.load_config()['capture_profile'] == before
    if confirm:
        qtbot.mousePress(editor, Qt.LeftButton, pos=QPoint(40, 40))
        qtbot.mouseRelease(editor, Qt.LeftButton, pos=QPoint(640, 240))
        editor.confirm_btn.click()
        assert worker.capture_profile.source_kind == 'desktop'
        assert worker.capture_context.source_kind == 'desktop'
        assert binding.profile.source_kind == 'desktop'
        assert config.load_config()['capture_profile']['source_kind'] == 'desktop'
        assert worker.capture_context.window is None
    else:
        editor.reject()
        assert worker.capture_profile.source_kind == 'window'
        assert config.load_config()['capture_profile'] == before
    binding.stop()


def test_zoom_preserves_source_coordinates(qtbot, capture_geometry):
    from ui.window_region_picker import WindowRegionPicker
    profile, context = capture_values(capture_geometry, 'window')
    dialog = WindowRegionPicker(profile, QImage(800, 600, QImage.Format_RGB32), context)
    qtbot.addWidget(dialog)
    canvas = dialog.canvas
    canvas.resize(400, 300)
    qtbot.mousePress(canvas, Qt.LeftButton, pos=QPoint(40, 30))
    qtbot.mouseRelease(canvas, Qt.LeftButton, pos=QPoint(240, 130))
    dialog._zoom(1.25)
    saved = QSignalSpy(dialog.profile_selected)
    dialog.apply_btn.click()
    rect = saved[0][0].regions[0].rect
    assert rect.x == .1 and rect.y == .1 and rect.width == .5


def test_window_picker_waits_for_previous_preview_owner_to_drain(qtbot, capture_geometry):
    from ui.region_selection import RegionSelectionLifecycle
    from test_capture_selection_lifecycle import Preview
    from unittest.mock import Mock
    profile, context = capture_values(capture_geometry, 'window')
    worker = Mock()
    worker.capture_profile, worker.capture_context = profile, context
    worker.is_drained, worker.restart_pending = True, False
    worker.is_running.return_value = False
    controller = Mock()
    controller.capture_run_requested = False
    previews = []
    def factory(*args):
        preview = Preview()
        previews.append(preview)
        return preview
    lifecycle = RegionSelectionLifecycle(controller, worker, Mock(), Mock(), preview_factory=factory)
    assert lifecycle.request_dashboard_preview()
    lifecycle.start_quick_selection()
    assert len(previews) == 1
    previews[0].running = False
    previews[0].shutdown_finished.emit()
    assert len(previews) == 2
    lifecycle.request_shutdown()
    previews[1].running = False
    previews[1].shutdown_finished.emit()
