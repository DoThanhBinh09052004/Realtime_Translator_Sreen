"""Render a package state and emit user intent; no package service access."""
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton
from ui.controller_state import PackageRowState
from ui.icons import get_lucide_icon
from ui.styles import CYBER_PALETTE, SECONDARY_BUTTON_STYLE, PACK_ACTION_STYLE
from ui.widgets.cards import ModernCard


def format_bytes(value: int) -> str:
    amount = max(0, value)
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if amount < 1024 or unit == 'GiB':
            return f'{amount:.1f} {unit}' if unit != 'B' else f'{amount} B'
        amount /= 1024


class PackageStatusRow(ModernCard):
    action_requested = pyqtSignal(str, str)

    def __init__(self, state: PackageRowState, parent=None):
        super().__init__()
        self.setParent(parent)
        header = QHBoxLayout()
        header.setSpacing(12)
        self.title_label = QLabel()
        self.title_label.setObjectName('packTitle')
        self.title_label.setWordWrap(True)
        header.addWidget(self.title_label, 1)
        self.action_button = QPushButton()
        self.action_button.setObjectName('packAction')
        self.action_button.setAutoDefault(False)
        self.action_button.setMinimumHeight(32)
        self.action_button.setMinimumWidth(104)
        self.action_button.setCursor(Qt.PointingHandCursor)
        self.action_button.setIconSize(QSize(15, 15))
        self.action_button.setStyleSheet(SECONDARY_BUTTON_STYLE + PACK_ACTION_STYLE)
        self.action_button.clicked.connect(self._request_action)
        header.addWidget(self.action_button, 0, Qt.AlignTop)
        self.layout.addLayout(header)
        self.status_label = QLabel()
        self.status_label.setObjectName('packStatus')
        self.status_label.setWordWrap(True)
        self.detail_label = QLabel()
        self.detail_label.setObjectName('packDetail')
        self.detail_label.setWordWrap(True)
        self.reason_label = QLabel()
        self.reason_label.setObjectName('packReason')
        self.reason_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setObjectName('packProgress')
        self.progress.setFixedHeight(18)
        self.progress.setAccessibleName(f'Tiến độ tải {state.title}')
        for widget in (self.status_label, self.detail_label, self.progress, self.reason_label):
            self.layout.addWidget(widget)
        self.render(state)

    def render(self, state: PackageRowState) -> None:
        self.state = state
        self.title_label.setText(state.title)
        self.status_label.setText(state.status_text)
        detail = state.detail_text
        if state.phase == 'downloading':
            detail = f'{format_bytes(state.downloaded_bytes)} / {format_bytes(state.total_bytes)}' + (f' · {detail}' if detail else '')
        self.detail_label.setText(detail)
        self.detail_label.setVisible(bool(detail))
        self.reason_label.setText(state.action_reason)
        self.reason_label.setVisible(bool(state.action_reason))
        self.progress.setVisible(state.phase in ('downloading', 'verifying', 'installing', 'removing'))
        if state.phase == 'downloading' and state.total_bytes > 0:
            self.progress.setRange(0, 1000)
            self.progress.setValue(min(1000, max(0, state.downloaded_bytes * 1000 // state.total_bytes)))
        else:
            self.progress.setRange(0, 0)
        labels = {'install': 'Tải', 'cancel': 'Hủy tải', 'retry': 'Thử lại', 'remove': 'Xóa gói'}
        icons = {'install': 'download', 'cancel': 'x', 'retry': 'refresh-cw', 'remove': 'trash-2'}
        self.action_button.setVisible(state.action is not None)
        self.action_button.setEnabled(state.action_enabled)
        self.action_button.setText(labels.get(state.action, ''))
        self.action_button.setAccessibleName(f'{labels.get(state.action, "")} {state.title}')
        self.action_button.setToolTip(state.action_reason)
        self.action_button.setProperty('destructive', state.action == 'remove')
        self.action_button.style().unpolish(self.action_button)
        self.action_button.style().polish(self.action_button)
        if state.action:
            self.action_button.setIcon(get_lucide_icon(icons[state.action], color=CYBER_PALETTE['text_secondary'], size=15))

    def _request_action(self) -> None:
        if self.state.action and self.state.action_enabled:
            self.action_requested.emit(self.state.language_id, self.state.action)
