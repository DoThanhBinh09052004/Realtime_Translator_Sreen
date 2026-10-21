from PyQt5.QtGui import QColor
from ui.styles import CYBER_PALETTE
from ui.controller_state import SubtitlePageState


def subtitle_preview_style(state: SubtitlePageState) -> str:
    bg_col = QColor(state.bg_color)
    if not bg_col.isValid():
        bg_col = QColor("#0e0f12")
    text_col = QColor(state.text_color)
    if not text_col.isValid():
        text_col = QColor("#ffffff")

    alpha = max(0.0, min(1.0, state.bg_opacity / 100.0))
    r, g, b = bg_col.red(), bg_col.green(), bg_col.blue()

    return f"""
        QLabel {{
            color: {text_col.name()};
            background-color: rgba({r}, {g}, {b}, {alpha:.2f});
            font-size: {state.font_size}px;
            font-weight: 600;
            padding: 10px 20px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.18);
            font-family: 'Segoe UI', 'Inter', 'Arial', sans-serif;
        }}
    """


def color_button_presentation(hex_color: str) -> tuple[str, str]:
    col = QColor(hex_color)
    if not col.isValid():
        col = QColor("#14151a")
    text_col = "#000000" if (col.red() * 0.299 + col.green() * 0.587 + col.blue() * 0.114) > 150 else "#ffffff"
    text = f"  {col.name().upper()}"
    return text, f"""
        QPushButton {{
            background-color: {col.name()};
            color: {text_col};
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 6px;
            font-weight: 600;
            font-size: 12px;
            text-align: left;
            padding-left: 12px;
        }}
        QPushButton:hover {{
            border: 1px solid {CYBER_PALETTE['neon_indigo']};
        }}
    """


def drag_button_style(is_active: bool) -> str:
    if is_active:
        return f"""
            QPushButton {{
                background-color: {CYBER_PALETTE['neon_green']};
                color: #0b101b;
                border: 1px solid #34d399;
                border-radius: 6px;
                font-weight: 700;
                font-size: 12.5px;
                height: 34px;
            }}
            QPushButton:hover {{
                background-color: #34d399;
            }}
        """
    else:
        return f"""
            QPushButton {{
                background-color: {CYBER_PALETTE['bg_input']};
                color: {CYBER_PALETTE['text_primary']};
                border: 1px solid {CYBER_PALETTE['border']};
                border-radius: 6px;
                font-weight: 600;
                font-size: 12px;
                height: 34px;
            }}
            QPushButton:hover {{
                border: 1px solid {CYBER_PALETTE['neon_indigo']};
                background-color: {CYBER_PALETTE['bg_card_hover']};
            }}
        """
