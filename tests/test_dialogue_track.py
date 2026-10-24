from core.blocks.models import BlockTranslationResult


def ready(settings, text='Hello'):
    from core.dialogue.track import DialogueTrack
    t=DialogueTrack(7)
    t.observe(text,now_s=0); t.observe(text,now_s=.25)
    j=t.job(revision=1,settings=settings,now_s=.5)
    t.mark_dispatched(j,now_s=.5)
    return t,j


def test_quiet_and_continuous_dispatch(runtime_settings):
    from core.dialogue.track import DialogueTrack
    t=DialogueTrack(7)
    t.observe('Hello',now_s=0); t.observe('Hello world',now_s=.25)
    assert t.job(revision=1,settings=runtime_settings,now_s=.749) is None
    assert t.job(revision=1,settings=runtime_settings,now_s=.75).source_text=='Hello world'
    t=DialogueTrack(1)
    for i in range(7): t.observe('字'*(i+1),now_s=i*.25)
    j=t.job(revision=1,settings=runtime_settings,now_s=1.5)
    assert j is not None
    t.mark_dispatched(j,now_s=1.5)
    assert t.job(revision=1,settings=runtime_settings,now_s=3) is None
    t.observe('字'*8,now_s=1.75)
    assert t.job(revision=1,settings=runtime_settings,now_s=1.9) is None


def test_older_prefix_result_survives_growth(runtime_settings,dialogue_result):
    t,j=ready(runtime_settings)
    t.observe('Hello world. Second sentence',now_s=.6)
    assert t.apply_result(dialogue_result(j),now_s=.7)
    assert t.presentation.text=='Xin chào'


def test_punctuation_does_not_clear_or_requeue(runtime_settings,dialogue_result):
    t,j=ready(runtime_settings,'gods,this..')
    t.apply_result(dialogue_result(j),now_s=.6)
    t.observe('gods, this.',now_s=.8)
    assert t.presentation.text=='Xin chào'
    assert t.job(revision=1,settings=runtime_settings,now_s=3) is None


def test_one_second_hold_keeps_only_latest(runtime_settings,dialogue_result):
    t,j=ready(runtime_settings)
    t.apply_result(dialogue_result(j,'one'),now_s=.5)
    for text,now,result in [('Hello world',1.,'two'),('Hello world again',1.25,'three')]:
        t.observe(text,now_s=now)
        # Snapshot was eligible through a continuous stream; receipt is tested independently.
        from core.blocks.models import BlockJob
        job=BlockJob(1,7,text,runtime_settings,j.turn_id,t.text_version)
        t.mark_dispatched(job,now_s=now)
        assert t.apply_result(dialogue_result(job,result),now_s=now)
    assert t.presentation.text=='one'
    t.advance(now_s=1.5)
    assert t.presentation.text=='three'
    assert not t.apply_result(dialogue_result(j,'old'),now_s=2)


def test_challenger_and_a_b_a_retire_old_result(runtime_settings,dialogue_result):
    t,j=ready(runtime_settings,'I can go')
    t.observe('I cannot go',now_s=.6)
    assert t.apply_result(dialogue_result(j,'old'),now_s=.7)
    assert t.presentation is None
    t.observe('I cannot go',now_s=.9)
    t.observe('I can go',now_s=1.1); t.observe('I can go',now_s=1.4)
    assert t.active_turn(1)[2] != j.turn_id
    assert not t.apply_result(dialogue_result(j,'old'),now_s=2)


def test_challenger_rejected_restores_deferred_result(runtime_settings,dialogue_result):
    t,j=ready(runtime_settings)
    t.observe('Garbage OCR',now_s=.6)
    t.apply_result(dialogue_result(j,'good'),now_s=.7)
    t.observe('Hello',now_s=.8)
    assert t.presentation.text=='good'


def test_regression_and_missing_confirm_new_turn(runtime_settings,dialogue_result):
    t,j=ready(runtime_settings,'Hello world')
    t.observe('Hello',now_s=.6)
    assert t.active_turn(1)[2]==j.turn_id
    t.observe('Hello',now_s=1.2)
    assert t.active_turn(1)[2]!=j.turn_id
    assert not t.miss(now_s=1.3)
    t.observe('Hello',now_s=1.4)
    assert not t.miss(now_s=1.5)
    assert t.miss(now_s=1.6)
    assert t.active_turn(1) is None
    assert not t.miss(now_s=1.7)


def test_oversized_and_empty_never_dispatch(runtime_settings):
    from core.dialogue.track import DialogueTrack
    for source in ('','x'*2001):
        t=DialogueTrack(0)
        t.observe(source,now_s=0); t.observe(source,now_s=.25)
        assert t.job(revision=1,settings=runtime_settings,now_s=3) is None
