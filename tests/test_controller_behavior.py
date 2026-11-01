from PyQt5.QtWidgets import QPushButton
from core import config


def test_missing_key_routes_to_ai_without_starting(ui_window):
    ui_window.provider_combo.setCurrentText('Google Gemini')
    ui_window.worker.reset_mock()
    ui_window.start_ocr()
    assert ui_window.pages.currentIndex() == 1
    assert 'API Key' in ui_window.status.text()
    ui_window.worker.start_worker.assert_not_called()


def test_start_stop_and_callbacks_once(ui_window):
    from core.capture.models import CaptureProfile,CaptureRegion,NormalizedRect
    # Daily controls use the same explicitly bound profile as production.
    profile=CaptureProfile(1,'desktop','test',None,(CaptureRegion('11111111-1111-4111-8111-111111111111','Dialogue',NormalizedRect(0.,0.,1.,1.),True),),())
    config.save_capture_profile(profile,setup_complete=True)
    worker=ui_window.worker
    worker.is_running.return_value=False
    worker.isRunning.return_value=False
    worker.is_drained=True
    worker.restart_pending=False
    def running(value):
        worker.is_running.return_value=value
        worker.is_drained=not value
    worker.start_worker.side_effect=lambda:running(True)
    worker.stop_worker.side_effect=lambda:running(False)
    ui_window.set_capture_profile_state(profile,bound=True)
    config.save_region(config.DEFAULT_REGION, setup_complete=True)
    ui_window.provider_combo.setCurrentText('Google Gemini')
    ui_window.settings_coordinator.set_api_key('fake-test-key')
    ui_window.start_btn.click()
    ui_window.worker.start_worker.assert_called_once_with()
    assert ui_window.console_page.primary_btn.text() == '■ DỪNG DỊCH'
    ui_window.stop_btn.click()
    ui_window.worker.stop_worker.assert_called_once_with()
    assert ui_window.console_page.primary_btn.text() == '▶ BẮT ĐẦU DỊCH'
    buttons = ui_window.findChildren(QPushButton)
    ui_window.console_page.select_region_btn.click()
    ui_window.on_select_region_cb.assert_called_once_with()
    next(b for b in buttons if b.text().strip() == 'Thoát').click()
    ui_window.on_quit_cb.assert_called_once()
