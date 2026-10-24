import pytest
from core.contracts import SubtitleFrame, TranslationResult
from core.blocks.models import BlockJob, BlockTranslationResult


def test_policy_values_and_identity_contracts(runtime_settings):
    from core.dialogue.policy import DEFAULT_DIALOGUE_POLICY, classify_text, identity_text
    p = DEFAULT_DIALOGUE_POLICY
    assert (p.quiet_s, p.continuous_s, p.min_read_s, p.subtitle_end_hold_s, p.absent_scans) == (.5, 1.5, 1., 3., 2)
    for a,b in [('gods,this','gods, this'),('but..','but.'),('I’m here…',"I'm here.")]:
        assert classify_text(a,b) == 'same'
    for a,b in [('now here','nowhere'),('I can go','I cannot go'),('Take 1','Take 2'),('Go?','Go!')]:
        assert classify_text(a,b) == 'different'
    assert classify_text('Hello','Hello world. Next sentence') == 'append'
    assert classify_text('こんにちは','こんにちは世界') == 'append'
    assert classify_text('Hello world','Hello') == 'regression'
    assert identity_text('Take 1.5.') == 'Take 1.5'
    assert SubtitleFrame(1,1,'a','b').render_sequence == 0
    job=BlockJob(1,7,'Hello',runtime_settings,2,3)
    assert job.request_key == (1,7,2,3)
    assert BlockTranslationResult(1,7,'Hello',TranslationResult('x'),2,3).request_key == job.request_key


def test_observation_is_immutable(runtime_settings):
    from core.dialogue.models import DialogueObservation
    from core.contracts import OcrResult
    from dataclasses import FrozenInstanceError
    o=DialogueObservation(1,1,0,.2,runtime_settings,OcrResult('Hello'),None)
    with pytest.raises(FrozenInstanceError): o.scan_id=3
