from core.contracts import TranslationStatus


def test_paused_current_google_shows_retry_only_while_running(ui_window):
    w=ui_window.worker
    w.revision=2; w.translation_session_id=1; w.is_running.return_value=True
    w.retry_translation.return_value=True
    ui_window.show_translation_status(TranslationStatus('Google Translate',2,1,'paused',3))
    assert not ui_window.console_page.retry_translation_btn.isHidden()
    for _ in range(10): ui_window.retry_translation()
    w.retry_translation.assert_called_once()
    assert not ui_window.console_page.retry_translation_btn.isEnabled()
    ui_window.stop_ocr()
    assert ui_window.console_page.retry_translation_btn.isHidden()


def test_queued_old_provider_or_session_status_is_ignored(ui_window):
    w=ui_window.worker
    w.revision=3; w.translation_session_id=2; w.is_running.return_value=True
    for status in [TranslationStatus('Google Translate',2,2,'paused'),TranslationStatus('Google Translate',3,1,'paused'),TranslationStatus('OpenAI',3,2,'paused')]:
        ui_window.show_translation_status(status)
        assert ui_window.console_page.retry_translation_btn.isHidden()


def test_waiting_message_counts_down_without_triggering_retry(qtbot,ui_window):
    page=ui_window.console_page
    page.render_translation_status(TranslationStatus('Google Translate',1,1,'retry_wait',1,130),now_s=100)
    assert '30' in page.translation_message.text()
    page.render_translation_status(TranslationStatus('Google Translate',1,1,'retry_wait',1,130),now_s=110)
    assert '20' in page.translation_message.text()
    assert page.retry_translation_btn.isHidden()
    ui_window.worker.retry_translation.assert_not_called()


def test_failed_setting_save_preserves_paused_google_retry(ui_window,monkeypatch):
    from unittest.mock import Mock
    from core import config
    w=ui_window.worker
    w.revision=3; w.translation_session_id=1; w.is_running.return_value=True
    ui_window.show_translation_status(TranslationStatus('Google Translate',3,1,'paused',3))
    monkeypatch.setattr(config.os,'replace',Mock(side_effect=OSError('disk full')))
    ui_window.provider_combo.setCurrentText('OpenAI')
    assert ui_window.provider_combo.currentText()=='Google Translate'
    assert not ui_window.console_page.retry_translation_btn.isHidden()
    assert not ui_window.settings_coordinator.set_subtitle_style({'font_size':30})
    assert not ui_window.console_page.retry_translation_btn.isHidden()
