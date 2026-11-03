"""Package boundaries must stay cheap and preserve runtime resource lookup."""
import importlib
from pathlib import Path
import subprocess
import sys

import pytest

from ocr_asset_helpers import make_assets


@pytest.mark.parametrize('package', ['runtime', 'ocr', 'language_packs', 'translation'])
def test_core_package_import_has_no_runtime_side_effects(package):
    result = subprocess.run(
        [sys.executable, '-c',
         f"import sys; import core.{package}; "
         f"assert not any(n.startswith('core.{package}.') for n in sys.modules); "
         "assert not any(n in sys.modules for n in "
         "('paddleocr', 'engines.ocr', 'openai', 'mss', 'PyQt5', 'core.config'))"],
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('module,symbol', [
    ('runtime.worker', 'TranslationWorker'),
    ('runtime.lifecycle', 'WorkerLifecycle'),
    ('runtime.state', 'WorkerRuntimeState'),
    ('runtime.runner', 'CaptureOcrRunner'),
    ('runtime.output', 'TranslationOutputPolicy'),
    ('runtime.memory', 'compact_memory'),
    ('ocr.models', 'resolve_ocr_models'),
    ('ocr.reader', 'read_ocr'),
    ('ocr.frame_processor', 'FrameOcrProcessor'),
    ('language_packs.catalog', 'load_pack_catalog'),
    ('language_packs.contracts', 'PackOperationError'),
    ('language_packs.manager', 'LanguagePackManager'),
    ('language_packs.store', 'PackStore'),
    ('language_packs.transfer', 'install_pack'),
    ('translation.endpoint_policy', 'normalize_custom_api_endpoint'),
    ('translation.google_recovery', 'GoogleRecoveryGate'),
])
def test_core_entrypoints_live_in_their_domain(module, symbol):
    entrypoint = getattr(importlib.import_module(f'core.{module}'), symbol)
    assert entrypoint.__module__ == f'core.{module}'


@pytest.mark.parametrize('lang,det', [('en', 'en'), ('japan', 'ml')])
def test_source_models_resolve_project_assets_after_package_move(tmp_path, monkeypatch, lang, det):
    from core.ocr import models
    root = make_assets(tmp_path / 'assets' / 'ocr')
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    monkeypatch.setattr(models, '__file__', str(tmp_path / 'core' / 'ocr' / 'models.py'))
    resolved = models.resolve_ocr_models(lang)
    assert resolved.det == root / 'det' / det
    assert resolved.rec == root / 'rec' / lang
    assert resolved.dictionary == root / 'dict' / ('en_dict.txt' if lang == 'en' else 'japan_dict.txt')


def test_shared_modules_remain_at_core_root():
    assert {path.name for path in Path('core').glob('*.py')} == {
        '__init__.py', 'config.py', 'contracts.py', 'languages.py',
        'paths.py', 'retry.py', 'secrets.py',
    }
