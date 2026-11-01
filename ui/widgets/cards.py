from PyQt5.QtWidgets import QFrame, QSizePolicy, QVBoxLayout, QHBoxLayout, QLabel
from ui.styles import TOKENS, set_style, apply_widget_theme, card_style


class ModernCard(QFrame):
    """Thẻ container nội dung phong cách Linear Pro Card"""
    def __init__(self, title: str = "", subtitle: str = ""):
        super().__init__()
        self.setObjectName("cardFrame")
        set_style(self, card_style('tokens'))
        
        self.box_layout = QVBoxLayout(self)
        self.box_layout.setContentsMargins(16, 14, 16, 16)
        self.box_layout.setSpacing(10)
        
        if title:
            header_layout = QVBoxLayout()
            header_layout.setSpacing(2)
            
            t_lbl = QLabel(title)
            t_lbl.setWordWrap(True)
            t_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            set_style(t_lbl, f"""
                font-size: 13px;
                font-weight: 600;
                color: {TOKENS['text']};
            """)
            header_layout.addWidget(t_lbl)
            
            if subtitle:
                sub_lbl = QLabel(subtitle)
                sub_lbl.setWordWrap(True)
                sub_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
                set_style(sub_lbl, f"""
                    font-size: 11.5px;
                    color: {TOKENS['muted']};
                """)
                header_layout.addWidget(sub_lbl)
                
            self.box_layout.addLayout(header_layout)

    @property
    def layout(self):
        return self.box_layout

    def apply_theme(self, theme):
        apply_widget_theme(self, theme)
