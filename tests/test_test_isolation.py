from pathlib import Path
import os
import socket
import sys

import pytest

# Collection-time imports must already be safe, before any fixture is executed.
from core import config
from core import worker

_REPO = Path(__file__).resolve().parents[1]
assert not Path(config.CONFIG_PATH).is_relative_to(_REPO)
assert not Path(config.ENV_PATH).is_relative_to(_REPO)
assert all(name not in os.environ for name in (
    "OPENAI_API_KEY", "GEMINI_API_KEY", "MODEL_ID"
))


def test_config_and_env_paths_are_temporary(isolated_config, tmp_path):
    from core import config

    assert Path(config.CONFIG_PATH).is_relative_to(tmp_path)
    assert Path(config.ENV_PATH).is_relative_to(tmp_path)
    for name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "MODEL_ID"):
        assert name not in os.environ
    assert config.load_provider_api_key("OpenAI") == ""
    assert config.load_provider_api_key("Google Gemini") == ""
    config.save_provider_api_key("OpenAI", "fake-openai-key")
    assert config.load_provider_api_key("OpenAI") == "fake-openai-key"
    assert "sentinel-user-key" not in Path(config.ENV_PATH).read_text()


def test_network_is_blocked():
    with socket.socket() as connection:
        with pytest.raises(RuntimeError, match="Network disabled in tests"):
            connection.connect(("192.0.2.1", 443))


def test_paddle_is_not_imported():
    assert "paddle" not in sys.modules


def test_config_persistence_uses_only_temporary_files(isolated_config):
    from core import config

    state = config.State()
    state.update(bg_color="#123456", bg_opacity=65, text_color="#abcdef")
    saved = config.load_config()
    assert (state.bg_color, state.bg_opacity, state.text_color) == (
        "#123456", 65, "#abcdef"
    )
    assert (saved["bg_color"], saved["bg_opacity"], saved["text_color"]) == (
        "#123456", 65, "#abcdef"
    )
    for provider, key, model in (
        ("OpenAI", "fake-openai-key", "fake-openai-model"),
        ("Google Gemini", "fake-gemini-key", "fake-gemini-model"),
    ):
        config.save_active_provider(provider)
        config.save_provider_api_key(provider, key)
        config.save_provider_model_id(provider, model)
        assert config.load_active_provider() == provider
        assert config.load_provider_api_key(provider) == key
        assert config.load_provider_model_id(provider) == model


def test_engine_calls_use_fakes(isolated_config, fake_translator, fake_ocr):
    from core import config, worker
    from engines import translator, ocr
    import numpy as np

    config.save_provider_api_key("Google Gemini", "fake-gemini-key")
    assert translator.translate("Hello") == "fake translation"
    assert worker.translate("Other text") == "fake translation"
    assert fake_translator.call_count == 2
    assert ocr.ocr_image(np.zeros((4, 4), dtype=np.uint8)) == "fake source"
    assert worker.ocr_image(np.zeros((4, 4), dtype=np.uint8)) == "fake source"
    assert fake_ocr.call_count == 2


def test_desktop_capture_is_blocked():
    import mss

    with pytest.raises(RuntimeError, match="Desktop capture disabled in tests"):
        mss.mss()


def test_fake_clock_advances_without_sleep(fake_clock):
    assert fake_clock.now() == 0.0
    fake_clock.advance(2.5)
    assert fake_clock.now() == 2.5


def test_qt_runs_offscreen(qtbot):
    from PyQt5.QtWidgets import QApplication, QLabel

    label = QLabel("fake subtitle")
    qtbot.addWidget(label)
    assert QApplication.platformName() == "offscreen"
    assert label.text() == "fake subtitle"


def test_next_test_starts_with_empty_config(isolated_config):
    assert config.load_config() == config.normalize_config({})
    assert config.load_provider_api_key("OpenAI") == ""
    assert config.load_provider_api_key("Google Gemini") == ""
    assert not Path(config.CONFIG_PATH).exists()
    assert not Path(config.ENV_PATH).exists()


@pytest.mark.parametrize("operation", [
    lambda: socket.create_connection(("example.invalid", 443)),
    lambda: socket.getaddrinfo("example.invalid", 443),
])
def test_alternate_network_entrypoints_are_blocked(operation):
    with pytest.raises(RuntimeError, match="Network disabled in tests"):
        operation()
