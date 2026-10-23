from PyQt5.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton
from PyQt5.QtCore import Qt, QSize, QTimer, QSignalBlocker, pyqtSignal
from ui.widgets.cards import ModernCard
from ui.styles import CYBER_PALETTE, SECONDARY_BUTTON_STYLE, CARD_FRAME_STYLE
from ui.icons import get_lucide_icon
from ui.controller_state import AiPageState


class AiSettingsPage(QScrollArea):
    provider_changed = pyqtSignal(str)
    model_changed = pyqtSignal(str)
    api_key_changed = pyqtSignal(str)
    base_url_changed = pyqtSignal(str)

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

        active_provider = state.provider

        # Card 1: Provider & Model Selector
        prov_card = ModernCard("Công cụ dịch", "Chọn công cụ thực hiện tác vụ dịch thuật")
        
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        # Provider col
        p_col = QVBoxLayout()
        p_col.setSpacing(4)
        p_lbl = QLabel("Công cụ dịch")
        p_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};")
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(providers)
        self.provider_combo.setCurrentText(active_provider)
        self.provider_combo.currentTextChanged.connect(self.provider_changed.emit)
        p_col.addWidget(p_lbl)
        p_col.addWidget(self.provider_combo)
        row1.addLayout(p_col)

        # Model col
        self.model_container = QWidget()
        m_col = QVBoxLayout(self.model_container)
        m_col.setContentsMargins(0, 0, 0, 0)
        m_col.setSpacing(4)
        m_lbl = QLabel("Mô hình (Model ID)")
        m_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};")
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
        base_url_label.setStyleSheet(
            f"font-size: 11.5px; font-weight: 500; color: {CYBER_PALETTE['text_muted']};"
        )
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://api.example.com/v1")
        self.base_url_input.setText(state.base_url)
        self.base_url_input.editingFinished.connect(
            lambda: self.base_url_changed.emit(self.base_url_input.text())
        )
        base_url_layout.addWidget(base_url_label)
        base_url_layout.addWidget(self.base_url_input)
        prov_card.layout.addWidget(self.base_url_container)
        layout.addWidget(prov_card)

        # Card 2: API Key Management
        self.key_card = ModernCard("Khóa API (API Key)", "Khóa được lưu cục bộ an toàn trong file .env")
        
        k_layout = QVBoxLayout()
        k_layout.setSpacing(6)
        
        k_input_row = QHBoxLayout()
        k_input_row.setSpacing(8)

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText(state.placeholder)
        self.api_key_input.setText(state.api_key)
        self.api_key_input.textChanged.connect(self.api_key_changed.emit)
        k_input_row.addWidget(self.api_key_input)

        self.toggle_key_btn = QPushButton()
        self.toggle_key_btn.setFixedSize(36, 32)
        self.toggle_key_btn.setToolTip("Hiện / Ẩn API Key")
        self.toggle_key_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_key_btn.setIcon(get_lucide_icon("eye", color=CYBER_PALETTE['text_muted'], size=16))
        self.toggle_key_btn.setIconSize(QSize(16, 16))
        self.toggle_key_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.toggle_key_btn.clicked.connect(self.toggle_key_visibility)
        k_input_row.addWidget(self.toggle_key_btn)

        k_layout.addLayout(k_input_row)

        self.api_status_lbl = QLabel()
        self._render_status(state)
        k_layout.addWidget(self.api_status_lbl)

        self.key_card.layout.addLayout(k_layout)
        layout.addWidget(self.key_card)

        # Card 3: Guide Note
        note_card = ModernCard("Hướng dẫn lấy API Key")
        self.guide_card = note_card
        note_text = QLabel(
            "• Google Gemini: Truy cập Google AI Studio (aistudio.google.com)\n"
            "• OpenAI: Truy cập platform.openai.com/api-keys\n"
            "• DeepSeek: Truy cập platform.deepseek.com để tạo API Key\n"
            "• OpenRouter: Truy cập openrouter.ai/keys để nhận key dùng nhiều model"
        )
        note_text.setStyleSheet(f"color: {CYBER_PALETTE['text_muted']}; font-size: 12px; line-height: 1.5;")
        note_card.layout.addWidget(note_text)
        layout.addWidget(note_card)

        layout.addStretch()
        self.setWidget(content)
        self.render(state)

    def toggle_key_visibility(self):
        if self.api_key_input.echoMode() == QLineEdit.Password:
            self.api_key_input.setEchoMode(QLineEdit.Normal)
            self.toggle_key_btn.setIcon(get_lucide_icon("eye-off", color=CYBER_PALETTE['neon_indigo'], size=16))
        else:
            self.api_key_input.setEchoMode(QLineEdit.Password)
            self.toggle_key_btn.setIcon(get_lucide_icon("eye", color=CYBER_PALETTE['text_muted'], size=16))

    def render(self, state: AiPageState, *, changed_field='initial'):
        if changed_field in ('initial', 'provider', 'rollback'):
            blockers = [QSignalBlocker(widget) for widget in (
                self.provider_combo, self.model_combo, self.api_key_input, self.base_url_input,
            )]
            self.provider_combo.setCurrentText(state.provider)
            self.model_combo.clear()
            models = state.models if state.model_id in state.models else state.models + (state.model_id,)
            self.model_combo.addItems(models)
            self.model_combo.setCurrentText(state.model_id)
            self.api_key_input.setText(state.api_key)
            self.api_key_input.setPlaceholderText(state.placeholder)
            self.base_url_input.setText(state.base_url)
            del blockers
        self.base_url_container.setVisible(state.supports_base_url)
        self.model_container.setVisible(state.supports_models)
        self.key_card.setVisible(state.requires_api_key)
        self.guide_card.setVisible(state.requires_api_key)
        self.google_note.setVisible(not state.requires_api_key)
        self._render_status(state)

    def _render_status(self, state):
        if not state.requires_api_key:
            self.api_status_lbl.setText('Trạng thái: Google Translate không cần API key')
            color = CYBER_PALETTE['neon_green']
        elif state.provider == 'Custom API' and not state.base_url.strip():
            self.api_status_lbl.setText('Trạng thái: Chưa có Base URL hợp lệ cho Custom API')
            color = CYBER_PALETTE['neon_amber']
        elif state.api_key.strip():
            self.api_status_lbl.setText(f'Trạng thái: {state.provider} sẵn sàng (.env)')
            color = CYBER_PALETTE['neon_green']
        else:
            self.api_status_lbl.setText(f'Trạng thái: Chưa có API Key cho {state.provider}')
            color = CYBER_PALETTE['neon_amber']
        self.api_status_lbl.setStyleSheet(f'color: {color}; font-size: 11.5px; font-weight: 500;')

    def highlight_missing_key(self):
        self.key_card.setStyleSheet(f"""
                QFrame#cardFrame {{
                    background-color: {CYBER_PALETTE['bg_card']};
                    border: 1px solid {CYBER_PALETTE['neon_rose']};
                    border-radius: 8px;
                }}
            """)
        self.highlight_timer.start()

    def _clear_highlight(self):
        self.key_card.setStyleSheet(CARD_FRAME_STYLE)
