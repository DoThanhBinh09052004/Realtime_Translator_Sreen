"""OCR argument resolution and invocation without worker or engine ownership."""
from core.config import SUPPORTED_LANGUAGES


def resolve_ocr_language(source_name):
    return SUPPORTED_LANGUAGES.get(source_name) or (
        source_name if source_name in SUPPORTED_LANGUAGES.values() else None)


def read_ocr(image, lang, settings, reader):
    from core.config import resolve_ocr_threads
    perf_mode = getattr(settings, 'ocr_performance_mode', 'high')
    auto_threads = getattr(settings, 'ocr_auto_threads', True)
    custom_threads = getattr(settings, 'ocr_threads', 4)
    enable_mkldnn = (perf_mode == 'high')
    threads = resolve_ocr_threads(auto_threads, custom_threads)
    try:
        return reader(image, lang=lang, enable_mkldnn=enable_mkldnn, cpu_threads=threads)
    except TypeError:
        return reader(image, lang=lang)
