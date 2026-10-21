"""A translation service owned and used by one worker thread."""
from collections import OrderedDict
import math

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from core.contracts import EngineError, ProviderSettings, RuntimeSettings, TranslationResult

PROMPT_VERSION = 1
_MESSAGES = {
    "auth": "API key bị thiếu, không hợp lệ hoặc không có quyền truy cập.",
    "quota": "Đã hết hạn mức sử dụng của nhà cung cấp.",
    "rate_limit": "Nhà cung cấp đang giới hạn tốc độ yêu cầu.",
    "timeout": "Yêu cầu dịch quá thời gian chờ.",
    "network": "Không thể kết nối tới dịch vụ dịch.",
    "invalid_model": "Model không tồn tại hoặc không khả dụng.",
    "invalid_input": "Nội dung dịch không hợp lệ hoặc vượt quá 2000 ký tự.",
    "internal": "Không thể xử lý kết quả từ dịch vụ dịch.",
}


def _error(code: str, retryable: bool = False, retry_after_s=None) -> TranslationResult:
    return TranslationResult(error=EngineError(code, _MESSAGES[code], retryable, retry_after_s))


def _provider_error(exc: Exception) -> TranslationResult:
    # Inspect SDK types and machine codes, never the free-form exception message.
    if isinstance(exc, APITimeoutError):
        return _error("timeout", True)
    if isinstance(exc, APIConnectionError):
        return _error("network", True)
    if not isinstance(exc, APIStatusError):
        return _error("internal")
    body = exc.body if isinstance(exc.body, dict) else {}
    nested = body.get("error")
    if isinstance(nested, dict):
        body = nested
    codes = {str(value).lower() for value in (
        exc.code, exc.type, body.get("code"), body.get("type"), body.get("status"),
    ) if value is not None}
    details = body.get("details")
    if isinstance(details, list):
        codes.update(str(detail["reason"]).lower() for detail in details
                     if isinstance(detail, dict) and "reason" in detail)
    if exc.status_code == 402 or codes & {
        "insufficient_quota", "quota_exceeded", "billing_hard_limit_reached",
        "daily_limit_exceeded", "payment_required",
    }:
        return _error("quota")
    if exc.status_code in (401, 403) or codes & {
        "invalid_api_key", "api_key_invalid", "unauthenticated", "permission_denied",
    }:
        return _error("auth")
    if exc.status_code == 404 or codes & {"model_not_found", "invalid_model"}:
        return _error("invalid_model")
    if exc.status_code == 429:
        retry_after = None
        try:
            value = float(exc.response.headers.get("retry-after", ""))
            if math.isfinite(value) and value >= 0:
                retry_after = value
        except (TypeError, ValueError):
            pass
        return _error("rate_limit", True, retry_after)
    if exc.status_code == 408:
        return _error("timeout", True)
    if exc.status_code >= 500:
        return _error("network", True)
    return _error("invalid_input")


class TranslationService:
    """Owns a client and a FIFO cache; callers serialize use on the owning thread."""

    def __init__(self):
        self._client = None
        self._provider: ProviderSettings | None = None
        self._cache = OrderedDict()

    def close(self) -> None:
        client, self._client = self._client, None
        self._provider = None
        self._cache.clear()
        if client is not None:
            try:
                client.close()
            except Exception:
                # Cleanup must not expose provider exceptions or skip thread teardown.
                pass

    def _prepare_client(self, provider: ProviderSettings) -> None:
        previous = self._provider
        if previous is not None and (
            previous.name != provider.name or previous.api_key != provider.api_key
            or previous.base_url != provider.base_url
        ):
            self.close()
        if self._client is None:
            kwargs = {"api_key": provider.api_key, "max_retries": 0, "timeout": 8.0}
            if provider.base_url:
                kwargs["base_url"] = provider.base_url
            self._client = OpenAI(**kwargs)
        self._provider = provider

    def translate(self, text: str, settings: RuntimeSettings) -> TranslationResult:
        if not isinstance(text, str) or len(text) > 2000:
            return _error("invalid_input")
        text = text.strip()
        if not text:
            return TranslationResult()
        provider = settings.provider
        if not provider.api_key:
            self.close()
            return _error("auth")
        if not provider.model_id.strip():
            return _error("invalid_model")
        try:
            self._prepare_client(provider)
            key = (provider.name, provider.model_id, settings.source_lang,
                   settings.target_lang, text, PROMPT_VERSION)
            if key in self._cache:
                return self._cache[key]
            response = self._client.chat.completions.create(
                model=provider.model_id,
                messages=[
                    {"role": "system", "content": "You are a professional translator. Provide only the translated text without commentary."},
                    {"role": "user", "content": f"Translate the following text from {settings.source_lang} to {settings.target_lang}:\n\n{text}"},
                ],
                temperature=0, top_p=1.0, timeout=8.0,
            )
            content = response.choices[0].message.content
            if not isinstance(content, str) or not content.strip():
                return _error("internal")
            usage = getattr(response, "usage", None)
            result = TranslationResult(
                text=content.strip(), input_tokens=getattr(usage, "prompt_tokens", None),
                output_tokens=getattr(usage, "completion_tokens", None),
            )
            if len(self._cache) >= 300:
                self._cache.popitem(last=False)
            self._cache[key] = result
            return result
        except Exception as exc:
            return _provider_error(exc)
