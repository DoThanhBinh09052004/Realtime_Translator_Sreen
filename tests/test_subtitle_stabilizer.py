import pytest

from core.subtitle_stabilizer import StabilizationDecision, SubtitleStabilizer


def test_identical_observations_normalize_whitespace_and_wait_for_commit():
    state = SubtitleStabilizer()
    assert state.observe('  Hello\n world ', 0) == StabilizationDecision('wait', '')
    assert state.has_pending
    assert state.observe('Hello world', 0.5) == StabilizationDecision('translate', 'Hello world')
    assert state.has_pending
    state.commit('Hello world')
    assert not state.has_pending
    assert state.observe('Hello   world', 1).action == 'unchanged'


@pytest.mark.parametrize('values', [
    ['Hello', 'Hello there', 'Hello there friend'],
    ['Hello there friend', 'Hello there', 'Hello'],
])
def test_prefix_sequence_translates_latest_value_at_two_seconds(values):
    state = SubtitleStabilizer()
    assert state.observe(values[0], 10).action == 'wait'
    assert state.observe(values[1], 11.99).action == 'wait'
    assert state.observe(values[2], 12) == StabilizationDecision('translate', values[2])


def test_unrelated_text_starts_new_deadline():
    state = SubtitleStabilizer()
    state.observe('Hello', 0)
    assert state.observe('Goodbye', 1.9).action == 'wait'
    assert state.observe('Goodbye friend', 2).action == 'wait'
    assert state.observe('Goodbye friends', 3.9).action == 'translate'


def test_disappearing_candidate_is_translated_and_remains_retryable():
    state = SubtitleStabilizer()
    assert state.observe('', 0).action == 'wait'
    state.observe('Brief subtitle', 1)
    for now in [1.5, 2]:
        assert state.observe('', now) == StabilizationDecision('translate', 'Brief subtitle')
    state.commit('Brief subtitle')
    assert state.observe('', 3).action == 'wait'


def test_trailing_tokens_remain_suppressed_until_empty_segment_boundary():
    state = SubtitleStabilizer()
    state.commit('This is the whole sentence')
    for now, text in enumerate(['the whole sentence', 'sentence', 'whole sentence']):
        assert state.observe(text, now).action == 'unchanged'
        assert not state.has_pending
    state.observe('', 3)
    assert state.observe('sentence', 4).action == 'wait'
    assert state.observe('sentence', 4.5).action == 'translate'


def test_unrelated_segment_ends_suffix_suppression():
    state = SubtitleStabilizer()
    state.commit('Hello dear friend')
    state.observe('A new dialogue', 0)
    assert state.observe('friend', 1).action == 'wait'
    assert state.observe('friend', 1.5).action == 'translate'


def test_character_suffix_is_not_token_suffix():
    state = SubtitleStabilizer()
    state.commit('Something')
    assert state.observe('thing', 0).action == 'wait'
    assert state.observe('thing', 0.5).action == 'translate'


def test_committed_repeat_cancels_an_intervening_pending_candidate():
    state = SubtitleStabilizer()
    state.commit('Hello world')
    state.observe('Other dialogue', 0)
    assert state.observe('Hello world', 0.5).action == 'unchanged'
    assert not state.has_pending
    assert state.observe('', 1).action == 'wait'


def test_reset_clears_pending_and_committed_state():
    state = SubtitleStabilizer()
    state.commit('Hello world')
    state.observe('Other dialogue', 0)
    state.reset()
    assert not state.has_pending
    assert state.observe('Hello world', 1).action == 'wait'
