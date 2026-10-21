from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import numpy as np
import openai
import pytest

from core import config


def settings():
    from core.contracts import ProviderSettings, RuntimeSettings
    return RuntimeSettings("English", "Vietnamese",
                           ProviderSettings("OpenAI", "m1", "fake-key", None), 500)


def test_snapshot_repr_excludes_key():
    snapshot = settings()
    assert "fake-key" not in repr(snapshot.provider)
    assert "fake-key" not in repr(snapshot)
    with pytest.raises(FrozenInstanceError):
        snapshot.provider.model_id = "m2"
    with pytest.raises(FrozenInstanceError):
        snapshot.target_lang = "English"


def test_error_is_not_translation_text():
    from core.contracts import EngineError, OcrResult, TranslationResult
    error = EngineError("network", "Không thể kết nối", True)
    assert TranslationResult(text="stale", error=error).text == ""
    assert OcrResult(text="stale", error=error).text == ""
    assert OcrResult().error is None


def test_snapshot_loads_saved_provider_once():
    config.save_active_provider("OpenAI")
    config.save_provider_api_key("OpenAI", "fake-old-key")
    config.save_provider_model_id("OpenAI", "m1")
    state = config.State()
    snapshot = config.load_runtime_settings(state, 700)
    config.save_provider_api_key("OpenAI", "fake-new-key")
    config.save_provider_model_id("OpenAI", "m2")
    state.update(target="English")
    assert (snapshot.provider.api_key, snapshot.provider.model_id, snapshot.target_lang) == (
        "fake-old-key", "m1", "Vietnamese")
    assert snapshot.interval_ms == 700


def test_oversize_source_is_rejected_without_silent_truncation(fake_translator):
    from engines.translator import TranslationService
    service = TranslationService()
    result = service.translate("x" * 2001, settings())
    assert result.text == ""
    assert result.error.code == "invalid_input"
    assert not result.error.retryable
    fake_translator.assert_not_called()
    service.close()


@pytest.mark.parametrize("status,body,code,retryable", [
    (401, {}, "auth", False), (403, {}, "auth", False),
    (429, {"code": "insufficient_quota"}, "quota", False),
    (429, {"error": {"code": "quota_exceeded"}}, "quota", False),
    (402, {"code": "payment_required"}, "quota", False),
    (400, {"details": [{"reason": "API_KEY_INVALID"}]}, "auth", False),
    (429, {"code": "rate_limit_exceeded"}, "rate_limit", True),
    (404, {"code": "model_not_found"}, "invalid_model", False),
    (400, {"code": "invalid_model"}, "invalid_model", False),
    (400, {}, "invalid_input", False), (503, {}, "network", True),
])
def test_api_errors_are_structured_safe_and_not_cached(fake_translator, status, body, code, retryable):
    from engines.translator import TranslationService
    request = httpx.Request("POST", "https://fake.invalid")
    response = httpx.Response(status, headers={"retry-after": "5"}, request=request)
    fake_translator.side_effect = openai.APIStatusError("fake-key fake-source", response=response, body=body)
    service = TranslationService()
    result = service.translate("fake-source", settings())
    assert result.text == ""
    assert (result.error.code, result.error.retryable) == (code, retryable)
    assert "fake-key" not in result.error.user_message
    assert "fake-source" not in result.error.user_message
    if code == "rate_limit":
        assert result.error.retry_after_s == 5.0
    fake_translator.side_effect = None
    assert service.translate("fake-source", settings()).text == "fake translation"
    assert fake_translator.call_count == 2
    service.close()


@pytest.mark.parametrize("kind,code", [("timeout", "timeout"), ("connection", "network"), ("unknown", "internal")])
def test_exception_type_controls_retry(fake_translator, kind, code):
    from engines.translator import TranslationService
    request = httpx.Request("POST", "https://fake.invalid")
    fake_translator.side_effect = {
        "timeout": openai.APITimeoutError(request),
        "connection": openai.APIConnectionError(request=request),
        "unknown": RuntimeError("fake-key fake-source"),
    }[kind]
    service = TranslationService()
    result = service.translate("Hello", settings())
    assert result.text == ""
    assert result.error.code == code
    assert result.error.retryable == (kind != "unknown")
    assert "fake-key" not in result.error.user_message
    service.close()


def test_ocr_failure_is_distinct_from_successful_empty_result(fake_ocr, monkeypatch):
    from engines import ocr
    image = np.zeros((8, 8), dtype=np.uint8)
    fake_ocr.return_value = ""
    result = ocr.ocr_image(image)
    assert result.text == "" and result.error is None
    fake_ocr.side_effect = RuntimeError("fake-secret")
    failed = ocr.ocr_image(image)
    assert failed.text == "" and failed.error.code == "ocr"
    assert "fake-secret" not in failed.error.user_message
    monkeypatch.setattr(ocr, "_current_engine", None)
    monkeypatch.setattr(ocr, "PaddleOCR", Mock(side_effect=RuntimeError("fake-secret")))
    failed_init = ocr.ocr_image(image)
    assert failed_init.error.code == "ocr"


def test_missing_key_is_auth_error_without_request(fake_translator):
    from dataclasses import replace
    from engines.translator import TranslationService
    snapshot = settings()
    service = TranslationService()
    result = service.translate("Hello", replace(snapshot, provider=replace(snapshot.provider, api_key="")))
    assert result.text == "" and result.error.code == "auth"
    assert not result.error.retryable
    fake_translator.assert_not_called()
    service.close()


@pytest.mark.parametrize("content", ["", "  ", None])
def test_empty_or_missing_translation_is_not_cached(monkeypatch, content):
    from engines import translator
    create = Mock(side_effect=[
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="valid"))]),
    ])
    monkeypatch.setattr(translator, "OpenAI", lambda **kwargs: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)), close=lambda: None))
    service = translator.TranslationService()
    invalid = service.translate("Hello", settings())
    assert invalid.text == "" and invalid.error is not None
    assert service.translate("Hello", settings()).text == "valid"
    assert create.call_count == 2
    service.close()
