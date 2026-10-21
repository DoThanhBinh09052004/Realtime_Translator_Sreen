import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest

from core import config


def refuse_replace(*args, **kwargs):
    raise OSError("fake-secret must not reach UI or logs")


def test_failed_atomic_replace_preserves_original(monkeypatch, tmp_path, capsys):
    path = Path(config.CONFIG_PATH)
    original = b'{"font_size": 24, "other_setting": "keep"}'
    path.write_bytes(original)
    monkeypatch.setattr(config.os, "replace", refuse_replace)
    with pytest.raises(config.ConfigError):
        config.save_config("font_size", 30)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]
    assert "fake-secret" not in capsys.readouterr().out


def test_state_does_not_change_on_failed_save(monkeypatch):
    state = config.State()
    before = vars(state).copy()
    monkeypatch.setattr(config.os, "replace", refuse_replace)
    with pytest.raises(config.ConfigError):
        state.update(font_size=30, overlay_x=-100, overlay_y=40)
    assert vars(state) == before


def test_multi_field_update_has_one_atomic_commit(monkeypatch):
    state = config.State()
    replace = Mock(wraps=os.replace)
    monkeypatch.setattr(config.os, "replace", replace)
    state.update(overlay_x=-100, overlay_y=40, overlay_preset="custom")
    assert replace.call_count == 1
    source, destination = replace.call_args.args
    assert Path(source).parent == Path(destination).parent
    saved = config.load_config()
    assert (saved["overlay_x"], saved["overlay_y"]) == (-100, 40)


def test_model_saved_once_without_changing_env(monkeypatch):
    env = Path(config.ENV_PATH)
    env.write_text("MODEL_ID=legacy-model\n# keep\n", encoding="utf-8")
    assert config.load_provider_model_id("OpenAI") == "legacy-model"
    replace = Mock(wraps=os.replace)
    monkeypatch.setattr(config.os, "replace", replace)
    config.save_provider_model_id("OpenAI", "new-model")
    assert replace.call_count == 1
    assert config.load_provider_model_id("OpenAI") == "new-model"
    assert env.read_text() == "MODEL_ID=legacy-model\n# keep\n"


def test_failed_env_replace_preserves_file_and_environment(monkeypatch):
    env = Path(config.ENV_PATH)
    original = b"OPENAI_API_KEY=fake-old-key\n# keep\n"
    env.write_bytes(original)
    monkeypatch.setenv("OPENAI_API_KEY", "fake-old-key")
    monkeypatch.setattr(config.os, "replace", refuse_replace)
    with pytest.raises(config.ConfigError):
        config.save_provider_api_key("OpenAI", "fake-new-key")
    assert env.read_bytes() == original
    assert os.environ["OPENAI_API_KEY"] == "fake-old-key"


@pytest.fixture
def controller(qtbot):
    from ui.controller import ControllerWindow
    worker = Mock()
    worker.interval.return_value = 500
    window = ControllerWindow(worker, config.State(), lambda: None, lambda: None)
    qtbot.addWidget(window)
    return window


@pytest.mark.parametrize("widget, setter, value, expected", [
    ("font_size_slider", "setValue", 30, 22),
    ("opacity_slider", "setValue", 20, 80),
    ("src_combo", "setCurrentText", "Japanese", "English"),
    ("tgt_combo", "setCurrentText", "English", "Vietnamese"),
    ("provider_combo", "setCurrentText", "OpenAI", config.DEFAULT_PROVIDER),
    ("model_combo", "setCurrentText", "fake-new-model", config.DEFAULT_MODEL_ID),
    ("api_key_input", "setText", "fake-new-key", ""),
    ("interval_spin", "setValue", 800, 500),
])
def test_failed_save_restores_widget_and_state(controller, monkeypatch, widget, setter, value, expected):
    before = vars(controller.state).copy()
    controller.worker.reset_mock()
    monkeypatch.setattr(config.os, "replace", refuse_replace)
    control = getattr(controller, widget)
    getattr(control, setter)(value)
    read = control.value if setter == "setValue" else (
        control.text if setter == "setText" else control.currentText)
    assert read() == expected
    assert vars(controller.state) == before
    assert "Không thể lưu" in controller.status.text()
    assert "fake-secret" not in controller.status.text()
    controller.worker.setInterval.assert_not_called()


