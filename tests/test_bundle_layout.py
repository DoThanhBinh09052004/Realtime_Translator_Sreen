from pathlib import Path
import pytest
from ocr_asset_helpers import make_assets
from tools.bundle_layout import bundle_data

def test_bundle_data_includes_only_manifest_files_and_logo(tmp_path,monkeypatch):
    project=tmp_path/'project'; (project/'ui').mkdir(parents=True); (project/'ui/logo.png').write_bytes(b'logo')
    models=make_assets(project/'assets/ocr')
    (project/'.env').write_bytes(b'secret'); (models/'secret.txt').write_bytes(b'secret')
    data=bundle_data(project,models)
    assert (str(models/'cls/inference.pdmodel'),'assets/ocr/cls') in data
    assert (str(models/'manifest.json'),'assets/ocr') in data
    assert (str(project/'ui/logo.png'),'ui') in data
    assert len(data)==15
    assert all('secret' not in source and '.env' not in source for source,_ in data)
    monkeypatch.chdir(tmp_path)
    assert bundle_data(project,models)==data

@pytest.mark.parametrize('missing',['logo','model'])
def test_missing_asset_fails_preflight(tmp_path,missing):
    project=tmp_path/'project'; (project/'ui').mkdir(parents=True); (project/'ui/logo.png').write_bytes(b'logo')
    models=make_assets(project/'assets/ocr')
    (project/'ui/logo.png' if missing=='logo' else models/'cls/inference.pdmodel').unlink()
    with pytest.raises(ValueError if missing=='logo' else Exception): bundle_data(project,models)
