from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
import pytest
from ocr_asset_helpers import make_assets
from core.ocr_models import resolve_ocr_models
from engines import ocr

@pytest.fixture(autouse=True)
def clear_engine():
    ocr.release_ocr_engine()
    yield
    ocr.release_ocr_engine()

@pytest.mark.parametrize('lang,det', [('en','en'),('japan','ml')])
def test_frozen_en_and_japan_use_bundled_paths(tmp_path, monkeypatch, lang, det):
    root = make_assets(tmp_path/'assets/ocr')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    calls=[]
    monkeypatch.setattr(ocr, 'PaddleOCR', lambda **kwargs: calls.append(kwargs))
    ocr.SimplePaddleOCR(lang)
    args=calls[0]
    assert Path(args['det_model_dir']) == root/'det'/det
    assert Path(args['rec_model_dir']) == root/'rec'/lang
    assert Path(args['cls_model_dir']) == root/'cls'
    assert Path(args['rec_char_dict_path']) == root/'dict'/('en_dict.txt' if lang=='en' else 'japan_dict.txt')
    assert args['ocr_version']=='PP-OCRv4'
    assert args['use_angle_cls'] is False and args['cpu_threads']==2 and args['enable_mkldnn'] is False

@pytest.mark.parametrize('lang,missing', [('en',True),('ch',False),('korean',False)])
def test_frozen_invalid_assets_never_construct_paddle(tmp_path, monkeypatch, lang, missing):
    root=make_assets(tmp_path/'assets/ocr')
    if missing: (root/'cls/inference.pdmodel').unlink()
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'_MEIPASS',str(tmp_path),raising=False)
    def forbidden(**kwargs): pytest.fail('Paddle must not initialize')
    monkeypatch.setattr(ocr,'PaddleOCR',forbidden)
    result=ocr.ocr_image(np.zeros((20,20),dtype='uint8'),lang)
    assert result.error.code=='ocr_model_missing'
    assert result.error.retryable is False
    assert 'English/Japanese' in result.error.user_message

def test_source_without_staging_keeps_legacy_ocr(monkeypatch):
    monkeypatch.setattr(ocr,'resolve_ocr_models',lambda lang: None)
    calls=[]
    monkeypatch.setattr(ocr,'PaddleOCR',lambda **kw: calls.append(kw) or SimpleNamespace(ocr=lambda *a,**k: [[]]))
    assert ocr.ocr_image(np.zeros((20,20),dtype='uint8'),'japan').error is None
    assert calls[0]['lang']=='japan' and 'det_model_dir' not in calls[0]

def test_explicit_root_does_not_depend_on_cwd(tmp_path,monkeypatch):
    root=make_assets(tmp_path/'Bản dựng 空白')
    other=tmp_path/'elsewhere'; other.mkdir(); monkeypatch.chdir(other)
    before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    assert resolve_ocr_models('japan',root=root).det==root/'det/ml'
    assert before=={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in before}

def test_default_source_staging_keeps_unbundled_languages(tmp_path,monkeypatch):
    import core.ocr_models as models
    make_assets(tmp_path/'assets/ocr')
    monkeypatch.setattr(sys,'frozen',False,raising=False)
    monkeypatch.setattr(models,'__file__',str(tmp_path/'core/ocr_models.py'))
    assert models.resolve_ocr_models('ch') is None
    assert models.resolve_ocr_models('korean') is None

@pytest.mark.parametrize('lang', ['en', 'japan'])
@pytest.mark.parametrize('mode', ['source', 'frozen', 'explicit'])
def test_metadata_only_staging_preserves_only_default_source(tmp_path, monkeypatch, lang, mode):
    import core.ocr_models as models
    root = make_assets(tmp_path/'assets/ocr')
    for path in root.rglob('inference.*'):
        path.unlink()
    monkeypatch.setattr(sys, 'frozen', mode == 'frozen', raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    monkeypatch.setattr(models, '__file__', str(tmp_path/'core/ocr_models.py'))
    if mode == 'source':
        assert models.resolve_ocr_models(lang) is None
    else:
        with pytest.raises(models.OcrModelError):
            models.resolve_ocr_models(lang, **({'root': root} if mode == 'explicit' else {}))

@pytest.mark.parametrize('damage', ['partial', 'empty', 'corrupt'])
def test_default_source_rejects_damaged_weight_payload(tmp_path, monkeypatch, damage):
    import core.ocr_models as models
    root = make_assets(tmp_path/'assets/ocr')
    if damage == 'partial':
        for path in root.rglob('inference.*'):
            if path != root/'cls/inference.pdmodel':
                path.unlink()
    else:
        (root/'cls/inference.pdmodel').write_bytes(b'' if damage == 'empty' else b'corrupt')
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    monkeypatch.setattr(models, '__file__', str(tmp_path/'core/ocr_models.py'))
    with pytest.raises(models.OcrModelError):
        models.resolve_ocr_models('en')
