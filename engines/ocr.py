import os
import gc

# Cấu hình cờ tối ưu RAM cho PaddlePaddle trước khi nạp model
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['FLAGS_fraction_of_cpu_memory_to_use'] = '0.05'

import cv2
import numpy as np
from paddleocr import PaddleOCR
from core.contracts import EngineError, OcrResult, OcrSpan
from core.ocr_models import OcrModelError, resolve_ocr_models


class SimplePaddleOCR:
    """Wrapper bao bọc PaddleOCR xử lý trích xuất văn bản từ hình ảnh với cấu hình RAM tối thiểu"""
    def __init__(self, lang='en', *, store=None):
        self._lease = None
        self.ocr = None
        if store is None:
            models = resolve_ocr_models(lang)
        else:
            from core.languages import language_by_ocr_code
            language = language_by_ocr_code(lang)
            self._lease = store.lease(language.id)
            models = self._lease.__enter__()
        model_options = {}
        if models is not None:
            model_options = dict(det_model_dir=str(models.det), rec_model_dir=str(models.rec),
                                 cls_model_dir=str(models.cls), rec_char_dict_path=str(models.dictionary),
                                 ocr_version="PP-OCRv4")
        try:
            self.ocr = PaddleOCR(
                lang=lang,
                use_angle_cls=False,
                show_log=False,
                enable_mkldnn=False,
                cpu_threads=2,
                **model_options
            )
        except Exception:
            self.close()
            if store is not None:
                raise OcrModelError('Không thể nạp bộ nhận diện. Mở Quản lý gói ngôn ngữ để cài lại.') from None
            raise

    def close(self):
        """Release native objects and then the pack lease on the owner thread."""
        self.ocr = None
        lease, self._lease = self._lease, None
        if lease is not None:
            lease.__exit__(None, None, None)

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

            all_text, spans = [], []
            for line in result[0]:
                try:
                    text = line[1][0]
                    if not isinstance(text, str):
                        continue
                    all_text.append(text)
                except (TypeError, IndexError, KeyError):
                    continue
                try:
                    polygon = np.asarray(line[0], dtype=float)
                    confidence = float(line[1][1])
                    if (polygon.shape == (4, 2) and np.isfinite(polygon).all()
                            and np.isfinite(confidence) and 0 <= confidence <= 1
                            and np.ptp(polygon[:, 0]) > 0 and np.ptp(polygon[:, 1]) > 0):
                        spans.append(OcrSpan(text, tuple(tuple(p) for p in polygon), confidence))
                except (TypeError, ValueError, IndexError, KeyError):
                    pass
            if not all_text:
                return OcrResult()

            full_text = " ".join(all_text).strip()
            return OcrResult(text=full_text, spans=tuple(spans))

        except Exception:
            return OcrResult(error=EngineError("ocr", "Không thể nhận diện chữ trong ảnh.", True))


# Single active engine cache: chỉ giữ 1 model đang sử dụng, giải phóng model cũ khi đổi ngôn ngữ
_current_engine = None
_current_lang = None
_current_identity = None


def release_ocr_engine():
    """Giải phóng engine OCR hiện tại khỏi RAM và thu dọn rác"""
    global _current_engine, _current_lang, _current_identity
    engine, _current_engine = _current_engine, None
    _current_lang = _current_identity = None
    if engine is not None:
        close = getattr(engine, 'close', None)
        if close is not None:
            close()
        del engine
        gc.collect()


def get_ocr_engine(lang='en', *, store=None):
    """Lấy OCR engine cho ngôn ngữ chỉ định; tự động giải phóng ngôn ngữ trước đó để tiết kiệm RAM"""
    global _current_engine, _current_lang, _current_identity
    if store is None:
        identity = (None, lang)
    else:
        from core.languages import language_by_ocr_code
        identity = (id(store), *store.identity(language_by_ocr_code(lang).id))
    if _current_engine is not None and _current_identity == identity:
        return _current_engine

    if _current_engine is not None:
        release_ocr_engine()

    _current_engine = SimplePaddleOCR(lang=lang) if store is None else SimplePaddleOCR(lang=lang, store=store)
    _current_lang = lang
    _current_identity = identity

    return _current_engine


def ocr_image(img, lang='en', *, store=None) -> OcrResult:
    """Hàm giao tiếp chính để nhận diện chữ trong ảnh"""
    if img is None:
        return OcrResult(error=EngineError("invalid_input", "Ảnh nhận diện không hợp lệ.", False))
    try:
        engine = get_ocr_engine(lang=lang) if store is None else get_ocr_engine(lang=lang, store=store)
        return engine.extract_text(img)
    except OcrModelError as exc:
        return OcrResult(error=EngineError("ocr_model_missing", str(exc), False))
    except Exception:
        if store is not None:
            return OcrResult(error=EngineError('ocr_model_missing', 'Bộ nhận diện chưa sẵn sàng. Mở Quản lý gói ngôn ngữ để kiểm tra hoặc cài lại.', False))
        return OcrResult(error=EngineError("ocr", "Không thể khởi tạo bộ nhận diện chữ.", True))
