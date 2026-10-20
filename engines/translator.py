from openai import OpenAI
from core.config import (
    PROVIDERS, DEFAULT_PROVIDER, load_active_provider,
    load_provider_api_key, load_provider_model_id
)

_translation_cache = {}
_client = None


def get_client():
    global _client
    if _client is None:
        provider = load_active_provider()
        cfg = PROVIDERS.get(provider, PROVIDERS[DEFAULT_PROVIDER])
        api_key = load_provider_api_key(provider)
        if api_key:
            kwargs = {"api_key": api_key}
            if cfg.get("base_url"):
                kwargs["base_url"] = cfg["base_url"]
            _client = OpenAI(**kwargs)
    return _client


def reload_client():
    """Reset client để dùng API key/model mới từ config"""
    global _client
    _client = None


def translate(text: str, source_lang="English", target_lang="Vietnamese") -> str:
    """
    Dịch văn bản sử dụng mô hình LLM với bộ nhớ đệm Cache FIFO và timeout an toàn.
    """
    if not text or not text.strip():
        return ""

    provider = load_active_provider()
    client = get_client()
    if not client:
        return f"Loi: Chua cau hinh API Key cho {provider}."

    processed_text = text.strip()[:2000]
    model_id = load_provider_model_id(provider)

    cache_key = (processed_text, source_lang, target_lang)
    if cache_key in _translation_cache:
        return _translation_cache[cache_key]

    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional translator. Provide only the translated text without commentary."
                },
                {
                    "role": "user",
                    "content": f"Translate the following text from {source_lang} to {target_lang}:\n\n{processed_text}"
                }
            ],
            temperature=0,
            top_p=1.0,
            timeout=8.0,  # Ngăn chặn nghẽn worker thread khi mạng chập chờn
        )
        result = response.choices[0].message.content.strip()

        # shortcut: In-memory FIFO cache 300 items, nâng cấp lên SQLite/diskcache nếu cần lưu lịch sử dịch lâu dài.
        if len(_translation_cache) >= 300:
            _translation_cache.pop(next(iter(_translation_cache)))
        _translation_cache[cache_key] = result
        return result

    except Exception as e:
        error_message = str(e)
        if "429" in error_message or "RESOURCE_EXHAUSTED" in error_message:
            return "Loi: Vuot qua han muc su dung (Quota exceeded)."
        if "401" in error_message or "403" in error_message or "API_KEY_INVALID" in error_message:
            return f"Loi: API Key cua {provider} khong hop le hoac bi tu choi."
        return f"Loi he thong: {error_message}"


def translate_ja_to_vi(text: str) -> str:
    """Dịch chuyên biệt Nhật -> Việt"""
    return translate(text, source_lang="Japanese", target_lang="Vietnamese")

