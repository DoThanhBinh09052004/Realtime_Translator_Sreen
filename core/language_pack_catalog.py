"""Pure parsing of the release-pinned OCR artifact catalog."""
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from urllib.parse import urlsplit

from core.language_pack_contracts import ArtifactDefinition, ArtifactFile, PackCatalog, ResourceDefinition, pack_error
from core.languages import source_languages

MODEL_FILES = frozenset(('inference.pdmodel', 'inference.pdiparams', 'inference.pdiparams.info'))
ARCHIVE_METADATA_FILES = frozenset('._'+name for name in MODEL_FILES)
ALLOWED_ARCHIVE_FILES = MODEL_FILES | ARCHIVE_METADATA_FILES
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024 * 1024


def safe_relative(value: object) -> str:
    if not isinstance(value, str) or not value or '\\' in value or ':' in value or '\x00' in value:
        raise ValueError('path')
    path = PurePosixPath(value)
    if path.is_absolute() or PureWindowsPath(value).drive or any(p in ('..', '.') for p in path.parts) or path.as_posix() != value:
        raise ValueError('path')
    if any(part.endswith((' ', '.')) for part in path.parts):
        raise ValueError('path')
    return value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', value):
        raise ValueError('id')
    return value


def _size(value, maximum=MAX_FILE_BYTES):
    if type(value) is not int or not 0 < value <= maximum:
        raise ValueError('size')
    return value


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('digest')
    return value


def validate_pack_catalog(raw: object) -> PackCatalog:
    try:
        if not isinstance(raw, dict) or raw.get('schema') != 1:
            raise ValueError('schema')
        if raw.get('paddleocr_version') != '2.10.0' or raw.get('ocr_version') != 'PP-OCRv4':
            raise ValueError('version')
        components = {}
        for key, value in raw['components'].items():
            if _id(key) != value['id']:
                raise ValueError('component id')
            url = urlsplit(value['url'])
            if (url.scheme != 'https' or url.hostname != 'paddleocr.bj.bcebos.com'
                    or url.username or url.password or url.port not in (None, 443) or url.fragment or url.query
                    or not url.path.endswith('.tar')):
                raise ValueError('URL')
            root = safe_relative(value['archive_root'])
            if '/' in root:
                raise ValueError('root')
            files = tuple(ArtifactFile(safe_relative(f['path']), _size(f['size_bytes']), _digest(f['sha256'])) for f in value['files'])
            names = [f.path for f in files]
            if len(names) != len(set(names)) or not {'inference.pdmodel', 'inference.pdiparams'} <= set(names) <= ALLOWED_ARCHIVE_FILES:
                raise ValueError('files')
            if any(f.path in ARCHIVE_METADATA_FILES and f.size_bytes > 4096 for f in files):
                raise ValueError('archive metadata')
            components[key] = ArtifactDefinition(key, _id(value['revision']), value['url'],
                _size(value['archive_size_bytes'], MAX_ARCHIVE_BYTES), _digest(value['archive_sha256']), root, files)
        resources = { _id(key): ResourceDefinition(safe_relative(value['path']), _size(value['size_bytes'], 16*1024*1024),
                      _digest(value['sha256'])) for key, value in raw['resources'].items() }
        paths = [r.path for r in resources.values()]
        if len(paths) != len(set(paths)):
            raise ValueError('resource paths')
        if not {x for language in source_languages() for x in language.component_ids} <= components.keys():
            raise ValueError('missing component')
        if not {'notice', *(language.dictionary_resource for language in source_languages())} <= resources.keys():
            raise ValueError('missing resource')
        return PackCatalog(1, '2.10.0', 'PP-OCRv4', components, resources)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        raise pack_error('invalid_catalog') from exc


def load_pack_catalog(path: Path) -> PackCatalog:
    try:
        return validate_pack_catalog(json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_unique_pairs))
    except (OSError, ValueError) as exc:
        raise pack_error('invalid_catalog') from exc


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result
