from dataclasses import replace
from unittest.mock import Mock

from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtTest import QSignalSpy

from test_capture_app_integration import capture_values


def test_select_whole_screen_waits_for_confirmation(qtbot, capture_geometry):
    from ui.direct_region_selector import DirectRegionSelector
    profile, context = capture_values(capture_geometry)
    selector = DirectRegionSelector(profile, context)
    qtbot.addWidget(selector)
    saved = QSignalSpy(selector.profile_selected)
    selector.select_all_btn.click()
    assert len(saved) == 0
    selector.confirm_btn.click()
    rect = saved[0][0].regions[0].rect
    assert (rect.x, rect.y, rect.width, rect.height) == (0, 0, 1, 1)
    assert saved[0][0].source_kind == 'desktop'


def test_explicit_whole_source_replaces_multiple_regions_only_on_confirm(qtbot, capture_geometry):
    from ui.direct_region_selector import DirectRegionSelector
    from core.capture.models import CaptureRegion, NormalizedRect
    from uuid import uuid4
    profile, context = capture_values(capture_geometry)
    first = replace(profile.regions[0], rect=NormalizedRect(0, 0, .4, 1))
    other = CaptureRegion(str(uuid4()), 'Other', NormalizedRect(.6, 0, .4, 1), True)
    profile = replace(profile, regions=(first, other))
    selector = DirectRegionSelector(profile, context)
    qtbot.addWidget(selector)
    saved = QSignalSpy(selector.profile_selected)
    selector.select_all_btn.click()
    assert selector.profile == profile and len(saved) == 0
    selector.confirm_btn.click()
    assert len(saved) == 1 and len(saved[0][0].regions) == 1
    assert saved[0][0].exclusions == profile.exclusions


def test_drag_requires_enter_and_preserves_source(qtbot, capture_geometry):
    from ui.direct_region_selector import DirectRegionSelector
    profile, context = capture_values(capture_geometry, 'window')
    selector = DirectRegionSelector(profile, context)
    qtbot.addWidget(selector)
    selector.show()
    spy = QSignalSpy(selector.profile_selected)
    qtbot.mousePress(selector, Qt.LeftButton, pos=QPoint(40, 30))
    qtbot.mouseRelease(selector, Qt.LeftButton, pos=QPoint(240, 130))
    assert len(spy) == 0
    qtbot.keyClick(selector, Qt.Key_Return)
    assert len(spy) == 1
    result = spy[0][0]
    assert result.source_kind == 'window'
    assert result.window_hint == profile.window_hint
    assert result.regions[0].id == profile.regions[0].id
    assert result.regions[0].rect.x == 40 / selector.width()
    assert result.exclusions == profile.exclusions


def test_escape_does_not_save_and_geometry_change_blocks_confirm(qtbot, capture_geometry):
    from ui.direct_region_selector import DirectRegionSelector
    profile, context = capture_values(capture_geometry)
    selector = DirectRegionSelector(profile, context)
    qtbot.addWidget(selector)
    selector.show()
    saved, cancelled = QSignalSpy(selector.profile_selected), QSignalSpy(selector.cancelled)
    qtbot.mousePress(selector, Qt.LeftButton, pos=QPoint(20, 30))
    qtbot.mouseRelease(selector, Qt.LeftButton, pos=QPoint(220, 130))
    selector.update_context(replace(context, binding_epoch=context.binding_epoch + 1))
    qtbot.keyClick(selector, Qt.Key_Return)
    assert len(saved) == 0
    qtbot.keyClick(selector, Qt.Key_Escape)
    assert len(cancelled) == 1


def test_drag_can_move_and_resize_before_confirmation(qtbot, capture_geometry):
    from ui.direct_region_selector import DirectRegionSelector
    profile, context = capture_values(capture_geometry)
    selector = DirectRegionSelector(profile, context)
    qtbot.addWidget(selector)
    selector.show()
    qtbot.mousePress(selector, Qt.LeftButton, pos=QPoint(40, 40))
    qtbot.mouseRelease(selector, Qt.LeftButton, pos=QPoint(240, 140))
    qtbot.mousePress(selector, Qt.LeftButton, pos=QPoint(100, 100))
    qtbot.mouseRelease(selector, Qt.LeftButton, pos=QPoint(120, 120))
    assert selector.selection.topLeft() == QPoint(60, 60)
    corner = selector.selection.bottomRight()
    qtbot.mousePress(selector, Qt.LeftButton, pos=corner)
    qtbot.mouseRelease(selector, Qt.LeftButton, pos=corner + QPoint(30, 20))
    assert selector.selection.width() == 230
    assert selector.selection.height() == 120


