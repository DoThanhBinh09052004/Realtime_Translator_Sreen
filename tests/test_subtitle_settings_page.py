from dataclasses import replace
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtGui import QColor


def test_subtitle_render_and_actions(qtbot, ui_snapshot, monkeypatch):
    from ui.pages.subtitle_settings_page import SubtitleSettingsPage, QColorDialog
    page = SubtitleSettingsPage(ui_snapshot.subtitle)
    qtbot.addWidget(page)
    style = QSignalSpy(page.style_changed)
    preset = QSignalSpy(page.preset_changed)
    drag = QSignalSpy(page.drag_toggle_requested)
    page.render(replace(ui_snapshot.subtitle, font_size=24, bg_opacity=30, preset='top_center'))
    assert len(style) == len(preset) == 0
    assert '24px' in page.live_preview_box.styleSheet()
    assert '0.30' in page.live_preview_box.styleSheet()
    assert (page.font_size_slider.minimum(), page.font_size_slider.maximum()) == (14, 36)
    assert (page.opacity_slider.minimum(), page.opacity_slider.maximum()) == (0, 100)
    page.font_size_slider.setValue(30)
    page.opacity_slider.setValue(40)
    assert list(style) == [[{'font_size': 30}], [{'bg_opacity': 40}]]
    page.set_preset_display('bottom_left')
    assert len(preset) == 0
    page.preset_combo.setCurrentIndex(page.preset_combo.findData('custom'))
    assert list(preset) == [['custom']]
    monkeypatch.setattr(QColorDialog, 'getColor', lambda *args: QColor())
    page.pick_bg_color()
    page.pick_text_color()
    assert len(style) == 2
    monkeypatch.setattr(QColorDialog, 'getColor', lambda *args: QColor('#123456'))
    page.pick_bg_color()
    assert style[-1][0] == {'bg_color': '#123456'}
    page.drag_toggle_btn.click()
    assert len(drag) == 1
    page.set_drag_mode(True)
    assert 'Khóa vị trí' in page.drag_toggle_btn.text()
