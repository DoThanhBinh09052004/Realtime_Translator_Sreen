"""
Modern Cyber/Gaming Dark Theme - Design Tokens & Stylesheets
"""

CYBER_PALETTE = {
    # Nền
    "bg_main": "#0d0e17",
    "bg_primary": "#0d0e17",
    "bg_sidebar": "#131522",
    "bg_card": "#1a1d2e",
    "bg_card_hover": "#202439",
    "bg_input": "#22263d",
    "bg_input_hover": "#292e49",
    
    # Viền
    "border": "#282c44",
    "border_light": "#363c5d",
    "border_focus": "#6366f1",
    
    # Chữ
    "text_primary": "#f1f5f9",
    "text_secondary": "#cbd5e1",
    "text_muted": "#94a3b8",
    "text_dim": "#64748b",
    
    # Màu Neon Accents
    "neon_green": "#10b981",
    "neon_green_hover": "#34d399",
    "neon_green_bg": "rgba(16, 185, 129, 0.15)",
    
    # Neon Rose (Danger)
    "neon_rose": "#f43f5e",
    "neon_rose_hover": "#fb7185",
    "neon_rose_bg": "rgba(244, 63, 94, 0.15)",
    
    # Neon Indigo (Primary Accent)
    "neon_indigo": "#6366f1",
    "neon_indigo_hover": "#818cf8",
    "neon_indigo_bg": "rgba(99, 102, 241, 0.15)",
    
    # Amber (Warning)
    "neon_amber": "#fbbf24",
    "neon_amber_bg": "rgba(251, 191, 36, 0.15)"
}


def get_app_stylesheet() -> str:
    """Trả về CSS toàn cục cho ứng dụng"""
    p = CYBER_PALETTE
    return f"""
        QWidget {{
            background-color: {p['bg_main']};
            color: {p['text_primary']};
            font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", sans-serif;
            font-size: 13px;
        }}

        QLabel {{
            color: {p['text_primary']};
            background-color: transparent;
        }}

        /* Scroll Area & Scrollbars */
        QScrollArea {{
            border: none;
            background-color: transparent;
        }}

        QScrollBar:vertical {{
            border: none;
            background: {p['bg_main']};
            width: 7px;
            margin: 0px;
            border-radius: 3px;
        }}

        QScrollBar::handle:vertical {{
            background: {p['border_light']};
            min-height: 24px;
            border-radius: 3px;
        }}

        QScrollBar::handle:vertical:hover {{
            background: {p['neon_indigo']};
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}

        QScrollBar:horizontal {{
            height: 0px;
        }}

        /* Input Controls */
        QLineEdit, QComboBox, QSpinBox {{
            min-height: 32px;
            padding: 4px 10px;
            border-radius: 7px;
            background-color: {p['bg_input']};
            border: 1px solid {p['border']};
            color: {p['text_primary']};
            selection-background-color: {p['neon_indigo']};
        }}

        QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{
            border: 1px solid {p['border_light']};
            background-color: {p['bg_input_hover']};
        }}

        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border: 1px solid {p['neon_indigo']};
            background-color: {p['bg_input_hover']};
        }}

        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 26px;
            border-left: 1px solid {p['border']};
            border-top-right-radius: 7px;
            border-bottom-right-radius: 7px;
        }}

        QComboBox QAbstractItemView {{
            background-color: {p['bg_card']};
            color: {p['text_primary']};
            border: 1px solid {p['border']};
            border-radius: 7px;
            selection-background-color: {p['neon_indigo_bg']};
            selection-color: {p['text_primary']};
            padding: 4px;
            outline: none;
        }}

        QSpinBox::up-button, QSpinBox::down-button {{
            width: 18px;
            background: transparent;
            border: none;
        }}

        /* Tooltip */
        QToolTip {{
            background-color: {p['bg_card']};
            color: {p['text_primary']};
            border: 1px solid {p['neon_indigo']};
            border-radius: 5px;
            padding: 5px 8px;
            font-size: 12px;
        }}
    """


CARD_FRAME_STYLE = f"""
    QFrame#cardFrame {{
        background-color: {CYBER_PALETTE['bg_card']};
        border: 1px solid {CYBER_PALETTE['border']};
        border-radius: 10px;
    }}
"""

SIDEBAR_STYLE = f"""
    QFrame#sidebarFrame {{
        background-color: {CYBER_PALETTE['bg_sidebar']};
        border-right: 1px solid {CYBER_PALETTE['border']};
    }}
"""

NAV_BUTTON_NORMAL = f"""
    QPushButton {{
        background-color: transparent;
        color: {CYBER_PALETTE['text_muted']};
        border: none;
        border-left: 3px solid transparent;
        border-radius: 6px;
        padding: 9px 14px;
        text-align: left;
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: rgba(255, 255, 255, 0.04);
        color: {CYBER_PALETTE['text_primary']};
    }}
"""

NAV_BUTTON_ACTIVE = f"""
    QPushButton {{
        background-color: {CYBER_PALETTE['neon_indigo_bg']};
        color: #ffffff;
        border: none;
        border-left: 3px solid {CYBER_PALETTE['neon_indigo']};
        border-radius: 6px;
        padding: 9px 14px;
        text-align: left;
        font-size: 13px;
        font-weight: 700;
    }}
"""

HERO_START_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #34d399);
        color: #0b1511;
        border: none;
        border-radius: 8px;
        padding: 10px 18px;
        font-size: 14px;
        font-weight: 700;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #34d399, stop:1 #6ee7b7);
    }}
    QPushButton:pressed {{
        background: #059669;
    }}
"""

HERO_STOP_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f43f5e, stop:1 #fb7185);
        color: #17070b;
        border: none;
        border-radius: 8px;
        padding: 10px 18px;
        font-size: 14px;
        font-weight: 700;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #fb7185, stop:1 #fda4af);
    }}
    QPushButton:pressed {{
        background: #e11d48;
    }}
"""

SECONDARY_BUTTON_STYLE = f"""
    QPushButton {{
        background-color: {CYBER_PALETTE['bg_input']};
        color: {CYBER_PALETTE['text_primary']};
        border: 1px solid {CYBER_PALETTE['border']};
        border-radius: 7px;
        padding: 7px 12px;
        font-size: 12.5px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {CYBER_PALETTE['bg_input_hover']};
        border: 1px solid {CYBER_PALETTE['neon_indigo']};
    }}
    QPushButton:pressed {{
        background-color: {CYBER_PALETTE['bg_card']};
    }}
"""
