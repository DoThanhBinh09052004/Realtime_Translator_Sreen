import json
from dataclasses import replace
from pathlib import Path

from PyQt5.QtTest import QSignalSpy

from core import config


def test_invalid_endpoint_save_does_not_reconfigure(ui_window):
    ui_window.provider_combo.setCurrentText('Custom API')
    coordinator = ui_window.settings_coordinator
    assert coordinator.set_api_key('fake-key', persist=False)
    assert coordinator.set_custom_base_url('https://api.example.test/v1')
    path = Path(config.CONFIG_PATH)
    original = path.read_bytes()
    ui_window.worker.reset_mock()
    editor = ui_window.ai_page.base_url_input
    editor.setText('http://remote.example.test/v1')
    editor.editingFinished.emit()
    assert path.read_bytes() == original
    assert config.load_provider_api_key('Custom API') == 'fake-key'
    ui_window.worker.configure.assert_not_called()
    assert editor.text() == 'https://api.example.test/v1'
    assert 'HTTPS' in ui_window.status.text()
    assert 'remote.example.test' not in ui_window.status.text()


def test_valid_localhost_save_renders_canonical_url(ui_window):
    ui_window.provider_combo.setCurrentText('Custom API')
    ui_window.worker.reset_mock()
    editor = ui_window.ai_page.base_url_input
    editor.setText('http://LOCALHOST:8000/v1/')
    editor.editingFinished.emit()
    assert editor.text() == 'http://127.0.0.1:8000/v1'
    assert ui_window.settings_coordinator.snapshot().ai.base_url == 'http://127.0.0.1:8000/v1'
    ui_window.worker.configure.assert_called_once()


def test_base_url_render_does_not_save_or_overwrite_key_draft(ui_window):
    ui_window.provider_combo.setCurrentText('Custom API')
    page = ui_window.ai_page
    page.api_key_input.setText('unsaved-key-draft')
    spy = QSignalSpy(page.base_url_changed)
    state = replace(ui_window.settings_coordinator.snapshot().ai, base_url='https://new.example.test/v1')
    page.render(state, changed_field='base_url')
    assert page.base_url_input.text() == 'https://new.example.test/v1'
    assert page.api_key_input.text() == 'unsaved-key-draft'
    assert list(spy) == []


def test_legacy_unsafe_endpoint_keeps_provider_key_and_requires_url(qtbot):
    from unittest.mock import Mock
    from ui.controller import ControllerWindow
    config.save_provider_api_key('Custom API', 'fake-key', persist=False)
    path = Path(config.CONFIG_PATH)
    original = json.dumps({'current_provider': 'Custom API', 'custom_api_base_url': 'http://remote.example.test/v1',
                           'provider_models': {'Custom API': 'test-model'}}).encode()
    path.write_bytes(original)
    worker = Mock()
    worker.interval.return_value = 500
    window = ControllerWindow(worker, config.State(), Mock(), Mock())
    qtbot.addWidget(window)
    assert window.provider_combo.currentText() == 'Custom API'
    assert window.ai_page.base_url_input.text() == ''
    assert 'Base URL' in window.ai_page.api_status_lbl.text()
    assert config.load_provider_api_key('Custom API') == 'fake-key'
    assert path.read_bytes() == original
    worker.start_worker.assert_not_called()
