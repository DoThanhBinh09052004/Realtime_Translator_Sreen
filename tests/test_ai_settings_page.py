from dataclasses import replace
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QLineEdit

def test_context_controls_render_without_saving_or_touching_editors(qtbot,ui_snapshot):
    from ui.pages.ai_settings_page import AiSettingsPage
    from core.dialogue.context_models import ContextStatus
    state=replace(ui_snapshot.ai,context_enabled=True,context_supported=True)
    page=AiSettingsPage(state,('OpenAI',));qtbot.addWidget(page)
    spy=QSignalSpy(page.context_enabled_changed)
    page.api_key_input.setText('unsaved')
    page.render(state,changed_field='context_enabled')
    page.render_context_status(ContextStatus('text_fallback',1))
    assert page.context_checkbox.isChecked() and page.context_reset_button.isEnabled()
    assert 'ngữ cảnh gần đây' in page.context_status_label.text()
    assert page.api_key_input.text()=='unsaved' and len(spy)==0


def test_ai_render_keeps_editors_and_blocks_saves(qtbot, ui_snapshot):
    from ui.pages.ai_settings_page import AiSettingsPage
    page = AiSettingsPage(ui_snapshot.ai, ('Google Gemini', 'OpenAI'))
    qtbot.addWidget(page)
    spies = [QSignalSpy(signal) for signal in (page.provider_changed, page.model_changed, page.api_key_changed)]
    page.toggle_key_visibility()
    page.api_key_input.setSelection(2, 4)
    page.model_combo.lineEdit().setCursorPosition(3)
    page.render(ui_snapshot.ai, changed_field='api_key')
    page.render(ui_snapshot.ai, changed_field='model')
    assert page.api_key_input.selectedText() == 'ke-t'
    assert page.api_key_input.echoMode() == QLineEdit.Normal
    assert page.model_combo.lineEdit().cursorPosition() == 3
    assert not any(len(spy) for spy in spies)
    changed = replace(ui_snapshot.ai, provider='Google Gemini', model_id='custom-other', models=('suggested',), api_key='other-key')
    page.render(changed, changed_field='provider')
    assert page.model_combo.currentText() == 'custom-other'
    assert page.api_key_input.text() == 'other-key'
    assert not any(len(spy) for spy in spies)
    page.provider_combo.setCurrentText('OpenAI')
    page.api_key_input.setText('new-key')
    assert list(spies[0]) == [['OpenAI']]
    assert list(spies[2]) == []
    page.save_key_btn.click()
    assert list(spies[2]) == [['new-key']]
    page.render(ui_snapshot.ai, changed_field='rollback')
    assert page.api_key_input.text() == 'fake-test-key'


def test_highlight_timer_belongs_to_page(qtbot, ui_snapshot):
    from ui.pages.ai_settings_page import AiSettingsPage
    from PyQt5 import sip
    page = AiSettingsPage(ui_snapshot.ai, ('OpenAI',))
    page.highlight_missing_key()
    timer = page.findChild(QTimer)
    assert timer is not None and timer.isSingleShot() and timer.interval() == 2500
    sip.delete(page)
    assert sip.isdeleted(timer)
