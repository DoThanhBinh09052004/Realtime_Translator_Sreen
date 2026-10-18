from PyQt5.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QComboBox, QFrame, QSlider, QColorDialog,
    QLineEdit
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

from core.config import (
    SUPPORTED_LANGUAGES, SUPPORTED_TARGETS, load_config, save_config,
    load_api_key, save_api_key, load_model_id, save_model_id,
    AVAILABLE_MODELS
)
from engines.translator import reload_client



class Section(QFrame):
    """Container nhóm các thiết lập trong giao diện"""
    def __init__(self, title: str):
        super().__init__()

        self.setStyleSheet("""
            QFrame {
                background-color: #232338;
                border-radius: 8px;
            }

            QLabel {
                font-size: 12.5px;
                color: #cdd6f4;
            }

            QLabel#sectionTitle {
                font-size: 13px;
                font-weight: 600;
                color: #89b4fa;
                padding-bottom: 2px;
            }
        """)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 10, 12, 12)
        self.layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        self.layout.addWidget(title_label)


class ControllerWindow(QWidget):
    """Cửa sổ bảng điều khiển chính của ứng dụng"""
    def __init__(self, worker, state, on_select_region, on_quit, overlay=None):
        super().__init__()

        self.worker = worker
        self.state = state
        self.overlay = overlay

        # ===== Cấu hình Window =====
        self.setWindowTitle("Game Translator")
        self.setFixedSize(520, 860)

        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: "Segoe UI";
            }

            QPushButton {
                background-color: #45475a;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12.5px;
                font-weight: 600;
            }

            QPushButton:hover {
                background-color: #585b70;
            }

            QPushButton#start {
                background-color: #a6e3a1;
                color: #1e1e2e;
            }

            QPushButton#stop {
                background-color: #f38ba8;
                color: #1e1e2e;
            }

            QPushButton#region {
                background-color: #313244;
            }

            QPushButton#quit {
                background-color: #313244;
                color: #cdd6f4;
            }

            QComboBox, QSpinBox {
                min-height: 30px;
                padding: 4px 8px;
                font-size: 12.5px;
                border-radius: 6px;
                background-color: #2e2e44;
            }

            QLineEdit {
                min-height: 28px;
                padding: 4px 8px;
                font-size: 12.5px;
                border-radius: 6px;
                background-color: #2e2e44;
                border: 1px solid #45475a;
                color: #cdd6f4;
            }

            QLineEdit:focus {
                border: 1px solid #89b4fa;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ===== HEADER =====
        title = QLabel("Game Translator")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        root.addWidget(title)

        self.status = QLabel("Stopped")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("color: #f38ba8; font-size: 12.5px;")
        root.addWidget(self.status)

        # ===== API SETTINGS =====
        api_sec = Section("API Settings")

        api_sec.layout.addWidget(QLabel("OpenAI API Key"))
        key_row = QHBoxLayout()
        key_row.setSpacing(6)
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("sk-proj-...")
        self.api_key_input.setText(load_api_key())
        self.api_key_input.textChanged.connect(self._on_api_key_changed)
        key_row.addWidget(self.api_key_input)

        self.toggle_key_btn = QPushButton("👁")
        self.toggle_key_btn.setFixedSize(38, 30)
        self.toggle_key_btn.setToolTip("Hiện / Ẩn API Key")
        self.toggle_key_btn.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                border-radius: 6px;
                font-size: 14px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
        """)
        self.toggle_key_btn.clicked.connect(self._toggle_key_visibility)
        key_row.addWidget(self.toggle_key_btn)

        api_sec.layout.addLayout(key_row)

        api_sec.layout.addWidget(QLabel("Model"))
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(AVAILABLE_MODELS)
        saved_model = load_model_id()
        if saved_model not in AVAILABLE_MODELS:
            self.model_combo.addItem(saved_model)
        self.model_combo.setCurrentText(saved_model)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        api_sec.layout.addWidget(self.model_combo)

        self.api_status_lbl = QLabel()
        self._update_api_status()
        api_sec.layout.addWidget(self.api_status_lbl)

        self.api_section = api_sec
        root.addWidget(api_sec)


        # ===== CONTROL =====
        control = Section("Control")

        row = QHBoxLayout()
        row.setSpacing(10)

        self.start_btn = QPushButton("START")
        self.start_btn.setObjectName("start")
        self.start_btn.setFixedHeight(36)
        self.start_btn.clicked.connect(self.start_ocr)

        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setObjectName("stop")
        self.stop_btn.setFixedHeight(36)
        self.stop_btn.clicked.connect(self.stop_ocr)

        row.addWidget(self.start_btn)
        row.addWidget(self.stop_btn)

        control.layout.addLayout(row)
        root.addWidget(control)

        # ===== LANGUAGE =====
        lang = Section("Language")

        lang.layout.addWidget(QLabel("Source"))
        src = QComboBox()
        src.addItems(list(SUPPORTED_LANGUAGES.keys()))
        src.setCurrentText(self.state.source if self.state.source in SUPPORTED_LANGUAGES else "English")
        src.currentTextChanged.connect(
            lambda t: self.state.update(source=t)
        )
        lang.layout.addWidget(src)

        lang.layout.addWidget(QLabel("Target"))
        tgt = QComboBox()
        tgt.addItems(SUPPORTED_TARGETS)
        tgt.setCurrentText(self.state.target if self.state.target in SUPPORTED_TARGETS else "Vietnamese")
        tgt.currentTextChanged.connect(
            lambda t: self.state.update(target=t)
        )
        lang.layout.addWidget(tgt)

        root.addWidget(lang)

        # ===== OCR SETTINGS =====
        ocr = Section("OCR Settings")

        region_btn = QPushButton("Select OCR Region")
        region_btn.setObjectName("region")
        region_btn.setFixedHeight(32)
        region_btn.clicked.connect(on_select_region)
        ocr.layout.addWidget(region_btn)

        ocr.layout.addWidget(QLabel("Interval (ms)"))
        interval = QSpinBox()
        interval.setRange(100, 2000)
        if worker is not None:
            saved_interval = load_config().get("interval_ms", worker.interval())
            worker.setInterval(saved_interval)
        else:
            saved_interval = load_config().get("interval_ms", 500)
        interval.setValue(saved_interval)
        interval.valueChanged.connect(
            lambda v: ((worker.setInterval(v) if worker else None), save_config("interval_ms", v))
        )
        ocr.layout.addWidget(interval)

        root.addWidget(ocr)

        # ===== SUBTITLE STYLE =====
        style_sec = Section("Subtitle Style")

        style_sec.layout.addWidget(QLabel("Background Color"))
        self.bg_color_btn = QPushButton()
        self.bg_color_btn.setFixedHeight(32)
        self._update_color_btn_style(self.bg_color_btn, self.state.bg_color)
        self.bg_color_btn.clicked.connect(self._pick_bg_color)
        style_sec.layout.addWidget(self.bg_color_btn)

        opacity_header = QHBoxLayout()
        opacity_header.addWidget(QLabel("Background Opacity"))
        self.opacity_val_lbl = QLabel(f"{self.state.bg_opacity}%")
        self.opacity_val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.opacity_val_lbl.setStyleSheet("color: #89b4fa; font-weight: 600;")
        opacity_header.addWidget(self.opacity_val_lbl)
        style_sec.layout.addLayout(opacity_header)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(self.state.bg_opacity)
        self.opacity_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #313244;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #89b4fa;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #cdd6f4;
                border: 1px solid #89b4fa;
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
        """)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        style_sec.layout.addWidget(self.opacity_slider)

        style_sec.layout.addWidget(QLabel("Text Color"))
        self.text_color_btn = QPushButton()
        self.text_color_btn.setFixedHeight(32)
        self._update_color_btn_style(self.text_color_btn, self.state.text_color)
        self.text_color_btn.clicked.connect(self._pick_text_color)
        style_sec.layout.addWidget(self.text_color_btn)

        root.addWidget(style_sec)

        root.addStretch()

        # ===== FOOTER =====
        quit_btn = QPushButton("Quit")
        quit_btn.setObjectName("quit")
        quit_btn.setFixedHeight(32)
        quit_btn.clicked.connect(on_quit)
        root.addWidget(quit_btn)

    def _update_color_btn_style(self, btn: QPushButton, hex_color: str):
        col = QColor(hex_color)
        if not col.isValid():
            col = QColor("#1e1e2e")
        text_col = "#000000" if (col.red() * 0.299 + col.green() * 0.587 + col.blue() * 0.114) > 150 else "#ffffff"
        btn.setText(f"  {col.name().upper()}")
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {col.name()};
                color: {text_col};
                border: 1px solid rgba(255, 255, 255, 70);
                border-radius: 6px;
                font-weight: 600;
                font-size: 12px;
                text-align: left;
                padding-left: 10px;
            }}
            QPushButton:hover {{
                border: 2px solid #89b4fa;
            }}
        """)

    def _pick_bg_color(self):
        col = QColorDialog.getColor(QColor(self.state.bg_color), self, "Select Background Color")
        if col.isValid():
            hex_str = col.name()
            self.state.update(bg_color=hex_str)
            self._update_color_btn_style(self.bg_color_btn, hex_str)
            self._sync_overlay_style()

    def _pick_text_color(self):
        col = QColorDialog.getColor(QColor(self.state.text_color), self, "Select Text Color")
        if col.isValid():
            hex_str = col.name()
            self.state.update(text_color=hex_str)
            self._update_color_btn_style(self.text_color_btn, hex_str)
            self._sync_overlay_style()

    def _on_opacity_changed(self, val: int):
        self.opacity_val_lbl.setText(f"{val}%")
        self.state.update(bg_opacity=val)
        self._sync_overlay_style()

    def _sync_overlay_style(self):
        if self.overlay:
            self.overlay.apply_style(
                bg_hex=self.state.bg_color,
                opacity_pct=self.state.bg_opacity,
                text_hex=self.state.text_color
            )

    def _on_api_key_changed(self, text: str = ""):
        key = self.api_key_input.text().strip()
        save_api_key(key)
        reload_client()
        self._update_api_status()

    def _on_model_changed(self, model: str):
        if model.strip():
            save_model_id(model.strip())
            reload_client()

    def _toggle_key_visibility(self):
        if self.api_key_input.echoMode() == QLineEdit.Password:
            self.api_key_input.setEchoMode(QLineEdit.Normal)
            self.toggle_key_btn.setText("🔒")
        else:
            self.api_key_input.setEchoMode(QLineEdit.Password)
            self.toggle_key_btn.setText("👁")

    def _update_api_status(self):
        if load_api_key().strip():
            self.api_status_lbl.setText("Trạng thái: ✅ Sẵn sàng (.env)")
            self.api_status_lbl.setStyleSheet("color: #a6e3a1; font-size: 11.5px; font-weight: 600;")
        else:
            self.api_status_lbl.setText("Trạng thái: ⚠️ Chưa có API Key (Cần nhập để dịch)")
            self.api_status_lbl.setStyleSheet("color: #fab387; font-size: 11.5px; font-weight: 600;")

    def start_ocr(self):
        if not load_api_key().strip():
            self.status.setText("⚠️ Vui lòng nhập OpenAI API Key trước khi bắt đầu!")
            self.status.setStyleSheet("color: #f38ba8; font-size: 12.5px; font-weight: 600;")
            self.api_section.setStyleSheet("""
                QFrame {
                    background-color: #232338;
                    border-radius: 8px;
                    border: 2px solid #f38ba8;
                }
                QLabel {
                    font-size: 12.5px;
                    color: #cdd6f4;
                }
                QLabel#sectionTitle {
                    font-size: 13px;
                    font-weight: 600;
                    color: #f38ba8;
                    padding-bottom: 2px;
                }
            """)
            QTimer.singleShot(2500, lambda: self.api_section.setStyleSheet("""
                QFrame {
                    background-color: #232338;
                    border-radius: 8px;
                    border: none;
                }
                QLabel {
                    font-size: 12.5px;
                    color: #cdd6f4;
                }
                QLabel#sectionTitle {
                    font-size: 13px;
                    font-weight: 600;
                    color: #89b4fa;
                    padding-bottom: 2px;
                }
            """))
            return

        if self.worker:
            self.worker.start_worker()
        self.status.setText("Running (Background Worker)")
        self.status.setStyleSheet("color: #a6e3a1; font-size: 12.5px;")

    def stop_ocr(self):
        if self.worker:
            self.worker.stop_worker()
        self.status.setText("Stopped")
        self.status.setStyleSheet("color: #f38ba8; font-size: 12.5px;")

