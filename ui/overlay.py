from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QColor


class Overlay(QLabel):
    """
    Overlay hiển thị phụ đề nổi trên màn hình.
    Có hiệu ứng mờ dần (fade), tự căn giữa màn hình và cho phép click chuột xuyên thấu vào game.
    """

    def __init__(self, bg_hex="#1e1e2e", opacity_pct=80, text_hex="#ffffff"):
        super().__init__()

        # ===== 1. Cấu hình Window Flag =====
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # Xuyên thấu chuột, không chặn click game

        # ===== 2. Styling =====
        self.apply_style(bg_hex, opacity_pct, text_hex)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)

    def apply_style(self, bg_hex: str = "#1e1e2e", opacity_pct: int = 80, text_hex: str = "#ffffff"):
        """
        Cập nhật màu nền, độ mờ đục và màu chữ cho phụ đề.
        """
        bg_col = QColor(bg_hex)
        if not bg_col.isValid():
            bg_col = QColor("#1e1e2e")

        text_col = QColor(text_hex)
        if not text_col.isValid():
            text_col = QColor("#ffffff")

        alpha = max(0.0, min(1.0, opacity_pct / 100.0))
        r, g, b = bg_col.red(), bg_col.green(), bg_col.blue()

        self.setStyleSheet(f"""
            QLabel {{
                color: {text_col.name()};
                background-color: rgba({r}, {g}, {b}, {alpha:.2f});
                font-size: 22px;
                padding: 12px 20px;
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 40);
                font-family: 'Segoe UI', 'Arial';
            }}
        """)

        # ===== 3. Auto hide =====
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(6000)
        self.hide_timer.timeout.connect(self.fade_out)

        # ===== 4. Fade animation =====
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(300)
        self.fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.fade_anim.finished.connect(self._on_fade_finished)

        # ===== 5. Khởi tạo vị trí =====
        self.setText("Subtitle Ready")
        self.adjustSize()
        self.move_to_bottom_center()
        self.hide()

    def move_to_bottom_center(self):
        screen = self.screen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = screen.height() - self.height() - 80
        self.move(x, y)

    def get_geometry_rect(self):
        if not self.isVisible():
            return None
        return (self.x(), self.y(), self.width(), self.height())

    # ===== Cập nhật hiển thị =====
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
        """Giữ cho overlay sáng và reset timer tự ẩn"""
        if not self.isVisible() or self.windowOpacity() < 1.0:
            self.fade_in()
        self.hide_timer.start()

    def clear(self):
        self.hide_timer.stop()
        self.fade_out()

    # ===== Fade Animations =====
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
        self.fade_anim.start()

    def _on_fade_finished(self):
        if self.windowOpacity() <= 0.01:
            self.hide()


    def show(self):
        super().show()
        self.raise_()
