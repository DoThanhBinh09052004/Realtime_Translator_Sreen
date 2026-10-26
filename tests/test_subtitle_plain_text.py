import pytest
from PyQt5.QtCore import Qt

from core.contracts import SubtitleFrame
from ui.overlay import Overlay


@pytest.mark.parametrize('text', [
    '<b>literal</b>',
    '<img src="file:///missing.png">',
    '<a href="https://example.invalid">link</a>',
    'A < B > C &amp; D',
    '日本語\nTiếng Việt',
])
def test_subtitle_keeps_literal_text(qtbot, text):
    overlay = Overlay()
    qtbot.addWidget(overlay)
    overlay.set_mode('subtitle', 2)
    overlay.update_subtitle(SubtitleFrame(2, 1, 'source', text))

    assert overlay.textFormat() == Qt.PlainText
    assert overlay.text() == text


def test_drag_style_and_mode_preserve_plain_text(qtbot):
    overlay = Overlay()
    qtbot.addWidget(overlay)
    assert overlay.textFormat() == Qt.PlainText
    overlay.set_mode('subtitle', 2)
    overlay.update_subtitle(SubtitleFrame(2, 1, 'source', '<b>original</b>'))
    overlay.set_drag_mode(True)
    assert overlay.textFormat() == Qt.PlainText
    overlay.update_subtitle(SubtitleFrame(2, 2, 'source', '<i>latest</i>'))
    overlay.apply_style(text_hex='#00ff00')
    overlay.set_drag_mode(False)

    assert overlay.text() == '<i>latest</i>'
    assert overlay.textFormat() == Qt.PlainText

    overlay.set_mode('subtitle', 3)
    overlay.update_subtitle(SubtitleFrame(2, 3, 'source', '<b>stale</b>'))
    assert overlay.text() == ''
    assert overlay.textFormat() == Qt.PlainText

    overlay.update_subtitle(SubtitleFrame(3, 1, 'source', '日本語 &amp; Việt'))
    assert overlay.text() == '日本語 &amp; Việt'
    assert overlay.textFormat() == Qt.PlainText
