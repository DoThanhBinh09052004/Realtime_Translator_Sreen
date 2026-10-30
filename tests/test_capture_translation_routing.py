from dataclasses import replace

import pytest

from tests.test_capture_sessions import profile, context, observation


def test_geometry_move_repaints_held_blocks_without_new_ocr_or_translation(qtbot, runtime_settings, capture_geometry, span_factory, dialogue_result):
    from core.dialogue.coordinator import DialogueCoordinator
    settings = replace(runtime_settings, overlay_mode='blocks')
    now = [0.]; c = DialogueCoordinator(clock=lambda: now[0]); frames = []; changes = []
    c.blocks_updated.connect(frames.append); c.jobs_changed.connect(lambda *args: changes.append(args))
    c.reset(settings, revision=1, session_id=1, running=True)
    p = profile(); ctx = context(capture_geometry)
    try:
        c.configure_capture(p, ctx)
        c.observe_capture(observation(p, ctx, settings, {0: 'Hello'}, spans=(span_factory(),)))
        c.observe_capture(observation(p, ctx, settings, {0: 'Hello'}, scan=1, spans=(span_factory(),)))
        now[0] = .5; c.tick(); job = changes[-1][0][0]
        c.on_job_started(job); now[0] = .6; c.on_result(dialogue_result(job))
        before = len(changes); last = frames[-1]
        geometry = replace(capture_geometry, region_px=replace(capture_geometry.region_px, x=-200))
        moved = replace(ctx, geometry_sequence=2, geometry=geometry)
        c.update_capture_geometry(moved)
        assert frames[-1].geometry == geometry and frames[-1].blocks == last.blocks
        assert len(changes) == before
        c.update_capture_geometry(ctx)
        assert frames[-1].geometry == geometry
        resized = replace(moved, geometry_sequence=3, geometry=replace(geometry, image_size_px=(400, 600)))
        c.update_capture_geometry(resized)
        assert frames[-1].blocks == ()
        c.on_result(dialogue_result(job, 'stale'))
        assert frames[-1].blocks == ()
    finally:
        c.reset(settings, revision=2, session_id=2, running=False)


def test_capture_scan_signal_is_separate_from_legacy_bool(qtbot, runtime_settings, capture_geometry):
    from core.dialogue.coordinator import DialogueCoordinator
    c = DialogueCoordinator(clock=lambda: 0.); captured = []; legacy = []
    c.capture_scan_policy_changed.connect(lambda *args: captured.append(args))
    c.scan_policy_changed.connect(lambda *args: legacy.append(args))
    c.reset(runtime_settings, revision=1, session_id=1, running=True)
    p = profile(); ctx = context(capture_geometry)
    try:
        c.configure_capture(p, ctx)
        c.observe_capture(observation(p, ctx, runtime_settings, {0: 'Hello'}))
        assert captured[-1] == (1, frozenset({p.regions[0].id}))
        assert all(type(value) is bool for _, value in legacy)
    finally:
        c.reset(runtime_settings, revision=2, session_id=2, running=False)


def test_future_and_malformed_capture_batch_are_rejected(qtbot, runtime_settings, capture_geometry):
    from core.dialogue.coordinator import DialogueCoordinator
    c = DialogueCoordinator(clock=lambda: 0.)
    c.reset(runtime_settings, revision=1, session_id=1, running=True)
    p = profile(); ctx = context(capture_geometry)
    try:
        c.configure_capture(p, ctx)
        c.observe_capture(None)
        c.observe_capture(observation(p, ctx, runtime_settings, {0: 'future'}, 1., 0))
        for scan in (0, 1):
            c.observe_capture(observation(p, ctx, runtime_settings, {0: 'valid'}, 0., scan))
        assert [j.source_text for j in c.session.translation_jobs(now_s=.5)] == ['valid']
    finally:
        c.reset(runtime_settings, revision=2, session_id=2, running=False)


