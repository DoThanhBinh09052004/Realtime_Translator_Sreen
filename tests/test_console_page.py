from dataclasses import replace
from PyQt5.QtTest import QSignalSpy


def test_console_summary_is_silent_and_preserves_run_status(qtbot, ui_snapshot):
    from ui.pages.console_page import ConsolePage
    page = ConsolePage(ui_snapshot)
    qtbot.addWidget(page)
    page.set_run_status('Running')
    spy = QSignalSpy(page.start_requested)
    page.render_summary(ui_snapshot)
    assert '800 x 600' in page.metric_cards['region'].val_lbl.text()
    assert page.metric_cards['status'].val_lbl.text() == 'Running'
    assert page.metric_cards['ai'].val_lbl.text() == 'OpenAI\nfake-model'
    assert len(spy) == 0
    page.render_summary(replace(ui_snapshot, ocr=replace(ui_snapshot.ocr, region=None)))
    assert page.metric_cards['region'].val_lbl.text() == 'Chưa chọn vùng'
    for button, signal in [(page.start_btn, page.start_requested), (page.stop_btn, page.stop_requested),
                           (page.select_region_btn, page.select_region_requested),
                           (page.subtitle_settings_btn, page.subtitle_settings_requested)]:
        action = QSignalSpy(signal)
        button.click()
        assert len(action) == 1
