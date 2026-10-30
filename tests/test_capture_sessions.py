from dataclasses import replace
from uuid import UUID

import pytest

from core.capture.models import (CaptureContext, CaptureObservation, CaptureProfile,
                                 CaptureRegion, NormalizedRect, RegionOcrObservation)
from core.contracts import EngineError, OcrResult


def profile(count=2):
    return CaptureProfile(1, 'desktop', 'test', None, tuple(
        CaptureRegion(str(UUID(int=i+1)), str(i), NormalizedRect(i/count, 0, 1/count, 1), True)
        for i in range(count)), ())


def context(geometry):
    return CaptureContext(1, 1, 'desktop', None, geometry)


def observation(p, ctx, settings, texts, t=0., scan=0, *, spans=None):
    return CaptureObservation(1, scan, settings, ctx, tuple(
        RegionOcrObservation(p.regions[i].id, t, t, OcrResult(text, spans=spans or ()))
        for i, text in texts.items()))


def make_session(p, settings):
    from core.capture.sessions import RegionDialogueSession
    session = RegionDialogueSession(p)
    session.reset(1, settings)
    return session


def settle(session, batch):
    session.observe(batch)
    session.observe(replace(batch, scan_id=batch.scan_id+1))


def test_same_local_ids_route_jobs_active_turns_started_and_results(runtime_settings, capture_geometry, dialogue_result):
    p = profile(); ctx = context(capture_geometry); s = make_session(p, runtime_settings)
    settle(s, observation(p, ctx, runtime_settings, {0: 'Hello', 1: 'Hello'}))
    jobs = s.translation_jobs(now_s=.5)
    assert len(jobs) == 2 and len({j.block_id for j in jobs}) == 2
    assert all(len(j.request_key) == 4 for j in jobs)
    assert all((j.revision, j.block_id, j.turn_id) in s.active_turns for j in jobs)
    for j in jobs: s.mark_dispatched(j, now_s=.5)
    for j, text in zip(reversed(jobs), ('B', 'A')):
        assert s.apply_result(dialogue_result(j, text), now_s=.6)
    assert s.current_frame().text == 'A\n\nB'
    assert s.current_frame().source_text == 'Hello\n\nHello'


def test_empty_error_late_and_malformed_region_do_not_clear_other_region(runtime_settings, capture_geometry, dialogue_result):
    p = profile(); ctx = context(capture_geometry); s = make_session(p, runtime_settings)
    settle(s, observation(p, ctx, runtime_settings, {0: 'A', 1: 'B'}))
    for j in s.translation_jobs(now_s=.5):
        s.mark_dispatched(j, now_s=.5); s.apply_result(dialogue_result(j, j.source_text), now_s=.6)
    for scan, t in ((2, 1.), (3, 1.5)):
        batch = observation(p, ctx, runtime_settings, {1: ''}, t, scan)
        s.observe(batch)
    s.tick(now_s=4.5)
    assert s.current_frame().text == 'A'
    bad = RegionOcrObservation(p.regions[0].id, float('nan'), 4.6, OcrResult('wrong'))
    err = RegionOcrObservation(p.regions[1].id, 4.6, 4.6, OcrResult(error=EngineError('ocr', 'oops', True)))
    s.observe(CaptureObservation(1, 4, runtime_settings, ctx, (bad, err)))
    assert s.current_frame().text == 'A'
    assert len(s.drain_errors()) == 1
    s.observe(observation(p, ctx, runtime_settings, {0: 'wrong'}, 4.7, 2))
    assert s.current_frame().text == 'A'


def test_block_roi_local_rectangles_offset_to_full_source(runtime_settings, capture_geometry, span_factory, dialogue_result):
    settings = replace(runtime_settings, overlay_mode='blocks')
    p = profile(); ctx = context(capture_geometry); s = make_session(p, settings)
    settle(s, observation(p, ctx, settings, {0: 'Hello', 1: 'Hello'}, spans=(span_factory(),)))
    for j in s.translation_jobs(now_s=.5):
        s.mark_dispatched(j, now_s=.5); assert s.apply_result(dialogue_result(j), now_s=.6)
    frame = s.current_frame()
    assert frame.geometry.image_size_px == (800, 600)
    assert [b.source_rect.x for b in frame.blocks] == [10, 410]
    assert len({b.block_id for b in frame.blocks}) == 2


