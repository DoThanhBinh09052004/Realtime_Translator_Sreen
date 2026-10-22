from PyQt5.QtWidgets import QPushButton
from core import config


def test_missing_key_routes_to_ai_without_starting(ui_window):
    ui_window.worker.reset_mock()
    ui_window.start_ocr()
    assert ui_window.pages.currentIndex() == 1
    assert 'API Key' in ui_window.status.text()
    ui_window.worker.start_worker.assert_not_called()


def test_start_stop_and_callbacks_once(ui_window):
    config.save_provider_api_key(config.load_active_provider(), 'fake-test-key')
    ui_window.start_btn.click()
    ui_window.worker.start_worker.assert_called_once_with()
    assert ui_window.metric_cards['status'].val_lbl.text() == 'Đang hoạt động'
    ui_window.stop_btn.click()
    ui_window.worker.stop_worker.assert_called_once_with()
    assert ui_window.metric_cards['status'].val_lbl.text() == 'Đã dừng'
    buttons = ui_window.findChildren(QPushButton)
    next(b for b in buttons if b.text().strip() == 'Chọn lại vùng quét').click()
    ui_window.on_select_region_cb.assert_called_once_with()
    next(b for b in buttons if b.text().strip() == 'Thoát').click()
    ui_window.on_quit_cb.assert_called_once()
