from dataclasses import replace
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtTest import QSignalSpy
from core import config
from core.language_pack_contracts import PackError, PackSnapshot, PackState


def pack(language_id, state='installed', **changes):
    bundled = language_id in ('en', 'ja')
    values = dict(language_id=language_id, state=state, origin='bundled' if bundled else 'downloaded',
                  revision='fixture', removable=not bundled, in_use=False, installed_bytes=2048,
                  reclaimable_bytes=0 if bundled else 2048)
    return PackState(**(values | changes))


class FakeManager(QObject):
    snapshot_changed = pyqtSignal(object)

    def __init__(self, rows=None):
        super().__init__()
        self.value = PackSnapshot(tuple(rows or (pack('en'), pack('ja'), pack('zh-Hans', 'not_installed', origin='none'))))
        self.selected = None
        self.request_install = Mock()
        self.request_remove = Mock()
        self.cancel = Mock()
        self.refresh = Mock()

    def snapshot(self):
        return self.value

    def set_selected_language(self, language_id):
        self.selected = language_id

    def publish(self, rows, busy=False):
        self.value = PackSnapshot(tuple(rows), 'fixture-operation' if busy else None, busy)
        self.snapshot_changed.emit(self.value)


def window_with_manager(qtbot, *, source='English', running=False):
    from ui.controller import ControllerWindow
    state = config.State()
    state.update(source=source)
    config.save_active_provider('Google Translate')
    manager = FakeManager()
    worker = Mock()
    worker.is_running.return_value = running
    worker.interval.return_value = 500
    window = ControllerWindow(worker, state, Mock(), Mock(), pack_manager=manager)
    qtbot.addWidget(window)
    return window, manager, worker


@pytest.mark.parametrize('running', [False, True])
def test_install_updates_choices_without_source_runtime_or_start(qtbot, running):
    window, manager, worker = window_with_manager(qtbot, running=running)
    before = config.load_config()
    window.console_page.clear_translation_status = Mock()
    manager.publish((pack('en'), pack('ja'), pack('zh-Hans')))
    assert window.src_combo.count() == 5
    assert window.src_combo.currentText() == 'English'
    assert config.load_config() == before
    worker.configure.assert_not_called()
    worker.start_worker.assert_not_called()
    window.console_page.clear_translation_status.assert_not_called()
    window.src_combo.setCurrentText('Chinese')
    assert config.load_config()['source_lang'] == 'Chinese'
    assert manager.selected == 'zh-Hans'
    worker.configure.assert_called_once()
    worker.start_worker.assert_not_called()
    assert worker.is_running() is running
    assert [window.tgt_combo.itemText(i) for i in range(window.tgt_combo.count())] == ['Vietnamese', 'English']


def test_manager_action_opens_one_dialog_and_close_preserves_service(qtbot):
    window, manager, worker = window_with_manager(qtbot)
    changed = QSignalSpy(window.ocr_page.source_changed)
    window.src_combo.setCurrentIndex(window.src_combo.count() - 1)
    dialog = window._language_packs_dialog
    assert dialog.isVisible()
    assert window.src_combo.currentText() == 'English' and not changed
    dialog.close()
    manager.publish((pack('en'), pack('ja'), pack('zh-Hans', 'downloading', downloaded_bytes=4, total_bytes=10)), True)
    window.src_combo.setCurrentIndex(window.src_combo.count() - 1)
    assert window._language_packs_dialog is dialog
    assert dialog.rows['zh-Hans'].progress.value() == 400
    dialog.cancel_requested.emit()
    manager.cancel.assert_called_once()
    dialog.close()
    manager.cancel.assert_called_once()
    worker.configure.assert_not_called()
    worker.start_worker.assert_not_called()


def test_missing_saved_source_blocks_all_start_intent_and_recovers_without_start(qtbot):
    window, manager, worker = window_with_manager(qtbot, source='Chinese')
    starting = QSignalSpy(window.starting_translation)
    before = config.load_config()
    assert window.src_combo.currentIndex() == -1
    assert 'Chinese' in window.ocr_page.source_notice_label.text()
    window.start_ocr()
    assert window._language_packs_dialog.isVisible()
    assert not starting
    worker.start_worker.assert_not_called()
    assert config.load_config() == before
    assert window.status.text() != 'Đang hoạt động'
    manager.publish((pack('en'), pack('ja'), pack('zh-Hans')))
    assert window.src_combo.currentText() == 'Chinese'
    assert not window.ocr_page.source_notice_label.text()
    worker.start_worker.assert_not_called()
    worker.configure.assert_not_called()
    window.start_ocr()
    assert len(starting) == 1
    worker.start_worker.assert_called_once()


