"""Release boundaries exercised without loading native capture or OCR models."""
import builtins
from dataclasses import replace
from pathlib import Path
import runpy
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from core.capture.models import CaptureContext, WindowIdentity


@pytest.mark.parametrize('failure', [ModuleNotFoundError('windows_capture absent'), OSError('dependent DLL absent')])
def test_missing_native_capture_keeps_mss_usable_and_reports_window_error(monkeypatch, capture_geometry, failure):
    from core.capture.source import create_capture_source
    from test_capture_wgc import Owner
    imports = []
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name == 'windows_capture':
            imports.append(name)
            raise failure
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    import mss
    native = SimpleNamespace(grab=lambda rect: np.zeros((rect['height'], rect['width'], 4), dtype=np.uint8), close=lambda: None)
    monkeypatch.setattr(mss, 'mss', lambda: native)
    context = CaptureContext(1, 1, 'desktop', None, capture_geometry)
    desktop = create_capture_source(context)
    desktop.open(context)
    assert desktop.read_latest(now_s=1).source_size_px == capture_geometry.image_size_px
    desktop.close()
    assert not imports, 'MSS must never import the optional native package'
    window = replace(context, source_kind='window', window=WindowIdentity(1, 2, 3))
    adapter = create_capture_source(window)
    monkeypatch.setattr(adapter, '_identity_validator', lambda identity: True)
    owner = Owner()
    try:
        owner.call(lambda: adapter.open(window))
        status = adapter.status()
        assert imports == ['windows_capture']
        assert status.phase == 'error' and status.error.code == 'capture_open_failed'
        assert status.error.user_message and owner.call(lambda: adapter.read_latest(now_s=1)) is None
    finally:
        owner.call(adapter.close)
        owner.close()


def test_spec_passes_native_extension_metadata_and_assets_to_analysis(monkeypatch, tmp_path):
    """Execute the spec with hook outputs, rather than inspecting its text."""
    import tools.bundle_layout
    monkeypatch.setattr(tools.bundle_layout, 'bundle_data', lambda *args: [('model.bin', 'assets/ocr')])
    hooks = ModuleType('PyInstaller.utils.hooks')
    hooks.collect_all = lambda package: ([(package + '.data', package)],
        [(package + '.pyd', package)], [package + '.native'])
    hooks.copy_metadata = lambda distribution: [(distribution + '.dist-info', distribution + '.dist-info')]
    monkeypatch.setitem(sys.modules, 'PyInstaller.utils.hooks', hooks)
    captured = {}
    def analysis(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(pure=[], scripts=[], binaries=kwargs['binaries'], datas=kwargs['datas'])
    root = Path(__file__).resolve().parents[1]
    runpy.run_path(str(root / 'main.spec'), init_globals=dict(SPECPATH=str(root), Analysis=analysis,
        PYZ=lambda *args, **kwargs: None, EXE=lambda *args, **kwargs: None,
        COLLECT=lambda *args, **kwargs: None))
    assert ('windows_capture.pyd', 'windows_capture') in captured['binaries']
    assert 'windows_capture.native' in captured['hiddenimports']
    assert ('windows-capture.dist-info', 'windows-capture.dist-info') in captured['datas']
    assert ('model.bin', 'assets/ocr') in captured['datas']
