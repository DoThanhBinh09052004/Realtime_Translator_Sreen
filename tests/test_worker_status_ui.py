from dataclasses import replace
from threading import Event

import numpy as np
import pytest

from core import config
from core.contracts import EngineError, TranslationResult, TranslationStatus
from core.worker import TranslationWorker
from ui.controller import ControllerWindow


@pytest.fixture
def worker_window(qtbot, monkeypatch):
    import core.worker as module
    monkeypatch.setattr(module, 'compact_memory', lambda: None)
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION, 100)
    window = ControllerWindow(worker, worker.state, lambda: None, lambda: None)
    qtbot.addWidget(window)
    yield window
    worker.stop_worker()
    assert worker.wait(2000) and worker._block_translator.wait(2000)


def test_capture_startup_failure_stops_ui_and_explains_error(qtbot, worker_window):
    # The collection-time capture guard fails at the real worker boundary.
    window = worker_window
    window.start_ocr()
    qtbot.waitUntil(lambda: not window.worker.isRunning()
                    and not window.worker._block_translator.isRunning())
    qtbot.waitUntil(lambda: window.status.text() == 'Đã dừng', timeout=1000)
    assert window.metric_cards['status'].val_lbl.text() == 'Đã dừng'
    log = window.console_page.log_view.toPlainText()
    assert 'Không thể mở bộ chụp màn hình' in log
    assert 'Chọn lại vùng quét' in log
    assert window.console_page.retry_translation_btn.isHidden()


def test_ocr_error_is_visible_without_erasing_google_pause(worker_window):
    window = worker_window
    window.console_page.render_translation_status(
        TranslationStatus('Google Translate', 1, 1, 'paused', 3), now_s=0)
    window.worker.error_occurred.emit(
        EngineError('ocr', 'Không thể nhận diện chữ trong ảnh.', True))
    log = window.console_page.log_view.toPlainText()
    assert 'Không thể nhận diện chữ trong ảnh.' in log
    assert 'ngôn ngữ nguồn' in log
    assert not window.console_page.retry_translation_btn.isHidden()
    assert window.metric_cards['status'].val_lbl.text() == 'Tạm dừng dịch Google'


@pytest.mark.parametrize('restart', ['start', 'mode'])
def test_old_capture_finish_does_not_stop_requested_restart(
        qtbot, monkeypatch, worker_window, runtime_settings, capture_geometry, restart):
    import core.worker as module
    entered, release = Event(), Event()

    class Service:
        def __init__(self, **kwargs): pass
        def translate(self, *args):
            entered.set()
            assert release.wait(5)
            return TranslationResult('Xin chào')
        def close(self): pass

    class Capture:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def grab(self, region):
            return np.zeros((region['height'], region['width'], 4), dtype='uint8')

    monkeypatch.setattr(module, 'TranslationService', Service)
    monkeypatch.setattr(module.mss, 'mss', Capture)
    window = worker_window
    worker = window.worker
    settings = replace(runtime_settings, interval_ms=100, provider=replace(
        runtime_settings.provider, name='Google Translate', api_key='', model_id=''))
    worker.configure(settings)
    worker.set_region(dict(left=100, top=100, width=800, height=600))
    worker.set_capture_geometry(capture_geometry)
    window.start_ocr()
    try:
        qtbot.waitUntil(entered.is_set)
        if restart == 'start':
            window.stop_ocr()
            window.start_ocr()
        else:
            worker.configure(replace(settings, overlay_mode='blocks'))
        qtbot.waitUntil(lambda: not worker.isRunning())
        qtbot.wait(30)  # Deliver finished while the old backend is still draining.
        assert window.status.text() == 'Đang hoạt động'
        assert window.metric_cards['status'].val_lbl.text() == 'Đang hoạt động'
        release.set()
        qtbot.waitUntil(lambda: worker.is_running() and worker.isRunning())
        # A delayed notification from an older capture must also respect live state.
        worker.finished.emit()
        assert window.status.text() == 'Đang hoạt động'
    finally:
        release.set()
