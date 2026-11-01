"""Shared window palettes and styles; subtitle colors remain user-controlled."""
from types import MappingProxyType
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPalette, QColor

_LIGHT = dict(ground='#fafaf9', sidebar='#f2f2f0', surface='#ffffff', input='#ffffff', input_hover='#f4f4f3', raised='#eeeeec', border='#e3e3e0', border_control='#c8c8c4', text='#191919', muted='#61615e', focus='#376a77', selection_bg='#dce9ed', selection_text='#152b31', primary_bg='#191919', primary_text='#ffffff', primary_hover='#333333', positive='#23704d', warning='#895300', negative='#b52c40', positive_bg='#e8f3ec', warning_bg='#fff3db', negative_bg='#fcebef')
_DARK = dict(ground='#161616', sidebar='#1c1c1c', surface='#202020', input='#252525', input_hover='#303030', raised='#333333', border='#363636', border_control='#626262', text='#f2f2f0', muted='#b5b5b0', focus='#8fc9d1', selection_bg='#365158', selection_text='#ffffff', primary_bg='#eeeeeb', primary_text='#191919', primary_hover='#ffffff', positive='#83d3a5', warning='#edbf6c', negative='#ff96a6', positive_bg='#203b2b', warning_bg='#49391e', negative_bg='#472831')
_PALETTES = {'light': MappingProxyType(_LIGHT), 'dark': MappingProxyType(_DARK)}
TOKENS = MappingProxyType({key: f'@{key}@' for key in _LIGHT})


def get_palette(theme: str = 'light'):
    return _PALETTES.get(theme, _PALETTES['light'])


def theme_for(widget) -> str:
    while widget is not None:
        if hasattr(widget, '_ui_theme'):
            return widget._ui_theme
        widget = widget.parentWidget()
    return 'light'


def palette_for(widget):
    return get_palette(theme_for(widget))


def _resolve(template: str, theme: str) -> str:
    for key, value in get_palette(theme).items():
        template = template.replace(f'@{key}@', value)
    return template


def set_style(widget, template: str) -> None:
    """Store semantic placeholders, so later renders cannot restore stale colors."""
    widget._theme_style = template
    widget.setStyleSheet(_resolve(template, theme_for(widget)))


def apply_widget_theme(widget, theme: str) -> None:
    widget._ui_theme = theme
    p = get_palette(theme)
    palette = widget.palette()
    for role, color in ((QPalette.Window, 'ground'), (QPalette.WindowText, 'text'),
                        (QPalette.Base, 'input'), (QPalette.Text, 'text'),
                        (QPalette.Button, 'input'), (QPalette.ButtonText, 'text'),
                        (QPalette.Highlight, 'selection_bg'), (QPalette.HighlightedText, 'selection_text'),
                        (QPalette.ToolTipBase, 'surface'), (QPalette.ToolTipText, 'text')):
        palette.setColor(role, QColor(p[color]))
    widget.setPalette(palette)
    from ui.icons import get_lucide_icon
    for child in (widget, *widget.findChildren(QWidget)):
        child._ui_theme = theme
        if hasattr(child, '_theme_style'):
            child.setStyleSheet(_resolve(child._theme_style, theme))
        if hasattr(child, '_theme_icon'):
            name, role, size = child._theme_icon
            icon = get_lucide_icon(name, color=get_palette(theme)[role], size=size)
            if hasattr(child, 'setIcon'):
                child.setIcon(icon)
            else:
                child.setPixmap(icon.pixmap(size, size))
        child.update()


def button_style(role: str, theme: str = 'light') -> str:
    p = TOKENS if theme == 'tokens' else get_palette(theme)
    bg, fg, hover = p['input'], p['text'], p['input_hover']
    if role == 'primary':
        bg, fg, hover = p['primary_bg'], p['primary_text'], p['primary_hover']
    elif role == 'stop':
        bg, fg, hover = p['negative_bg'], p['negative'], p['raised']
    elif role == 'stopping':
        fg = p['muted']
    return f'''QPushButton {{background:{bg};color:{fg};border:1px solid {p['border_control']};border-radius:6px;padding:7px 12px;font-size:13px;font-weight:500;}}
        QPushButton:hover {{background:{hover};}}
        QPushButton:focus {{border:2px solid {p['focus']};}}
        QPushButton:disabled {{background:{p['raised']};color:{p['muted']};border-color:{p['border']};}}'''


def card_style(theme: str = 'light') -> str:
    p = TOKENS if theme == 'tokens' else get_palette(theme)
    return f"QFrame#cardFrame {{background:{p['surface']};border:1px solid {p['border']};border-radius:8px;}}"


def sidebar_style(theme: str = 'light') -> str:
    p = TOKENS if theme == 'tokens' else get_palette(theme)
    return f"QFrame#sidebarFrame {{background:{p['sidebar']};border-right:1px solid {p['border']};}}"


def nav_button_style(active: bool, collapsed: bool, theme: str = 'light') -> str:
    p = TOKENS if theme == 'tokens' else get_palette(theme)
    return f'''QPushButton {{background:{p['raised'] if active else 'transparent'};color:{p['text'] if active else p['muted']};border:0;border-radius:6px;text-align:{'center' if collapsed else 'left'};padding:8px;font-size:13px;}}
        QPushButton:hover {{background:{p['raised']};color:{p['text']};}} QPushButton:focus {{border:1px solid {p['focus']};}}'''


def pack_action_style(theme: str = 'light') -> str:
    p = TOKENS if theme == 'tokens' else get_palette(theme)
    return f'QPushButton[destructive="true"]:enabled {{color:{p["negative"]};}}'


def language_packs_style(theme: str = 'light') -> str:
    p = TOKENS if theme == 'tokens' else get_palette(theme)
    return f'''QLabel#packDialogTitle {{font-size:18px;font-weight:600;}} QLabel#packTitle, QLabel#packGroupTitle {{font-weight:600;}}
        QLabel#packDetail, QLabel#packStatus {{color:{p['muted']};}} QLabel#packReason {{color:{p['warning']};}}'''


def get_app_stylesheet(theme: str = 'light') -> str:
    p = TOKENS if theme == 'tokens' else get_palette(theme)
    return f'''QWidget {{color:{p['text']};font-family:"Segoe UI";font-size:14px;}}
        QWidget#controllerWindow, QDialog {{background:{p['ground']};}}
        QLabel {{background:transparent;}} QScrollArea {{border:0;background:transparent;}}
        QScrollBar:vertical {{background:{p['ground']};width:7px;border:0;}}
        QScrollBar::handle:vertical {{background:{p['border_control']};min-height:24px;border-radius:3px;}}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{height:0;}}
        QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{background:{p['input']};color:{p['text']};border:1px solid {p['border_control']};border-radius:6px;padding:6px 8px;selection-background-color:{p['selection_bg']};selection-color:{p['selection_text']};}}
        QLineEdit, QComboBox, QSpinBox {{min-height:24px;}}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{border-color:{p['focus']};}}
        QComboBox::drop-down {{width:20px;border:0;}}
        QComboBox QAbstractItemView {{background:{p['surface']};color:{p['text']};padding:4px;border:1px solid {p['border_control']};selection-background-color:{p['selection_bg']};selection-color:{p['selection_text']};outline:0;}}
        QToolTip {{background:{p['surface']};color:{p['text']};border:1px solid {p['border_control']};padding:6px;}}
        QProgressBar {{background:{p['input']};color:{p['text']};border:1px solid {p['border_control']};border-radius:4px;}}
        QProgressBar::chunk {{background:{p['focus']};}}
        {button_style('secondary', theme)} {card_style(theme)}'''
