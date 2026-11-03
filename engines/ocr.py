import os
import gc

# Cấu hình cờ tối ưu RAM cho PaddlePaddle trước khi nạp model
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['FLAGS_fraction_of_cpu_memory_to_use'] = '0.05'

import cv2
import numpy as np
from paddleocr import PaddleOCR
from core.contracts import EngineError, OcrResult, OcrSpan
from core.ocr.models import OcrModelError, resolve_ocr_models


def normalize_ocr_crop(img, bucket_step: int = 32):
    """Pad image width to the nearest multiple of bucket_step to stabilize oneDNN tensor cache."""
    if not isinstance(img, np.ndarray) or img.ndim < 2:
        return img
    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        return img
    remainder = w % bucket_step
    if remainder == 0:
        return img
    pad_right = bucket_step - remainder
    return cv2.copyMakeBorder(img, 0, 0, 0, pad_right, cv2.BORDER_CONSTANT, value=0)


class SimplePaddleOCR:
    """Wrapper bao bọc PaddleOCR xử lý trích xuất văn bản từ hình ảnh với cấu hình hiệu năng linh hoạt"""
    def __init__(self, lang='en', *, enable_mkldnn: bool = False, cpu_threads: int = 2, store=None):
        self._lease = None
        self.ocr = None
        self.enable_mkldnn = bool(enable_mkldnn)
        self.cpu_threads = int(cpu_threads)
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
                enable_mkldnn=self.enable_mkldnn,
                cpu_threads=self.cpu_threads,
                **model_options
            )
            if hasattr(self.ocr, 'text_recognizer') and hasattr(self.ocr.text_recognizer, '__call__'):
                orig_rec = self.ocr.text_recognizer.__call__
                def _bucketed_rec(img_list, *args, **kwargs):
                    if isinstance(img_list, list):
                        img_list = [normalize_ocr_crop(c) for c in img_list]
                    return orig_rec(img_list, *args, **kwargs)
                self.ocr.text_recognizer.__call__ = _bucketed_rec
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


# Single active engine cache: chỉ giữ 1 model đang sử dụng, giải phóng model cũ khi đổi ngôn ngữ hoặc cấu hình
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


def get_ocr_engine(lang='en', *, enable_mkldnn: bool = True, cpu_threads: int = 4, store=None):
    """Lấy OCR engine cho ngôn ngữ chỉ định; tự động giải phóng ngôn ngữ/cấu hình trước đó để tiết kiệm RAM"""
    global _current_engine, _current_lang, _current_identity
    if store is None:
        identity = (None, lang, bool(enable_mkldnn), int(cpu_threads))
    else:
        from core.languages import language_by_ocr_code
        identity = (id(store), *store.identity(language_by_ocr_code(lang).id), bool(enable_mkldnn), int(cpu_threads))
    if _current_engine is not None and _current_identity == identity:
        return _current_engine

    if _current_engine is not None:
        release_ocr_engine()

    _current_engine = (
        SimplePaddleOCR(lang=lang, enable_mkldnn=enable_mkldnn, cpu_threads=cpu_threads)
        if store is None
        else SimplePaddleOCR(lang=lang, enable_mkldnn=enable_mkldnn, cpu_threads=cpu_threads, store=store)
    )
    _current_lang = lang
    _current_identity = identity

    return _current_engine


def ocr_image(img, lang='en', *, enable_mkldnn: bool = True, cpu_threads: int = 4, store=None) -> OcrResult:
    """Hàm giao tiếp chính để nhận diện chữ trong ảnh"""
    if img is None:
        return OcrResult(error=EngineError("invalid_input", "Ảnh nhận diện không hợp lệ.", False))
    try:
        engine = get_ocr_engine(lang=lang, enable_mkldnn=enable_mkldnn, cpu_threads=cpu_threads, store=store)
        return engine.extract_text(img)
    except OcrModelError as exc:
        return OcrResult(error=EngineError("ocr_model_missing", str(exc), False))
    except Exception:
        if store is not None:
            return OcrResult(error=EngineError('ocr_model_missing', 'Bộ nhận diện chưa sẵn sàng. Mở Quản lý gói ngôn ngữ để kiểm tra hoặc cài lại.', False))
        return OcrResult(error=EngineError("ocr", "Không thể khởi tạo bộ nhận diện chữ.", True))
