from pathlib import Path
from unittest.mock import Mock

from PyQt5.QtCore import Qt

from core import config


def test_typing_key_does_not_save_until_explicit_apply(qtbot, ui_window):
    ui_window.provider_combo.setCurrentText('OpenAI')
    ui_window.worker.reset_mock()
    page = ui_window.ai_page
    page.api_key_input.setText('fake-draft-key')
    assert config.load_provider_api_key('OpenAI') == ''
    ui_window.worker.configure.assert_not_called()
    page.persist_key_checkbox.setChecked(False)
    qtbot.mouseClick(page.save_key_btn, Qt.LeftButton)
    assert config.load_provider_api_key('OpenAI') == 'fake-draft-key'
    assert config.provider_key_storage('OpenAI') == 'session'
    ui_window.worker.configure.assert_called_once()
    assert not list(config.get_secret_store()._directory.glob('*.bin'))


def test_delete_key_updates_worker_and_ui(qtbot, ui_window):
    page = ui_window.ai_page
    ui_window.provider_combo.setCurrentText('OpenAI')
    page.api_key_input.setText('fake-key')
    qtbot.mouseClick(page.save_key_btn, Qt.LeftButton)
    assert config.provider_key_storage('OpenAI') == 'saved'
    ui_window.worker.reset_mock()
    qtbot.mouseClick(page.delete_key_btn, Qt.LeftButton)
    assert config.load_provider_api_key('OpenAI') == ''
    assert page.api_key_input.text() == ''
    ui_window.worker.configure.assert_called_once()


def test_failed_dpapi_save_can_be_applied_in_session_without_retyping(qtbot, ui_window, monkeypatch):
    from core.secrets import SecretStoreError
    ui_window.provider_combo.setCurrentText('OpenAI')
    page = ui_window.ai_page
    page.api_key_input.setText('fake-draft-key')
    monkeypatch.setattr(config.get_secret_store()._protector, 'protect', Mock(side_effect=SecretStoreError('failed')))
    ui_window.worker.reset_mock()
    qtbot.mouseClick(page.save_key_btn, Qt.LeftButton)
    assert page.api_key_input.text() == 'fake-draft-key'
    assert config.load_provider_api_key('OpenAI') == ''
    ui_window.worker.configure.assert_not_called()
    page.persist_key_checkbox.setChecked(False)
    qtbot.mouseClick(page.save_key_btn, Qt.LeftButton)
    assert config.load_provider_api_key('OpenAI') == 'fake-draft-key'
    assert 'fake-draft-key' not in ui_window.status.text()


def test_explicit_ui_import_can_keep_legacy_file(qtbot, ui_window, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox
    ui_window.provider_combo.setCurrentText('OpenAI')
    path = Path(config.ENV_PATH)
    path.write_text('OPENAI_API_KEY=legacy-secret\nOTHER=keep\n')
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.No)
    qtbot.mouseClick(ui_window.ai_page.import_key_btn, Qt.LeftButton)
    assert config.load_provider_api_key('OpenAI') == 'legacy-secret'
    assert ui_window.api_key_input.text() == 'legacy-secret'
    assert 'OPENAI_API_KEY=legacy-secret' in path.read_text()
