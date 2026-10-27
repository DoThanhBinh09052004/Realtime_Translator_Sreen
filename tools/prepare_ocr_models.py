"""Stage the pinned OCR assets; never import Paddle or download models."""
import argparse
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import shutil
import sys
import tempfile
import os

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.ocr_models import MODEL_SOURCES, MESSAGE, OcrModelError, validate_ocr_assets
from core.language_pack_catalog import load_pack_catalog
from core.language_pack_contracts import PackOperationError


def prepare_pack_resources(output: Path, dictionary_root: Path, catalog_path: Path) -> None:
    """Stage release catalog and small dictionaries without changing model manifest."""
    from tools.bundle_layout import validate_pack_resources
    output, dictionary_root, catalog_path = map(lambda p: Path(p).resolve(), (output, dictionary_root, catalog_path))
    catalog = load_pack_catalog(catalog_path)
    dictionary_sources = {'dict-en': 'en_dict.txt', 'dict-ja': 'dict/japan_dict.txt',
                          'dict-ch': 'ppocr_keys_v1.txt', 'dict-ko': 'dict/korean_dict.txt'}
    try:
        with tempfile.TemporaryDirectory(prefix='.pack-resources-', dir=output.parent) as temporary:
            staging = Path(temporary)
            for key, resource in catalog.resources.items():
                destination = staging / resource.path
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = output / resource.path if key == 'notice' else dictionary_root / dictionary_sources[key]
                shutil.copyfile(source, destination)
            shutil.copyfile(catalog_path, staging / 'language-packs.json')
            validate_pack_resources(staging)
            # The legacy dictionary/notice contents are already covered by its manifest.
            for key, resource in catalog.resources.items():
                if key not in ('dict-ch', 'dict-ko'):
                    existing = output / resource.path
                    if not existing.is_file() or hashlib.sha256(existing.read_bytes()).hexdigest() != resource.sha256:
                        raise OcrModelError('Bundled dictionary or notice differs from the release catalog.')
                    continue
                destination = output / resource.path
                if not destination.resolve().is_relative_to(output):
                    raise OcrModelError('Resource destination is outside the model root.')
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging / resource.path, destination)
            os.replace(staging / 'language-packs.json', output / 'language-packs.json')
    except (OSError, KeyError, PackOperationError) as exc:
        raise OcrModelError('Language pack resources are missing or invalid.') from exc

def prepare_models(source_cache: Path, output: Path, dictionary_root: Path, *, license_path: Path) -> dict:
    source_cache, output, dictionary_root = map(Path, (source_cache, output, dictionary_root))
    if output.exists():
        raise OcrModelError('Output already exists; choose a new staging directory.')
    output.parent.mkdir(parents=True, exist_ok=True)
    # TemporaryDirectory owns only the new staging sibling, never an existing target.
    with tempfile.TemporaryDirectory(prefix='.ocr-stage-', dir=output.parent) as temporary:
        staging = Path(temporary)/'ocr'
        staging.mkdir()
        copies = []
        for destination, source in MODEL_SOURCES.items():
            for name in ('inference.pdmodel', 'inference.pdiparams', 'inference.pdiparams.info'):
                origin = source_cache/source/name
                if name.endswith('.info') and not origin.exists():
                    continue
                copies.append((origin, f'{destination}/{name}'))
        copies += [(dictionary_root/'en_dict.txt', 'dict/en_dict.txt'),
                   (dictionary_root/'dict/japan_dict.txt', 'dict/japan_dict.txt'),
                   (Path(license_path), 'NOTICE.paddleocr.txt')]
        files = {}
        try:
            for source, relative in copies:
                destination = staging/relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                files[relative] = hashlib.sha256(destination.read_bytes()).hexdigest()
            manifest = dict(schema=1, paddleocr_version='2.10.0', ocr_version='PP-OCRv4',
                            languages=['en', 'japan'], files=files, provenance={
                                **MODEL_SOURCES, 'dictionaries': 'paddleocr 2.10.0 ppocr/utils',
                                'notice': 'paddleocr 2.10.0 LICENSE'})
            (staging/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
            validate_ocr_assets(staging)
            staging.rename(output)
        except OSError as exc:
            raise OcrModelError(MESSAGE) from exc
    return manifest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-cache', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--pack-catalog', type=Path, help='Optional pinned catalog and extra OCR dictionaries')
    args = parser.parse_args()
    try:
        package = distribution('paddleocr')
        if package.version != '2.10.0':
            raise OcrModelError('Preparation requires PaddleOCR 2.10.0.')
        prepare_models(args.source_cache, args.output,
                       Path(package.locate_file('paddleocr/ppocr/utils')),
                       license_path=Path(package.locate_file('paddleocr/LICENSE')))
        if args.pack_catalog is not None:
            prepare_pack_resources(args.output, Path(package.locate_file('paddleocr/ppocr/utils')), args.pack_catalog)
    except (OcrModelError, LookupError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(args.output/'manifest.json')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
