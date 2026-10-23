from core.blocks.models import TextBlock, Rect, BlockTranslationResult
from core.contracts import TranslationResult


def test_geometry_changes_without_translation_restart(runtime_settings, capture_geometry):
    from core.blocks.session import BlockSession
    s = BlockSession()
    def observe(text, x, t, rev=1):
        return s.observe((TextBlock(0, text, Rect(x, 10, 100, 20)),), settings=runtime_settings,
                         revision=rev, frame_id=int(t*100), geometry=capture_geometry, now_s=t)
    observe('Hello', 10, 0)
    assert not s.translation_jobs()
    observe('Hello', 30, .5)
    job, = s.translation_jobs()
    observe('Hello', 40, 1)
    assert s.apply_result(BlockTranslationResult(1, job.block_id, 'Hello', TranslationResult('Xin chào')))
    assert s.current_frame().blocks[0].source_rect.x == 40
    assert not s.translation_jobs()
    assert not s.apply_result(BlockTranslationResult(0, job.block_id, 'Hello', TranslationResult('old')))
    observe('Other', 40, 1.5)
    assert not s.current_frame().blocks
    assert not s.apply_result(BlockTranslationResult(1, job.block_id, 'Hello', TranslationResult('old')))
    observe('Other', 40, 2, rev=2)
    assert not s.apply_result(BlockTranslationResult(1, job.block_id, 'Other', TranslationResult('old')))


def test_progressive_candidate_deadline_is_two_seconds(runtime_settings, capture_geometry):
    from core.blocks.session import BlockSession
    s = BlockSession()
    for t, text in [(0, 'H'), (1, 'He'), (1.99, 'Hel'), (2, 'Hell')]:
        s.observe((TextBlock(0, text, Rect(10, 10, 100, 20)),), settings=runtime_settings,
                  revision=1, frame_id=1, geometry=capture_geometry, now_s=t)
        assert bool(s.translation_jobs()) == (t == 2)


def test_duplicate_text_has_distinct_ids_and_removed_track_rejects_result(runtime_settings, capture_geometry):
    from core.blocks.session import BlockSession
    s = BlockSession()
    blocks = (TextBlock(0, 'A', Rect(10, 10, 100, 20)), TextBlock(1, 'A', Rect(400, 10, 100, 20)))
    for i in range(2):
        s.observe(blocks[::-1] if i else blocks, settings=runtime_settings, revision=1, frame_id=i,
                  geometry=capture_geometry, now_s=i)
    jobs = s.translation_jobs()
    assert len({j.block_id for j in jobs}) == 2
    s.observe((), settings=runtime_settings, revision=1, frame_id=3, geometry=capture_geometry, now_s=3)
    assert not s.current_frame().blocks
    assert not s.apply_result(BlockTranslationResult(1, jobs[0].block_id, 'A', TranslationResult('old')))


def test_oversized_block_does_not_block_valid_neighbors(runtime_settings, capture_geometry):
    from core.blocks.session import BlockSession
    s = BlockSession()
    blocks = (TextBlock(0, 'x'*2001, Rect(0, 0, 100, 20)), TextBlock(1, 'ok', Rect(300, 0, 100, 20)))
    for i in range(2):
        s.observe(blocks, settings=runtime_settings, revision=1, frame_id=i, geometry=capture_geometry, now_s=i)
    assert [j.source_text for j in s.translation_jobs()] == ['ok']
    assert s.drain_errors()[0].code == 'invalid_input'
    assert not s.drain_errors()
