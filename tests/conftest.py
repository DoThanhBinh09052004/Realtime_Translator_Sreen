"""Install safety guards at collection time, before application imports."""
import os
from pathlib import Path
import socket
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYTEST_QT_API"] = "pyqt5"

# Autouse fixtures run too late to protect module-level application imports.
_bootstrap = pytest.MonkeyPatch()
_session_dir = tempfile.TemporaryDirectory(prefix="translator-tests-")
for _name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY", "CUSTOM_API_KEY", "MODEL_ID"):
    _bootstrap.delenv(_name, raising=False)

from core import config

_bootstrap.setattr(config, "CONFIG_PATH", str(Path(_session_dir.name) / "config.json"))
_bootstrap.setattr(config, "ENV_PATH", str(Path(_session_dir.name) / ".env"))


def _deny_network(*args, **kwargs):
    raise RuntimeError("Network disabled in tests; use a fake transport")


for _name in ("connect", "connect_ex"):
    _bootstrap.setattr(socket.socket, _name, _deny_network)
_bootstrap.setattr(socket, "create_connection", _deny_network)
_bootstrap.setattr(socket, "getaddrinfo", _deny_network)


def _deny_capture(*args, **kwargs):
    raise RuntimeError("Desktop capture disabled in tests; supply a fake frame")


import mss
import openai

_bootstrap.setattr(mss, "mss", _deny_capture)
_translation = Mock(return_value="fake translation")
_ocr = Mock(return_value="fake source")


def _fake_completion(**kwargs):
    text = _translation(**kwargs)
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def _fake_client(**kwargs):
    return SimpleNamespace(
        base_url=kwargs.get("base_url", "https://api.openai.invalid/v1"),
        chat=SimpleNamespace(completions=SimpleNamespace(create=_fake_completion)),
        close=lambda: None,
    )


_bootstrap.setattr(openai, "OpenAI", _fake_client)


class _FakePaddleOCR:
    def __init__(self, **kwargs):
        pass

    def ocr(self, image, **kwargs):
        text = _ocr(image, **kwargs)
        return [[[None, (text, 1.0)]]] if text else [[]]


# Replacing the module also prevents Paddle's import-time model checks/downloads.
_paddleocr = ModuleType("paddleocr")
_paddleocr.PaddleOCR = _FakePaddleOCR
_bootstrap.setitem(sys.modules, "paddleocr", _paddleocr)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Every test, including UI tests, gets fresh config files and no real keys."""
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config, "ENV_PATH", str(tmp_path / ".env"))
    # Register absent keys too so app writes to os.environ are undone at teardown.
    for name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY", "CUSTOM_API_KEY", "MODEL_ID"):
        monkeypatch.setenv(name, "fake-bootstrap")
        monkeypatch.delenv(name)
    _translation.reset_mock(return_value=True, side_effect=True)
    _translation.return_value = "fake translation"
    _ocr.reset_mock(return_value=True, side_effect=True)
    _ocr.return_value = "fake source"
    ocr = sys.modules.get("engines.ocr")
    if ocr is not None:
        monkeypatch.setattr(ocr, "_current_engine", None)
        monkeypatch.setattr(ocr, "_current_lang", None)
    return config


@pytest.fixture
def fake_translator():
    """Configurable fake completion callable; records request kwargs."""
    return _translation


@pytest.fixture
def fake_ocr():
    """Configurable fake OCR callable; records image arguments."""
    return _ocr


class FakeClock:
    def __init__(self):
        self._time = 0.0

    def now(self) -> float:
        return self._time

    def advance(self, seconds: float) -> None:
        self._time += seconds


@pytest.fixture
def fake_clock():
    return FakeClock()


@pytest.fixture
def ui_window(qtbot):
    from ui.controller import ControllerWindow
    worker = Mock()
    worker.interval.return_value = 500
    window = ControllerWindow(worker, config.State(), Mock(), Mock(), overlay=None)
    qtbot.addWidget(window)
    return window


@pytest.fixture
def ui_snapshot():
    from ui.controller_state import AiPageState, OcrPageState, SubtitlePageState, ControllerSnapshot
    return ControllerSnapshot(
        AiPageState('OpenAI', 'fake-model', ('fake-model',), 'fake-test-key', 'sk-proj-...'),
        OcrPageState('English', 'Vietnamese', 500, (-100, 0, 800, 600)),
        SubtitlePageState('#1e1e2e', '#ffffff', 80, 22, 'bottom_center', None, None))


def pytest_unconfigure(config):
    _bootstrap.undo()
    _session_dir.cleanup()