def test_reconfigure_same_profile_only_updates_geometry(qtbot, runtime_settings, capture_geometry, dialogue_result):
    from core.dialogue.coordinator import DialogueCoordinator
    c = DialogueCoordinator(clock=lambda: .6)
    c.reset(runtime_settings, revision=1, session_id=1, running=True)
    p = profile(); ctx = context(capture_geometry)
    try:
        c.configure_capture(p, ctx)
        for scan in (0, 1): c.observe_capture(observation(p, ctx, runtime_settings, {0: 'A'}, scan=scan))
        job = c.session.translation_jobs(now_s=.5)[0]
        c.on_job_started(job); c.on_result(dialogue_result(job, 'A'))
        c.configure_capture(p, replace(ctx, geometry_sequence=2))
        assert c.session.current_frame().text == 'A'
    finally:
        c.reset(runtime_settings, revision=2, session_id=2, running=False)


def test_routed_regions_share_provider_rate_limit(qtbot, runtime_settings, capture_geometry):
    from core.blocks.translation_worker import BlockTranslationWorker
    from core.contracts import EngineError, TranslationResult
    from tests.test_capture_sessions import make_session, settle
    now = [0.]; calls = []
    settings = replace(runtime_settings, provider=replace(runtime_settings.provider, name='OpenAI'))
    p = profile(); s = make_session(p, settings)
    settle(s, observation(p, context(capture_geometry), settings, {0: 'A', 1: 'B'}))
    class Service:
        def translate(self, text, settings):
            calls.append((text, now[0]))
            return (TranslationResult(error=EngineError('rate_limit', 'wait', True, 5.))
                    if len(calls) == 1 else TranslationResult(text))
        def close(self): pass
    worker = BlockTranslationWorker(clock=lambda: now[0], service_factory=Service)
    worker.replace_pending(s.translation_jobs(now_s=.5), s.active_turns, 1)
    worker.start()
    try:
        qtbot.waitUntil(lambda: bool(worker.drain_results()))
        now[0] = 1.; qtbot.wait(50)
        assert calls == [('A', 0.)]
        now[0] = 5.; qtbot.waitUntil(lambda: len(calls) == 3)
        assert calls[1:] == [('B', 5.), ('A', 5.)]
    finally:
        worker.request_stop(); assert worker.wait(2000)


@pytest.mark.parametrize('change', ['reorder', 'disable', 'delete'])
def test_profile_change_requires_new_revision_and_old_callbacks_cannot_revive(change, qtbot, runtime_settings, capture_geometry, dialogue_result):
    from core.dialogue.coordinator import DialogueCoordinator
    c = DialogueCoordinator(clock=lambda: .6)
    c.reset(runtime_settings, revision=1, session_id=1, running=True)
    p = profile(); ctx = context(capture_geometry)
    if change == 'reorder': regions = tuple(reversed(p.regions))
    elif change == 'disable': regions = (p.regions[0], replace(p.regions[1], enabled=False))
    else: regions = (p.regions[0],)
    changed = replace(p, regions=regions)
    try:
        c.configure_capture(p, ctx)
        for scan in (0, 1): c.observe_capture(observation(p, ctx, runtime_settings, {0: 'A'}, scan=scan))
        old = c.session.translation_jobs(now_s=.5)[0]; c.on_job_started(old)
        with pytest.raises(ValueError, match='revision'):
            c.configure_capture(changed, ctx)
        c.reset(runtime_settings, revision=2, session_id=2, running=True)
        c.configure_capture(changed, ctx)
        for scan in (0, 1):
            c.observe_capture(replace(observation(changed, ctx, runtime_settings, {0: 'A'}, scan=scan), revision=2))
        current = c.session.translation_jobs(now_s=.5)[0]; c.on_job_started(current)
        c.on_job_started(old); c.on_result(dialogue_result(old, 'old'))
        assert c.session.current_frame().text == ''
        c.on_result(dialogue_result(current, 'new'))
        assert c.session.current_frame().text == 'new'
    finally:
        c.reset(runtime_settings, revision=3, session_id=3, running=False)