@pytest.mark.parametrize('count', [1, 3, 8])
def test_block_quota_totals_32(count, runtime_settings, capture_geometry, span_factory):
    settings = replace(runtime_settings, overlay_mode='blocks')
    p = profile(count); s = make_session(p, settings)
    # Separated one-pixel spans cannot be grouped into fewer tracks.
    spans = tuple(span_factory(str(i), x=1, y=i*18, width=1, height=1) for i in range(32))
    batch = observation(p, context(capture_geometry), settings, dict.fromkeys(range(count), 'x'), spans=spans)
    batch = replace(batch, regions=tuple(replace(item, ocr=replace(item.ocr, spans=tuple(
        replace(span, text=f'{index}:{span.text}') for span in item.ocr.spans)))
        for index, item in enumerate(batch.regions)))
    settle(s, batch)
    assert len(s.active_turns) == 32
    jobs = s.translation_jobs(now_s=.5)
    assert len(jobs) == 32
    quota, extra = divmod(32, count)
    assert [sum(j.source_text.startswith(f'{i}:') for j in jobs) for i in range(count)] == [
        quota+(i < extra) for i in range(count)]
    from core.blocks.translation_worker import BlockTranslationWorker
    worker = BlockTranslationWorker()
    worker.replace_pending(jobs, s.active_turns, 1)
    assert worker.pending_count == 32
    worker.request_stop()


def test_region_starvation_expires_only_that_region(runtime_settings, capture_geometry, dialogue_result):
    p = profile(); ctx = context(capture_geometry); s = make_session(p, runtime_settings)
    settle(s, observation(p, ctx, runtime_settings, {0: 'A', 1: 'B'}))
    for j in s.translation_jobs(now_s=.5):
        s.mark_dispatched(j, now_s=.5); s.apply_result(dialogue_result(j, j.source_text), now_s=.6)
    s.observe(observation(p, ctx, runtime_settings, {1: 'B'}, 5.9, 2))
    s.tick(now_s=6.)
    assert s.current_frame().text == 'B'


def test_reset_reorder_and_geometry_invalidation_do_not_revive_or_recycle(runtime_settings, capture_geometry, dialogue_result):
    p = profile(); ctx = context(capture_geometry); s = make_session(p, runtime_settings)
    settle(s, observation(p, ctx, runtime_settings, {0: 'A'}))
    old = s.translation_jobs(now_s=.5)[0]; s.mark_dispatched(old, now_s=.5)
    changed = replace(ctx, binding_epoch=2, geometry_sequence=2)
    s.set_geometry(changed)
    assert not s.apply_result(dialogue_result(old), now_s=.6)
    settle(s, observation(p, changed, runtime_settings, {0: 'A'}, 1., 2))
    new = s.translation_jobs(now_s=1.5)[0]
    assert new.block_id > old.block_id
    s.reset(2, runtime_settings)
    assert not s.apply_result(dialogue_result(new), now_s=1.6)


def test_reject_wrong_settings_revision_epoch_sequence_and_timestamp(runtime_settings, capture_geometry):
    p = profile(); ctx = context(capture_geometry); s = make_session(p, runtime_settings)
    s.set_geometry(ctx)
    base = observation(p, ctx, runtime_settings, {0: 'A'})
    for bad in (replace(base, revision=0), replace(base, settings=replace(runtime_settings, target_lang='French')),
                replace(base, context=replace(ctx, binding_epoch=0)),
                replace(base, context=replace(ctx, geometry_sequence=0)),
                replace(base, regions=(replace(base.regions[0], captured_at_s=2.),))):
        s.observe(bad)
        assert not s.translation_jobs(now_s=.5)
    settle(s, base)
    assert len(s.translation_jobs(now_s=.5)) == 1


