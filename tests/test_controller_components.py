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
    from ui.widgets.cards import ModernCard, MetricCard
    from ui.presentation import color_button_presentation, drag_button_style
    from PyQt5.QtWidgets import QLabel
    card = ModernCard('Title', 'Subtitle')
    qtbot.addWidget(card)
    assert card.layout is card.box_layout
    assert {label.text() for label in card.findChildren(QLabel)} == {'Title', 'Subtitle'}
    metric = MetricCard('Status', 'Old')
    qtbot.addWidget(metric)
    metric.set_value('New')
    assert metric.val_lbl.text() == 'New'
    assert any(label.pixmap() and not label.pixmap().isNull() for label in metric.findChildren(QLabel))
    text, style = color_button_presentation('invalid')
    assert text.strip() == '#14151A'
    assert '#14151a' in style
    assert '#34d399' in drag_button_style(True)
