from dataclasses import FrozenInstanceError, replace
import pytest


def test_snapshot_hides_key_and_preview_matches_values(ui_snapshot):
    from ui.presentation import subtitle_preview_style
    assert 'fake-test-key' not in repr(ui_snapshot)
    assert ui_snapshot.ai.models == ('fake-model',)
    with pytest.raises(FrozenInstanceError):
        ui_snapshot.ai.model_id = 'changed'
    style = subtitle_preview_style(ui_snapshot.subtitle)
    assert 'font-size: 22px' in style
    assert 'rgba(30, 30, 46, 0.80)' in style
    fallback = subtitle_preview_style(replace(ui_snapshot.subtitle, bg_color='invalid', text_color='invalid'))
    assert 'rgba(14, 15, 18, 0.80)' in fallback
    assert '#ffffff' in fallback


def test_card_layout_value_and_color_fallback(qtbot):
    from ui.widgets.cards import ModernCard
    from ui.presentation import color_button_presentation, drag_button_style
    from PyQt5.QtWidgets import QLabel
    card = ModernCard('Title', 'Subtitle')
    qtbot.addWidget(card)
    assert card.layout is card.box_layout
    assert {label.text() for label in card.findChildren(QLabel)} == {'Title', 'Subtitle'}
    text, style = color_button_presentation('invalid')
    assert text.strip() == '#14151A'
    assert '#14151a' in style
    assert drag_button_style(True) != drag_button_style(False)


def test_theme_preserves_drafts_and_runtime(ui_window):
    from ui.controller_state import PresentedPair, PresentedTranslation
    ui_window.ai_page.api_key_input.setText('draft-not-saved')
    ui_window.console_page.render_presented(PresentedTranslation(1, 'subtitle', 1, (PresentedPair('Hello', 'Xin chào'),)))
    ui_window.worker.reset_mock()
    ui_window.apply_theme('dark')
    assert ui_window.ai_page.api_key_input.text() == 'draft-not-saved'
    assert ui_window.console_page.output_widget.target_edit.toPlainText() == 'Xin chào'
    assert ui_window.console_page.subtitle_preview.text() == 'Xin chào'
    ui_window.apply_theme('light')
    ui_window.worker.configure.assert_not_called()
    ui_window.worker.start_worker.assert_not_called()
    ui_window.worker.stop_worker.assert_not_called()


def test_dashboard_uses_shared_font_sizes_for_controls_and_section_titles(ui_window):
    from PyQt5.QtWidgets import QLabel
    from PyQt5.QtWidgets import QApplication
    page = ui_window.console_page
    ui_window.show()
    QApplication.processEvents()
    assert page.capture_settings.choose_btn.font().pixelSize() == page.src_combo.font().pixelSize() == 14
    region = next(label for label in page.region_card.findChildren(QLabel) if label.text() == 'Vùng đọc chữ')
    output = next(label for label in page.output_card.findChildren(QLabel) if label.text() == 'Bản dịch mới nhất')
    assert region.font().pixelSize() == output.font().pixelSize() == 16
    assert region.font().weight() == output.font().weight()


def test_controller_widgets_belong_to_existing_pages(ui_window):
    for page, attributes in [
        (ui_window.ai_page, ('model_combo', 'api_key_input', 'key_card')),
        (ui_window.subtitle_page, ('font_size_slider', 'opacity_slider', 'preset_combo')),
        (ui_window.ocr_page, ('src_combo', 'tgt_combo', 'interval_spin', 'reg_info_lbl')),
    ]:
        for attribute in attributes:
            widget = getattr(ui_window, attribute)
            assert widget is getattr(page, attribute)
            assert page.isAncestorOf(widget)
    assert ui_window.settings_coordinator.parent() is ui_window


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_theme_palette_is_readonly_and_readable(theme):
    from PyQt5.QtGui import QColor
    from ui.styles import get_palette
    p = get_palette(theme)
    def luminance(value):
        c = QColor(value)
        channels = (c.redF(), c.greenF(), c.blueF())
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
        return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))
    for foreground, background in [('text', 'ground'), ('text', 'surface'), ('muted', 'surface'), ('primary_text', 'primary_bg')]:
        a, b = sorted((luminance(p[foreground]), luminance(p[background])))
        assert (b + .05) / (a + .05) >= 4.5
    with pytest.raises(TypeError):
        p['text'] = '#000000'


def test_cached_language_dialog_and_new_rows_follow_theme(ui_window):
    from ui.controller_state import LanguagePacksState, PackageRowState
    ui_window.open_language_packs()
    dialog = ui_window._language_packs_dialog
    assert ui_window.settings_coordinator.set_ui_theme('dark')
    row = PackageRowState('ko', 'Tiếng Hàn', 'not_installed', 'Chưa cài', '', 0, 0, 0, 'install', True)
    dialog.render(LanguagePacksState((row,), False))
    from ui.styles import theme_for, get_palette
    assert theme_for(dialog.rows['ko']) == 'dark'
    assert get_palette('dark')['surface'] in dialog.rows['ko'].styleSheet()
    dialog.close()
    ui_window.apply_theme('light')
    assert theme_for(dialog) == 'light'


def test_dark_theme_reaches_native_scroll_surfaces_and_tables(ui_window, qtbot, capture_geometry):
    from PyQt5.QtGui import QPalette, QColor
    from ui.capture_regions_dialog import CaptureRegionsDialog
    from ui.styles import get_palette
    from test_capture_app_integration import capture_values
    p = get_palette('dark')
    ui_window.apply_theme('dark')
    for page in (ui_window.console_page, ui_window.ai_page):
        content = page.scroll_area.widget() if hasattr(page, 'scroll_area') else page.widget()
        assert content.palette().color(QPalette.Window) == QColor(p['ground'])
    profile, context = capture_values(capture_geometry)
    dialog = CaptureRegionsDialog(profile, None, context)
    qtbot.addWidget(dialog)
    dialog.apply_theme('dark')
    assert dialog.table.palette().color(QPalette.Base) == QColor(p['input'])
    assert dialog.table.horizontalHeader().palette().color(QPalette.Window) == QColor(p['ground'])
