import json
from pathlib import Path
from tools.evaluate_dialogue_context import load_cases,validate_cases,summarize_context_run,main,RequestBudget

CORPUS=Path('tests/fixtures/dialogue/context_cases.json')

def test_corpus_has_required_languages_and_cases():
    cases=load_cases(CORPUS);validate_cases(cases)
    assert len(cases)>=30 and sum(len(c['turns']) for c in cases)>=150
    assert {c['source_lang'] for c in cases}=={'English','Japanese'}

def test_live_rejected_before_loading_keys_without_explicit_flags(monkeypatch):
    monkeypatch.setattr('core.config.load_provider_settings',lambda *a:(_ for _ in ()).throw(AssertionError('credentials touched')))
    assert main(['live','--cases',str(CORPUS)])==2

def test_request_budget_stops_before_next_call():
    budget=RequestBudget(1);budget.consume()
    try:budget.consume()
    except RuntimeError:pass
    else:assert False
    assert budget.used==1

def test_metrics_do_not_invent_missing_timestamps_or_tokens():
    result=summarize_context_run([dict(kind='received',request_key=[1,0,1,1])],[])
    assert result['capture_to_overlay_p95_ms'] is None
    assert result['input_tokens'] is None and result['stable_to_overlay_p95_ms'] is None

def test_scoring_separates_ambiguous_cases():
    report=summarize_context_run([], [dict(ambiguous=True,correct=False),dict(ambiguous=False,correct=True)])
    assert report['quality']['ambiguous']['count']==1
    assert report['quality']['unambiguous']['correct']==1

def test_gold_never_enters_prompt():
    from tools.evaluate_dialogue_context import input_turn
    turn=dict(text='A: hello',lines=['A','hello'],speaker_gold='SECRET',allowed_address_forms=['GOLD'])
    assert 'SECRET' not in json.dumps(input_turn(turn)) and 'GOLD' not in json.dumps(input_turn(turn))

def test_runtime_report_joins_real_stable_selection_and_overlay(qapp,runtime_settings):
    from tools.evaluate_dialogue_context import _run_case
    from types import SimpleNamespace
    case=dict(load_cases(CORPUS)[0]);case['turns']=case['turns'][:1];events=[]
    def create(kwargs,**ignored):
        payload=json.dumps(dict(translation='Xin chào',speaker=None,addressee=None,addressing=None,updates=dict(entities=[],relations=[],terms=[])))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=payload),finish_reason='stop')],usage=None)
    outputs,errors=_run_case(qapp,case,runtime_settings,structured=True,create=create,run=0,events=events)
    assert outputs and not errors
    by_kind={e['kind']:e for e in events}
    assert {'stable','queued','started','received','selected','presented'}<=by_kind.keys()
    assert by_kind['stable']['request_key']==by_kind['presented']['request_key']
    assert by_kind['presented']['stamp']['scope_id']=='legacy-subtitle'
    report=summarize_context_run(events,[])
    assert report['stable_to_overlay_p95_ms'] is not None
    assert report['capture_to_overlay_p95_ms'] is None

def test_retry_and_drop_metrics_are_counted_from_events():
    events=[dict(kind='started',run=0,case='x',variant='context',request_key=[1,0,1,1],wall_s=1.),dict(kind='started',run=0,case='x',variant='context',request_key=[1,0,1,1],wall_s=2.),dict(kind='dropped',request_key=[1,0,1,1])]
    report=summarize_context_run(events,[])
    assert report['retries']==1 and report['dropped']==1

def test_manual_annotations_unblind_variants_and_separate_cohorts(tmp_path):
    from tools.evaluate_dialogue_context import load_annotations
    review=tmp_path/'review.json';key=tmp_path/'key.json'
    review.write_text(json.dumps([dict(case='x',run=0,turn=1,ambiguous=False,context_dependent=True,correct_A=True,correct_B=False,initial_error_A=False,initial_error_B=True,propagated_error_A=False,propagated_error_B=True),dict(case='x',run=0,turn=2,ambiguous=True,context_dependent=False,correct_A=False,correct_B=True)]))
    key.write_text(json.dumps([dict(case='x',run=0,key=dict(A='context',B='baseline'))]))
    annotations=load_annotations(review,key);report=summarize_context_run([],annotations)
    assert report['quality']['by_variant']['context']['context_dependent']['accuracy']==1.
    assert report['quality']['by_variant']['baseline']['ambiguous']['accuracy']==1.
    assert report['quality']['by_variant']['baseline']['propagated_errors']==1

def test_slow_transport_records_actual_dropped_work(qapp,runtime_settings):
    from tools.evaluate_dialogue_context import _run_case
    from types import SimpleNamespace
    import time
    case=dict(load_cases(CORPUS)[0]);case['turns']=case['turns'][:3];events=[]
    def create(kwargs,**ignored):
        time.sleep(.04)
        payload=json.dumps(dict(translation='Dịch '+json.loads(kwargs['messages'][1]['content'])['current_text'],speaker=None,addressee=None,addressing=None,updates=dict(entities=[],relations=[],terms=[])))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=payload),finish_reason='stop')],usage=None)
    _run_case(qapp,case,runtime_settings,structured=True,create=create,run=0,events=events,cadence_ms=5)
    report=summarize_context_run(events,[])
    assert report['dropped']>=1
    assert report['capture_to_overlay_p95_ms'] is None

def test_quality_replay_waits_for_production_retry(qapp,runtime_settings):
    from tools.evaluate_dialogue_context import _run_case
    from types import SimpleNamespace
    from openai import APIConnectionError
    import httpx
    case=dict(load_cases(CORPUS)[0]);case['turns']=case['turns'][:1];events=[];calls=[]
    def create(kwargs,**ignored):
        calls.append(1)
        if len(calls)==1:raise APIConnectionError(request=httpx.Request('POST','https://fake.invalid'))
        payload=json.dumps(dict(translation='Xin chào',speaker=None,addressee=None,addressing=None,updates=dict(entities=[],relations=[],terms=[])))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=payload),finish_reason='stop')],usage=None)
    outputs,errors=_run_case(qapp,case,runtime_settings,structured=True,create=create,run=0,events=events)
    assert len(calls)==2 and outputs
    assert summarize_context_run(events,[])['retries']==1
