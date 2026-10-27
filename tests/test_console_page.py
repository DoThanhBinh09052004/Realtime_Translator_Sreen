from dataclasses import replace
import pytest
from PyQt5.QtCore import QPoint, QRect
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


@pytest.mark.parametrize('height', [480, 720, 920])
def test_console_metrics_do_not_overlap_on_first_show(qapp, ui_window, ui_snapshot, height):
    page = ui_window.console_page
    page.render_summary(ui_snapshot)
    ui_window.resize(740, height)
    ui_window.show()
    qapp.processEvents()

    cards = list(page.metric_cards.values())
    container = cards[0].parentWidget()
    for index, card in enumerate(cards):
        assert container.rect().contains(card.geometry()), card.geometry()
        for other in cards[index + 1:]:
            assert not card.geometry().intersects(other.geometry())
        label = card.val_lbl
        metrics = label.fontMetrics()
        text_height = metrics.height() + metrics.lineSpacing() * (len(label.text().splitlines()) - 1)
        assert label.contentsRect().height() >= text_height

    page.ensureWidgetVisible(page.clear_log_btn)
    qapp.processEvents()
    button = page.clear_log_btn
    assert page.viewport().rect().contains(QRect(button.mapTo(page.viewport(), QPoint()), button.size()))
