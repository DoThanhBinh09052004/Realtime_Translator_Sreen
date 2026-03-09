# controller.py sửa: 
# - Source combo: Chỉ "English" và "Japanese" (default "English")
# - Target combo: Chỉ "Vietnamese" (cố định, nhưng vẫn giữ combo cho nhất quán, hoặc có thể làm label nếu muốn đơn giản hơn)
# - Xóa "Auto" và "Vietnamese" khỏi source options

from PyQt5.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QComboBox, QFrame
)
from PyQt5.QtCore import Qt

LANGUAGES_SOURCE = ["English", "Japanese"]  # Chỉ source: Eng và Jap
LANGUAGES_TARGET = ["Vietnamese"]  # Chỉ target: Viet

LANGUAGE_MAP = {
    "English": "English",
    "Japanese": "Japanese",
    "Vietnamese": "Vietnamese"
}


class Section(QFrame):
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
    def __init__(self, timer, state, on_select_region, on_quit):
        super().__init__()

        self.timer = timer
        self.state = state

        # ===== WINDOW =====
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
        src.addItems(LANGUAGES_SOURCE)
        src.setCurrentText("English")
        src.currentTextChanged.connect(
            lambda t: self.state.update(source=LANGUAGE_MAP[t])
        )
        lang.layout.addWidget(src)

        lang.layout.addWidget(QLabel("Target"))
        tgt = QComboBox()
        tgt.addItems(LANGUAGES_TARGET)
        tgt.setCurrentText("Vietnamese")
        tgt.currentTextChanged.connect(
            lambda t: self.state.update(target=LANGUAGE_MAP[t])
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
        interval.setRange(150, 2000)
        interval.setValue(timer.interval())
        interval.valueChanged.connect(timer.setInterval)
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
        self.timer.start()
        self.status.setText("Running")
        self.status.setStyleSheet("color: #a6e3a1; font-size: 12.5px;")

    def stop_ocr(self):
        self.timer.stop()
        self.status.setText("Stopped")
        self.status.setStyleSheet("color: #f38ba8; font-size: 12.5px;")