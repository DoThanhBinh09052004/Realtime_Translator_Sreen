from uuid import uuid4
from unittest.mock import Mock
import pytest
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QApplication

from core import config
from core.config import save_config_values, save_capture_profile, load_capture_setup_complete
from core.capture.models import CaptureProfile, CaptureRegion, NormalizedRect
from ui.controller import ControllerWindow
from ui.overlay import Overlay
from ui.region_selection import RegionSelectionLifecycle
from ui.controller_state import (
    DailyReadiness,
    DailyRunState,
    PresentedPair,
    PresentedTranslation,
)


def _setup_profile(name="Primary Desktop", setup_complete=True):
    region_id = str(uuid4())
    region = CaptureRegion(region_id, "Vùng 1", NormalizedRect(0.1, 0.1, 0.5, 0.5), enabled=True)
    profile = CaptureProfile(1, "desktop", name, None, (region,), ())
    save_capture_profile(profile, setup_complete=setup_complete)
    return profile


def test_minimum_window_keeps_primary_action_visible(qtbot):
    """Window at minimum size 660x480 keeps primary action button and status visible without horizontal scroll."""
    worker = Mock()
    worker.interval.return_value = 500
    worker.is_running.return_value = False
    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)

    window.resize(660, 480)
    window.show()
    qtbot.wait(50)

    assert window.width() >= 660
    assert window.height() >= 480

    # Primary toggle button and status line must be visible
    assert window.console_page.primary_btn.isVisible()
    assert window.console_page.readiness_lbl.isVisible()

    # Must fit horizontally without requiring horizontal scroll
    QApplication.processEvents()
    assert window.console_page.horizontalScrollBar().maximum() == 0

    # Primary button must be accessible within visible window area
    pos = window.console_page.primary_btn.mapTo(window, QPoint(0, 0))
    assert pos.x() >= 0
    assert pos.y() < window.height()


def test_wide_dashboard_keeps_subtitle_preview_in_first_screen(qtbot, ui_window):
    from PyQt5.QtCore import QRect
    page = ui_window.console_page
    page.render_presented(PresentedTranslation(1, 'subtitle', 1, (PresentedPair('Stay close.', 'Con đường phía trước rất nguy hiểm. Hãy theo sát tôi.'),)))
    ui_window.resize(1200, 800)
    ui_window.show()
    QApplication.processEvents()
    preview = page.subtitle_preview
    assert page.viewport().rect().contains(QRect(preview.mapTo(page.viewport(), QPoint()), preview.size()))


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_dashboard_source_controls_share_a_baseline_and_height(ui_window, theme):
    page = ui_window.console_page
    ui_window.resize(1200, 800)
    ui_window.apply_theme(theme)
    ui_window.show()
    QApplication.processEvents()
    controls = (page.src_combo, page.tgt_combo, page.capture_settings.source_combo,
                page.capture_settings.choose_btn, page.capture_settings.refresh_btn, page.provider_combo)
    assert len({control.mapTo(page, QPoint()).y() for control in controls}) == 1
    assert len({control.height() for control in controls}) == 1


def test_dashboard_subtitle_is_centered_inside_its_preview_surface(ui_window):
    from PyQt5.QtCore import QRect
    page = ui_window.console_page
    page.render_presented(PresentedTranslation(1, 'subtitle', 1, (PresentedPair('Stay close.', 'Hãy theo sát tôi.'),)))
    ui_window.resize(1200, 800)
    ui_window.show()
    QApplication.processEvents()
    frame = page.subtitle_preview_frame
    label = page.subtitle_preview
    rect = QRect(label.mapTo(frame, QPoint()), label.size())
    assert frame.rect().contains(rect)
    assert abs(rect.left() - (frame.width() - 1 - rect.right())) <= 1
    assert abs(rect.top() - (frame.height() - 1 - rect.bottom())) <= 1


def test_dialogue_reading_boxes_wrap_without_horizontal_scrollbars(ui_window):
    page = ui_window.console_page
    page.render_presented(PresentedTranslation(1, 'subtitle', 1, (PresentedPair('The path ahead is dangerous. Stay close.', 'Con đường phía trước rất nguy hiểm. Hãy theo sát tôi.'),)))
    ui_window.resize(1200, 800)
    ui_window.show()
    QApplication.processEvents()
    for editor in (page.output_widget.source_edit, page.output_widget.target_edit):
        assert editor.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
        assert editor.lineWrapMode() == editor.WidgetWidth


def test_long_source_and_translation_do_not_expand_window(qtbot):
    """Long source title (200 chars) and multi-line unicode translations do not expand window geometry."""
    worker = Mock()
    worker.interval.return_value = 500
    worker.is_running.return_value = False
    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)

    window.resize(660, 480)
    window.show()
    qtbot.wait(50)

    # 200-character window / profile title
    long_title = "Cửa sổ có tiêu đề siêu dài để kiểm tra tràn layout " * 4  # ~208 chars
    profile = _setup_profile(name=long_title)
    window.set_capture_profile_state(profile, bound=True)

    # Multi-line long unicode strings (Vietnamese diacritics & Japanese)
    long_source = "とても長い原文テキストです。" * 20
    long_translation = "Đây là một đoạn phụ đề rất dài nhằm kiểm tra hiện tượng tràn khung hình và đảm bảo elide hoặc xuống dòng an toàn mà không mở rộng cửa sổ. " * 5
    pair = PresentedPair(long_source, long_translation)
    presentation = PresentedTranslation(revision=1, mode="subtitle", sequence=1, pairs=(pair,))

    window.console_page.render_presented(presentation)
    QApplication.processEvents()

    # Window width must not exceed 660
    assert window.width() <= 660
    # No horizontal scrollbar
    assert window.console_page.horizontalScrollBar().maximum() == 0


