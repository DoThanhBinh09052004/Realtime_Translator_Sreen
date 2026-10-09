import os
from openai import OpenAI
from dotenv import load_dotenv

# Load file .env từ thư mục gốc
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT_DIR, ".env"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("⚠️ Cảnh báo: Chưa tìm thấy OPENAI_API_KEY trong file .env!")

_translation_cache = {}
_client = None


def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            _client = OpenAI(api_key=api_key)
    return _client


def translate(text: str, source_lang="English", target_lang="Vietnamese") -> str:
    """
    Dịch văn bản sử dụng mô hình LLM với bộ nhớ đệm Cache FIFO và timeout an toàn.
    """
    if not text or not text.strip():
        return ""

    client = get_client()
    if not client:
        return "Loi: Chua cau hinh OPENAI_API_KEY."

    processed_text = text.strip()[:2000]

    cache_key = (processed_text, source_lang, target_lang)
    if cache_key in _translation_cache:
        return _translation_cache[cache_key]

    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
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

        # shortcut: In-memory FIFO cache 1000 items, nâng cấp lên SQLite/diskcache nếu cần lưu lịch sử dịch lâu dài.
        if len(_translation_cache) >= 1000:
            _translation_cache.pop(next(iter(_translation_cache)))
        _translation_cache[cache_key] = result
        return result

    except Exception as e:
        error_message = str(e)
        if "429" in error_message:
            return "Loi: Vuot qua han muc su dung (Quota exceeded)."
        return f"Loi he thong: {error_message}"


def translate_ja_to_vi(text: str) -> str:
    """Dịch chuyên biệt Nhật -> Việt"""
    return translate(text, source_lang="Japanese", target_lang="Vietnamese")
