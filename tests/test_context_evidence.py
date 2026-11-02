from core.contracts import OcrResult, OcrSpan, RuntimeSettings, ProviderSettings
from core.dialogue.evidence import evidence_from_ocr
from core.dialogue.track import DialogueTrack

def test_speaker_lines_come_from_same_observation():
    a=evidence_from_ocr(OcrResult('A Hello',(None) if False else None,(OcrSpan('Hello',((0,20),(30,20),(30,30),(0,30)),.9),OcrSpan('A',((0,0),(10,0),(10,10),(0,10)),.9))))
    assert [l.text for l in a.lines]==['A','Hello']
    assert a.lines[0].is_label_candidate
    track=DialogueTrack(0)
    track.observe('A Hello',now_s=0,evidence=a)
    track.observe('A Hello',now_s=.6,evidence=a)
    settings=RuntimeSettings('English','Vietnamese',ProviderSettings('x','m','k',None),500)
    assert track.job(revision=1,settings=settings,now_s=.6).evidence==a
    track.observe('B Goodbye',now_s=.7,evidence=evidence_from_ocr(OcrResult('B Goodbye')))
    assert track.evidence==a

def test_append_emits_one_source_turn_with_new_version():
    track=DialogueTrack(0)
    track.observe('Hello',now_s=0)
    track.observe('Hello',now_s=.6)
    assert len(track.drain_stable_turns(revision=1))==1
    assert track.drain_stable_turns(revision=1)==()
    track.observe('Hello there',now_s=.7)
    track.advance(now_s=1.3)
    event=track.drain_stable_turns(revision=1)[0]
    assert event.turn_id==1 and event.text_version==2

def test_spanless_ocr_remains_translatable():
    assert evidence_from_ocr(OcrResult('Hello')).lines[0].text=='Hello'

def test_append_stability_uses_same_readiness_as_dispatch():
    track=DialogueTrack(0)
    settings=RuntimeSettings('English','Vietnamese',ProviderSettings('x','m','k',None),500)
    track.observe('Hello',now_s=0);track.observe('Hello',now_s=.6)
    track.drain_stable_turns(revision=1)
    job=track.job(revision=1,settings=settings,now_s=.6);track.mark_dispatched(job,now_s=.6)
    track.observe('Hello friend',now_s=1.6)
    assert track.job(revision=1,settings=settings,now_s=1.6) is None
    assert track.drain_stable_turns(revision=1)==()
    track.advance(now_s=2.2)
    assert track.drain_stable_turns(revision=1)[0].text_version==2
