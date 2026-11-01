import json
from dataclasses import replace
import pytest
from core.contracts import OcrResult
from tests.context_helpers import ContextRuntimeHarness

def structured(text):
    return json.dumps(dict(translation=text,speaker=None,addressee=None,addressing=None,updates=dict(entities=[],relations=[],terms=[])))

def dialogue_response(speaker,addressee,self_form,other_form,translation):
    def create(kwargs):
        payload=json.loads(kwargs['messages'][1]['content']);context=payload['context']
        ids={entity['name']:entity['entity_id'] for entity in context['entities']}
        refs=[dict(source_id=context['current']['source_id'],quote=payload['current_text'])]
        entities=[]
        for name in (speaker,addressee):
            if name not in ids:
                eid=f'new:{len(entities)+1}';ids[name]=eid
                entities.append(dict(id=eid,name=name,aliases=[],evidence=refs))
        return json.dumps(dict(translation=translation,speaker=ids[speaker],addressee=ids[addressee],addressing=dict(self=self_form,other=other_form),updates=dict(entities=entities,relations=[dict(speaker=ids[speaker],addressee=ids[addressee],self=self_form,other=other_form,evidence=refs)],terms=[])))
    return create

def test_three_person_dialogue_uses_previous_presentations_in_one_request(qtbot,runtime_settings):
    now=[0.];settings=replace(runtime_settings,context_enabled=True)
    sources=['A: Sensei, can you help me?','Sensei: Of course. What do you need?','B: Sensei, I will go with you.','A: B, you should stay here.','B: A, I will stay here.']
    answers=['Thầy giúp em được không?','Được chứ. Em cần gì?','Thầy ơi, em đi cùng thầy.','B, cậu nên ở lại đây.','A, tớ sẽ ở lại đây.']
    roles=[('A','Sensei','em','thầy'),('Sensei','A','thầy','em'),('B','Sensei','em','thầy'),('A','B','tớ','cậu'),('B','A','tớ','cậu')]
    h=ContextRuntimeHarness(qtbot,settings,[dialogue_response(*role,answer) for role,answer in zip(roles,answers)],clock=lambda:now[0])
    try:
        for index,source in enumerate(sources):
            base=index*3.
            for offset in (0.,.6,1.2):
                now[0]=base+offset;h.observe(OcrResult(source),at_s=now[0])
            qtbot.waitUntil(lambda:len(h.calls)==index+1)
            qtbot.waitUntil(lambda:any(p.pairs and p.pairs[0].translated_text==answers[index] for p in h.presented))
        payload=json.loads(h.calls[-1]['messages'][1]['content'])
        assert sources[0] in [t['text'] for t in payload['context']['original_history']]
        assert answers[-2] in [t['translated_text'] for t in payload['context']['style_only_not_evidence']]
        second=json.loads(h.calls[1]['messages'][1]['content'])['context']
        third=json.loads(h.calls[2]['messages'][1]['content'])['context']
        assert {(r['speaker_id'],r['addressee_id']) for r in second['relations']}=={('e1','e2')}
        assert {('e1','e2'),('e2','e1')}<={(r['speaker_id'],r['addressee_id']) for r in third['relations']}
        assert any(r['speaker_id']=='e1' and r['addressee_id']=='e3' and r['other_form']=='cậu' for r in payload['context']['relations'])
        assert len(h.calls)==5
        assert all(not p.pairs or not p.pairs[0].translated_text.startswith('{') for p in h.presented)
    finally:h.close()

@pytest.mark.parametrize('enabled,response,expected',[(True,'plain translation','plain translation'),(True,'{"translation":',''),(False,'legacy text','legacy text')])
def test_runtime_format_fallback_and_opt_out(qtbot,runtime_settings,enabled,response,expected):
    now=[0.];h=ContextRuntimeHarness(qtbot,replace(runtime_settings,context_enabled=enabled),[response],clock=lambda:now[0])
    errors=[];h.coordinator.error_occurred.connect(errors.append)
    try:
        for at in (0.,.6):
            now[0]=at;h.observe(OcrResult('Japanese narration: 静かな夜。'),at_s=at)
        qtbot.waitUntil(lambda:bool(h.calls))
        if expected:qtbot.waitUntil(lambda:any(p.pairs and p.pairs[0].translated_text==expected for p in h.presented))
        else:
            qtbot.waitUntil(lambda:bool(errors))
            assert errors[0].code=='invalid_response' and not h.overlay.text()
        assert len(h.calls)==1
    finally:h.close()

def test_source_change_during_inflight_reply_cannot_revive_memory(qtbot,runtime_settings):
    from threading import Event
    from core.dialogue.context_models import SourceKey,ScopeSpec
    entered,release=Event(),Event();now=[0.];settings=replace(runtime_settings,context_enabled=True)
    def held(kwargs):
        entered.set();release.wait(3)
        return dialogue_response('A','Sensei','em','thầy','Thầy giúp em.')(kwargs)
    h=ContextRuntimeHarness(qtbot,settings,[held],clock=lambda:now[0])
    try:
        for at in (0.,.6):now[0]=at;h.observe(OcrResult('A: Sensei help'),at_s=at)
        qtbot.waitUntil(entered.is_set)
        h.coordinator.reset(settings,revision=2,session_id=2,running=True,memory_source=SourceKey('window',(2,)),memory_scopes=(ScopeSpec('legacy-subtitle'),))
        h.overlay.set_mode('subtitle',2);release.set()
        qtbot.waitUntil(lambda:any(e['kind']=='dropped' for e in h.events))
        view=h.coordinator.context_memory.view('legacy-subtitle',now_s=.6)
        assert not view.entities and not view.relations and not view.styles
        assert not h.overlay.text()
    finally:release.set();h.close()

def test_conflicting_address_forms_reach_next_production_prompt(qtbot,runtime_settings):
    now=[0.];settings=replace(runtime_settings,context_enabled=True)
    sources=['A: Sensei, help me please.','A: Sensei, please read this.','A: Sensei, I am not your student; we are colleagues.','A: Sensei, what comes next?']
    responses=[dialogue_response('A','Sensei','em','thầy','Thầy giúp em.'),dialogue_response('A','Sensei','em','thầy','Thầy đọc giúp em.'),dialogue_response('A','Sensei','tôi','bạn','Chúng ta là đồng nghiệp.'),dialogue_response('A','Sensei','tôi','bạn','Tiếp theo là gì?')]
    h=ContextRuntimeHarness(qtbot,settings,responses,clock=lambda:now[0])
    try:
        for index,source in enumerate(sources):
            for offset in (0.,.6,1.2):now[0]=index*3.+offset;h.observe(OcrResult(source),at_s=now[0])
            qtbot.waitUntil(lambda:len(h.calls)==index+1)
            qtbot.waitUntil(lambda:len(h.coordinator.context_memory.view('legacy-subtitle',now_s=now[0]).styles)==min(2,index+1) and any(p.pairs and p.pairs[0].source_text==source for p in h.presented))
        third=json.loads(h.calls[2]['messages'][1]['content'])['context']
        fourth=json.loads(h.calls[3]['messages'][1]['content'])['context']
        assert third['relations'][0]['status']=='supported'
        assert fourth['relations'][0]['status']=='conflicted'
    finally:h.close()