def test_selected_region_not_applied_when_save_fails(controller, monkeypatch):
    from main import apply_selected_region
    controller.worker.reset_mock()
    monkeypatch.setattr(config.os, "replace", refuse_replace)
    assert not apply_selected_region(controller, controller.worker,
                                     {"left": -10, "top": 0, "width": 200, "height": 100})
    controller.worker.set_region.assert_not_called()
    assert "Không thể lưu" in controller.status.text()


def test_failed_sync_preserves_original_and_cleans_temporary_file(monkeypatch, tmp_path):
    path = Path(config.CONFIG_PATH)
    path.write_bytes(b'{"font_size": 24}')
    monkeypatch.setattr(config.os, "fsync", refuse_replace)
    with pytest.raises(config.ConfigError):
        config.save_config("font_size", 30)
    assert path.read_bytes() == b'{"font_size": 24}'
    assert list(tmp_path.iterdir()) == [path]


def test_unreadable_config_is_not_overwritten(monkeypatch):
    path = Path(config.CONFIG_PATH)
    path.write_bytes(b'{"font_size": 24}')
    import builtins
    real_open = builtins.open

    def denied(file, *args, **kwargs):
        if os.fspath(file) == config.CONFIG_PATH:
            raise PermissionError("fake-secret")
        return real_open(file, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", denied)
        assert config.State().font_size == 22
        with pytest.raises(config.ConfigError):
            config.save_config("font_size", 30)
    assert path.read_bytes() == b'{"font_size": 24}'


def test_concurrent_config_updates_preserve_all_fields():
    def save(index):
        config.save_config(f"extra_{index}", index)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(save, range(12)))
    saved = config.load_config()
    assert all(saved[f"extra_{index}"] == index for index in range(12))


def test_failed_preset_save_restores_selection(controller, monkeypatch):
    monkeypatch.setattr(config.os, "replace", refuse_replace)
    controller.preset_combo.setCurrentIndex(controller.preset_combo.findData("top_center"))
    assert controller.preset_combo.currentData() == "bottom_center"
    assert controller.state.overlay_preset == "bottom_center"
    assert "Không thể lưu" in controller.status.text()


@pytest.mark.parametrize("field, handler", [
    ("bg_color", "_pick_bg_color"), ("text_color", "_pick_text_color"),
])
def test_failed_color_save_keeps_preview_and_overlay(controller, monkeypatch, field, handler):
    from PyQt5.QtGui import QColor
    from ui.controller import QColorDialog

    before = getattr(controller.state, field)
    preview = controller.live_preview_box.styleSheet()
    controller.overlay = Mock()
    monkeypatch.setattr(QColorDialog, "getColor", lambda *args: QColor("#123456"))
    monkeypatch.setattr(config.os, "replace", refuse_replace)
    getattr(controller, handler)()
    assert getattr(controller.state, field) == before
    assert controller.live_preview_box.styleSheet() == preview
    controller.overlay.apply_style.assert_not_called()
    assert "Không thể lưu" in controller.status.text()


def test_failed_overlay_drag_restores_saved_position(controller, monkeypatch):
    controller.state.update(overlay_preset="custom", overlay_x=-100, overlay_y=40)
    controller.overlay = Mock()
    monkeypatch.setattr(config.os, "replace", refuse_replace)
    controller._on_overlay_position_changed(200, 300)
    assert (controller.state.overlay_x, controller.state.overlay_y) == (-100, 40)
    controller.overlay.move.assert_called_once_with(-100, 40)
    assert controller.overlay.current_preset == "custom"


def test_successful_ui_save_applies_committed_values(controller):
    controller.font_size_slider.setValue(30)
    assert controller.state.font_size == config.load_config()["font_size"] == 30
    assert controller.font_size_val_lbl.text() == "30px"
    controller.interval_spin.setValue(800)
    assert config.load_config()["interval_ms"] == 800
    controller.worker.setInterval.assert_called_with(800)


def test_selected_region_is_applied_only_after_persistence(controller):
    from main import apply_selected_region
    new_region = {"left": -10, "top": 0, "width": 200, "height": 100}
    controller.worker.set_region.side_effect = lambda region: (
        None if config.load_region() == region else pytest.fail("region applied before save"))
    assert apply_selected_region(controller, controller.worker, new_region)
    controller.worker.set_region.assert_called_once_with(new_region)


@pytest.mark.parametrize("value", ["fake-key\nMODEL_ID=injected", "fake-key\rtest", "fake-key\0"])
def test_invalid_key_does_not_modify_env(value):
    path = Path(config.ENV_PATH)
    with pytest.raises(config.ConfigError):
        config.save_provider_api_key("OpenAI", value)
    assert not path.exists()
