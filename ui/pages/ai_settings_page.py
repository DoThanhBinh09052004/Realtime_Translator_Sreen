from PyQt5.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton, QCheckBox, QGridLayout, QBoxLayout, QLayout, QFrame, QSizePolicy
from PyQt5.QtCore import Qt, QSize, QTimer, QSignalBlocker, pyqtSignal
from ui.widgets.cards import ModernCard
from ui.styles import TOKENS, set_style, apply_widget_theme, button_style, card_style, text_style, CONTROL_HEIGHT, palette_for
from ui.icons import set_theme_icon, get_provider_icon
from ui.controller_state import AiPageState


class AiSettingsPage(QScrollArea):
    provider_changed = pyqtSignal(str)
    model_changed = pyqtSignal(str)
    api_key_changed = pyqtSignal(str)
    api_key_save_requested = pyqtSignal(str, bool)
    api_key_delete_requested = pyqtSignal()
    legacy_key_import_requested = pyqtSignal(bool)
    base_url_changed = pyqtSignal(str)
    context_enabled_changed = pyqtSignal(bool)
    context_reset_requested = pyqtSignal()

    def __init__(self, state: AiPageState, providers: tuple[str, ...], parent=None):
        super().__init__(parent)
        self.highlight_timer = QTimer(self)
        self.highlight_timer.setSingleShot(True)
        self.highlight_timer.setInterval(2500)
        self.highlight_timer.timeout.connect(self._clear_highlight)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 4, 4, 4)
        layout.setSpacing(14)
        layout.setSizeConstraint(QLayout.SetMinAndMaxSize)

        self.columns = QBoxLayout(QBoxLayout.LeftToRight)
        layout.addLayout(self.columns)
        self.main_column = QWidget()
        main_layout = QVBoxLayout(self.main_column)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(14)
        main_layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.columns.setSpacing(16)
        self.columns.addWidget(self.main_column, 62)
        provider_card = ModernCard("Chọn công cụ dịch")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.provider_buttons = {}
        self.provider_logo_labels = {}
        descriptions = {
            'Google Translate': 'Dịch trực tuyến, không cần API key',
            'Google Gemini': 'Sử dụng mô hình Gemini của Google',
            'OpenAI': 'Sử dụng mô hình GPT của OpenAI',
            'DeepSeek': 'Sử dụng mô hình của DeepSeek',
            'Custom API': 'Kết nối với API tương thích OpenAI',
        }
        self.selected_provider = state.provider
        for index, name in enumerate(providers):
            button = QPushButton()
            row = QHBoxLayout(button)
            row.setContentsMargins(16, 10, 16, 10)
            row.setSpacing(16)
            logo = QLabel()
            logo.setFixedSize(40, 40)
            logo.setAlignment(Qt.AlignCenter)
            logo.setPixmap(get_provider_icon(name, palette_for(self)['text'], 38).pixmap(38, 38))
            row.addWidget(logo, 0, Qt.AlignVCenter)
            copy = QVBoxLayout()
            copy.setSpacing(3)
            title = QLabel(name)
            description = QLabel(descriptions.get(name, 'Công cụ dịch'))
            for label in (title, description):
                label.setWordWrap(True)
                label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
                label.setAttribute(Qt.WA_TransparentForMouseEvents)
            logo.setAttribute(Qt.WA_TransparentForMouseEvents)
            set_style(title, text_style('body') + 'font-weight:600;background:transparent;border:none;')
            set_style(description, text_style('caption') + 'background:transparent;border:none;')
            copy.addWidget(title)
            copy.addWidget(description)
            row.addLayout(copy, 1)
            self.provider_logo_labels[name] = logo
            button.setCheckable(True)
            button.setMinimumHeight(64)
            button.setAccessibleName('Chọn ' + name)
            set_style(button, button_style('secondary', 'tokens') + f"QPushButton:checked {{background:{TOKENS['surface']};border:2px solid {TOKENS['text']};}}")
            button.clicked.connect(lambda checked=False, name=name: self._request_provider(name))
            self.provider_buttons[name] = button
            grid.addWidget(button, index // 2, index % 2)
        provider_card.layout.addLayout(grid)
        main_layout.addWidget(provider_card)
        prov_card = ModernCard("Cấu hình " + state.provider)
        self.config_card = prov_card
        self.config_title_label = prov_card.findChildren(QLabel)[0]
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        # Model col
        self.model_container = QWidget()
        m_col = QVBoxLayout(self.model_container)
        m_col.setContentsMargins(0, 0, 0, 0)
        m_col.setSpacing(4)
        m_lbl = QLabel("Model ID")
        set_style(m_lbl, text_style('body') + 'font-weight:500;')
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(state.models)
        self.model_combo.setCurrentText(state.model_id)
        self.model_combo.currentTextChanged.connect(self.model_changed.emit)
        m_col.addWidget(m_lbl)
        m_col.addWidget(self.model_combo)
        row1.addWidget(self.model_container)

        prov_card.layout.addLayout(row1)
        self.google_note = QLabel('Dịch trực tuyến, không cần API key')
        self.google_note.setWordWrap(True)
        prov_card.layout.addWidget(self.google_note)

        self.base_url_container = QWidget()
        base_url_layout = QVBoxLayout(self.base_url_container)
        base_url_layout.setContentsMargins(0, 8, 0, 0)
        base_url_layout.setSpacing(4)
        base_url_label = QLabel("Base URL (OpenAI-compatible)")
        set_style(base_url_label,
            f"font-size: 12px; font-weight: 500; color: {TOKENS['muted']};"
        )
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://api.example.com/v1")
        self.base_url_input.setText(state.base_url)
        self.base_url_input.editingFinished.connect(
            lambda: self.base_url_changed.emit(self.base_url_input.text())
        )
        base_url_layout.addWidget(base_url_label)
        base_url_layout.addWidget(self.base_url_input)
        endpoint_help = QLabel('Máy chủ từ xa cần HTTPS. HTTP chỉ dùng cho localhost/IP loopback. Nhập endpoint cuối, không chuyển hướng.')
        endpoint_help.setWordWrap(True)
        base_url_layout.addWidget(endpoint_help)
        prov_card.layout.addWidget(self.base_url_container)
        main_layout.addWidget(prov_card)

        context_card=ModernCard('Ngữ cảnh hội thoại')
        self.context_checkbox=QCheckBox('Giữ ngữ cảnh hội thoại')
        self.context_checkbox.toggled.connect(self.context_enabled_changed.emit)
        context_row = QBoxLayout(QBoxLayout.LeftToRight)
        self.context_row = context_row
        context_row.addWidget(self.context_checkbox, 1)
        self.context_checkbox.setToolTip('Khoanh cả tên nhân vật và lời thoại nếu có. Bộ nhớ chỉ giữ trong phiên.')
        self.context_reset_button=QPushButton('Bắt đầu hội thoại mới')
        set_style(self.context_reset_button, button_style('secondary', 'tokens'))
        self.context_reset_button.clicked.connect(self.context_reset_requested.emit)
        context_row.addWidget(self.context_reset_button)
        context_card.layout.addLayout(context_row)
        self.context_status_label=QLabel()
        self.context_status_label.setWordWrap(True)
        context_card.layout.addWidget(self.context_status_label)
        memory_note=QLabel('Bộ nhớ được xóa khi đóng ứng dụng.')
        memory_note.setWordWrap(True)
        context_card.layout.addWidget(memory_note)


        # Card 2: API Key Management
        self.key_card = QFrame()
        key_layout = QVBoxLayout(self.key_card)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(QLabel("API key"))

        k_layout = QVBoxLayout()
        k_layout.setSpacing(10)

        k_input_row = QHBoxLayout()
        k_input_row.setSpacing(8)

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText(state.placeholder)
        self.api_key_input.setText(state.api_key)
        k_input_row.addWidget(self.api_key_input)

        self.toggle_key_btn = QPushButton()
        self.toggle_key_btn.setFixedSize(CONTROL_HEIGHT, CONTROL_HEIGHT)
        self.toggle_key_btn.setToolTip("Hiện / Ẩn API Key")
        self.toggle_key_btn.setCursor(Qt.PointingHandCursor)
        set_theme_icon(self.toggle_key_btn, "eye", 'muted', 16)
        self.toggle_key_btn.setIconSize(QSize(16, 16))
        set_style(self.toggle_key_btn, button_style('secondary', 'tokens'))
        self.toggle_key_btn.clicked.connect(self.toggle_key_visibility)
        k_input_row.addWidget(self.toggle_key_btn)

        k_layout.addLayout(k_input_row)

        self.persist_key_checkbox = QCheckBox('Lưu an toàn trên máy này')
        self.persist_key_checkbox.setChecked(True)
        k_layout.addWidget(self.persist_key_checkbox)
        actions = QHBoxLayout()
        self.save_key_btn = QPushButton('Áp dụng key')
        self.delete_key_btn = QPushButton('Xóa key')
        self.import_key_btn = QPushButton('Nhập key cũ từ .env')
        for button in (self.save_key_btn, self.delete_key_btn, self.import_key_btn):
            set_style(button, button_style('secondary', 'tokens'))
            if button is not self.import_key_btn:
                actions.addWidget(button)
        self.save_key_btn.setMaximumWidth(140)
        self.delete_key_btn.setMaximumWidth(110)
        actions.setSpacing(12)
        actions.addStretch()
        set_style(self.save_key_btn, button_style('primary', 'tokens'))
        self.save_key_btn.clicked.connect(self._apply_key)
        self.delete_key_btn.clicked.connect(self.api_key_delete_requested.emit)
        self.import_key_btn.clicked.connect(lambda: self.legacy_key_import_requested.emit(self.persist_key_checkbox.isChecked()))
        k_layout.addLayout(actions)
        self.advanced_btn = advanced = QPushButton('Tùy chọn nâng cao')
        advanced.setCheckable(True)
        advanced.setMaximumWidth(150)
        set_style(advanced, 'QPushButton {' + text_style('caption') + 'border:none;background:transparent;text-align:left;padding:2px 0;}')
        advanced.toggled.connect(self.import_key_btn.setVisible)
        k_layout.addWidget(advanced)
        k_layout.addWidget(self.import_key_btn)
        self.import_key_btn.hide()

        self.api_status_lbl = QLabel()
        self._render_status(state)
        self.api_status_lbl.setWordWrap(True)
        actions.addWidget(self.api_status_lbl, 1)

        key_layout.addLayout(k_layout)
        prov_card.layout.addWidget(self.key_card)
        main_layout.addWidget(context_card)
        main_layout.addStretch()

        # Card 3: Guide Note
        note_card = ModernCard('Thiết lập công cụ')
        self.guide_card = note_card
        for number, title, description in (
            ('1', 'Chọn công cụ', 'Chọn nhà cung cấp dịch phù hợp với nhu cầu của bạn.'),
            ('2', 'Nhập model và API key', 'Nhập tên model (nếu có) và API key của bạn.'),
            ('3', 'Áp dụng để sử dụng', 'Nhấn Áp dụng key để lưu key. Model được lưu khi thay đổi.'),
        ):
            row = QHBoxLayout()
            row.setSpacing(16)
            badge = QLabel(number)
            badge.setAlignment(Qt.AlignCenter)
            badge.setFixedSize(40, 40)
            set_style(badge, text_style('section') + f'background:{TOKENS["raised"]};border-radius:20px;')
            row.addWidget(badge, 0, Qt.AlignTop)
            copy = QVBoxLayout()
            heading = QLabel(title)
            heading.setWordWrap(True)
            set_style(heading, text_style('body') + 'font-weight:600;')
            body = QLabel(description)
            body.setWordWrap(True)
            set_style(body, text_style('caption'))
            copy.addWidget(heading)
            copy.addWidget(body)
            row.addLayout(copy, 1)
            note_card.layout.addLayout(row)
            note_card.layout.addSpacing(18)
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        set_style(divider, f'color:{TOKENS["border"]};background:{TOKENS["border"]};max-height:1px;border:none;')
        note_card.layout.addSpacing(12)
        note_card.layout.addWidget(divider)
        note_card.layout.addSpacing(12)
        google_row = QHBoxLayout()
        self.google_guide_logo = QLabel()
        self.google_guide_logo.setFixedSize(40, 40)
        google_row.addWidget(self.google_guide_logo)
        google_copy = QLabel('Google Translate\nDịch trực tuyến, không cần API key.')
        google_copy.setWordWrap(True)
        set_style(google_copy, text_style('body'))
        google_row.setSpacing(18)
        google_row.addWidget(google_copy, 1)
        note_card.layout.addLayout(google_row)
        note_card.layout.addSpacing(18)
        privacy = QLabel('Dữ liệu gửi đi\n\nVăn bản nhận diện được gửi đến công cụ bạn chọn.')
        privacy.setWordWrap(True)
        set_style(privacy, text_style('caption'))
        note_card.layout.addWidget(privacy)
        note_card.layout.addStretch()
        self.columns.addWidget(note_card, 38)


        layout.addStretch()
        footer = QLabel('✓  Thiết lập được đồng bộ với màn hình chính.')
        set_style(footer, text_style('caption'))
        layout.addWidget(footer)
        for card in (provider_card, prov_card, context_card, note_card):
            labels = card.findChildren(QLabel)
            if labels:
                set_style(labels[0], text_style('section'))
        self.setWidget(content)
        self.render(state)
        self._reflow_layout(self.viewport().width())

    def _render_provider_selection(self):
        for name, button in self.provider_buttons.items():
            blocker = QSignalBlocker(button)
            button.setChecked(name == self.selected_provider)
            del blocker

    def _request_provider(self, name: str) -> None:
        self._render_provider_selection()
        if name != self.selected_provider:
            self.provider_changed.emit(name)

    def _reflow_layout(self, width: int) -> None:
        self.columns.setDirection(QBoxLayout.LeftToRight if width >= 800 else QBoxLayout.TopToBottom)
        self.context_row.setDirection(QBoxLayout.LeftToRight if width >= 800 else QBoxLayout.TopToBottom)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_layout(self.viewport().width())

    def _apply_key(self):
        self.api_key_save_requested.emit(self.api_key_input.text(), self.persist_key_checkbox.isChecked())
        self.api_key_changed.emit(self.api_key_input.text())

    def toggle_key_visibility(self):
        if self.api_key_input.echoMode() == QLineEdit.Password:
            self.api_key_input.setEchoMode(QLineEdit.Normal)
            set_theme_icon(self.toggle_key_btn, "eye-off", 'focus', 16)
        else:
            self.api_key_input.setEchoMode(QLineEdit.Password)
            set_theme_icon(self.toggle_key_btn, "eye", 'muted', 16)

    def render(self, state: AiPageState, *, changed_field='initial'):
        blocker=QSignalBlocker(self.context_checkbox)
        self.context_checkbox.setChecked(state.context_enabled)
        del blocker
        self.context_checkbox.setEnabled(state.context_supported)
        self.context_reset_button.setEnabled(state.context_enabled and state.context_supported)
        self.context_status_label.setText('Tính năng này dùng với công cụ dịch AI.' if state.provider=='Google Translate'
                                        else 'Hiện hỗ trợ chế độ phụ đề.' if not state.context_supported else '')
        if changed_field == 'base_url':
            blocker = QSignalBlocker(self.base_url_input)
            self.base_url_input.setText(state.base_url)
            del blocker
        if changed_field in ('initial', 'provider', 'rollback', 'api_key_import', 'api_key_deleted'):
            blockers = [QSignalBlocker(widget) for widget in (
                self.model_combo, self.api_key_input, self.base_url_input,
            )]
            self.selected_provider = state.provider
            self._render_provider_selection()
            self.model_combo.clear()
            models = state.models if state.model_id in state.models else state.models + (state.model_id,)
            self.model_combo.addItems(models)
            self.model_combo.setCurrentText(state.model_id)
            self.api_key_input.setText(state.api_key)
            self.api_key_input.setPlaceholderText(state.placeholder)
            self.base_url_input.setText(state.base_url)
            self.persist_key_checkbox.setChecked(state.key_storage != 'session')
            self.api_key_input.setEchoMode(QLineEdit.Password)
            del blockers
        self.base_url_container.setVisible(state.supports_base_url)
        self.model_container.setVisible(state.supports_models)
        self.key_card.setVisible(state.requires_api_key)
        self.guide_card.show()
        self.config_title_label.setText("Cấu hình " + state.provider)
        self.google_note.setVisible(not state.requires_api_key)
        self._render_status(state)

    def render_context_status(self,status):
        if status.phase=='text_fallback' and self.context_checkbox.isEnabled() and self.context_checkbox.isChecked():
            self.context_status_label.setText('Đang dịch bằng ngữ cảnh gần đây; công cụ chưa hỗ trợ cập nhật trí nhớ nhân vật.')

    def _render_status(self, state):
        if not state.requires_api_key:
            self.api_status_lbl.setText('Trạng thái: Google Translate không cần API key')
            color = TOKENS['positive']
        elif state.provider == 'Custom API' and not state.base_url.strip():
            self.api_status_lbl.setText('Trạng thái: Chưa có Base URL hợp lệ cho Custom API')
            color = TOKENS['warning']
        elif state.key_storage == 'unavailable':
            self.api_status_lbl.setText('Không đọc được key đã lưu. Có thể nhập key chỉ dùng trong phiên.')
            color = TOKENS['warning']
        elif state.api_key.strip():
            mode = 'Chỉ dùng trong phiên' if state.key_storage == 'session' else 'Đã lưu key mã hóa'
            self.api_status_lbl.setText(f'{mode}; chưa kiểm tra kết nối')
            color = TOKENS['warning']
        else:
            self.api_status_lbl.setText(f'Trạng thái: Chưa có API Key cho {state.provider}')
            color = TOKENS['warning']
        set_style(self.api_status_lbl, text_style('caption', color=color))

    def highlight_missing_key(self):
        set_style(self.config_card, f"""
                QFrame#cardFrame {{
                    background-color: {TOKENS['surface']};
                    border: 1px solid {TOKENS['negative']};
                    border-radius: 8px;
                }}
            """)
        self.highlight_timer.start()

    def _clear_highlight(self):
        set_style(self.config_card, card_style('tokens'))

    def apply_theme(self, theme: str):
        apply_widget_theme(self, theme)
        for name, button in self.provider_buttons.items():
            self.provider_logo_labels[name].setPixmap(get_provider_icon(name, palette_for(self)['text'], 38).pixmap(38, 38))
        self.google_guide_logo.setPixmap(get_provider_icon('Google Translate', palette_for(self)['text'], 40).pixmap(40, 40))
