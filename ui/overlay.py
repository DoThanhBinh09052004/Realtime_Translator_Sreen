from PyQt5.QtWidgets import QLabel, QGraphicsDropShadowEffect
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt5.QtGui import QColor
from ui.block_overlay import BlockOverlay


class Overlay(QLabel):
    """
    Overlay hiển thị phụ đề nổi Modern Gaming HUD trên màn hình.
    Có hiệu ứng mờ dần (fade), bóng đổ khối cao cấp (Drop Shadow),
    giới hạn chiều rộng thông minh, hỗ trợ presets và chế độ mở khóa kéo thả tự do.
    """

    position_changed = pyqtSignal(int, int)
    capture_geometry_changed = pyqtSignal(object)
    block_error = pyqtSignal(object)

    def showEvent(self, event):
        super().showEvent(event)
        self.capture_geometry_changed.emit(self.get_geometry_rect())

    def hideEvent(self, event):
        super().hideEvent(event)
        self.capture_geometry_changed.emit(None)

    def moveEvent(self, event):
        super().moveEvent(event)
        self.capture_geometry_changed.emit(self.get_geometry_rect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.capture_geometry_changed.emit(self.get_geometry_rect())

    def __init__(self, bg_hex="#1e1e2e", opacity_pct=80, text_hex="#ffffff", font_size=22):
        super().__init__()
        self._mode = 'subtitle'
        self._mode_revision = 0
        self._block_frame_id = -1
        self._last_subtitle_candidate_id = -1
        self.block_overlay = BlockOverlay(self)
        self.block_overlay.block_error.connect(self.block_error.emit)

        # ===== 1. Cấu hình Window Flag =====
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # Xuyên thấu chuột mặc định

        # ===== 2. State & Styling =====
        self.bg_hex = bg_hex
        self.opacity_pct = opacity_pct
        self.text_hex = text_hex
        self.font_size = font_size
        self.current_preset = "bottom_center"
        self.is_drag_mode = False
        self._last_normal_text = "Subtitle Ready"

        # Note: Tránh gán QGraphicsDropShadowEffect trực tiếp lên Top-Level Translucent Window
        # vì Windows Layered Window API sẽ báo lỗi UpdateLayeredWindowIndirect (dirty rect âm).

        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)

        # Cài đặt kích thước tối đa 75% màn hình
        screen_geo = self.screen().availableGeometry()
        self.setMaximumWidth(int(screen_geo.width() * 0.75))

        self.apply_style(bg_hex, opacity_pct, text_hex, font_size)

        # ===== 3. Auto hide =====
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(6000)
        self.hide_timer.timeout.connect(self.fade_out)

        # ===== 4. Fade animation =====
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(280)
        self.fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.fade_anim.finished.connect(self._on_fade_finished)

        # ===== 5. Khởi tạo vị trí =====
        self.setText("Subtitle Ready")
        self.adjustSize()
        self.apply_preset("bottom_center")
        self.hide()

    def apply_style(self, bg_hex: str = None, opacity_pct: int = None, text_hex: str = None, font_size: int = None):
        """
        Cập nhật màu nền, độ mờ đục, màu chữ và cỡ chữ cho phụ đề.
        """
        self.block_overlay.apply_style(bg_hex, opacity_pct, text_hex, font_size)
        if bg_hex is not None:
            self.bg_hex = bg_hex
        if opacity_pct is not None:
            self.opacity_pct = opacity_pct
        if text_hex is not None:
            self.text_hex = text_hex
        if font_size is not None:
            self.font_size = font_size

        bg_col = QColor(self.bg_hex)
        if not bg_col.isValid():
            bg_col = QColor("#1e1e2e")

        text_col = QColor(self.text_hex)
        if not text_col.isValid():
            text_col = QColor("#ffffff")

        alpha = max(0.0, min(1.0, self.opacity_pct / 100.0))
        r, g, b = bg_col.red(), bg_col.green(), bg_col.blue()

        border_css = "2px dashed #6366f1" if self.is_drag_mode else "1px solid rgba(255, 255, 255, 0.18)"

        self.setStyleSheet(f"""
            QLabel {{
                color: {text_col.name()};
                background-color: rgba({r}, {g}, {b}, {alpha:.2f});
                font-size: {self.font_size}px;
                font-weight: 600;
                padding: 10px 22px;
                border-radius: 12px;
                border: {border_css};
                font-family: 'Segoe UI', 'Inter', 'Arial', sans-serif;
            }}
        """)

    def apply_preset(self, preset: str):
        """Định vị phụ đề theo các vị trí preset phổ biến"""
        screen = self.screen().availableGeometry()
        w = max(self.width(), 200)
        h = max(self.height(), 40)

        if preset == "top_center":
            x = (screen.width() - w) // 2
            y = screen.top() + 60
        elif preset == "bottom_left":
            x = screen.left() + 60
            y = screen.height() - h - 80
        elif preset == "bottom_center":
            x = (screen.width() - w) // 2
            y = screen.height() - h - 80
        else:
            return

        self.current_preset = preset
        self.move(x, y)

    def set_drag_mode(self, enabled: bool):
        """Bật/tắt chế độ kéo thả định vị phụ đề trên màn hình"""
        if self._mode == 'blocks':
            return
        self.is_drag_mode = enabled
        if enabled:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.setCursor(Qt.SizeAllCursor)
            self._last_normal_text = self.text()
            self.setText("✥ Giữ chuột để kéo phụ đề đến vị trí mong muốn")
            self.adjustSize()
            self.apply_style()
            self.fade_anim.stop()
            self.setWindowOpacity(1.0)
            self.show()
            self.raise_()
        else:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.unsetCursor()
            self.apply_style()
            if self._last_normal_text and self._last_normal_text.strip():
                self.setText(self._last_normal_text)
                self.adjustSize()
            else:
                self.setText("")
                self.hide()

    def mousePressEvent(self, event):
        if self.is_drag_mode and event.button() == Qt.LeftButton:
            self._drag_start_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_drag_mode and event.buttons() == Qt.LeftButton and hasattr(self, "_drag_start_pos"):
            new_pos = event.globalPos() - self._drag_start_pos
            self.move(new_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_drag_mode and event.button() == Qt.LeftButton:
            self.current_preset = "custom"
            self.position_changed.emit(self.x(), self.y())
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def move_to_bottom_center(self):
        self.apply_preset("bottom_center")

    def get_geometry_rect(self):
        if self._mode == 'blocks' or not self.isVisible():
            return None
        return (self.x(), self.y(), self.width(), self.height())

    # ===== Cập nhật hiển thị =====
    def update_text(self, text: str):
        if self._mode == 'blocks':
            return
        if not text or not text.strip():
            self.fade_out()
            return

        if self.is_drag_mode:
            self._last_normal_text = text
            return

        center_x = self.x() + self.width() // 2
        bottom_y = self.y() + self.height()

        self.setText(text)
        self.adjustSize()

        new_x = center_x - self.width() // 2
        new_y = bottom_y - self.height()

        # Giữ phụ đề trong phạm vi màn hình
        screen = self.screen().availableGeometry()
        new_x = max(10, min(new_x, screen.width() - self.width() - 10))
        new_y = max(10, min(new_y, screen.height() - self.height() - 10))
        self.move(new_x, new_y)

        self._show_with_timer()

    def refresh(self):
        """Giữ cho overlay sáng và reset timer tự ẩn"""
        if self._mode == 'blocks' or not self.text().strip():
            return
        if not self.isVisible() or self.windowOpacity() < 1.0:
            self.fade_in()
        self.hide_timer.start()

    def clear(self):
        self.block_overlay.clear()
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
        if self._mode == 'blocks':
            return
        super().show()
        self.raise_()

    def hide(self):
        if hasattr(self, 'block_overlay'):
            self.block_overlay.hide()
        super().hide()

    def closeEvent(self, event):
        self.block_overlay.close()
        super().closeEvent(event)

    def set_mode(self, mode, revision):
        self.hide_timer.stop()
        self.fade_anim.stop()
        self.block_overlay.clear()
        self._mode, self._mode_revision, self._block_frame_id = mode, revision, -1
        self._last_subtitle_candidate_id = -1
        self.is_drag_mode = False
        self.setText('')
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.unsetCursor()
        self.apply_style()
        self.hide()
        self.capture_geometry_changed.emit(None)

    def update_blocks(self, frame):
        if (self._mode != 'blocks' or frame.revision != self._mode_revision
                or frame.frame_id < self._block_frame_id):
            return
        self._block_frame_id = frame.frame_id
        self.block_overlay.set_frame(frame)

    def update_subtitle(self, frame):
        if (self._mode != 'subtitle' or frame.revision != self._mode_revision
                or frame.candidate_id < self._last_subtitle_candidate_id):
            return
        self._last_subtitle_candidate_id = frame.candidate_id
        if frame.text:
            self.update_text(frame.text)
        else:
            self.hide_timer.stop()
            self.fade_anim.stop()
            self.setText('')
            self.hide()