def test_fresh_user_can_translate_without_opening_advanced_settings(qtbot):
    """A fresh user can select a source, define a region, start translation, and receive presented output entirely on Screen A."""
    save_config_values({"capture_setup_complete": False})
    save_config_values({"source_lang": "English", "target_lang": "Vietnamese", "current_provider": "Google Translate"})

    worker = Mock()
    worker.interval.return_value = 500
    worker.is_running.return_value = False
    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)

    # 1. Fresh state initially on Screen A
    assert window.pages.currentIndex() == 0
    assert not load_capture_setup_complete()
    assert window.daily_coordinator.readiness().ready is False

    # 2. Select source via daily screen controls
    window.console_page.capture_settings.source_selected.emit("desktop", "Desktop 1")
    assert window.pages.currentIndex() == 0

    # 3. Save region (simulates region editor confirmation without opening advanced settings)
    profile = _setup_profile(setup_complete=True)
    window.set_capture_profile_state(profile, bound=True)
    window.daily_coordinator.refresh()

    assert window.daily_coordinator.readiness().ready is True
    assert window.pages.currentIndex() == 0

    # 4. Click primary start button
    window.console_page.primary_btn.click()
    assert window.capture_run_requested is True
    worker.start_worker.assert_called_once()
    assert window.pages.currentIndex() == 0

    # 5. Presented translation arrives
    pair = PresentedPair("Fresh source line", "Dòng bản dịch đầu tiên")
    presentation = PresentedTranslation(revision=1, mode="subtitle", sequence=1, pairs=(pair,))
    window._on_translation_presented(presentation)

    assert not window.console_page.output_widget.is_empty()
    assert "Dòng bản dịch đầu tiên" in window.console_page.output_widget.target_edit.toPlainText()
    assert window.pages.currentIndex() == 0


def test_both_overlay_modes_reject_old_revision_after_source_change(qtbot):
    """Both subtitle and block overlay modes reject late frames from previous revisions after source change."""
    worker = Mock()
    worker.interval.return_value = 500
    worker.is_running.return_value = False
    overlay = Overlay()
    qtbot.addWidget(overlay)

    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=overlay)
    qtbot.addWidget(window)

    # 1. Test Subtitle Mode
    overlay.set_mode("subtitle", revision=1)
    assert overlay._mode_revision == 1

    # Frame with matching revision is accepted
    class FakeSubtitleFrame:
        revision = 1
        render_sequence = 1
        candidate_id = 1
        text = "Subtitle translation 1"
        source_text = "Subtitle source 1"

    overlay.update_subtitle(FakeSubtitleFrame())
    assert overlay.text() == "Subtitle translation 1"

    # Source change bumps revision
    overlay.set_mode("subtitle", revision=2)
    assert overlay._mode_revision == 2

    # Late frame with old revision 1 is rejected
    class FakeLateSubtitleFrame:
        revision = 1
        render_sequence = 2
        candidate_id = 2
        text = "Late rejected subtitle"
        source_text = "Late source"

    overlay.update_subtitle(FakeLateSubtitleFrame())
    assert overlay.text() != "Late rejected subtitle"

    # 2. Test Block Mode
    overlay.set_mode("blocks", revision=3)
    assert overlay._mode_revision == 3

    class FakeBlockFrame:
        revision = 2  # old revision
        frame_id = 1
        blocks = ()

    # Old revision block frame is rejected
    overlay.update_blocks(FakeBlockFrame())
    assert overlay._block_frame_id == -1

    # Matching revision is processed
    class FakeMatchingBlockFrame:
        revision = 3
        frame_id = 1
        blocks = ()

    overlay.update_blocks(FakeMatchingBlockFrame())
    assert overlay._block_frame_id == 1


def test_quit_drains_dashboard_preview_and_translation(qtbot):
    """Quit action drains dashboard preview and translation cleanly."""
    worker = Mock()
    worker.interval.return_value = 500
    worker.is_running.return_value = True

    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)
    window.capture_run_requested = True

    lifecycle = Mock(spec=RegionSelectionLifecycle)
    lifecycle._shutdown_requested = False
    lifecycle._preview_purpose = "dashboard"
    lifecycle.preview_worker = Mock()
    lifecycle.current_editor = None
    lifecycle.worker = worker
    lifecycle.controller = window
    lifecycle._poll = Mock()
    lifecycle._advance_capture = Mock()
    lifecycle.close = Mock()

    window.daily_coordinator.lifecycle = lifecycle

    # Execute region lifecycle request_shutdown (as called during on_quit in main.py)
    RegionSelectionLifecycle.request_shutdown(lifecycle)

    lifecycle.cancel_dashboard_preview.assert_called_once()
    lifecycle.worker.stop_worker.assert_called_once()
    assert lifecycle._shutdown_requested is True
    assert window.capture_run_requested is False
