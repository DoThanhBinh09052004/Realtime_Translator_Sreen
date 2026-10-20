"""
Linear / Raycast Pro Dark Theme - Design Tokens & Stylesheets
"""

CYBER_PALETTE = {
    # Nền (Linear Pro Matte Dark)
    "bg_main": "#0e0f12",
    "bg_primary": "#0e0f12",
    "bg_sidebar": "#14151a",
    "bg_card": "#191a21",
    "bg_card_hover": "#20222b",
    "bg_input": "#1f212a",
    "bg_input_hover": "#252834",
    
    # Viền (Subtle Precision 1px Borders)
    "border": "#23252e",
    "border_card": "#282a36",
    "border_light": "#323544",
    "border_focus": "#6366f1",
    
    # Chữ (High-clarity Typography)
    "text_primary": "#f4f4f7",
    "text_secondary": "#c5c8d8",
    "text_muted": "#8c90a4",
    "text_dim": "#616578",
    
    # Accent Colors (Professional SaaS Palette)
    "neon_green": "#10b981",
    "neon_green_hover": "#059669",
    "neon_green_bg": "rgba(16, 185, 129, 0.12)",
    
    "neon_rose": "#f43f5e",
    "neon_rose_hover": "#e11d48",
    "neon_rose_bg": "rgba(244, 63, 94, 0.12)",
    
    "neon_indigo": "#6366f1",
    "neon_indigo_hover": "#4f46e5",
    "neon_indigo_bg": "rgba(99, 102, 241, 0.12)",
    
    "neon_amber": "#f59e0b",
    "neon_amber_bg": "rgba(245, 158, 11, 0.12)"
}


def get_app_stylesheet() -> str:
    """Trả về CSS toàn cục phong cách Linear / Raycast Pro"""
    p = CYBER_PALETTE
    return f"""
        QWidget {{
            background-color: {p['bg_main']};
            color: {p['text_primary']};
            font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Inter", "Roboto", sans-serif;
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
            width: 6px;
            margin: 0px;
            border-radius: 3px;
        }}

        QScrollBar::handle:vertical {{
            background: {p['border_light']};
            min-height: 20px;
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
            border-radius: 6px;
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
            width: 24px;
            border-left: 1px solid {p['border']};
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
        }}

        QComboBox QAbstractItemView {{
            background-color: {p['bg_card']};
            color: {p['text_primary']};
            border: 1px solid {p['border_card']};
            border-radius: 6px;
            selection-background-color: {p['neon_indigo_bg']};
            selection-color: #ffffff;
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
            border: 1px solid {p['border_card']};
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 12px;
        }}
    """


CARD_FRAME_STYLE = f"""
    QFrame#cardFrame {{
        background-color: {CYBER_PALETTE['bg_card']};
        border: 1px solid {CYBER_PALETTE['border_card']};
        border-radius: 8px;
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
        padding: 8px 12px;
        text-align: left;
        font-size: 13px;
        font-weight: 500;
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
        padding: 8px 12px;
        text-align: left;
        font-size: 13px;
        font-weight: 600;
    }}
"""

HERO_START_STYLE = f"""
    QPushButton {{
        background-color: #10b981;
        color: #ffffff;
        border: 1px solid #059669;
        border-radius: 6px;
        padding: 9px 16px;
        font-size: 13.5px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: #059669;
    }}
    QPushButton:pressed {{
        background-color: #047857;
    }}
"""

HERO_STOP_STYLE = f"""
    QPushButton {{
        background-color: #f43f5e;
        color: #ffffff;
        border: 1px solid #e11d48;
        border-radius: 6px;
        padding: 9px 16px;
        font-size: 13.5px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: #e11d48;
    }}
    QPushButton:pressed {{
        background-color: #be123c;
    }}
"""

SECONDARY_BUTTON_STYLE = f"""
    QPushButton {{
        background-color: {CYBER_PALETTE['bg_input']};
        color: {CYBER_PALETTE['text_primary']};
        border: 1px solid {CYBER_PALETTE['border_card']};
        border-radius: 6px;
        padding: 7px 12px;
        font-size: 12.5px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {CYBER_PALETTE['bg_input_hover']};
        border: 1px solid {CYBER_PALETTE['border_light']};
    }}
    QPushButton:pressed {{
        background-color: {CYBER_PALETTE['bg_card']};
    }}
"""
