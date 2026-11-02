from pathlib import Path
import pytest

from ocr_asset_helpers import make_assets
from pack_resource_helpers import make_pack_resources
from tools import prepare_ocr_models
from tools.bundle_layout import bundle_data
from core.ocr_models import OcrModelError
from core.language_pack_contracts import PackOperationError


def test_prepare_additional_dictionaries_preserves_legacy_bundle(tmp_path):
    models = make_assets(tmp_path / 'Bộ đọc 日本語')
    before = {p.relative_to(models): p.read_bytes() for p in models.rglob('*') if p.is_file()}
    package = tmp_path / 'package'
    catalog = make_pack_resources(models, package)
    prepare_ocr_models.prepare_pack_resources(models, package, catalog)
    assert (models / 'pack_resources/ch_dict.txt').read_bytes() == b'Chinese dictionary'
    assert (models / 'pack_resources/korean_dict.txt').read_bytes() == b'Korean dictionary'
    assert (models / 'language-packs.json').read_bytes() == catalog.read_bytes()
    assert all((models / p).read_bytes() == data for p, data in before.items())


def test_resource_hash_mismatch_never_publishes_catalog(tmp_path):
    models = make_assets(tmp_path / 'models')
    package = tmp_path / 'package'
    catalog = make_pack_resources(models, package)
    (package / 'dict/korean_dict.txt').write_bytes(b'wrong dictionary')
    with pytest.raises(OcrModelError):
        prepare_ocr_models.prepare_pack_resources(models, package, catalog)
    assert not (models / 'language-packs.json').exists()
    assert not (models / 'pack_resources/ch_dict.txt').exists()


def test_new_bundle_requires_catalog_and_uses_resource_allowlist(tmp_path, monkeypatch):
    project = tmp_path / 'project'; (project / 'ui').mkdir(parents=True)
    (project / 'ui/logo.png').write_bytes(b'logo')
    models = make_assets(project / 'assets/ocr')
    with pytest.raises(PackOperationError):
        bundle_data(project, models)
    package = tmp_path / 'package'
    catalog = make_pack_resources(models, package)
    prepare_ocr_models.prepare_pack_resources(models, package, catalog)
    (models / 'pack_resources/secret.txt').write_bytes(b'not a resource')
    (models / 'models.tar').write_bytes(b'not a resource')
    monkeypatch.chdir(tmp_path)
    entries = bundle_data(project, models)
    assert (str(models / 'language-packs.json'), 'assets/ocr') in entries
    assert (str(models / 'pack_resources/ch_dict.txt'), 'assets/ocr/pack_resources') in entries
    assert (str(models / 'pack_resources/korean_dict.txt'), 'assets/ocr/pack_resources') in entries
    assert not any(Path(source).name in ('secret.txt', 'models.tar') for source, _ in entries)
    (models / 'pack_resources/ch_dict.txt').write_bytes(b'corrupt')
    with pytest.raises(PackOperationError):
        bundle_data(project, models)
