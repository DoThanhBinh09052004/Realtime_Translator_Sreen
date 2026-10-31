from dataclasses import replace
import pytest
from PyQt5.QtCore import QPoint, QRect
from PyQt5.QtTest import QSignalSpy


def test_console_summary_is_silent_and_preserves_run_status(qtbot, ui_snapshot):
    from ui.pages.console_page import ConsolePage
    page = ConsolePage(ui_snapshot)
    qtbot.addWidget(page)
    page.set_run_status('Running')
    spy = QSignalSpy(page.toggle_requested)
    page.render_summary(ui_snapshot)
    assert '800 x 600' in page.metric_cards['region'].val_lbl.text()
    assert page.metric_cards['status'].val_lbl.text() == 'Running'
    assert page.metric_cards['ai'].val_lbl.text() == 'OpenAI\nfake-model'
    assert len(spy) == 0
    page.render_summary(replace(ui_snapshot, ocr=replace(ui_snapshot.ocr, region=None)))
    assert page.metric_cards['region'].val_lbl.text() == 'Chưa chọn vùng'

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
