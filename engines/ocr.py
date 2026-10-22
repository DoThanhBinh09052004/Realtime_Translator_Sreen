import os
import gc

# Cấu hình cờ tối ưu RAM cho PaddlePaddle trước khi nạp model
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['FLAGS_fraction_of_cpu_memory_to_use'] = '0.05'

import cv2
import numpy as np
from paddleocr import PaddleOCR
from core.contracts import EngineError, OcrResult


class SimplePaddleOCR:
    """Wrapper bao bọc PaddleOCR xử lý trích xuất văn bản từ hình ảnh với cấu hình RAM tối thiểu"""
    def __init__(self, lang='en'):
        self.ocr = PaddleOCR(
            lang=lang,
            use_angle_cls=False,
            show_log=False,
            enable_mkldnn=False,
            cpu_threads=2
        )

    def extract_text(self, img) -> OcrResult:
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
                return OcrResult()

            all_text = [line[1][0] for line in result[0] if len(line) >= 2]
            if not all_text:
                return OcrResult()

            full_text = " ".join(all_text).strip()
            return OcrResult(text=full_text)

        except Exception:
            return OcrResult(error=EngineError("ocr", "Không thể nhận diện chữ trong ảnh.", True))


# Single active engine cache: chỉ giữ 1 model đang sử dụng, giải phóng model cũ khi đổi ngôn ngữ
_current_engine = None
_current_lang = None


def release_ocr_engine():
    """Giải phóng engine OCR hiện tại khỏi RAM và thu dọn rác"""
    global _current_engine, _current_lang
    if _current_engine is not None:
        try:
            del _current_engine
        except Exception:
            pass
        _current_engine = None
        _current_lang = None
        gc.collect()


def get_ocr_engine(lang='en'):
    """Lấy OCR engine cho ngôn ngữ chỉ định; tự động giải phóng ngôn ngữ trước đó để tiết kiệm RAM"""
    global _current_engine, _current_lang
    if _current_engine is not None and _current_lang == lang:
        return _current_engine

    if _current_engine is not None and _current_lang != lang:
        release_ocr_engine()

    _current_engine = SimplePaddleOCR(lang=lang)
    _current_lang = lang

    return _current_engine


def ocr_image(img, lang='en') -> OcrResult:
    """Hàm giao tiếp chính để nhận diện chữ trong ảnh"""
    if img is None:
        return OcrResult(error=EngineError("invalid_input", "Ảnh nhận diện không hợp lệ.", False))
    try:
        return get_ocr_engine(lang=lang).extract_text(img)
    except Exception:
        return OcrResult(error=EngineError("ocr", "Không thể khởi tạo bộ nhận diện chữ.", True))
