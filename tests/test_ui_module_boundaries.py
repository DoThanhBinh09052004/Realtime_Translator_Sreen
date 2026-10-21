import ast
import importlib
from importlib.util import resolve_name
from pathlib import Path
import pytest


def forbidden_imports(source, package, forbidden):
    names = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = resolve_name('.' * node.level + (node.module or ''), package) if node.level else node.module or ''
            names.extend([base, *(f'{base}.{alias.name}' for alias in node.names)])
    return [name for name in names if any(name == bad or name.startswith(bad + '.') for bad in forbidden)]


@pytest.mark.parametrize('source,expected', [
    ('import core.config', True), ('from core import worker', True),
    ('from .. import controller', True), ('from ..controller import ControllerWindow', True),
    ('import engines.ocr', True), ('from engines import translator', True),
    ('from ..controller_state import AiPageState', False),
])
def test_boundary_detector_resolves_absolute_and_relative_imports(source, expected):
    assert bool(forbidden_imports(source, 'ui.pages', {'ui.controller', 'core.config', 'core.worker', 'engines'})) == expected


def test_view_and_coordinator_dependency_boundaries():
    for folder in ('pages', 'widgets'):
        for path in Path('ui', folder).glob('*.py'):
            assert not forbidden_imports(path.read_text(encoding='utf-8-sig'), f'ui.{folder}',
                                         {'ui.controller', 'core.config', 'core.worker', 'engines'}), path
    assert not forbidden_imports(Path('ui/settings_coordinator.py').read_text(encoding='utf-8-sig'), 'ui',
                                 {'ui.controller', 'ui.pages'})


def test_importing_views_never_initializes_runtime(monkeypatch):
    import openai
    import paddleocr
    import mss
    from core import config
    def forbidden(*args, **kwargs):
        pytest.fail('View import initialized runtime or accessed persistence')
    monkeypatch.setattr(openai, 'OpenAI', forbidden)
    monkeypatch.setattr(paddleocr, 'PaddleOCR', forbidden)
    monkeypatch.setattr(mss, 'mss', forbidden)
    monkeypatch.setattr(config, 'load_config', forbidden)
    for folder in ('pages', 'widgets'):
        for path in Path('ui', folder).glob('*.py'):
            if path.stem != '__init__':
                importlib.reload(importlib.import_module(f'ui.{folder}.{path.stem}'))
