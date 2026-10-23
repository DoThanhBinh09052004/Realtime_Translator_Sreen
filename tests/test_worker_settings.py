from dataclasses import replace
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from core import config
from core.worker import TranslationWorker


def make_worker():
    config.save_active_provider('Google Gemini')
    config.save_provider_api_key("Google Gemini", "fake-key")
    return TranslationWorker(config.State(), config.DEFAULT_REGION)


def install_capture(monkeypatch, worker, on_frame=lambda count: None, frames=5, changing=False):
    from core import worker as module

    class Capture:
        count = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def grab(self, region):
            self.count += 1
            on_frame(self.count)
            if self.count > frames:
                with module.QMutexLocker(worker._mutex):
                    worker._is_running = False
            return np.full((8, 8, 4), self.count * 20 if changing else 0, dtype=np.uint8)

    monkeypatch.setattr(module.mss, "mss", Capture)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(module, "compact_memory", lambda: None)


@pytest.mark.parametrize("change", ["source", "target", "model", "key", "base_url", "provider"])
def test_changed_settings_reprocess_static_frame(monkeypatch, fake_translator, change):
    worker = make_worker()
    original = config.load_runtime_settings(worker.state, 500)
    changes = {
        "source": replace(original, source_lang="Japanese"),
        "target": replace(original, target_lang="English"),
        "model": replace(original, provider=replace(original.provider, model_id="new-model")),
        "key": replace(original, provider=replace(original.provider, api_key="fake-new-key")),
        "base_url": replace(original, provider=replace(original.provider, base_url="https://other.invalid")),
        "provider": replace(original, provider=replace(original.provider, name="OpenAI", base_url=None)),
    }
    changed = changes[change]
    install_capture(monkeypatch, worker, lambda count: worker.configure(changed) if count == 3 else None)
    emitted = []
    worker.text_translated.connect(emitted.append)
    worker._is_running = True
    worker.run()
    assert fake_translator.call_count == 2
    assert emitted == ["fake translation", "fake translation"]
    request = fake_translator.call_args.kwargs
    assert request["model"] == changed.provider.model_id
    assert f"from {changed.source_lang} to {changed.target_lang}" in request["messages"][1]["content"]


def test_configure_only_marks_invalidation_without_mutating_worker_cache():
    worker = make_worker()
    worker._prev_text = "old text"
    old_thumb = np.zeros((40, 100), dtype=np.uint8)
    worker._prev_frame_thumb = old_thumb
    snapshot = config.load_runtime_settings(worker.state, 500)
    first_revision = worker.configure(snapshot)
    assert worker.configure(replace(snapshot, target_lang="English")) > first_revision
    assert worker._prev_text == "old text"
    assert worker._prev_frame_thumb is old_thumb


def test_reconfiguration_during_request_discards_old_result_and_does_not_deadlock(monkeypatch, fake_translator):
    worker = make_worker()
    original = config.load_runtime_settings(worker.state, 500)
    changed = replace(original, provider=replace(original.provider, model_id="new-model"))

    def completion(**kwargs):
        if fake_translator.call_count == 1:
            worker.configure(changed)
            return "old translation"
        return "new translation"

    fake_translator.side_effect = completion
    install_capture(monkeypatch, worker)
    emitted = []
    worker.text_translated.connect(emitted.append)
    worker._is_running = True
    worker.run()
    assert emitted == ["new translation"]
    assert [call.kwargs["model"] for call in fake_translator.call_args_list] == [
        original.provider.model_id, "new-model"]


def test_translation_error_is_never_emitted_as_subtitle(monkeypatch, fake_translator):
    worker = make_worker()
    fake_translator.side_effect = RuntimeError("fake-secret")
    install_capture(monkeypatch, worker)
    translated, errors = [], []
    worker.text_translated.connect(translated.append)
    worker.error_occurred.connect(errors.append)
    worker._is_running = True
    worker.run()
    assert translated == []
    assert len(errors) == 1
    assert errors[0].code == "internal"
    assert "fake-secret" not in errors[0].user_message


@pytest.mark.parametrize("code,retry_after_s,cooldown_s", [
    ("timeout", None, 2.0),
    ("network", None, 2.0),
    ("rate_limit", None, 5.0),
    ("rate_limit", 12.0, 12.0),
])
def test_gemini_retryable_errors_pause_requests(
        monkeypatch, code, retry_after_s, cooldown_s):
    from core import worker as module
    from core.contracts import EngineError, OcrResult, TranslationResult

    worker = make_worker()
    settings = config.load_runtime_settings(worker.state, 500)
    worker._is_running = True
    now = [100.0]
    attempts = []

    class FailingService:
        def translate(self, text, runtime_settings):
            attempts.append(text)
            return TranslationResult(error=EngineError(
                code, "temporary failure", True, retry_after_s))

    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(module, "ocr_image", lambda *args, **kwargs: OcrResult(text="Hello"))
    monkeypatch.setattr(worker, "_is_frame_changed", lambda image: True)
    image = np.zeros((8, 8), dtype=np.uint8)

    worker._process_frame(image, settings, worker._revision, FailingService())
    assert attempts == []
    worker._process_frame(image, settings, worker._revision, FailingService())
    now[0] = 100.0 + cooldown_s - 0.01
    worker._process_frame(image, settings, worker._revision, FailingService())
    assert attempts == ["Hello"]

    now[0] = 100.0 + cooldown_s
    worker._process_frame(image, settings, worker._revision, FailingService())
    assert attempts == ["Hello", "Hello"]