def test_block_retirement_local_ids_are_monotonic(runtime_settings, capture_geometry, span_factory, dialogue_result):
    settings = replace(runtime_settings, overlay_mode='blocks')
    p = profile(1); ctx = context(capture_geometry); s = make_session(p, settings)
    settle(s, observation(p, ctx, settings, {0: 'A'}, spans=(span_factory('A'),)))
    old = s.translation_jobs(now_s=.5)[0]; s.mark_dispatched(old, now_s=.5)
    s.observe(observation(p, ctx, settings, {0: ''}, .7, 2))
    s.observe(observation(p, ctx, settings, {0: ''}, .9, 3))
    settle(s, observation(p, ctx, settings, {0: 'B'}, 1., 4, spans=(span_factory('B'),)))
    new = s.translation_jobs(now_s=1.5)[0]
    assert new.block_id > old.block_id
    assert not s.apply_result(dialogue_result(old), now_s=1.6)


def test_malformed_batch_does_not_reset_other_regions_or_consume_scan(runtime_settings, capture_geometry, dialogue_result):
    p = profile(); ctx = context(capture_geometry); s = make_session(p, runtime_settings)
    settle(s, observation(p, ctx, runtime_settings, {0: 'A'}))
    job = s.translation_jobs(now_s=.5)[0]; s.mark_dispatched(job, now_s=.5)
    assert s.apply_result(dialogue_result(job, 'A'), now_s=.6)
    bad = replace(observation(p, replace(ctx, binding_epoch=2), runtime_settings, {0: 'bad'}, 1., 2),
                  regions=(None,))
    s.observe(bad)
    assert s.current_frame().text == 'A'
    settle(s, observation(p, ctx, runtime_settings, {1: 'B'}, 1., 2))
    assert [j.source_text for j in s.translation_jobs(now_s=1.5)] == ['B']


def test_static_frame_uses_success_completion_for_freshness(runtime_settings, capture_geometry, dialogue_result):
    p = profile(); ctx = context(capture_geometry); s = make_session(p, runtime_settings)
    settle(s, observation(p, ctx, runtime_settings, {0: 'A'}))
    job = s.translation_jobs(now_s=.5)[0]; s.mark_dispatched(job, now_s=.5)
    assert s.apply_result(dialogue_result(job, 'A'), now_s=.6)
    batch = observation(p, ctx, runtime_settings, {0: 'A'}, 10., 2)
    s.observe(replace(batch, regions=(replace(batch.regions[0], captured_at_s=0.),)))
    s.tick(now_s=10.)
    assert s.current_frame().text == 'A'


def test_hard_geometry_reset_preserves_scan_watermark(runtime_settings, capture_geometry):
    p = profile(); ctx = context(capture_geometry); s = make_session(p, runtime_settings)
    settle(s, observation(p, ctx, runtime_settings, {0: 'A'}, scan=10))
    new = replace(ctx, binding_epoch=2)
    s.set_geometry(new)
    settle(s, observation(p, new, runtime_settings, {0: 'stale'}, 1., 1))
    assert not s.translation_jobs(now_s=1.5)


def test_retired_local_ids_above_32_never_collide_with_another_roi(runtime_settings, capture_geometry, span_factory):
    settings = replace(runtime_settings, overlay_mode='blocks')
    p = profile(); ctx = context(capture_geometry); s = make_session(p, settings)
    settle(s, observation(p, ctx, settings, {0: 'A', 1: 'A'}, spans=(span_factory('A'),)))
    first = s.translation_jobs(now_s=.5)
    ids = {j.block_id for j in first}
    permanent = first[1].block_id
    for index in range(35):
        scan = 2+index*4; now = 1.+index
        for step in (0, 1): s.observe(observation(p, ctx, settings, {0: ''}, now, scan+step))
        settle(s, observation(p, ctx, settings, {0: 'A', 1: 'A'}, now+.1, scan+2,
                              spans=(span_factory('A'),)))
        jobs = s.translation_jobs(now_s=now+.6)
        assert len(jobs) == 2 and jobs[1].block_id == permanent
        assert jobs[0].block_id not in ids
        ids.add(jobs[0].block_id)
        assert all((j.revision, j.block_id, j.turn_id) in s.active_turns for j in jobs)
    assert len(ids) == 37


