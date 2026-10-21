from dataclasses import replace
from unittest.mock import Mock
from PyQt5.QtTest import QSignalSpy
from core import config


def test_ocr_render_is_silent_and_user_changes_emit_once(qtbot, ui_snapshot):
    from ui.pages.ocr_settings_page import OcrSettingsPage
    page = OcrSettingsPage(ui_snapshot.ocr, ('English', 'Japanese'), ('Vietnamese', 'English'))
    qtbot.addWidget(page)
    spies = [QSignalSpy(signal) for signal in (page.source_changed, page.target_changed, page.interval_changed, page.select_region_requested)]
    page.render(replace(ui_snapshot.ocr, interval_ms=800))
    assert not any(len(spy) for spy in spies)
    assert (page.interval_spin.minimum(), page.interval_spin.maximum(), page.interval_spin.singleStep()) == (100, 3000, 50)
    assert page.interval_spin.suffix() == ' ms'
    assert page.interval_spin.value() == 800
    assert 'X=-100' in page.reg_info_lbl.text()
    page.src_combo.setCurrentText('Japanese')
    page.tgt_combo.setCurrentText('English')
    page.interval_spin.setValue(900)
    page.select_region_btn.click()
    assert [list(spy) for spy in spies] == [[['Japanese']], [['English']], [[900]], [[]]]


def test_window_initializes_saved_interval_once(qtbot):
    from ui.controller import ControllerWindow
    config.save_config('interval_ms', 800)
    worker = Mock()
    worker.interval.return_value = 500
    window = ControllerWindow(worker, config.State(), Mock(), Mock())
    qtbot.addWidget(window)
    worker.setInterval.assert_called_once_with(800)
    assert window.interval_spin.value() == 800