def test_client_created_used_and_closed_on_worker_thread(monkeypatch, qtbot):
    from engines import translator
    owner = threading.get_ident()
    calls = []

    def record(kind):
        calls.append((kind, threading.get_ident()))

    def create(**kwargs):
        record("request")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="translated"))])

    def factory(**kwargs):
        record("create")
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
                               close=lambda: record("close"))

    monkeypatch.setattr(translator, "OpenAI", factory)
    worker = make_worker()
    install_capture(monkeypatch, worker, frames=2)
    assert calls == []
    worker.start_worker()
    try:
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=2000)
    finally:
        assert worker.wait(2000)
    assert [kind for kind, _ in calls] == ["create", "request", "close"]
    assert len({thread for _, thread in calls}) == 1
    assert calls[0][1] != owner


def test_changing_key_does_not_close_client_while_request_is_in_flight(monkeypatch, qtbot):
    from engines import translator
    entered, released = threading.Event(), threading.Event()
    clients = []
    calls = []

    def factory(**kwargs):
        index = len(clients)

        def create(**request):
            calls.append((index, "request"))
            if index == 0:
                entered.set()
                assert released.wait(3)
                assert clients[0].close.call_count == 0
            calls.append((index, "returned"))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="translated"))])

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
                                 close=Mock(side_effect=lambda: calls.append((index, "close"))))
        clients.append(client)
        return client

    monkeypatch.setattr(translator, "OpenAI", factory)
    worker = make_worker()
    install_capture(monkeypatch, worker)
    worker.start_worker()
    try:
        qtbot.waitUntil(entered.is_set, timeout=2000)
        original = config.load_runtime_settings(worker.state, 500)
        worker.configure(replace(original, provider=replace(original.provider, api_key="fake-new-key")))
        assert clients[0].close.call_count == 0
        released.set()
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=2000)
    finally:
        released.set()
        assert worker.wait(4000)
    assert calls == [(0, "request"), (0, "returned"), (0, "close"),
                     (1, "request"), (1, "returned"), (1, "close")]


def test_worker_uses_snapshot_instead_of_mutable_ui_state(monkeypatch, fake_translator):
    worker = make_worker()

    def on_frame(count):
        worker.state.source = "Korean"
        worker.state.target = "English"

    install_capture(monkeypatch, worker, on_frame)
    worker._is_running = True
    worker.run()
    assert fake_translator.call_count == 1
    content = fake_translator.call_args.kwargs["messages"][1]["content"]
    assert "from English to Vietnamese" in content


def test_worker_shutdown_clears_untranslated_pending_candidate(monkeypatch, fake_translator):
    worker = make_worker()
    pending_before_stop = []

    def on_frame(count):
        if count == 2:
            pending_before_stop.append(worker._stabilizer.has_pending)

    install_capture(monkeypatch, worker, on_frame, frames=1)
    emitted = []
    worker.text_translated.connect(emitted.append)
    worker._is_running = True
    worker.run()
    assert pending_before_stop == [True]
    assert not worker._stabilizer.has_pending
    assert emitted == []
    assert fake_translator.call_count == 0


@pytest.mark.parametrize("changing,source,expected", [(False, "", 2), (True, "fake source", 1)])
def test_memory_compaction_still_depends_on_idle_frames(monkeypatch, fake_ocr, changing, source, expected):
    from core import worker as module
    worker = make_worker()
    fake_ocr.return_value = source
    install_capture(monkeypatch, worker, changing=changing)
    compact = Mock()
    monkeypatch.setattr(module, "compact_memory", compact)
    worker._is_running = True
    worker.run()
    # One cleanup at thread exit; only static frames trigger idle compaction.
    assert compact.call_count == expected


@pytest.mark.parametrize("widget,value", [
    ("provider_combo", "OpenAI"), ("model_combo", "new-model"),
    ("api_key_input", "fake-new-key"), ("src_combo", "Japanese"), ("tgt_combo", "English"),
])
def test_ui_configures_worker_only_after_successful_save(qtbot, monkeypatch, widget, value):
    from ui.controller import ControllerWindow
    config.save_active_provider('Google Gemini')
    worker = Mock()
    worker.interval.return_value = 500
    window = ControllerWindow(worker, config.State(), lambda: None, lambda: None)
    qtbot.addWidget(window)
    control = getattr(window, widget)
    setter = control.setText if widget == "api_key_input" else control.setCurrentText
    worker.reset_mock()

    def configured(snapshot):
        assert snapshot == config.load_runtime_settings(window.state, 500)

    worker.configure.side_effect = configured
    setter(value)
    worker.configure.assert_called_once()
    worker.reset_mock()
    monkeypatch.setattr(config.os, "replace", Mock(side_effect=OSError("fake-secret")))
    setter("Korean" if widget == "src_combo" else "Vietnamese" if widget == "tgt_combo" else (
        "Google Gemini" if widget == "provider_combo" else "fake-next-value"))
    worker.configure.assert_not_called()
