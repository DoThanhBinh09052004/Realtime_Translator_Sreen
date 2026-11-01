from core.dialogue.context_builder import build_context
from tests.context_helpers import make_turn, make_view

def test_current_turn_never_appears_in_history():
    turn=make_turn(); snapshot=build_context(make_view(turns=(turn,)),turn)
    assert snapshot.history==()

def test_unicode_budget_is_utf8_bytes():
    current=make_turn(9,'日😀'*1000)
    snapshot=build_context(make_view(turns=tuple(make_turn(i,'日😀'*1000) for i in range(1,9))),current)
    assert len(snapshot.context_json.encode('utf-8'))<=6144
    assert snapshot.current.source_text==current.source_text

def test_digest_changes_for_speaker_context_and_scope():
    a=build_context(make_view(),make_turn(text='A: hello'))
    b=build_context(make_view(),make_turn(text='B: hello'))
    assert a.stamp.snapshot_digest!=b.stamp.snapshot_digest
    assert a.stamp!=build_context(make_view(scope_id='r2'),make_turn(text='A: hello')).stamp
