from PyQt5.QtGui import QColor
from ui.styles import TOKENS, FONT_FAMILY
from ui.controller_state import SubtitlePageState


def subtitle_preview_style(state: SubtitlePageState, *, compact: bool = False) -> str:
    bg_col = QColor(state.bg_color)
    if not bg_col.isValid():
        bg_col = QColor("#0e0f12")
    text_col = QColor(state.text_color)
    if not text_col.isValid():
        text_col = QColor("#ffffff")

    alpha = max(0.0, min(1.0, state.bg_opacity / 100.0))
    r, g, b = bg_col.red(), bg_col.green(), bg_col.blue()
    border = 'none' if compact else '1px solid rgba(255, 255, 255, 0.18)'

    return f"""
        QLabel {{
            color: {text_col.name()};
            background-color: rgba({r}, {g}, {b}, {alpha:.2f});
            font-size: {state.font_size}px;
            font-weight: 600;
            padding: {8 if compact else 10}px {16 if compact else 20}px;
            border-radius: {6 if compact else 12}px;
            border: {border};
            font-family: '{FONT_FAMILY}';
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
            border: 1px solid {TOKENS['focus']};
        }}
    """


def drag_button_style(is_active: bool) -> str:
    if is_active:
        return f"""
            QPushButton {{
                background-color: {TOKENS['positive_bg']};
                color: {TOKENS['positive']};
                border: 1px solid {TOKENS['positive']};
                border-radius: 6px;
                font-weight: 700;
                font-size: 12.5px;
                height: 34px;
            }}
            QPushButton:hover {{
                background-color: {TOKENS['raised']};
            }}
        """
    else:
        return f"""
            QPushButton {{
                background-color: {TOKENS['input']};
                color: {TOKENS['text']};
                border: 1px solid {TOKENS['border']};
                border-radius: 6px;
                font-weight: 600;
                font-size: 12px;
                height: 34px;
            }}
            QPushButton:hover {{
                border: 1px solid {TOKENS['focus']};
                background-color: {TOKENS['raised']};
            }}
        """


def preview_position(state, context):
    presets = {'bottom_center': (.5, .85), 'top_center': (.5, .15), 'bottom_left': (.2, .85)}
    if state.preset in presets:
        return presets[state.preset]
    # Saved overlay coordinates are Qt logical top-left values. A source image
    # is physical pixels and lacks the overlay size/work-area transform.
    return None
