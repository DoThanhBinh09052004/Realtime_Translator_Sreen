from pathlib import Path
from unittest.mock import Mock
from core import config


def test_google_ui_hides_credentials_and_can_start(ui_window):
    page=ui_window.ai_page
    assert ui_window.settings_coordinator.snapshot().ai.provider=='Google Translate'
    assert page.model_container.isHidden() and page.key_card.isHidden() and page.guide_card.isHidden()
    assert 'không cần API key' in page.google_note.text()
    ui_window.worker.reset_mock(); ui_window.start_ocr()
    ui_window.worker.start_worker.assert_called_once()
    ui_window.provider_combo.setCurrentText('OpenAI')
    assert not page.key_card.isHidden() and not page.model_container.isHidden()


def test_queued_google_model_key_signal_cannot_write_env(ui_window):
    c=ui_window.settings_coordinator
    before=Path(config.CONFIG_PATH).read_bytes() if Path(config.CONFIG_PATH).exists() else None
    ui_window.worker.reset_mock()
    assert not c.set_model('queued AI model')
    assert not c.set_api_key('queued fake-key')
    assert not Path(config.ENV_PATH).exists()
    assert before==(Path(config.CONFIG_PATH).read_bytes() if Path(config.CONFIG_PATH).exists() else None)
    ui_window.worker.configure.assert_not_called()


def test_failed_provider_save_keeps_visible_tool_and_worker(ui_window,monkeypatch):
    before=ui_window.settings_coordinator.snapshot()
    monkeypatch.setattr(config.os,'replace',Mock(side_effect=OSError('disk full')))
    ui_window.worker.reset_mock()
    ui_window.provider_combo.setCurrentText('OpenAI')
    assert ui_window.provider_combo.currentText()=='Google Translate'
    assert ui_window.settings_coordinator.snapshot()==before
    ui_window.worker.configure.assert_not_called()
