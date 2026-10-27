"""Read-only validation and resolution of the English/Japanese OCR bundle."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.language_pack_store import PackStore

MODEL_SOURCES = {
    'det/en': 'whl/det/en/en_PP-OCRv3_det_infer',
    'det/ml': 'whl/det/ml/Multilingual_PP-OCRv3_det_infer',
    'rec/en': 'whl/rec/en/en_PP-OCRv4_rec_infer',
    'rec/japan': 'whl/rec/japan/japan_PP-OCRv4_rec_infer',
    'cls': 'whl/cls/ch_ppocr_mobile_v2.0_cls_infer',
}
REQUIRED = {f'{directory}/{name}' for directory in MODEL_SOURCES
            for name in ('inference.pdmodel', 'inference.pdiparams')}
REQUIRED |= {'dict/en_dict.txt', 'dict/japan_dict.txt', 'NOTICE.paddleocr.txt'}
ALLOWED = REQUIRED | {f'{directory}/inference.pdiparams.info' for directory in MODEL_SOURCES}
MESSAGE = 'OCR models are unavailable or invalid. Select English/Japanese or reinstall the complete OCR bundle.'

class OcrModelError(Exception):
    """An actionable error that never reveals local cache paths."""

@dataclass(frozen=True)
class OcrModelPaths:
    det: Path
    rec: Path
    cls: Path
    dictionary: Path

def validate_ocr_assets(root: Path) -> dict:
    root = Path(root).resolve()
    try:
        manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
        if (manifest.get('schema') != 1 or manifest.get('paddleocr_version') != '2.10.0'
                or manifest.get('ocr_version') != 'PP-OCRv4'
                or manifest.get('languages') != ['en', 'japan']):
            raise ValueError('metadata')
        files = manifest['files']
        if not isinstance(files, dict) or not REQUIRED <= files.keys() or not files.keys() <= ALLOWED:
            raise ValueError('file list')
        for relative, digest in files.items():
            posix = PurePosixPath(relative)
            if (posix.is_absolute() or PureWindowsPath(relative).drive or '\\' in relative
                    or '..' in posix.parts or posix.as_posix() != relative):
                raise ValueError('unsafe path')
            path = (root/relative).resolve()
            if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size == 0:
                raise ValueError('missing file')
            if not isinstance(digest, str) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('hash')
        if not isinstance(manifest.get('provenance'), dict) or not MODEL_SOURCES.keys() <= manifest['provenance'].keys():
            raise ValueError('provenance')
        return manifest
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise OcrModelError(MESSAGE) from exc

def resolve_ocr_models(lang: str, *, root: Path | None = None, store: 'PackStore | None' = None) -> OcrModelPaths | None:
    if store is not None and root is None:
        from core.languages import language_by_ocr_code
        return store.resolve(language_by_ocr_code(lang).id)
    explicit = root is not None
    frozen = bool(getattr(sys, 'frozen', False))
    if root is None:
        base = Path(sys._MEIPASS) if frozen else Path(__file__).resolve().parents[1]
        root = base/'assets'/'ocr'
    root = Path(root).resolve()
    if not explicit and not frozen:
        if not root.exists() or lang not in ('en', 'japan'):
            return None
        # Git retains release provenance but excludes model payloads. A source
        # checkout containing only that metadata still uses legacy Paddle OCR.
        payloads = (root/directory/name for directory in MODEL_SOURCES
                    for name in ('inference.pdmodel', 'inference.pdiparams'))
        if not any(path.exists() or path.is_symlink() for path in payloads):
            return None
    if lang not in ('en', 'japan'):
        raise OcrModelError(MESSAGE)
    validate_ocr_assets(root)
    return OcrModelPaths(root/'det'/('en' if lang == 'en' else 'ml'), root/'rec'/lang,
                         root/'cls', root/'dict'/('en_dict.txt' if lang == 'en' else 'japan_dict.txt'))
