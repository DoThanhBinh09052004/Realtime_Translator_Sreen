"""App-independent language pack management view."""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget
from ui.controller_state import LanguagePacksState
from ui.styles import get_app_stylesheet, LANGUAGE_PACKS_STYLE, SECONDARY_BUTTON_STYLE, PACK_ACTION_STYLE
from ui.widgets.package_status_row import PackageStatusRow, format_bytes


class LanguagePacksDialog(QDialog):
    install_requested = pyqtSignal(str)
    cancel_requested = pyqtSignal()
    remove_requested = pyqtSignal(str)

    def __init__(self, state: LanguagePacksState, parent=None):
        super().__init__(parent)
        self.setObjectName('languagePacksDialog')
        self.setWindowTitle('Quản lý gói ngôn ngữ')
        self.setWindowModality(Qt.WindowModal)
        self.setStyleSheet(get_app_stylesheet() + LANGUAGE_PACKS_STYLE)
        screen = self.screen() or QApplication.primaryScreen()
        geometry = screen.availableGeometry() if screen else None
        width, height = (geometry.width(), geometry.height()) if geometry else (560, 520)
        self.setMinimumSize(min(440, width), min(360, height))
        self.resize(min(560, width), min(520, height))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        heading = QLabel('Quản lý gói ngôn ngữ')
        heading.setObjectName('packDialogTitle')
        heading.setWordWrap(True)
        layout.addWidget(heading)
        intro = QLabel('Tải thêm ngôn ngữ để dùng OCR. Tải xong, chọn ngôn ngữ nguồn trong phần Dịch thuật & OCR.')
        intro.setObjectName('packDetail')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.message_label = QLabel()
        self.message_label.setObjectName('packReason')
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFocusPolicy(Qt.NoFocus)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(12)
        self.groups = {}
        for key, title in (('installed', 'Đã cài'), ('available', 'Có thể tải')):
            group = QWidget()
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(0, 0, 0, 0)
            group_layout.setSpacing(10)
            label = QLabel(title)
            label.setObjectName('packGroupTitle')
            group_layout.addWidget(label)
            content_layout.addWidget(group)
            self.groups[key] = (group, group_layout)
        content_layout.addStretch()
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll, 1)
        footer = QLabel('Đóng cửa sổ vẫn tiếp tục tải. Gói có sẵn trong ứng dụng được giữ lại.')
        footer.setObjectName('packDetail')
        footer.setWordWrap(True)
        layout.addWidget(footer)
        self.close_button = QPushButton('Đóng')
        self.close_button.setObjectName('packClose')
        self.close_button.setAutoDefault(False)
        self.close_button.setMinimumHeight(32)
        self.close_button.setStyleSheet(SECONDARY_BUTTON_STYLE + PACK_ACTION_STYLE)
        self.close_button.clicked.connect(self.close)
        layout.addWidget(self.close_button, 0, Qt.AlignRight)
        self.rows = {}
        self.render(state)

    def render(self, state: LanguagePacksState) -> None:
        self.message_label.setText(state.message)
        self.message_label.setVisible(bool(state.message))
        ids = {item.language_id for item in state.rows}
        for language_id in tuple(self.rows):
            if language_id not in ids:
                row = self.rows.pop(language_id)
                row.hide()
                row.deleteLater()
        focus_order = []
        for item in state.rows:
            row = self.rows.get(item.language_id)
            if row is None:
                row = PackageStatusRow(item)
                row.action_requested.connect(self._dispatch_action)
                self.rows[item.language_id] = row
            else:
                row.render(item)
            key = 'installed' if item.phase in ('installed', 'removing') else 'available'
            group, group_layout = self.groups[key]
            if row.parentWidget() is not group:
                group_layout.addWidget(row)
            if item.action and item.action_enabled:
                focus_order.append(row.action_button)
        # Traverse controls in the same order as the visible sections.
        focus_order.sort(key=lambda button: (0 if button.parentWidget().state.phase in ('installed', 'removing') else 1,
                                             list(self.rows).index(button.parentWidget().state.language_id)))
        for previous, following in zip(focus_order, focus_order[1:] + [self.close_button]):
            self.setTabOrder(previous, following)
        if focus_order:
            self.setTabOrder(self.close_button, focus_order[0])
        for group, group_layout in self.groups.values():
            group.setVisible(group_layout.count() > 1)

    def showEvent(self, event):
        super().showEvent(event)
        # availableGeometry includes no taskbar, but Qt's client size excludes
        # the native title bar and resize frame. Keep both inside the screen.
        available = self.screen().availableGeometry()
        frame = self.frameGeometry()
        max_width = max(1, available.width() - (frame.width() - self.width()))
        max_height = max(1, available.height() - (frame.height() - self.height()))
        self.setMinimumSize(min(440, max_width), min(360, max_height))
        self.resize(min(self.width(), max_width), min(self.height(), max_height))
        frame = self.frameGeometry()
        x = max(available.left(), min(frame.left(), available.right() - frame.width() + 1))
        y = max(available.top(), min(frame.top(), available.bottom() - frame.height() + 1))
        self.move(x, y)
        self.close_button.setFocus(Qt.OtherFocusReason)

    def _dispatch_action(self, language_id: str, action: str) -> None:
        if action in ('install', 'retry'):
            self.install_requested.emit(language_id)
        elif action == 'cancel':
            self.cancel_requested.emit()
        elif action == 'remove':
            state = self.rows[language_id].state
            answer = QMessageBox.question(
                self, 'Xóa gói ngôn ngữ',
                f'Xóa gói {state.title}? Có thể thu hồi {format_bytes(state.reclaimable_bytes)}. '
                'Bạn có thể tải lại gói sau.',
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if answer == QMessageBox.Yes:
                self.remove_requested.emit(language_id)