@pytest.mark.parametrize('mode', ['subtitle', 'blocks'])
def test_held_ocr_after_origin_move_refreshes_text_and_keeps_latest_mapping(mode, runtime_settings, capture_geometry, span_factory, dialogue_result):
    settings = replace(runtime_settings, overlay_mode=mode)
    p = profile(); ctx = context(capture_geometry); s = make_session(p, settings)
    settle(s, observation(p, ctx, settings, {0: 'A'}, spans=(span_factory('A'),)))
    job = s.translation_jobs(now_s=.5)[0]; s.mark_dispatched(job, now_s=.5)
    assert s.apply_result(dialogue_result(job, 'translated A'), now_s=.6)
    moved = replace(ctx, geometry_sequence=2, geometry=replace(capture_geometry,
                    region_px=replace(capture_geometry.region_px, x=-200)))
    s.set_geometry(moved)
    # Both completions retain the snapshot taken before the GUI moved.
    settle(s, observation(p, ctx, settings, {0: 'A extended'}, 5.9, 2,
                          spans=(span_factory('A extended'),)))
    s.tick(now_s=6.)
    frame = s.current_frame()
    assert (frame.text if mode == 'subtitle' else frame.blocks[0].translated_text) == 'translated A'
    jobs = s.translation_jobs(now_s=6.5)
    assert [job.source_text for job in jobs] == ['A extended']
    s.mark_dispatched(jobs[0], now_s=6.5)
    assert s.apply_result(dialogue_result(jobs[0], 'translated extended'), now_s=6.6)
    frame = s.current_frame()
    assert (frame.text if mode == 'subtitle' else frame.blocks[0].translated_text) == 'translated extended'
    if mode == 'blocks': assert frame.geometry == moved.geometry
    assert s._context == moved


@pytest.mark.parametrize('difference', ['epoch', 'size', 'identity'])
def test_older_geometry_ocr_with_incompatible_source_cannot_refresh(difference, runtime_settings, capture_geometry, dialogue_result):
    from core.capture.models import WindowIdentity
    p = profile(); ctx = context(capture_geometry); s = make_session(p, runtime_settings)
    settle(s, observation(p, ctx, runtime_settings, {0: 'A'}))
    job = s.translation_jobs(now_s=.5)[0]; s.mark_dispatched(job, now_s=.5)
    assert s.apply_result(dialogue_result(job, 'A'), now_s=.6)
    s.set_geometry(replace(ctx, geometry_sequence=2))
    if difference == 'epoch': incompatible = replace(ctx, binding_epoch=0)
    elif difference == 'size': incompatible = replace(ctx, geometry=replace(capture_geometry, image_size_px=(400, 600)))
    else: incompatible = replace(ctx, window=WindowIdentity(1, 2, 3))
    settle(s, observation(p, incompatible, runtime_settings, {0: 'A'}, 5.9, 2))
    s.tick(now_s=6.)
    assert s.current_frame().text == ''


def test_newer_epoch_can_restart_geometry_sequence(runtime_settings, capture_geometry):
    p = profile(); ctx = replace(context(capture_geometry), geometry_sequence=10)
    s = make_session(p, runtime_settings)
    settle(s, observation(p, ctx, runtime_settings, {0: 'A'}))
    old = s.translation_jobs(now_s=.5)[0]
    new = replace(ctx, binding_epoch=2, geometry_sequence=1)
    settle(s, observation(p, new, runtime_settings, {0: 'new source'}, 1., 2))
    jobs = s.translation_jobs(now_s=1.5)
    assert [job.source_text for job in jobs] == ['new source']
    assert jobs[0].block_id > old.block_id
