from pathlib import Path
import pytest
from ocr_asset_helpers import make_assets
from tools.bundle_layout import bundle_data
from tools.prepare_ocr_models import prepare_pack_resources
from pack_resource_helpers import make_pack_resources


def resource_assets(root, tmp_path):
    models=make_assets(root)
    package=tmp_path/'package'
    prepare_pack_resources(models, package, make_pack_resources(models, package))
    return models

def test_bundle_data_includes_only_manifest_files_and_logo(tmp_path,monkeypatch):
    project=tmp_path/'project'; (project/'ui').mkdir(parents=True); (project/'ui/logo.png').write_bytes(b'logo')
    models=resource_assets(project/'assets/ocr', tmp_path)
    (project/'.env').write_bytes(b'secret'); (models/'secret.txt').write_bytes(b'secret')
    data=bundle_data(project,models)
    assert (str(models/'cls/inference.pdmodel'),'assets/ocr/cls') in data
    assert (str(models/'manifest.json'),'assets/ocr') in data
    assert (str(project/'ui/logo.png'),'ui') in data
    assert (str(models/'language-packs.json'),'assets/ocr') in data
    assert len(data)==18
    assert all('secret' not in source and '.env' not in source for source,_ in data)
    monkeypatch.chdir(tmp_path)
    assert bundle_data(project,models)==data

@pytest.mark.parametrize('missing',['logo','model'])
def test_missing_asset_fails_preflight(tmp_path,missing):
    project=tmp_path/'project'; (project/'ui').mkdir(parents=True); (project/'ui/logo.png').write_bytes(b'logo')
    models=resource_assets(project/'assets/ocr', tmp_path)
    (project/'ui/logo.png' if missing=='logo' else models/'cls/inference.pdmodel').unlink()
    with pytest.raises(ValueError if missing=='logo' else Exception): bundle_data(project,models)
