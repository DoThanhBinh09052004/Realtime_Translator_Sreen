from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from ui.styles import CARD_FRAME_STYLE, CYBER_PALETTE
from ui.icons import get_lucide_icon


class ModernCard(QFrame):
    """Thẻ container nội dung phong cách Linear Pro Card"""
    def __init__(self, title: str = "", subtitle: str = ""):
        super().__init__()
        self.setObjectName("cardFrame")
        self.setStyleSheet(CARD_FRAME_STYLE)
        
        self.box_layout = QVBoxLayout(self)
        self.box_layout.setContentsMargins(16, 14, 16, 16)
        self.box_layout.setSpacing(10)
        
        if title:
            header_layout = QVBoxLayout()
            header_layout.setSpacing(2)
            
            t_lbl = QLabel(title)
            t_lbl.setStyleSheet(f"""
                font-size: 13px;
                font-weight: 600;
                color: {CYBER_PALETTE['text_primary']};
            """)
            header_layout.addWidget(t_lbl)
            
            if subtitle:
                sub_lbl = QLabel(subtitle)
                sub_lbl.setStyleSheet(f"""
                    font-size: 11.5px;
                    color: {CYBER_PALETTE['text_muted']};
                """)
                header_layout.addWidget(sub_lbl)
                
            self.box_layout.addLayout(header_layout)

    @property
    def layout(self):
        return self.box_layout


class MetricCard(QFrame):
    """Thẻ tóm tắt thông số với vector Lucide Icon"""
    def __init__(self, title: str, value: str = "--", icon_name: str = "activity", icon_color: str = "#8c90a4"):
        super().__init__()
        self.setObjectName("metricCard")
        self.setStyleSheet(f"""
            QFrame#metricCard {{
                background-color: {CYBER_PALETTE['bg_input']};
                border: 1px solid {CYBER_PALETTE['border']};
                border-radius: 7px;
                padding: 4px;
            }}
            QFrame#metricCard:hover {{
                border: 1px solid {CYBER_PALETTE['border_light']};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        
        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        icon_lbl = QLabel()
        icon = get_lucide_icon(icon_name, color=icon_color, size=15)
        icon_lbl.setPixmap(icon.pixmap(15, 15))
        header_row.addWidget(icon_lbl)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(f"font-size: 10.5px; font-weight: 600; color: {CYBER_PALETTE['text_muted']}; letter-spacing: 0.3px;")
        header_row.addWidget(t_lbl)
        header_row.addStretch()
        layout.addLayout(header_row)
        
        self.val_lbl = QLabel(value)
        self.val_lbl.setStyleSheet(f"""
            font-size: 12px;
            font-weight: 600;
            color: {CYBER_PALETTE['text_primary']};
        """)
        self.val_lbl.setWordWrap(True)
        layout.addWidget(self.val_lbl)
        
    def set_value(self, val: str):
        self.val_lbl.setText(val)
