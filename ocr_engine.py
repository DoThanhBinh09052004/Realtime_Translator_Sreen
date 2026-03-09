import cv2
import numpy as np
from paddleocr import PaddleOCR
import os
import gc

# Bỏ qua check model
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'

class SimplePaddleOCR:
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
    
    def extract_text(self, img):
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
            gc.collect()
            return full_text
        
        except Exception as e:
            print(f"⚠️ Lỗi OCR: {e}")
            return ""

# Global vars để theo dõi engine và lang hiện tại
_ocr_engine = None
_current_lang = None  # Biến theo dõi lang hiện tại

def get_ocr_engine(lang='en'):
    global _ocr_engine, _current_lang
    
    # Nếu lang thay đổi HOẶC engine chưa có → tái khởi tạo
    if _ocr_engine is None or _current_lang != lang:
        try:
            print(f"🔄 Khởi tạo lại OCR engine cho lang: {lang}")
            _ocr_engine = SimplePaddleOCR(lang=lang)
            _current_lang = lang  # Cập nhật lang hiện tại
        except Exception as e:
            print(f"❌ Lỗi khởi tạo engine: {e}")
            _ocr_engine = None
            _current_lang = None
            return None
    
    return _ocr_engine

def ocr_image(img, lang='en'):
    engine = get_ocr_engine(lang=lang)
    if engine is None or img is None:
        return ""
    return engine.extract_text(img)