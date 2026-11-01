from dataclasses import replace
import pytest
from core.dialogue.context_models import *
from core.dialogue.context_memory import DialogueMemory
from core.dialogue.context_builder import build_context
from tests.context_helpers import stable

def setup_memory():
    m=DialogueMemory(); m.reconcile(SourceKey('window',(1,)),(),(ScopeSpec('r1'),),now_s=0)
    return m

def commit(m,turn,form='em',other='thầy'):
    current=m.observe('r1',turn); view=m.view('r1',now_s=1)
    snap=build_context(view,current)
    refs=(EvidenceRef(current.source_id,turn.source_text),)
    delta=MemoryDelta((EntityRecord('new:1','A',(),refs),EntityRecord('new:2','Sensei',(),refs)),(RelationRecord('new:1','new:2',form,other,evidence=refs),))
    receipt=PresentationReceipt((turn.revision,0,turn.turn_id,turn.text_version),turn.source_text,'dịch',ContextOutcome(snap.stamp,delta=delta))
    assert m.commit(receipt,snap,now_s=1)
    return snap,receipt

def test_two_distinct_source_turns_support_directed_relation():
    m=setup_memory(); commit(m,stable('A: Sensei help'))
    assert m.view('r1',now_s=1).relations[0].status=='candidate'
    commit(m,stable('A: Sensei please',turn=2))
    view=m.view('r1',now_s=1)
    assert len(view.relations)==1 and view.relations[0].status=='supported'

def test_retry_cache_and_append_cannot_promote_relationship():
    m=setup_memory(); snap,receipt=commit(m,stable('A: Sensei help'))
    assert not m.commit(receipt,snap,now_s=1)
    commit(m,stable('A: Sensei help please',version=2))
    assert m.view('r1',now_s=1).relations[0].status=='candidate'

def test_conflict_suspends_previous_addressing():
    m=setup_memory(); commit(m,stable('A: Sensei help')); commit(m,stable('A: Sensei please',turn=2))
    commit(m,stable('A: Sensei friend',turn=3),form='tôi',other='bạn')
    assert m.view('r1',now_s=1).relations[0].status=='conflicted'

def test_resource_bounds_after_ten_thousand_turns():
    m=setup_memory()
    for i in range(10000): m.observe('r1',stable(f'A: line {i}',turn=i+1))
    assert len(m.view('r1',now_s=1).turns)==8
    assert len(m._scopes['r1'].routes)<=32

def test_idle_and_epoch_invalidate_old_results():
    m=setup_memory(); snap,receipt=commit(m,stable('A: Sensei help'))
    m.mark_seen('r1',now_s=1)
    assert m.view('r1',now_s=120.999).turns
    assert not m.view('r1',now_s=121).turns
    assert not m.commit(receipt,snap,now_s=121)

def test_tables_and_proof_storage_are_bounded_after_many_commits():
    m=setup_memory()
    for i in range(150):
        turn=stable(f'Person{i}: Teacher{i} help',turn=i+1)
        current=m.observe('r1',turn);snap=build_context(m.view('r1',now_s=1),current)
        refs=(EvidenceRef(current.source_id,turn.source_text),)
        delta=MemoryDelta((EntityRecord('new:1',f'Person{i}',(),refs),EntityRecord('new:2',f'Teacher{i}',(),refs)),(RelationRecord('new:1','new:2','em','thầy',evidence=refs),))
        assert m.commit(PresentationReceipt((1,0,i+1,1),turn.source_text,'text',ContextOutcome(snap.stamp,delta=delta)),snap,now_s=1)
        view=m.view('r1',now_s=1);ids={e.entity_id for e in view.entities}
        assert len(view.entities)<=32 and len(view.relations)<=64
        assert all(r.speaker_id in ids and r.addressee_id in ids for r in view.relations)
        assert len(m._scopes['r1'].proofs)<=320 and len(m._scopes['r1'].receipts)<=32

def test_same_utterance_after_restart_is_not_new_evidence():
    m=setup_memory();commit(m,stable('A: Sensei help'))
    commit(m,stable('A: Sensei help',revision=2))
    assert m.view('r1',now_s=1).relations[0].status=='candidate'

def test_unsupported_evidence_never_creates_entities():
    m=setup_memory();current=m.observe('r1',stable());snap=build_context(m.view('r1',now_s=1),current)
    delta=MemoryDelta((EntityRecord('new:1','Invented',(),(EvidenceRef(999,'Invented'),)),))
    assert not m.commit(PresentationReceipt((1,0,1,1),current.source_text,'x',ContextOutcome(snap.stamp,delta=delta)),snap,now_s=1)
    assert not m.view('r1',now_s=1).entities

@pytest.mark.parametrize('conflict',[False,True])
def test_unrelated_append_preserves_supported_and_conflicted_relation(conflict):
    m=setup_memory();commit(m,stable('A: Sensei help'));commit(m,stable('A: Sensei please',turn=2))
    if conflict:commit(m,stable('A: Sensei friend',turn=3),form='tôi',other='bạn')
    expected='conflicted' if conflict else 'supported'
    m.observe('r1',stable('B: Wait',turn=4))
    m.observe('r1',stable('B: Wait here',turn=4,version=2))
    assert m.view('r1',now_s=1).relations[0].status==expected

def test_corrected_conflicting_turn_cannot_leave_its_forms_on_old_evidence():
    m=setup_memory();commit(m,stable('A: Sensei help'))
    commit(m,stable('A: Sensei friend',turn=2),form='tôi',other='bạn')
    m.observe('r1',stable('A: Sensei correction',turn=2,version=2))
    relations=m.view('r1',now_s=1).relations
    assert not relations or (relations[0].self_form,relations[0].other_form)==('em','thầy')
