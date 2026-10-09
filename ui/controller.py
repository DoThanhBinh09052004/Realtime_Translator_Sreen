from PyQt5.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QComboBox, QFrame
)
from PyQt5.QtCore import Qt

from core.config import SUPPORTED_LANGUAGES, SUPPORTED_TARGETS, load_config, save_config



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
    def __init__(self, worker, state, on_select_region, on_quit):
        super().__init__()

        self.worker = worker
        self.state = state

        # ===== Cấu hình Window =====
        self.setWindowTitle("Game Translator")
        self.setFixedSize(520, 600)

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
        saved_interval = load_config().get("interval_ms", worker.interval())
        worker.setInterval(saved_interval)
        interval.setValue(saved_interval)
        interval.valueChanged.connect(
            lambda v: (worker.setInterval(v), save_config("interval_ms", v))
        )
        ocr.layout.addWidget(interval)

        root.addWidget(ocr)

        root.addStretch()

        # ===== FOOTER =====
        quit_btn = QPushButton("Quit")
        quit_btn.setObjectName("quit")
        quit_btn.setFixedHeight(32)
        quit_btn.clicked.connect(on_quit)
        root.addWidget(quit_btn)

    def start_ocr(self):
        self.worker.start_worker()
        self.status.setText("Running (Background Worker)")
        self.status.setStyleSheet("color: #a6e3a1; font-size: 12.5px;")

    def stop_ocr(self):
        self.worker.stop_worker()
        self.status.setText("Stopped")
        self.status.setStyleSheet("color: #f38ba8; font-size: 12.5px;")
