from dataclasses import replace

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QMessageBox


def row_state(**changes):
    from ui.controller_state import PackageRowState
    values = dict(language_id='zh-Hans', title='Chinese (Giản thể)', phase='not_installed',
                  status_text='Chưa cài', detail_text='Tải gói để nhận diện ngôn ngữ này.',
                  downloaded_bytes=0, total_bytes=4096, reclaimable_bytes=2048,
                  action='install', action_enabled=True)
    return PackageRowState(**(values | changes))


@pytest.mark.parametrize('icon', ['download', 'x', 'refresh-cw', 'trash-2'])
def test_package_action_icons_have_explicit_lucide_glyphs(icon):
    from ui.icons import get_lucide_svg
    assert get_lucide_svg(icon) != get_lucide_svg('missing-icon-fallback')


def test_row_progress_is_phase_driven_and_render_is_silent(qtbot):
    from ui.widgets.package_status_row import PackageStatusRow
    state = row_state(phase='downloading', action='cancel', downloaded_bytes=1024)
    row = PackageStatusRow(state)
    qtbot.addWidget(row)
    intent = QSignalSpy(row.action_requested)
    assert row.progress.maximum() == 1000 and row.progress.value() == 250
    row.render(replace(state, downloaded_bytes=2048))
    assert row.progress.value() == 500 and not intent
    for phase in ('verifying', 'installing', 'removing'):
        row.render(replace(state, phase=phase, status_text=phase))
        assert row.progress.maximum() == 0
        assert row.status_label.text() == phase
    row.render(row_state(phase='error', action='retry', detail_text='Không có mạng. Kiểm tra kết nối rồi Thử lại.'))
    assert row.detail_label.wordWrap()
    assert row.title_label.wordWrap()
    row.action_button.click()
    assert list(intent) == [['zh-Hans', 'retry']]


def test_bundled_and_selected_rows_show_protection(qtbot):
    from ui.widgets.package_status_row import PackageStatusRow
    row = PackageStatusRow(row_state(phase='installed', action=None,
                                    status_text='Có sẵn trong ứng dụng'))
    qtbot.addWidget(row)
    assert row.action_button.isHidden()
    row.render(row_state(phase='installed', action='remove', action_enabled=False,
                         status_text='Đang chọn', action_reason='Chọn ngôn ngữ khác trước khi xóa.'))
    assert not row.action_button.isEnabled()
    assert 'Chọn ngôn ngữ khác' in row.reason_label.text()


@pytest.mark.parametrize('phase,action,visible', [
    ('not_installed', 'install', False), ('downloading', 'cancel', True),
    ('verifying', 'cancel', True), ('installing', 'cancel', True),
    ('installed', 'remove', False), ('removing', None, True), ('error', 'retry', False),
])
def test_all_package_phases_keep_text_and_progress_semantics(qtbot, phase, action, visible):
    from ui.widgets.package_status_row import PackageStatusRow
    state = row_state(phase=phase, action=action)
    row = PackageStatusRow(state)
    qtbot.addWidget(row)
    assert row.title_label.text() == 'Chinese (Giản thể)'
    assert row.progress.isHidden() is not visible
    assert row.action_button.isHidden() is (action is None)


def test_dialog_confirms_removal_with_cancel_default_and_exact_bytes(qtbot, monkeypatch):
    from ui.controller_state import LanguagePacksState
    from ui.language_packs_dialog import LanguagePacksDialog
    dialog = LanguagePacksDialog(LanguagePacksState((row_state(phase='installed', action='remove'),), False))
    qtbot.addWidget(dialog)
    removed = QSignalSpy(dialog.remove_requested)
    calls = []
    def question(*args):
        calls.append(args)
        return QMessageBox.Cancel
    monkeypatch.setattr(QMessageBox, 'question', question)
    dialog.rows['zh-Hans'].action_button.click()
    assert calls[0][-1] == QMessageBox.Cancel
    assert 'Chinese' in calls[0][2] and '2.0 KiB' in calls[0][2]
    assert not removed
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    dialog.rows['zh-Hans'].action_button.click()
    assert list(removed) == [['zh-Hans']]


def test_dialog_keyboard_close_and_progress_keep_view_intents_separate(qtbot):
    from ui.controller_state import LanguagePacksState
    from ui.language_packs_dialog import LanguagePacksDialog
    state = LanguagePacksState((row_state(phase='downloading', action='cancel'),), True)
    dialog = LanguagePacksDialog(state)
    qtbot.addWidget(dialog)
    cancelled = QSignalSpy(dialog.cancel_requested)
    installed = QSignalSpy(dialog.install_requested)
    dialog.open()
    dialog.activateWindow()
    qtbot.waitUntil(dialog.isActiveWindow)
    dialog.rows['zh-Hans'].action_button.setFocus()
    qtbot.keyClick(dialog, Qt.Key_Tab)
    assert dialog.close_button.hasFocus()
    qtbot.keyClick(dialog, Qt.Key_Tab, Qt.ShiftModifier)
    assert dialog.rows['zh-Hans'].action_button.hasFocus()
    dialog.render(state)
    assert not cancelled and not installed
    qtbot.keyClick(dialog, Qt.Key_Escape)
    assert not dialog.isVisible() and not cancelled
    dialog.open()
    assert dialog.rows['zh-Hans'].state.phase == 'downloading'


def test_dialog_including_window_frame_fits_available_screen(qtbot):
    from ui.controller_state import LanguagePacksState
    from ui.language_packs_dialog import LanguagePacksDialog
    dialog = LanguagePacksDialog(LanguagePacksState((row_state(),), False))
    qtbot.addWidget(dialog)
    dialog.resize(9999, 9999)
    dialog.open()
    assert dialog.screen().availableGeometry().contains(dialog.frameGeometry())