def test_quick_lifecycle_waits_for_drain_without_preview(qtbot, capture_geometry):
    from ui.region_selection import RegionSelectionLifecycle
    from test_capture_selection_lifecycle import Runtime
    profile, context = capture_values(capture_geometry)
    worker = Runtime(profile, context)
    controller = Mock()
    controller.capture_run_requested = False
    lifecycle = RegionSelectionLifecycle(controller, worker, Mock(), Mock(), preview_factory=Mock())
    lifecycle.start_quick_selection()
    assert lifecycle.current_editor is None
    worker.is_drained = True
    worker.shutdown_finished.emit()
    assert lifecycle.current_editor is not None
    qtbot.addWidget(lifecycle.current_editor)
    lifecycle.preview_factory.assert_not_called()
    lifecycle.current_editor.reject()
    controller.settings_coordinator.apply_capture_profile.assert_not_called()
    assert not lifecycle.is_active


def test_quick_selection_cannot_confirm_after_source_loss(qtbot, capture_geometry):
    from ui.region_selection import RegionSelectionLifecycle
    from test_capture_selection_lifecycle import Runtime
    from core.capture.models import SourceStatus
    profile, context = capture_values(capture_geometry, 'window')
    worker = Runtime(profile, context)
    worker.is_drained = True
    controller = Mock()
    controller.capture_run_requested = False
    from test_capture_selection_lifecycle import Preview
    from PyQt5.QtGui import QImage
    preview = Preview()
    lifecycle = RegionSelectionLifecycle(controller, worker, Mock(), Mock(), preview_factory=lambda *a: preview)
    lifecycle.start_quick_selection()
    preview.preview_ready.emit(QImage(800, 600, QImage.Format_RGB32), context)
    preview.running = False
    preview.shutdown_finished.emit()
    editor = lifecycle.current_editor
    qtbot.addWidget(editor)
    qtbot.mousePress(editor.canvas, Qt.LeftButton, pos=QPoint(40, 40))
    qtbot.mouseRelease(editor.canvas, Qt.LeftButton, pos=QPoint(240, 140))
    lifecycle.on_capture_terminal(SourceStatus(context.binding_epoch, 'unavailable'))
    editor.apply_btn.click()
    controller.settings_coordinator.apply_capture_profile.assert_not_called()
    editor.reject()


def test_source_bounds_respect_negative_origin_and_scaled_monitor(qtbot, capture_geometry):
    from ui.direct_region_selector import DirectRegionSelector
    from core.blocks.models import Rect, ScreenMapping
    profile, context = capture_values(capture_geometry, 'window')
    screen = ScreenMapping('left', Rect(-1280, 0, 1280, 720), Rect(-1920, 0, 1920, 1080))
    geometry = replace(context.geometry, screen=screen, region_px=Rect(-1500, 150, 600, 300),
                       image_size_px=(600, 300))
    selector = DirectRegionSelector(profile, replace(context, geometry=geometry))
    qtbot.addWidget(selector)
    assert selector.geometry() == QRect(-1000, 100, 400, 200)
    selector.show()
    saved = QSignalSpy(selector.profile_selected)
    # Reversed drag outside the source is clamped, never changes the source.
    qtbot.mousePress(selector, Qt.LeftButton, pos=QPoint(200, 100))
    qtbot.mouseRelease(selector, Qt.LeftButton, pos=QPoint(-50, -30))
    qtbot.keyClick(selector, Qt.Key_Return)
    rect = saved[0][0].regions[0].rect
    assert (rect.x, rect.y, rect.width, rect.height) == (0, 0, .5, .5)
