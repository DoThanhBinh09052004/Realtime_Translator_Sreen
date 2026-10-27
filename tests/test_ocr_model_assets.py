import json
import pytest
from ocr_asset_helpers import make_assets, make_source_cache
from core.ocr_models import OcrModelError, validate_ocr_assets
from tools.prepare_ocr_models import prepare_models

def test_prepare_copies_only_en_japan_models(tmp_path):
    cache, dictionaries, license_path = make_source_cache(tmp_path)
    (cache/'secret.txt').write_text('secret')
    before = {p: p.read_bytes() for p in cache.rglob('*') if p.is_file()}
    output = tmp_path/'Bản dựng Nhật 空白'
    manifest = prepare_models(cache, output, dictionaries, license_path=license_path)
    assert manifest['languages'] == ['en','japan']
    assert len(list(output.rglob('inference.pdmodel'))) == 5
    assert (output/'dict/japan_dict.txt').read_bytes() == b'dict/japan_dict.txt'
    assert not (output/'secret.txt').exists()
    assert before == {p: p.read_bytes() for p in before}
    assert validate_ocr_assets(output) == manifest

def test_prepare_fails_without_classifier(tmp_path):
    cache, dictionaries, license_path = make_source_cache(tmp_path)
    (cache/'whl/cls/ch_ppocr_mobile_v2.0_cls_infer/inference.pdmodel').unlink()
    with pytest.raises(OcrModelError):
        prepare_models(cache, tmp_path/'out', dictionaries, license_path=license_path)
    assert not (tmp_path/'out/manifest.json').exists()

def test_prepare_never_overwrites_existing_output(tmp_path):
    cache, dictionaries, license_path = make_source_cache(tmp_path)
    output = tmp_path/'out'; output.mkdir(); (output/'sentinel').write_bytes(b'keep')
    with pytest.raises(OcrModelError):
        prepare_models(cache, output, dictionaries, license_path=license_path)
    assert (output/'sentinel').read_bytes() == b'keep'

@pytest.mark.parametrize('damage', ['model','dictionary','empty','corrupt','schema','version','escape','absolute'])
def test_validation_rejects_incomplete_or_corrupt_assets(tmp_path, damage):
    root = make_assets(tmp_path/'assets')
    manifest_path = root/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if damage == 'model': (root/'cls/inference.pdmodel').unlink()
    elif damage == 'dictionary': (root/'dict/japan_dict.txt').unlink()
    elif damage in ('empty','corrupt'): (root/'det/en/inference.pdmodel').write_bytes(b'' if damage=='empty' else b'bad')
    elif damage == 'schema': manifest['schema'] = 2
    elif damage == 'version': manifest['paddleocr_version'] = '3.0'
    else: manifest['files']['../outside.txt' if damage=='escape' else str(tmp_path/'outside.txt')] = '0'*64
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(OcrModelError): validate_ocr_assets(root)

def test_validation_is_read_only(tmp_path):
    root = make_assets(tmp_path/'assets')
    before = {p:(p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    validate_ocr_assets(root)
    assert before == {p:(p.read_bytes(), p.stat().st_mtime_ns) for p in before}