def test_failed_source_save_rolls_back_selection_and_manager(qtbot, monkeypatch):
    window, manager, worker = window_with_manager(qtbot)
    def denied(*args):
        raise OSError('denied')
    monkeypatch.setattr(config.os, 'replace', denied)
    window.src_combo.setCurrentText('Japanese')
    assert window.src_combo.currentText() == 'English'
    assert window.state.source == 'English' and manager.selected == 'en'
    worker.configure.assert_not_called()


def test_removing_and_missing_sources_rejected_before_persist(qtbot):
    window, manager, worker = window_with_manager(qtbot)
    manager.publish((pack('en'), pack('ja'), pack('zh-Hans', 'removing')), True)
    before = config.load_config()
    assert not window.settings_coordinator.set_source('Chinese')
    assert config.load_config() == before
    worker.configure.assert_not_called()


def test_projection_protects_bundled_selected_and_busy_rows(qtbot):
    window, manager, worker = window_with_manager(qtbot)
    manager.publish((pack('en'), pack('ja'), pack('zh-Hans'), pack('ko', 'error',
                    error=PackError('network', 'Kiểm tra kết nối rồi thử lại.', True))))
    rows = {row.language_id: row for row in window.settings_coordinator.pack_dialog_state().rows}
    assert rows['en'].action is None and rows['ja'].action is None
    assert rows['zh-Hans'].action == 'remove' and rows['zh-Hans'].action_enabled
    assert rows['ko'].action == 'retry' and 'Kiểm tra' in rows['ko'].detail_text
    window.src_combo.setCurrentText('Chinese')
    rows = {row.language_id: row for row in window.settings_coordinator.pack_dialog_state().rows}
    assert not rows['zh-Hans'].action_enabled
    assert 'Chọn ngôn ngữ khác' in rows['zh-Hans'].action_reason
    manager.publish((pack('en'), pack('ja'), pack('zh-Hans'), pack('ko', 'downloading')), True)
    rows = {row.language_id: row for row in window.settings_coordinator.pack_dialog_state().rows}
    assert rows['ko'].action == 'cancel' and rows['ko'].action_enabled


def test_projection_shows_installed_size_and_protects_missing_bundle(qtbot):
    window, manager, worker = window_with_manager(qtbot)
    manager.publish((pack('en', 'not_installed', origin='none'), pack('ja'), pack('zh-Hans')))
    rows = {row.language_id: row for row in window.settings_coordinator.pack_dialog_state().rows}
    assert rows['en'].action is None and 'cài lại' in rows['en'].action_reason
    assert '2,048' in rows['zh-Hans'].detail_text


def test_switch_stop_close_and_late_completion_never_selects_or_restarts(qtbot):
    window, manager, worker = window_with_manager(qtbot, source='Japanese', running=True)
    window.open_language_packs()
    manager.publish((pack('en'), pack('ja'), pack('zh-Hans', 'downloading')), True)
    window.src_combo.setCurrentText('English')
    window.stop_ocr()
    window._language_packs_dialog.close()
    manager.publish((pack('en'), pack('ja'), pack('zh-Hans')))
    window.open_language_packs()
    assert window.src_combo.currentText() == 'English'
    assert window.state.source == 'English'
    worker.configure.assert_called_once()
    worker.start_worker.assert_not_called()
    worker.stop_worker.assert_called_once()


def test_native_missing_error_refreshes_readiness(qtbot):
    window, manager, worker = window_with_manager(qtbot)
    window.show_worker_error(Mock(code='ocr_model_missing', user_message='Thiếu gói OCR'))
    manager.refresh.assert_called_once()


def test_dialog_close_restores_source_focus(qtbot):
    window, manager, worker = window_with_manager(qtbot)
    window.show()
    window._switch_to_page(2)
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow)
    window.open_language_packs()
    window._language_packs_dialog.close()
    assert window.focusWidget() is window.src_combo


def test_deleting_inactive_pack_removes_choice_without_selecting_or_configuring(qtbot):
    window, manager, worker = window_with_manager(qtbot)
    manager.publish((pack('en'), pack('ja'), pack('zh-Hans')))
    manager.publish((pack('en'), pack('ja'), pack('zh-Hans', 'not_installed', origin='none')))
    assert [window.src_combo.itemData(index) for index in range(2)] == ['en', 'ja']
    assert window.src_combo.findData('zh-Hans') == -1
    assert window.state.source == 'English'
    worker.configure.assert_not_called()
    worker.start_worker.assert_not_called()
