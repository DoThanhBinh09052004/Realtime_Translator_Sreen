import os
import cv2
import numpy as np
from paddleocr import PaddleOCR
import gc

# Bỏ qua kiểm tra model source của Paddle
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'


class SimplePaddleOCR:
    """Wrapper bao bọc PaddleOCR xử lý trích xuất văn bản từ hình ảnh"""
    def __init__(self, lang='en'):
        try:
            self.ocr = PaddleOCR(
                lang=lang,
                use_angle_cls=False
            )
            print(f"✅ OCR Engine sẵn sàng với lang={lang}")
        except Exception as e:
            print(f"❌ Lỗi khởi tạo OCR: {e}")
            raise e

    def extract_text(self, img) -> str:
        try:
            if len(img.shape) == 2:  # grayscale
                rgb_img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
            elif len(img.shape) == 3:
                if img.shape[2] == 3:
                    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                else:
                    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
            else:
                raise ValueError("Invalid image shape")

            result = self.ocr.ocr(rgb_img, cls=False)
            del rgb_img

            if not result or not result[0]:
                return ""

            all_text = [line[1][0] for line in result[0] if len(line) >= 2]
            if not all_text:
                return ""

            full_text = " ".join(all_text).strip()
            return full_text

        except Exception as e:
            print(f"⚠️ Lỗi OCR: {e}")
            return ""


# Caching engine theo từng ngôn ngữ để tránh nạp lại model nặng nề
_ocr_engines = {}


def get_ocr_engine(lang='en'):
    global _ocr_engines
    if lang not in _ocr_engines:
        try:
            print(f"🔄 Đang tải mô hình OCR cho ngôn ngữ: {lang}...")
            _ocr_engines[lang] = SimplePaddleOCR(lang=lang)
        except Exception as e:
            print(f"❌ Không thể nạp OCR engine cho {lang}: {e}")
            return None

    return _ocr_engines[lang]


def ocr_image(img, lang='en') -> str:
    """Hàm giao tiếp chính để nhận diện chữ trong ảnh"""
    engine = get_ocr_engine(lang=lang)
    if engine is None or img is None:
        return ""
    return engine.extract_text(img)
