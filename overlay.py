from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve


class Overlay(QLabel):
    """Overlay hiển thị subtitle – KHÔNG kéo thả"""

    def __init__(self):
        super().__init__()

        # ===== 1. Window config =====
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # ===== 2. UI =====
        self.setStyleSheet("""
            QLabel {
                color: black;
                background-color: white;
                font-size: 22px;
                padding: 12px 20px;
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 60);
                font-family: 'Segoe UI', 'Arial';
            }
        """)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)

        # ===== 3. Auto hide =====
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(6000)
        self.hide_timer.timeout.connect(self.fade_out)

        # ===== 4. Fade animation =====
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(300)
        self.fade_anim.setEasingCurve(QEasingCurve.InOutQuad)

        # ===== 5. Init =====
        self.setText("Subtitle Ready")
        self.adjustSize()
        self.move_to_bottom_center()
        self.hide()

    def move_to_bottom_center(self):
        screen = self.screen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = screen.height() - self.height() - 80
        self.move(x, y)

    # ===== Update text =====
    def update_text(self, text: str):
        if not text or not text.strip():
            self.fade_out()
            return

        center_x = self.x() + self.width() // 2
        bottom_y = self.y() + self.height()

        self.setText(text)
        self.adjustSize()

        new_x = center_x - self.width() // 2
        new_y = bottom_y - self.height()
        self.move(new_x, new_y)

        self._show_with_timer()

    def refresh(self):
        if not self.isVisible() or self.windowOpacity() < 1.0:
            self.fade_in()
        self.hide_timer.start()

    def clear(self):
        self.hide_timer.stop()
        self.fade_out()

    # ===== Fade =====
    def _show_with_timer(self):
        if not self.isVisible() or self.windowOpacity() < 1.0:
            self.fade_in()
        self.hide_timer.start()

    def fade_in(self):
        self.fade_anim.stop()
        self.show()
        self.fade_anim.setStartValue(self.windowOpacity())
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()

    def fade_out(self):
        self.fade_anim.stop()
        self.fade_anim.setStartValue(self.windowOpacity())
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.finished.connect(self._on_fade_out_finished)
        self.fade_anim.start()

    def _on_fade_out_finished(self):
        if self.windowOpacity() == 0:
            self.hide()
            try:
                self.fade_anim.finished.disconnect(self._on_fade_out_finished)
            except TypeError:
                pass

    def show(self):
        super().show()
        self.raise_()