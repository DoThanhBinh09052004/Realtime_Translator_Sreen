"""Opt-in diagnostic replay. Offline is fake transport, never a quality benchmark.

Examples: python -m tools.evaluate_dialogue_context offline --output scratch/context-eval
Live additionally requires --provider --model --allow-network --max-requests.
Never pass keys on the command line. Gold annotations never enter model input.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import random
import sys
import time

DEFAULT_CASES=Path(__file__).resolve().parents[1]/'tests/fixtures/dialogue/context_cases.json'

def load_cases(path):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema_version')!=1:raise ValueError('Unsupported corpus schema')
    cases=tuple(data['cases']);validate_cases(cases);return cases

def validate_cases(cases):
    ids=set()
    for case in cases:
        if not isinstance(case,dict) or case['id'] in ids or case['source_lang'] not in ('English','Japanese') or case['target_lang']!='Vietnamese' or type(case['ambiguous']) is not bool or not case['turns']:
            raise ValueError('Invalid dialogue case')
        ids.add(case['id'])
        for turn in case['turns']:
            if not isinstance(turn['text'],str) or not 0<len(turn['text'])<=2000 or type(turn['lines']) is not list or not all(isinstance(line,str) for line in turn['lines']):raise ValueError('Invalid source turn')
            if 'speaker_gold' not in turn or 'addressee_gold' not in turn or type(turn['allowed_address_forms']) is not list:raise ValueError('Missing gold annotations')

def input_turn(turn):
    return dict(text=turn['text'],lines=list(turn['lines']))

def load_annotations(review_path,key_path):
    rows=json.loads(Path(review_path).read_text(encoding='utf-8'))
    keys={(k['case'],k['run']):k['key'] for k in json.loads(Path(key_path).read_text(encoding='utf-8'))}
    annotations=[]
    for row in rows:
        key=keys[row['case'],row['run']]
        for blind in ('A','B'):
            correct=row.get(f'correct_{blind}')
            if correct is not None and type(correct) is not bool:raise ValueError('Manual correctness must be bool or null')
            annotations.append(dict(case=row['case'],run=row['run'],turn=row['turn'],variant=key[blind],correct=correct,
                ambiguous=row['ambiguous'],context_dependent=row['context_dependent'],
                initial_error=row.get(f'initial_error_{blind}'),propagated_error=row.get(f'propagated_error_{blind}')))
    return annotations

class RequestBudget:
    def __init__(self,maximum):
        if type(maximum) is not int or maximum<1:raise ValueError('Positive request ceiling required')
        self.maximum,self.used=maximum,0
    def consume(self):
        if self.used>=self.maximum:raise RuntimeError('Request ceiling reached before next API call')
        self.used+=1

def _percentile(values,fraction):
    if not values:return None
    values=sorted(values);return values[min(len(values)-1,int((len(values)-1)*fraction))]

def summarize_context_run(events,annotations):
    grouped={}; tokens_in=[];tokens_out=[];starts={};retries=0;relation_states={};queued=set()
    counts={kind:sum(e.get('kind')==kind for e in events) for kind in ('request','cache','retry','dropped','schema_error')}
    for event in events:
        key=(event.get('run'),event.get('case'),event.get('variant'),tuple(event.get('request_key') or ()))
        row=grouped.setdefault(key,{})
        if event.get('kind')=='queued':queued.add(key)
        if event.get('kind')=='started':
            retries+=key in starts;starts[key]=True
        if type(event.get('wall_s')) in (float,int):row[event.get('kind')]=event['wall_s']
        if event.get('kind')=='selected' and 'candidate_relations' in event:
            relation_states[(event.get('run'),event.get('case'),event.get('variant'),event.get('scope_id'))]={name:event.get(name,0) for name in ('candidate_relations','supported_relations','conflicted_relations')}
        for name,values in (('input_tokens',tokens_in),('output_tokens',tokens_out)):
            if type(event.get(name)) is int:values.append(event[name])
    def durations(start,end):return [1000*(r[end]-r[start]) for r in grouped.values() if start in r and end in r and r[end]>=r[start]]
    quality={}
    for label,ambiguous in (('ambiguous',True),('unambiguous',False)):
        rows=[a for a in annotations if a.get('ambiguous') is ambiguous and type(a.get('correct')) is bool]
        quality[label]=dict(count=len(rows),correct=sum(a['correct'] for a in rows),accuracy=sum(a['correct'] for a in rows)/len(rows) if rows else None)
    quality['by_variant']={}
    for variant in ('baseline','context'):
        selected=[a for a in annotations if a.get('variant')==variant]
        result={}
        for cohort,predicate in (('all',lambda a:True),('ambiguous',lambda a:a.get('ambiguous') is True),('unambiguous',lambda a:a.get('ambiguous') is False),('context_dependent',lambda a:a.get('context_dependent') is True),('independent',lambda a:a.get('context_dependent') is False)):
            rows=[a for a in selected if predicate(a) and type(a.get('correct')) is bool]
            result[cohort]=dict(count=len(rows),correct=sum(a['correct'] for a in rows),accuracy=sum(a['correct'] for a in rows)/len(rows) if rows else None)
        for field in ('initial_error','propagated_error'):
            scored=[a for a in selected if type(a.get(field)) is bool]
            result[field+'s']=sum(a[field] for a in scored) if scored else None
        quality['by_variant'][variant]=result
    return dict(request_count=counts['request'],cache_hits=counts['cache'],retries=max(retries,counts['retry']),dropped=counts['dropped'],schema_errors=counts['schema_error'],
                input_tokens=sum(tokens_in) if tokens_in else None,output_tokens=sum(tokens_out) if tokens_out else None,
                request_latency_p50_ms=_percentile(durations('started','received'),.5),request_latency_p95_ms=_percentile(durations('started','received'),.95),
                stable_to_overlay_p50_ms=_percentile(durations('stable','presented'),.5),stable_to_overlay_p95_ms=_percentile(durations('stable','presented'),.95),
                capture_to_overlay_p95_ms=_percentile(durations('captured','presented'),.95),queued_not_started=len(queued-starts.keys()),
                final_relation_states={name:sum(s[name] for s in relation_states.values()) for name in ('candidate_relations','supported_relations','conflicted_relations')} if relation_states else None,quality=quality)

def _run_case(app,case,settings,*,structured,create,run,events,cadence_ms=None,client_factory=None):
    """Real production session, bounded queue, service and overlay; transcript OCR only."""
    from types import SimpleNamespace
    from unittest.mock import patch
    from PyQt5.QtCore import Qt,QThread
    from core.dialogue.coordinator import DialogueCoordinator
    from core.dialogue.context_models import SourceKey,ScopeSpec
    from core.dialogue.models import DialogueObservation
    from core.blocks.translation_worker import BlockTranslationWorker
    from core.contracts import OcrResult,OcrSpan
    from ui.overlay import Overlay
    settings=replace(settings,context_enabled=structured)
    now=[time.monotonic()];calls=[];outputs=[];errors=[];pending={};selected=[None];completed=[]
    coordinator=DialogueCoordinator(clock=lambda:now[0]);overlay=Overlay();overlay.set_mode('subtitle',1)
    variant='context' if structured else 'baseline'
    def record(kind,key=None,**data):
        events.append(dict(kind=kind,run=run,case=case['id'],variant=variant,request_key=key,**data))
    def transport(**kwargs):
        calls.append(kwargs);return create(kwargs,structured=structured)
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=transport)),close=lambda:None)
    def result_ready(result):
        record('usage',result.request_key,input_tokens=result.result.input_tokens,output_tokens=result.result.output_tokens)
        if result.result.from_cache:record('cache',result.request_key)
        if result.result.error:
            errors.append(result.result.error.code)
            record('schema_error' if result.result.error.code=='invalid_response' else 'error',result.request_key)
        if result.result.error is None or not result.result.error.retryable or worker._token(result) in worker._exhausted:
            completed.append(result.request_key)
        coordinator.on_result(result)
    def presented(frame):
        overlay.update_subtitle(frame)
        if frame.text:outputs.append(dict(source=frame.source_text,translation=frame.text))
    def started(job):
        coordinator.on_job_started(job)
    def diagnostic(event):
        data={k:v for k,v in event.items() if k not in ('kind','request_key','t','revision','captured_at_s')}
        # Captured times in this transcript are synthetic. Only actual GUI signal arrival is timed.
        record(event['kind'],event.get('request_key'),wall_s=time.perf_counter(),**data)
        if event['kind']=='selected':selected[0]=event
    def overlay_presented(presentation):
        if presentation.pairs and selected[0] is not None:
            event=selected[0]
            record('presented',event['request_key'],wall_s=time.perf_counter(),source_id=event.get('source_id'),stamp=event.get('stamp'))
    coordinator.diagnostic_event.connect(diagnostic)
    overlay.translation_presented.connect(overlay_presented)
    coordinator.subtitle_updated.connect(presented)
    worker=BlockTranslationWorker(clock=lambda:now[0])
    worker.diagnostic_event.connect(diagnostic,Qt.QueuedConnection)
    coordinator.jobs_changed.connect(worker.replace_pending)
    worker.job_started.connect(started,Qt.QueuedConnection)
    worker.result_ready.connect(result_ready,Qt.QueuedConnection)
    coordinator.reset(settings,revision=1,session_id=1,running=True,memory_source=SourceKey('window',(1,)),memory_scopes=(ScopeSpec('legacy-subtitle'),))
    def pump_until(predicate,timeout=35.):
        end=time.monotonic()+timeout
        logical,wall=now[0],time.monotonic()
        while not predicate():
            now[0]=logical+time.monotonic()-wall
            app.processEvents();QThread.msleep(1)
            if time.monotonic()>end:raise RuntimeError('Replay timed out waiting for production queue')
    try:
        with patch('engines.translator.OpenAI',client_factory or (lambda **kw:client)):
            worker.start();scan=0
            for index,turn in enumerate(case['turns']):
                original=input_turn(turn);spans=tuple(OcrSpan(line,((0.,i*20.),(200.,i*20.),(200.,i*20.+15.),(0.,i*20.+15.)),1.) for i,line in enumerate(original['lines']))
                before=len(completed)
                base=max(now[0]+.01,index*3.)
                for offset in (0.,.6,1.2):
                    now[0]=base+offset;scan+=1
                    coordinator.observe(DialogueObservation(1,scan,now[0],now[0],settings,OcrResult(original['text'],spans=spans),None))
                    app.processEvents()
                if cadence_ms is None:pump_until(lambda:len(completed)>before)
                else:
                    end=time.monotonic()+cadence_ms/1000.
                    while time.monotonic()<end:app.processEvents();QThread.msleep(1)
            if cadence_ms is not None:
                pump_until(lambda:worker.pending_count==0 and worker._inflight is None)
                app.processEvents()
    finally:
        coordinator._timer.stop();worker.request_stop();worker.wait(12000);overlay.close()
    return outputs,errors

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('offline','live','score'),nargs='?',default='offline')
    parser.add_argument('--cases',type=Path,default=DEFAULT_CASES)
    parser.add_argument('--output',type=Path,default=Path('scratch/context-evaluation'))
    parser.add_argument('--provider');parser.add_argument('--model');parser.add_argument('--allow-network',action='store_true');parser.add_argument('--max-requests',type=int)
    parser.add_argument('--runs',type=int,default=1);parser.add_argument('--limit-cases',type=int);parser.add_argument('--cadence-ms',type=int)
    parser.add_argument('--annotations',type=Path);parser.add_argument('--review-key',type=Path)
    args=parser.parse_args(argv)
    if args.mode=='live' and (not args.provider or not args.model or not args.allow_network or not args.max_requests or args.max_requests<1):
        print('Live requires explicit provider, model, --allow-network and positive --max-requests. Agree a budget before running.',file=sys.stderr);return 2
    if args.runs<1 or args.limit_cases is not None and args.limit_cases<1 or args.cadence_ms is not None and args.cadence_ms<1:return 2
    # Restrict output to diagnostic scratch; never overwrite config or other user files.
    root=Path(__file__).resolve().parents[1]/'scratch'
    output=args.output.resolve()
    if not output.is_relative_to(root.resolve()):print('Output must be inside project scratch/',file=sys.stderr);return 2
    if args.mode=='score':
        annotations=load_annotations(args.annotations or output/'review-pairs.json',args.review_key or output/'review-key.json')
        events=[json.loads(line) for line in (output/'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        report=summarize_context_run(events,annotations)
        report.update(manual_annotations=sum(type(a['correct']) is bool for a in annotations),quality_verified=False,
                      note='Human annotation counts only. Review cohort sizes, uncertainty, provider and live timing before deciding the release gate.')
        (output/'scored-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False));return 0
    cases=load_cases(args.cases)
    if args.limit_cases:cases=cases[:args.limit_cases]
    from core.contracts import ProviderSettings,RuntimeSettings
    events=[];budget=RequestBudget(args.max_requests or max(1,sum(len(c['turns']) for c in cases)*2*args.runs))
    client_factory=None
    if args.mode=='live':
        from core.config import load_provider_settings,PROVIDERS
        if args.provider not in PROVIDERS or args.provider=='Google Translate':return 2
        provider=replace(load_provider_settings(args.provider),model_id=args.model)
        # The real TranslationService creates, uses and closes this SDK on its one worker thread.
        from engines.translator import OpenAI
        def client_factory(**kwargs):
            client=OpenAI(**kwargs);original=client.chat.completions.create
            def counted(**request):
                budget.consume();events.append(dict(kind='request'))
                return original(**request)
            client.chat.completions.create=counted
            return client
    else:provider=ProviderSettings('OpenAI','offline-fake','offline-only',None)
    def create(kwargs,*,structured):
        from types import SimpleNamespace
        budget.consume();events.append(dict(kind='request'))
        if structured:
            source=json.loads(kwargs['messages'][1]['content'])['current_text']
            text=json.dumps(dict(translation='[FAKE] '+source,speaker=None,addressee=None,addressing=None,updates=dict(entities=[],relations=[],terms=[])),ensure_ascii=False)
        else:text='[FAKE] '+kwargs['messages'][1]['content'].split('\n\n',1)[-1]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text),finish_reason='stop')],usage=None)
    from PyQt5.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    pairs=[];failure=None
    try:
        for run in range(args.runs):
            for index,case in enumerate(cases):
                variants=(False,True) if (run+index)%2==0 else (True,False)
                results={}
                for variant in variants:
                    settings=RuntimeSettings(case['source_lang'],case['target_lang'],provider,500,context_enabled=variant)
                    results['context' if variant else 'baseline']=_run_case(app,case,settings,structured=variant,create=create,run=run,events=events,cadence_ms=args.cadence_ms,client_factory=client_factory)
                    if budget.used>=budget.maximum:break
                blind=['baseline','context'];random.Random(f'{run}-{case["id"]}').shuffle(blind)
                variants_key=dict(A=blind[0],B=blind[1])
                remaining={variant:list(results.get(variant,([],[]))[0]) for variant in ('baseline','context')}
                for turn_index,turn in enumerate(case['turns']):
                    translations={}
                    for variant in ('baseline','context'):
                        match=next((item for item in remaining[variant] if item['source']==turn['text']),None)
                        translations[variant]=match['translation'] if match else None
                        if match:remaining[variant].remove(match)
                    pairs.append(dict(case=case['id'],run=run,turn=turn_index+1,source=turn['text'],category=case['category'],ambiguous=case['ambiguous'],
                        context_dependent=turn.get('context_dependent',case['category']!='independent'),A=translations[blind[0]],B=translations[blind[1]],
                        correct_A=None,correct_B=None,initial_error_A=None,initial_error_B=None,propagated_error_A=None,propagated_error_B=None,variant_key=variants_key))
                if budget.used>=budget.maximum:break
            if budget.used>=budget.maximum:break
    except RuntimeError as exc:failure=str(exc)
    summary=summarize_context_run(events,[])
    summary.update(transport='fake' if args.mode=='offline' else 'live',quality_verified=False,requests_used=budget.used,request_ceiling=budget.maximum,
                   timing_note='Transcript uses logical OCR observation times. Stable signal arrival to real overlay presentation and request wall times measured; capture-to-overlay unavailable.',
                   budget_note='Request ceiling is not a monetary cap; provider usage/thinking may be unavailable.',failure=failure,
                   acceptance=dict(context_dependent_gain_pp=15,baseline_above_85_requires_half_errors=True,independent_loss_max_pp=3,stable_overlay_p95_increase_max_percent=20,extra_success_requests=0))
    output.mkdir(parents=True,exist_ok=True)
    (output/'events.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in events),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    # Keep variant keys separate from the human review sheet.
    keys=[];seen_keys=set()
    for p in pairs:
        key=p.pop('variant_key');identity=(p['case'],p['run'])
        if identity not in seen_keys:keys.append(dict(case=p['case'],run=p['run'],key=key));seen_keys.add(identity)
    (output/'review-pairs.json').write_text(json.dumps(pairs,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'review-key.json').write_text(json.dumps(keys,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False));return 1 if failure else 0

if __name__=='__main__':raise SystemExit(main())
