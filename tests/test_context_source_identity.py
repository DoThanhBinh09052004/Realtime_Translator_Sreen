from dataclasses import replace

import pytest

from core import config
from core.capture.models import NormalizedRect, WindowIdentity
from core.dialogue.context_models import ScopeSpec, SourceKey
from core.runtime.worker import TranslationWorker
from tests.test_capture_sessions import context, profile


@pytest.fixture(params=['worker', 'helper'])
def identity(qtbot, request):
    if request.param == 'helper':
        from core.dialogue.source_identity import memory_identity
        return memory_identity
    worker = TranslationWorker(config.State(), {})

    def compute(*, source_invalid=False, profile=None, context=None, geometry=None, region=None):
        worker._context_source_invalid = source_invalid
        worker._capture_geometry = geometry
        worker._region = {} if region is None else region
        return worker._memory_identity(profile, context)

    return compute


def test_window_identity_and_enabled_scope_include_exclusion_digest(identity, capture_geometry):
    p = profile()
    p = replace(p, source_kind='window', regions=(p.regions[0], replace(p.regions[1], enabled=False)),
                exclusions=(NormalizedRect(0.0, 0.0, 0.25, 0.5),))
    ctx = replace(context(capture_geometry), source_kind='window', binding_epoch=7,
                  window=WindowIdentity(10, 20, 30))
    assert identity(profile=p, context=ctx) == (
        SourceKey('window', (10, 20, 30, 7)),
        (ScopeSpec(p.regions[0].id, (800, 600, 0.0, 0, 0.5, 1,
            'b75543aeaf8b6dcf1ff7d1f578805fe78952d215ef1efb422480ab4900edddf8')),))


@pytest.mark.parametrize('monitor,expected', [('selected', 'selected'), (None, 'test')])
def test_desktop_identity_uses_selected_monitor_or_context_screen(identity, capture_geometry, monitor, expected):
    p = replace(profile(), monitor_name=monitor)
    source, scopes = identity(profile=p, context=context(capture_geometry))
    assert source == SourceKey('desktop', (expected, 1))
    assert [s.scope_id for s in scopes] == [r.id for r in p.regions]
    assert scopes[0].layout_key[-1] == '2e38e77b22c314a449e91fafed92a43826ac6aa403ae6a8acb6cf58239fbaf5d'


@pytest.mark.parametrize('region,expected', [({}, ('legacy', (0, 0, 0, 0))),
    ({'monitor': 2, 'left': -50, 'top': 10, 'width': 80, 'height': 90}, ('2', (-50, 10, 80, 90)))])
def test_legacy_region_defaults_and_monitor_string(identity, region, expected):
    screen, layout = expected
    assert identity(region=region) == (SourceKey('desktop', (screen,)), (ScopeSpec('legacy-subtitle', layout),))


def test_partial_capture_configuration_uses_legacy_geometry(identity, capture_geometry):
    assert identity(profile=profile(), geometry=capture_geometry, region={'monitor': 9, 'width': 80}) == (
        SourceKey('desktop', ('test',)), (ScopeSpec('legacy-subtitle', (0, 0, 80, 0)),))


def test_invalid_source_short_circuits_capture_and_legacy_identity(identity):
    assert identity(source_invalid=True, profile=object(), context=object(), region=object()) == (None, ())


def test_worker_reconciles_memory_when_exclusions_change(qtbot, capture_geometry):
    from tests.context_helpers import stable
    worker = TranslationWorker(config.State(), {})
    p = profile()
    ctx = context(capture_geometry)
    worker.configure_capture(p, ctx)
    memory = worker._coordinator.context_memory
    scope_id = p.regions[0].id
    memory.observe(scope_id, stable())
    before = memory.view(scope_id, now_s=0)
    worker.configure_capture(p, replace(ctx, geometry_sequence=2))
    assert memory.view(scope_id, now_s=0).turns == before.turns
    worker.configure_capture(replace(p, exclusions=(NormalizedRect(0, 0, .25, .5),)), ctx)
    assert not memory.view(scope_id, now_s=0).turns
    assert memory.view(scope_id, now_s=0).epoch != before.epoch
