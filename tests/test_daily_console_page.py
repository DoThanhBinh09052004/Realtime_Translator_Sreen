from dataclasses import replace
from pathlib import Path
import pytest
from PyQt5.QtCore import Qt, QSize, QRectF, QPoint, QRect
from PyQt5.QtGui import QImage, QColor
from PyQt5.QtTest import QSignalSpy

from core.contracts import TranslationStatus
from core.capture.models import CaptureProfile, CaptureRegion, NormalizedRect, CaptureContext
from core.blocks.models import Rect, ScreenMapping, CaptureGeometry
from ui.controller_state import (
    DailyReadiness,
    DailyRunState,
    PresentedPair,
    PresentedTranslation,
    LanguageChoice,
)
from tests.test_ui_module_boundaries import forbidden_imports


def test_daily_view_renders_without_runtime_imports():
    targets = [
        Path('ui/pages/console_page.py'),
        Path('ui/widgets/capture_snapshot.py'),
        Path('ui/widgets/translation_output.py'),
    ]
    for target in targets:
        assert target.exists(), f"File {target} must exist"
        source = target.read_text(encoding='utf-8-sig')
        pkg = 'ui.pages' if 'pages' in target.parts else 'ui.widgets'
        bad = forbidden_imports(source, pkg, {'ui.controller', 'core.config', 'core.worker', 'engines'})
        assert not bad, f"Forbidden imports in {target}: {bad}"


def test_render_does_not_emit_language_changes(qtbot, ui_snapshot):
    from ui.pages.console_page import ConsolePage
    page = ConsolePage(ui_snapshot)
    qtbot.addWidget(page)

    spy_source = QSignalSpy(page.source_changed)
    spy_target = QSignalSpy(page.target_changed)

    readiness = DailyReadiness(ready=True, reason="Sẵn sàng", action=None)
    run_state = DailyRunState(phase="stopped", message="Đã dừng", can_toggle=True, preview_enabled=True)

    page.render_daily(ui_snapshot, readiness, run_state)

    assert len(spy_source) == 0
    assert len(spy_target) == 0


def test_primary_action_emits_one_toggle(qtbot, ui_snapshot):
    from ui.pages.console_page import ConsolePage
    page = ConsolePage(ui_snapshot)
    qtbot.addWidget(page)

    spy = QSignalSpy(page.toggle_requested)
    page.primary_btn.click()
    assert len(spy) == 1


def test_provider_render_does_not_request_a_change(qtbot, ui_snapshot):
    from ui.pages.console_page import ConsolePage
    page = ConsolePage(ui_snapshot)
    qtbot.addWidget(page)
    page.set_provider_choices(('Google Translate', 'OpenAI'))
    changes = QSignalSpy(page.provider_changed)
    page.render_summary(ui_snapshot)
    page.apply_theme('dark')
    assert len(changes) == 0
    assert page.provider_combo.currentData() == 'OpenAI'
    assert not page.provider_combo.itemIcon(0).isNull()



def test_copy_uses_presented_translation_plain_text(qtbot):
    from PyQt5.QtWidgets import QApplication
    from ui.widgets.translation_output import TranslationOutputWidget
    widget = TranslationOutputWidget()
    qtbot.addWidget(widget)
    assert not widget.copy_btn.isEnabled()
    pair = PresentedPair('原文', '<b>Đường phía trước</b>')
    widget.render(PresentedTranslation(1, 'subtitle', 1, (pair,)))
    widget.apply_theme('dark')
    widget.copy_btn.click()
    assert QApplication.clipboard().text() == '<b>Đường phía trước</b>'
    assert widget.source_edit.toPlainText() == '原文'


def test_details_collapsed_and_log_bounded_to_300(qtbot, ui_snapshot):
    from ui.pages.console_page import ConsolePage
    page = ConsolePage(ui_snapshot)
    qtbot.addWidget(page)

    assert page.details_container.isHidden() or not page.is_details_expanded()
    assert page.log_view.maximumBlockCount() == 300

    for i in range(350):
        page.append_log(f"log line {i}")

    assert page.log_view.blockCount() == 300


