"""Small startup UI; deliberately imports no OCR or application runtime."""
import importlib
import json
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QFrame, QLabel, QVBoxLayout, QHBoxLayout,
                            QProgressBar, QApplication)

from ui.styles import apply_widget_theme, set_style


def saved_startup_theme():
    from core.paths import get_app_paths
    try:
        data = json.loads((get_app_paths().config_dir / 'config.json').read_text(encoding='utf-8'))
        return 'dark' if data.get('ui_theme') == 'dark' else 'light'
    except (OSError, ValueError):
        return 'light'


class StartupSplash(QFrame):
    def __init__(self, theme='light'):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint)
        self.setObjectName('startupSplash')
        self.setFixedSize(580, 300)
        self.setWindowTitle('Translate HUD — Đang khởi động')
        set_style(self, 'QFrame#startupSplash {background:@ground@;border:1px solid @border_control@;border-radius:10px;} QLabel {border:0;}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 28)
        layout.setSpacing(20)
        brand = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(QPixmap(str(Path(__file__).parent / ('logo-dark.png' if theme == 'dark' else 'logo.png'))).scaled(90, 84, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        brand.addWidget(mark)
        text = QVBoxLayout()
        title = QLabel('Translate HUD')
        set_style(title, 'font-family:"Segoe UI";font-size:28px;font-weight:600;color:@text@;')
        subtitle = QLabel('Dịch màn hình theo thời gian thực')
        set_style(subtitle, 'font-size:13px;color:@muted@;')
        text.addWidget(title)
        text.addWidget(subtitle)
        brand.addLayout(text, 1)
        layout.addLayout(brand)
        layout.addStretch()
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(6)
        self.progress.setTextVisible(False)
        set_style(self.progress, 'QProgressBar {background:@raised@;border:0;border-radius:3px;} QProgressBar::chunk {background:@focus@;border-radius:3px;}')
        layout.addWidget(self.progress)
        self.status = QLabel('Đang tải thiết lập…')
        self.status.setAlignment(Qt.AlignCenter)
        set_style(self.status, 'font-size:14px;color:@text@;')
        layout.addWidget(self.status)
        footer = QLabel('Vui lòng chờ trong giây lát')
        footer.setAlignment(Qt.AlignCenter)
        set_style(footer, 'font-size:12px;color:@muted@;')
        layout.addWidget(footer)
        apply_widget_theme(self, theme)
        self.move(QApplication.primaryScreen().availableGeometry().center() - self.rect().center())

    def set_stage(self, message):
        self.status.setText(message)

    def closeEvent(self, event):
        # Startup owns the runtime thread; never destroy it while importing.
        event.ignore()


class StartupLoader(QThread):
    stage = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.error = False

    def run(self):
        try:
            for message, modules in (
                ('Đang tải thiết lập…', ('core.config',)),
                ('Đang chuẩn bị OCR…', ('engines.ocr', 'core.runtime.worker')),
                ('Đang tải giao diện…', ('ui.overlay', 'ui.controller', 'ui.game_controls',
                    'ui.region_selection', 'ui.capture_binding', 'ui.screen_geometry',
                    'core.language_packs.manager')),
            ):
                self.stage.emit(message)
                for module in modules:
                    importlib.import_module(module)
        except Exception:
            self.error = True
