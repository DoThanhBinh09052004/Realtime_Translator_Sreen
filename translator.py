import os
from openai import OpenAI
from dotenv import load_dotenv

# Load biến môi trường từ file .env
load_dotenv()

# 🔑 API key OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError(
        "KHÔNG TÌM THẤY API KEY!\n"
    )
client = OpenAI(api_key=OPENAI_API_KEY)
MODEL_ID = "gpt-4.1-mini"

def translate(text, source_lang="English", target_lang="Vietnamese"):
    """
    Dịch văn bản sử dụng mô hình ngôn ngữ lớn của OpenAI.
    """
    if not text or not text.strip():
        return ""

    # Giới hạn độ dài để tối ưu hiệu suất và chi phí
    processed_text = text[:2000]  # Chỉ lấy 2000 ký tự đầu tiên

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
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        error_message = str(e)
        if "429" in error_message:
            return "Loi: Vuot qua han muc su dung (Quota exceeded)."
        return f"Loi he thong: {error_message}"

def translate_ja_to_vi(text):
    """
    Chuyên biệt hóa việc dịch thuật từ tiếng Nhật sang tiếng Việt.
    """
    return translate(text, source_lang="Japanese", target_lang="Vietnamese")

if __name__ == "__main__":
    # Kịch bản kiểm thử 1: Anh - Việt
    english_input = "The silver-tongued politician tried to sugarcoat the bitter pill of tax hikes."
    print("NGUON:", english_input)
    print("DICH:", translate(english_input))

    print("-" * 30)

    # Kịch bản kiểm thử 2: Nhật - Việt
    japanese_input = "政治家は増税という苦い薬を甘く見せようとしたが、国民はそのごまかしを見抜いた。"
    print("NGUON (JA):", japanese_input)
    print("DICH (VI):", translate_ja_to_vi(japanese_input))