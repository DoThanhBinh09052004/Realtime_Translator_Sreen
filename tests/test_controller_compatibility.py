def test_aliases_are_owned_widgets_and_facade_exports(ui_window):
    from ui.controller import ModernCard, MetricCard, QColorDialog
    from ui.widgets.cards import ModernCard as Card, MetricCard as Metric
    from ui.pages.subtitle_settings_page import QColorDialog as Dialog
    assert (ModernCard, MetricCard, QColorDialog) == (Card, Metric, Dialog)
    for page, attributes in [
        (ui_window.ai_page, ('provider_combo', 'model_combo', 'api_key_input', 'key_card')),
        (ui_window.subtitle_page, ('font_size_slider', 'opacity_slider', 'preset_combo', 'live_preview_box')),
        (ui_window.ocr_page, ('src_combo', 'tgt_combo', 'interval_spin', 'reg_info_lbl')),
    ]:
        for attribute in attributes:
            widget = getattr(ui_window, attribute)
            assert widget is getattr(page, attribute)
            assert page.isAncestorOf(widget)
    assert ui_window.settings_coordinator.parent() is ui_window
