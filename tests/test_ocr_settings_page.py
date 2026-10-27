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


def test_installed_choices_and_management_action_are_separate(qtbot, ui_snapshot):
    from ui.controller_state import LanguageChoice
    from ui.pages.ocr_settings_page import OcrSettingsPage
    choices = (LanguageChoice('en', 'English', 'English'), LanguageChoice('ja', 'Japanese', 'Japanese'))
    page = OcrSettingsPage(replace(ui_snapshot.ocr, source_choices=choices), (), ('Vietnamese', 'English'))
    qtbot.addWidget(page)
    changed, manage = QSignalSpy(page.source_changed), QSignalSpy(page.manage_packs_requested)
    assert page.src_combo.count() == 4
    assert page.src_combo.itemData(0) == 'en'
    page.src_combo.setCurrentIndex(3)
    assert page.src_combo.currentText() == 'English'
    assert not changed and list(manage) == [[]]
    page.src_combo.setCurrentIndex(1)
    assert list(changed) == [['Japanese']]
    page.update_source_choices(choices + (LanguageChoice('zh-Hans', 'Chinese', 'Chinese'),), 'Japanese')
    assert page.src_combo.currentText() == 'Japanese' and len(changed) == 1


def test_missing_source_remains_unselected_until_pack_arrives(qtbot, ui_snapshot):
    from ui.controller_state import LanguageChoice
    from ui.pages.ocr_settings_page import OcrSettingsPage
    state = replace(ui_snapshot.ocr, source='Chinese', source_choices=(), source_notice='Thiếu gói Chinese.')
    page = OcrSettingsPage(state, ('English', 'Japanese'), ('Vietnamese', 'English'))
    qtbot.addWidget(page)
    changed = QSignalSpy(page.source_changed)
    assert page.src_combo.currentIndex() == -1
    assert 'Chọn ngôn ngữ đã cài' == page.src_combo.placeholderText()
    assert page.source_notice_label.text() == 'Thiếu gói Chinese.'
    page.render(replace(state, source_choices=(LanguageChoice('zh-Hans', 'Chinese', 'Chinese'),), source_notice=''))
    assert page.src_combo.currentText() == 'Chinese' and not changed
