import os
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QPainterPath
from ui.icons import get_lucide_icon
from ui.styles import CYBER_PALETTE, SIDEBAR_STYLE, NAV_BUTTON_ACTIVE, NAV_BUTTON_NORMAL, SECONDARY_BUTTON_STYLE


class ControllerSidebar(QFrame):
    page_requested = pyqtSignal(int)
    quit_requested = pyqtSignal()

    def __init__(self, nav_items, logo_path, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebarFrame")
        self.setStyleSheet(SIDEBAR_STYLE)
        self.setFixedWidth(205)

        sidebar_layout = QVBoxLayout(self)
        sidebar_layout.setContentsMargins(14, 16, 14, 16)
        sidebar_layout.setSpacing(6)

        # Brand Header với Logo mới
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        
        brand_icon_lbl = QLabel()
        if logo_path and os.path.exists(logo_path):
            size = 28
            radius = 6
            src = QPixmap(logo_path).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            rounded_pix = QPixmap(size, size)
            rounded_pix.fill(Qt.transparent)
            painter = QPainter(rounded_pix)
            painter.setRenderHint(QPainter.Antialiasing)
            clip_path = QPainterPath()
            clip_path.addRoundedRect(0, 0, size, size, radius, radius)
            painter.setClipPath(clip_path)
            painter.drawPixmap(0, 0, src)
            painter.end()
            brand_icon_lbl.setPixmap(rounded_pix)
        else:
            zap_icon = get_lucide_icon("zap", color=CYBER_PALETTE['neon_indigo'], size=20)
            brand_icon_lbl.setPixmap(zap_icon.pixmap(20, 20))
        brand_row.addWidget(brand_icon_lbl)

        brand_text_box = QVBoxLayout()
        brand_text_box.setSpacing(1)
        brand_title = QLabel("Translate HUD")
        brand_title.setStyleSheet("font-size: 13.5px; font-weight: 700; letter-spacing: 0.2px;")
        brand_sub = QLabel("Realtime Screen OCR")
        brand_sub.setStyleSheet(f"font-size: 10.5px; color: {CYBER_PALETTE['text_muted']};")
        brand_text_box.addWidget(brand_title)
        brand_text_box.addWidget(brand_sub)
        brand_row.addLayout(brand_text_box)
        sidebar_layout.addLayout(brand_row)

        sidebar_layout.addSpacing(14)

        # Navigation Buttons (Lucide Vector Icons, Không Emoji)
        self.nav_buttons = []
        self.nav_item_defs = nav_items

        for idx, (icon_name, label_text, tooltip_text) in enumerate(self.nav_item_defs):
            btn = QPushButton(f"  {label_text}")
            btn.setToolTip(tooltip_text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(36)
            btn.setIconSize(QSize(17, 17))
            
            icon_col = "#ffffff" if idx == 0 else CYBER_PALETTE['text_muted']
            btn.setIcon(get_lucide_icon(icon_name, color=icon_col, size=17))
            btn.setStyleSheet(NAV_BUTTON_ACTIVE if idx == 0 else NAV_BUTTON_NORMAL)
            btn.clicked.connect(lambda checked, i=idx: self.page_requested.emit(i))
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sidebar_layout.addStretch()

        # Sidebar Footer: Live Status indicator & Quit
        status_box = QFrame()
        status_box.setStyleSheet(f"""
            QFrame {{
                background-color: {CYBER_PALETTE['bg_main']};
                border: 1px solid {CYBER_PALETTE['border']};
                border-radius: 7px;
                padding: 6px;
            }}
        """)
        status_layout = QVBoxLayout(status_box)
        status_layout.setContentsMargins(8, 6, 8, 6)
        status_layout.setSpacing(3)

        sys_status_lbl = QLabel("TRẠNG THÁI HỆ THỐNG")
        sys_status_lbl.setStyleSheet(f"font-size: 9.5px; font-weight: 600; color: {CYBER_PALETTE['text_dim']};")
        status_layout.addWidget(sys_status_lbl)

        self.status = QLabel("Đã dừng")
        self.status.setStyleSheet(f"font-size: 11.5px; font-weight: 600; color: {CYBER_PALETTE['neon_rose']};")
        status_layout.addWidget(self.status)
        sidebar_layout.addWidget(status_box)

        sidebar_layout.addSpacing(4)

        quit_btn = QPushButton("  Thoát")
        quit_btn.setFixedHeight(32)
        quit_btn.setIcon(get_lucide_icon("log-out", color=CYBER_PALETTE['text_muted'], size=14))
        quit_btn.setIconSize(QSize(14, 14))
        quit_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        quit_btn.setCursor(Qt.PointingHandCursor)
        quit_btn.clicked.connect(self.quit_requested.emit)
        self.quit_button = quit_btn
        sidebar_layout.addWidget(quit_btn)


    def set_active_page(self, index):
        for i, btn in enumerate(self.nav_buttons):
            is_active = (i == index)
            btn.setStyleSheet(NAV_BUTTON_ACTIVE if is_active else NAV_BUTTON_NORMAL)
            icon_name = self.nav_item_defs[i][0]
            icon_col = "#ffffff" if is_active else CYBER_PALETTE['text_muted']
            btn.setIcon(get_lucide_icon(icon_name, color=icon_col, size=17))

    def set_status(self, text, style):
        self.status.setText(text)
        self.status.setStyleSheet(style)
