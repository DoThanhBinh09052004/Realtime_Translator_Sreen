"""Explicit video diagnostics. Default replay is offline; live requires opt-in."""
import argparse
from dataclasses import asdict, replace
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from core.blocks.models import Rect, ScreenMapping, CaptureGeometry, BlockTranslationResult
from core.contracts import RuntimeSettings, ProviderSettings, OcrResult, OcrSpan, EngineError, TranslationResult
from core.dialogue.models import DialogueObservation
from core.dialogue.coordinator import DialogueCoordinator
from ui.overlay import Overlay

_APP=None


def application():
    global _APP
    _APP=QApplication.instance() or QApplication([])
    return _APP


def geometry(size):
    w,h=size
    rect=Rect(0,0,w,h)
    return CaptureGeometry(rect,ScreenMapping('video',rect,rect),(w,h))


def save_artifacts(out_dir,summary,events):
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    (out_dir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (out_dir/'events.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in events),encoding='utf-8')


def run_replay(transcript_path: Path, *, latency_ms: int, mode: str, out_dir: Path) -> dict:
    if latency_ms<0 or mode not in ('subtitle','blocks','both'):raise ValueError('Invalid replay arguments')
    data=json.loads(Path(transcript_path).read_text(encoding='utf-8'))
    rows=sorted(data['observations'],key=lambda r:r.get('completed_at_s',r.get('t',0)))
    app=application();events=[];oracle=bool(rows) and all('expected_turn' in r for r in rows)
    summary=dict(clears_within_active_turn=0 if oracle else None,
                 shown_closed_turn_results=0 if oracle else None,peak_inflight=0,peak_pending=0,
                 nonempty_shows=0,latency_ms=latency_ms,oracle=oracle,modes={})
    for current_mode in (('subtitle','blocks') if mode=='both' else (mode,)):
        now=[0.];pending={};active=set();flight=None;expected=[None];source_tags={}
        prior=[()];counts=dict(nonempty_shows=0,clears=0,requests=0,cache_hits=0)
        settings=RuntimeSettings('English','Vietnamese',ProviderSettings('OpenAI','offline-replay','',None),300,current_mode)
        c=DialogueCoordinator(clock=lambda:now[0]);o=Overlay()
        # No captured desktop exists: test widget/layout without a native capture-affinity call.
        o.block_overlay._protected=True
        o.set_mode(current_mode,1)
        def pending_changed(jobs,turns,revision):
            active.clear();active.update(turns);pending.clear()
            for j in jobs:pending[(j.revision,j.block_id,j.turn_id)]=j
            summary['peak_pending']=max(summary['peak_pending'],len(pending))
        def show(frame):
            if current_mode=='subtitle':
                o.update_subtitle(frame)
                entries=((frame.source_text,frame.text),) if o.text() else ()
            else:
                o.update_blocks(frame)
                entries=tuple((b.source_text,b.translated_text) for b in frame.blocks)
            if entries and entries!=prior[0]:
                counts['nonempty_shows']+=1
                if oracle:
                    for source,_ in entries:
                        tag=source_tags.get(source)
                        if tag is not None and tag!=expected[0] and (source,_) not in prior[0]:
                            summary['shown_closed_turn_results']+=1
            if prior[0] and not entries:
                counts['clears']+=1
                if oracle and expected[0] is not None:summary['clears_within_active_turn']+=1
            prior[0]=entries
        c.jobs_changed.connect(pending_changed)
        c.subtitle_updated.connect(show);c.blocks_updated.connect(show)
        c.diagnostic_event.connect(lambda e:events.append(dict(e,mode=current_mode)))
        c.reset(settings,revision=1,session_id=1,running=True);c._timer.stop()
        g=geometry(data.get('size',[796,99]));index=0;cache={}
        end=float(data.get('duration_s',rows[-1].get('t',0)))+float(data.get('tail_s',2))
        for step in range(math.ceil(end/.025)+1):
            now[0]=round(step*.025,6)
            while index<len(rows) and rows[index].get('completed_at_s',rows[index].get('t',0))<=now[0]:
                r=rows[index];index+=1;expected[0]=r.get('expected_turn')
                source=' '.join(r['text'].split());source_tags[source]=expected[0]
                spans=tuple(OcrSpan(s['text'],tuple(tuple(p) for p in s['polygon']),s['confidence']) for s in r.get('spans',[]))
                if source and 'spans' not in r:spans=(OcrSpan(source,((10,10),(700,10),(700,30),(10,30)),.99),)
                error=EngineError(**r['error']) if r.get('error') else None
                c.observe(DialogueObservation(1,index,r.get('captured_at_s',r.get('t',0)),
                            r.get('completed_at_s',r.get('t',0)),settings,OcrResult(source,error,spans),g))
            c.tick()
            # Minimal fake transport: one scheduled completion, no dialogue classification here.
            if flight and flight[0]<=now[0]:
                _,j,cached=flight;flight=None
                value=cache.setdefault(j.source_text,'Dịch: '+j.source_text)
                c.on_result(BlockTranslationResult(j.revision,j.block_id,j.source_text,
                            TranslationResult(value,from_cache=cached),j.turn_id,j.text_version))
            if flight is None and pending:
                token,j=next(iter(pending.items()));pending.pop(token)
                if token in active:
                    cached=j.source_text in cache
                    c.on_job_started(j)
                    flight=(now[0]+(0 if cached else latency_ms/1000),j,cached)
                    counts['requests']+=not cached;counts['cache_hits']+=cached
                    summary['peak_inflight']=1
                    events.append(dict(kind='request',t=now[0],mode=current_mode,request_key=j.request_key,from_cache=cached))
        summary['nonempty_shows']+=counts['nonempty_shows'];summary['modes'][current_mode]=counts
        c.reset(settings,revision=2,session_id=2,running=False)
        c.deleteLater();o.close();o.deleteLater();app.processEvents()
    summary['method']='production coordinator + offscreen Overlay; fake scheduled translation; native capture exclusion unmeasured'
    save_artifacts(out_dir,summary,events)
    return summary


def clip_info(video):
    import cv2
    cap=cv2.VideoCapture(str(video))
    if not cap.isOpened():raise ValueError('Cannot open video')
    fps=cap.get(cv2.CAP_PROP_FPS)
    if fps<=0:cap.release();raise ValueError('Invalid video FPS')
    reported=cap.get(cv2.CAP_PROP_FRAME_COUNT)/fps
    cap.set(cv2.CAP_PROP_POS_MSEC,reported*1000);ok,_=cap.read()
    decoded=cap.get(cv2.CAP_PROP_POS_FRAMES)/fps
    duration=decoded if not ok and 0<decoded<=reported else reported
    cap.release()
    return dict(metadata_duration_s=reported,decoded_duration_s=duration,fps=fps)


def crop_frame(frame,crop,size):
    import cv2
    h,w=frame.shape[:2];x1,y1,x2,y2=crop
    return cv2.resize(frame[int(h*y1):int(h*y2),int(w*x1):int(w*x2)],tuple(size))


def record_video(video, *, crop, size, out_dir):
    import cv2
    from engines.ocr import ocr_image, release_ocr_engine
    info=clip_info(video);cap=cv2.VideoCapture(str(video));rows=[];t=0.
    started=time.perf_counter()
    cap.set(cv2.CAP_PROP_POS_MSEC,0);ok,first=cap.read()
    if not ok:cap.release();raise ValueError('No decodable frames')
    ocr_image(cv2.cvtColor(crop_frame(first,crop,size),cv2.COLOR_BGR2GRAY),lang='en')
    warm=time.perf_counter()-started
    try:
        while t<info['decoded_duration_s']:
            started=time.perf_counter()
            cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=cap.read()
            if not ok:break
            result=ocr_image(cv2.cvtColor(crop_frame(frame,crop,size),cv2.COLOR_BGR2GRAY),lang='en')
            elapsed=time.perf_counter()-started
            rows.append(dict(captured_at_s=t,completed_at_s=t+elapsed,text=result.text,
                             spans=[asdict(s) for s in result.spans],error=asdict(result.error) if result.error else None))
            t+=max(.3,elapsed)
    finally:cap.release();release_ocr_engine()
    payload=dict(video=str(video),size=size,crop=crop,duration_s=info['decoded_duration_s'],tail_s=2,
                 warm_s=warm,metadata=info,observations=rows,method='offline real OCR, serial capture timestamps; no player UI')
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    path=out_dir/'transcript.json';path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    return path


def run_live(video, *, provider, mode, crop, size, out_dir):
    import cv2
    import core.worker as module
    from core import config
    from core.google_recovery import GoogleRecoveryGate
    app=application();info=clip_info(video);events=[];gate=GoogleRecoveryGate()
    settings=config.load_provider_settings(provider)
    # The opt-in selects a provider explicitly; no active-provider settings are saved.
    for current_mode in (('subtitle','blocks') if mode=='both' else (mode,)):
        epoch=[0.]
        class Capture:
            def __enter__(self):self.cap=cv2.VideoCapture(str(video));epoch[0]=time.monotonic();return self
            def __exit__(self,*args):self.cap.release()
            def grab(self,region):
                t=min(time.monotonic()-epoch[0],max(0,info['decoded_duration_s']-.15))
                self.cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=self.cap.read()
                if not ok:raise ValueError('Video EOF')
                return cv2.cvtColor(crop_frame(frame,crop,size),cv2.COLOR_BGR2BGRA)
        original=module.mss.mss;module.mss.mss=Capture
        w=module.TranslationWorker(config.State(),dict(left=0,top=0,width=size[0],height=size[1]))
        o=Overlay();o.block_overlay._protected=True
        w._google_recovery=gate;w._block_translator.google_recovery=gate
        w.revision_changed.connect(lambda r:o.set_mode(current_mode,r))
        w.subtitle_updated.connect(o.update_subtitle);w.blocks_updated.connect(o.update_blocks)
        w._coordinator.diagnostic_event.connect(lambda e:events.append(dict(e,mode=current_mode)))
        w.error_occurred.connect(lambda e:events.append(dict(kind='error',code=e.code)))
        w.configure(RuntimeSettings('English','Vietnamese',settings,300,current_mode));w.set_capture_geometry(geometry(size))
        stop_timer=QTimer(w);stop_timer.setSingleShot(True)
        stop_timer.timeout.connect(w.stop_worker)
        w.shutdown_finished.connect(app.quit)
        try:
            w.start_worker();stop_timer.start(round((info['decoded_duration_s']+2)*1000));app.exec_()
        finally:
            stop_timer.stop();w.shutdown_finished.disconnect(app.quit)
            if w.isRunning() or w._block_translator.isRunning():
                w.stop_worker()
                while w.isRunning() or w._block_translator.isRunning():
                    app.processEvents();time.sleep(.01)
            o.close();module.mss.mss=original
    summary=dict(provider=provider,mode=mode,metadata=info,tail_s=2,events=len(events),
                 nonempty_shows=sum(e.get('kind')=='shown' for e in events),
                 errors=sum(e.get('kind')=='error' for e in events),
                 method='real video OCR + selected network provider; Qt offscreen; native capture exclusion unmeasured')
    save_artifacts(out_dir,summary,events)
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('record','replay','live'):
        p=sub.add_parser(command);p.add_argument('--out',required=True,type=Path)
        if command=='replay':
            p.add_argument('--transcript',required=True,type=Path);p.add_argument('--latency-ms',type=int,default=700)
        else:
            p.add_argument('--video',required=True,type=Path)
            p.add_argument('--crop',type=float,nargs=4,default=[.20,.75,.80,.89]);p.add_argument('--size',type=int,nargs=2,default=[796,99])
        if command!='record':p.add_argument('--mode',choices=['subtitle','blocks','both'],default='both' if command=='replay' else 'subtitle')
        if command=='live':p.add_argument('--provider');p.add_argument('--allow-network',action='store_true')
    args=parser.parse_args(argv)
    if args.command=='live':
        from core.config import PROVIDERS
        if not args.allow_network or args.provider not in PROVIDERS:
            print('Live requires an explicit valid --provider and --allow-network.',file=sys.stderr);return 2
    if args.command!='replay':
        x1,y1,x2,y2=args.crop
        if not (0<=x1<x2<=1 and 0<=y1<y2<=1 and all(0<n<=8192 for n in args.size)):return 2
    try:
        if args.command=='record':
            result={'transcript':str(record_video(args.video,crop=args.crop,size=args.size,out_dir=args.out))}
        elif args.command=='replay':result=run_replay(args.transcript,latency_ms=args.latency_ms,mode=args.mode,out_dir=args.out)
        else:result=run_live(args.video,provider=args.provider,mode=args.mode,crop=args.crop,size=args.size,out_dir=args.out)
    except Exception as exc:
        print('Diagnostic failed: '+type(exc).__name__,file=sys.stderr);return 1
    print(json.dumps(result,ensure_ascii=True))
    return 1 if args.command=='live' and not result['nonempty_shows'] else 0


if __name__=='__main__':raise SystemExit(main())