def test_snapshot_letterbox_aligns_region_rectangles(qtbot):
    from ui.widgets.capture_snapshot import CaptureSnapshotWidget

    widget = CaptureSnapshotWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 100)

    # 100x100 image into 200x100 widget -> draw_w=100, draw_h=100, offset_x=50, offset_y=0
    image = QImage(100, 100, QImage.Format_ARGB32)
    image.fill(QColor(0, 0, 0))

    region1 = CaptureRegion("reg-1", "Vùng 1", NormalizedRect(0.1, 0.2, 0.3, 0.4), enabled=True)
    region_disabled = CaptureRegion("reg-2", "Vùng tắt", NormalizedRect(0.0, 0.0, 0.5, 0.5), enabled=False)
    exclusion = NormalizedRect(0.5, 0.5, 0.2, 0.2)
    profile = CaptureProfile(1, "desktop", None, None, (region1, region_disabled), (exclusion,))
    geom = CaptureGeometry(Rect(0, 0, 100, 100), ScreenMapping("s", Rect(0, 0, 100, 100), Rect(0, 0, 100, 100)), (100, 100))
    context = CaptureContext(1, 1, "desktop", None, geom)

    widget.set_snapshot(image, profile, context)

    rects = widget.aligned_rectangles()
    # Expect 2 rectangles: region1 and exclusion (disabled region omitted from active outlines)
    assert len(rects) == 2
    # rect format: (label, QRectF, is_exclusion)
    r1_label, r1_rect, r1_excl = rects[0]
    assert r1_label == "Vùng 1"
    assert not r1_excl
    assert abs(r1_rect.x() - 60.0) < 1.0
    assert abs(r1_rect.y() - 20.0) < 1.0
    assert abs(r1_rect.width() - 30.0) < 1.0
    assert abs(r1_rect.height() - 40.0) < 1.0

    ex_label, ex_rect, ex_excl = rects[1]
    assert ex_excl
    assert abs(ex_rect.x() - 100.0) < 1.0
    assert abs(ex_rect.y() - 50.0) < 1.0
    assert abs(ex_rect.width() - 20.0) < 1.0
    assert abs(ex_rect.height() - 20.0) < 1.0


def test_ocr_text_is_plain_selectable_text(qtbot):
    from ui.widgets.translation_output import TranslationOutputWidget

    widget = TranslationOutputWidget()
    qtbot.addWidget(widget)

    raw_source = '<script>alert("xss")</script>\nLine 2'
    raw_trans = '&lt;script&gt;\nDòng 2'
    presentation = PresentedTranslation(
        revision=1,
        mode="subtitle",
        sequence=1,
        pairs=(PresentedPair(raw_source, raw_trans),),
    )

    widget.render(presentation)

    assert widget.source_edit.isReadOnly()
    assert widget.target_edit.isReadOnly()
    assert bool(widget.source_edit.textInteractionFlags() & Qt.TextSelectableByMouse)
    assert bool(widget.target_edit.textInteractionFlags() & Qt.TextSelectableByMouse)
    assert widget.source_edit.toPlainText() == raw_source
    assert widget.target_edit.toPlainText() == raw_trans


def test_paused_translation_retry_remains_visible_when_details_closed(qtbot, ui_snapshot):
    from ui.pages.console_page import ConsolePage
    page = ConsolePage(ui_snapshot)
    qtbot.addWidget(page)

    assert page.details_container.isHidden() or not page.is_details_expanded()

    status = TranslationStatus("Google Translate", 1, 1, "paused", 3)
    page.render_translation_status(status, now_s=100.0)

    assert not page.retry_translation_btn.isHidden()
    assert page.retry_translation_btn.isEnabled()
    assert not page.translation_message.isHidden()
    assert page.details_container.isHidden() or not page.is_details_expanded()


def test_console_summary_is_silent_and_preserves_run_status(qtbot, ui_snapshot):
    from ui.pages.console_page import ConsolePage
    page = ConsolePage(ui_snapshot)
    qtbot.addWidget(page)
    page.set_run_status('Running')
    spy = QSignalSpy(page.toggle_requested)
    page.render_summary(ui_snapshot)
    assert '800 × 600' in page.region_info_lbl.text()
    assert page.readiness_lbl.text() == 'Running'
    assert page.provider_combo.currentData() == 'OpenAI'
    assert not page.provider_combo.itemIcon(0).isNull()

    assert len(spy) == 0
    page.render_summary(replace(ui_snapshot, ocr=replace(ui_snapshot.ocr, region=None)))
    assert 'Chưa chọn vùng' in page.region_info_lbl.text()

    for button, signal in [
        (page.primary_btn, page.toggle_requested),
        (page.select_region_btn, page.select_region_requested),
        (page.subtitle_settings_btn, page.subtitle_settings_requested),
    ]:
        action = QSignalSpy(signal)
        button.click()
        assert len(action) == 1


@pytest.mark.parametrize('height', [480, 720, 920])
def test_console_layout_fits_and_scrolls_on_first_show(qapp, ui_window, ui_snapshot, height):
    page = ui_window.console_page
    page.render_summary(ui_snapshot)
    ui_window.resize(740, height)
    ui_window.show()
    qapp.processEvents()

    assert page.primary_btn.isVisible()
    assert page.snapshot_widget.isVisible()
    assert page.output_widget.isVisible()

    page._toggle_details()
    qapp.processEvents()
    page.ensureWidgetVisible(page.clear_log_btn)
    qapp.processEvents()
    button = page.clear_log_btn
    assert page.viewport().rect().contains(QRect(button.mapTo(page.viewport(), QPoint()), button.size()))
