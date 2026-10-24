"""Geometry-owned block tracks with provider-independent dialogue state."""
from dataclasses import dataclass
from math import hypot
from core.contracts import EngineError
from core.blocks.models import OverlayBlock, OverlayFrame
from core.dialogue.track import DialogueTrack
from core.dialogue.policy import DEFAULT_DIALOGUE_POLICY, identity_text, classify_text

@dataclass
class _LocatedTrack:
    state: DialogueTrack
    rect: object

def _distance(a, b):
    return hypot(a.x+a.width/2-b.x-b.width/2, a.y+a.height/2-b.y-b.height/2)


def _iou(a, b):
    intersection = max(0, min(a.right, b.right)-max(a.x, b.x))*max(0, min(a.bottom, b.bottom)-max(a.y, b.y))
    return intersection / (a.width*a.height+b.width*b.height-intersection)


def _containment(a, b):
    intersection = max(0,min(a.right,b.right)-max(a.x,b.x))*max(0,min(a.bottom,b.bottom)-max(a.y,b.y))
    return intersection/min(a.width*a.height,b.width*b.height)


def _anchor_delta(a, b):
    horizontal = min(abs(a.x-b.x),abs(a.right-b.right),abs(a.x+a.width/2-b.x-b.width/2))
    vertical = min(abs(a.y-b.y),abs(a.bottom-b.bottom),abs(a.y+a.height/2-b.y-b.height/2))
    return horizontal+vertical


class BlockSession:
    def __init__(self, *, policy=DEFAULT_DIALOGUE_POLICY):
        self.policy=policy
        self.reset()

    def reset(self):
        self._tracks={}
        self._next_id=0
        self._revision=None
        self._frame=None
        self._now=0.
        self._errors=[]
        self._oversized={}

    @property
    def active_turns(self):
        return frozenset(k for t in self._tracks.values()
                         if (k:=t.state.active_turn(self._revision)) is not None)

    @property
    def needs_scan(self):
        return any(t.state.has_pending or t.state.missing_count for t in self._tracks.values())

    @property
    def has_pending(self): return self.needs_scan

    def observe(self, blocks, *, settings, revision, frame_id, geometry, now_s):
        if revision!=self._revision:
            self.reset();self._revision=revision
        self._now,self._settings=now_s,settings
        blocks=tuple(sorted((b for b in blocks if b.source_text.strip()),
                            key=lambda b:(b.source_rect.y,b.source_rect.x,b.source_text)))[:32]
        matches,used={},set()
        for phase in ('exact','progressive','spatial'):
            pairs=[]
            for i,b in enumerate(blocks):
                if i in matches: continue
                for key,t in self._tracks.items():
                    if key in used: continue
                    distance=_distance(b.source_rect,t.rect)
                    score=_iou(b.source_rect,t.rect)
                    if phase=='exact':
                        valid=(identity_text(b.source_text)==identity_text(t.state.source_text)
                               and distance<=max(64,4*max(b.source_rect.height,t.rect.height)))
                        rank=(0,distance)
                    elif phase=='progressive':
                        containment=_containment(b.source_rect,t.rect)
                        anchor=_anchor_delta(b.source_rect,t.rect)
                        valid=(classify_text(t.state.source_text,b.source_text) in ('append','regression')
                               and containment>=.60 and anchor<=max(16,b.source_rect.height,t.rect.height))
                        rank=(-containment,anchor)
                    else:
                        valid=score>=.30
                        rank=(-score,distance)
                    if valid:pairs.append((*rank,key,i))
            for _,_,key,i in sorted(pairs):
                if key not in used and i not in matches:
                    matches[i]=key;used.add(key)
        retained={}
        for key,t in self._tracks.items():
            if key not in used and not t.state.miss(now_s=now_s): retained[key]=t
        remaining=32-len(retained)-len(used)
        for i,b in enumerate(blocks):
            key=matches.get(i)
            t=self._tracks.get(key)
            if t is None:
                if remaining<=0: continue
                remaining-=1
                key=self._next_id;self._next_id+=1
                t=_LocatedTrack(DialogueTrack(key,policy=self.policy),b.source_rect)
            t.rect=b.source_rect
            t.state.observe(b.source_text,now_s=now_s)
            retained[key]=t
            version=(t.state.turn_id,t.state.text_version)
            if len(t.state.source_text)>2000 and self._oversized.get(key)!=version:
                self._oversized[key]=version
                self._errors=(self._errors+[EngineError('invalid_input','Khối chữ vượt quá 2000 ký tự.',False)])[-32:]
        self._tracks=retained
        self._oversized={k:v for k,v in self._oversized.items() if k in retained}
        self._frame=OverlayFrame(revision,frame_id,geometry,())
        return self.current_frame()

    def translation_jobs(self, *, now_s=None):
        now_s=self._now if now_s is None else now_s
        return tuple(j for t in self._tracks.values()
                     if now_s-t.state.last_seen_s < self.policy.block_fresh_s
                     and (j:=t.state.job(revision=self._revision,settings=self._settings,now_s=now_s)) is not None)

    def mark_dispatched(self, job, *, now_s):
        t=self._tracks.get(job.block_id)
        if t and job.revision==self._revision:t.state.mark_dispatched(job,now_s=now_s)

    def apply_result(self, result, *, now_s=None):
        self._now=self._now if now_s is None else now_s
        t=self._tracks.get(result.block_id)
        return bool(t and result.revision==self._revision and t.state.apply_result(result,now_s=self._now))

    def tick(self, *, now_s):
        self._now=now_s
        for t in self._tracks.values():t.state.advance(now_s=now_s)

    def current_frame(self):
        if self._frame is None:return None
        f=self._frame
        return OverlayFrame(f.revision,f.frame_id,f.geometry,tuple(
            OverlayBlock(k,t.state.presentation.source_text,t.state.presentation.text,t.rect)
            for k,t in sorted(self._tracks.items(),key=lambda kv:(kv[1].rect.y,kv[1].rect.x,kv[0]))
            if t.state.presentation and self._now-t.state.last_seen_s < self.policy.block_fresh_s))

    def drain_errors(self):
        errors,self._errors=tuple(self._errors),[]
        return errors
