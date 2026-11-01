from ui.capture_settings import CaptureSettings
from test_capture_app_integration import capture_values


def test_source_confirmation_collapses_only_after_binding(qtbot, capture_geometry):
    panel = CaptureSettings(screens=lambda: (capture_geometry.screen,))
    qtbot.addWidget(panel)
    assert panel.choose_btn.text() == 'Dùng màn hình này'
    assert 'Chưa áp dụng' in panel.status_label.text()
    panel.choose_btn.click()
    assert not panel.kind_combo.isHidden()
    profile, _ = capture_values(capture_geometry)
    panel.set_profile(profile, bound=True)
    assert panel.kind_combo.isHidden()
    assert not panel.change_btn.isHidden()
    assert 'Nguồn đang dùng' in panel.summary_label.text()
    panel.change_btn.click()
    assert not panel.kind_combo.isHidden()
    assert 'Chưa áp dụng' in panel.status_label.text()


def test_failed_binding_keeps_picker_and_old_source_summary(qtbot, capture_geometry):
    panel = CaptureSettings(screens=lambda: (capture_geometry.screen,))
    qtbot.addWidget(panel)
    profile, _ = capture_values(capture_geometry)
    panel.set_profile(profile, bound=True)
    panel.change_btn.click()
    panel.choose_btn.click()
    assert not panel.kind_combo.isHidden()
    assert 'Nguồn đang dùng' in panel.summary_label.text()
    panel.kind_combo.setCurrentIndex(1)
    assert panel.choose_btn.text() == 'Dùng cửa sổ này'


def test_compact_source_requires_confirmation_and_stays_visible(qtbot, capture_geometry):
    panel = CaptureSettings(compact=True, screens=lambda: (capture_geometry.screen,))
    qtbot.addWidget(panel)
    emitted = []
    panel.source_selected.connect(lambda *args: emitted.append(args))
    panel.refresh_sources()
    assert emitted == []
    panel.choose_btn.click()
    assert len(emitted) == 1

    profile, _ = capture_values(capture_geometry)
    panel.set_profile(profile, bound=True)
    assert not panel.source_combo.isHidden()
    assert not panel.choose_btn.isHidden()
    assert panel.choose_btn.text() == 'Xác nhận'
    summary = panel.summary_label.text()
    panel.apply_theme('dark')
    assert panel.summary_label.text() == summary
    assert len(emitted) == 1


def test_unbound_source_never_claims_previous_source_is_active(qtbot, capture_geometry):
    panel = CaptureSettings(compact=True, screens=lambda: (capture_geometry.screen,))
    qtbot.addWidget(panel)
    profile, _ = capture_values(capture_geometry)
    panel.set_profile(profile, bound=True)
    assert not panel.summary_label.isHidden()
    panel.set_profile(profile, bound=False)
    assert panel.summary_label.isHidden()
    assert not panel.status_label.isHidden()
