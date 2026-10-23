from core.blocks.models import BlockTranslationResult
from core.contracts import TranslationResult


def test_stability_disappearance_and_old_candidate_are_safe(runtime_settings):
    from core.google_subtitle_session import GoogleSubtitleSession
    session=GoogleSubtitleSession()
    def observe(text,t,rev=1): return session.observe(text,settings=runtime_settings,revision=rev,now_s=t)
    observe('A',0)
    assert not session.translation_jobs()
    observe('A',.5)
    old,=session.translation_jobs()
    assert session.apply_result(BlockTranslationResult(1,old.block_id,'A',TranslationResult('a')))
    assert session.current_frame().text=='a'
    assert observe('B',1).text==''
    observe('A',1.5)
    assert not session.apply_result(BlockTranslationResult(1,old.block_id,'A',TranslationResult('old')))
    observe('A',2)
    new,=session.translation_jobs()
    assert new.block_id > old.block_id
    frame=observe('',2.5)
    assert frame.text==frame.source_text=='' and not session.translation_jobs()
    assert not session.apply_result(BlockTranslationResult(1,new.block_id,'A',TranslationResult('old')))
    observe('A',3,rev=2)
    assert not session.apply_result(BlockTranslationResult(1,new.block_id,'A',TranslationResult('old')))


def test_typewriter_deadline_and_repeated_observation_keep_candidate(runtime_settings):
    from core.google_subtitle_session import GoogleSubtitleSession
    s=GoogleSubtitleSession()
    for t,text in [(0,'H'),(1,'He'),(1.99,'Hel'),(2,'Hell')]:
        s.observe(text,settings=runtime_settings,revision=1,now_s=t)
        assert bool(s.translation_jobs())==(t==2)
    old=s.translation_jobs()[0]
    s.observe('Hell',settings=runtime_settings,revision=1,now_s=2.5)
    assert s.translation_jobs()[0].block_id==old.block_id
