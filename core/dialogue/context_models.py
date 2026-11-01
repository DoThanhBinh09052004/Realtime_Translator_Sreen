"""Bounded immutable dialogue values shared with the SDK thread (stdlib only)."""
from dataclasses import dataclass
from math import isfinite
from typing import Literal

CONTEXT_SCHEMA_VERSION = 1

@dataclass(frozen=True)
class ContextPolicy:
    history: int = 8
    entities: int = 32
    relations: int = 64
    terms: int = 64
    selected: int = 8
    styles: int = 2
    context_bytes: int = 6144
    scene_idle_s: float = 120.
    aliases: int = 4
    evidence: int = 2
    updates: int = 2
    lines: int = 32
    def __post_init__(self):
        for name,maximum in (('history',8),('entities',32),('relations',64),('terms',64),('selected',8),('styles',2),('context_bytes',6144),('aliases',4),('evidence',2),('updates',2),('lines',32)):
            value=getattr(self,name)
            if type(value) is not int or not 1<=value<=maximum:raise ValueError('Invalid context policy bound')
        if type(self.scene_idle_s) not in (int,float) or not isfinite(self.scene_idle_s) or self.scene_idle_s<=0:raise ValueError('Invalid scene timeout')

@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float = 0.
    is_label_candidate: bool = False
    def __post_init__(self):
        if not isinstance(self.text,str) or len(self.text)>2000 or not isfinite(self.confidence) or not 0<=self.confidence<=1:
            raise ValueError('Invalid OCR line')

@dataclass(frozen=True)
class OcrEvidence:
    lines: tuple[OcrLine,...] = ()
    def __post_init__(self):
        if type(self.lines) is not tuple or len(self.lines)>32 or any(not isinstance(x,OcrLine) for x in self.lines) or sum(len(x.text) for x in self.lines)>2000:
            raise ValueError('Invalid OCR evidence')

@dataclass(frozen=True)
class StableTurn:
    revision: int
    track_id: int
    turn_id: int
    text_version: int
    source_text: str
    evidence: OcrEvidence
    captured_at_s: float
    stable_at_s: float
    def __post_init__(self):
        if any(type(v) is not int or v<0 for v in (self.revision,self.track_id)) or any(type(v) is not int or v<1 for v in (self.turn_id,self.text_version)):
            raise ValueError('Invalid turn identity')
        _text(self.source_text,2000)
        if not isinstance(self.evidence,OcrEvidence) or not all(type(v) in (int,float) and isfinite(v) for v in (self.captured_at_s,self.stable_at_s)) or self.captured_at_s>self.stable_at_s:
            raise ValueError('Invalid stable observation')

@dataclass(frozen=True)
class SourceTurn:
    source_id: int
    text_version: int
    source_text: str
    evidence: OcrEvidence
    captured_at_s: float
    stable_at_s: float
    def __post_init__(self):
        _text(self.source_text,2000)
        if type(self.source_id) is not int or self.source_id<1 or type(self.text_version) is not int or self.text_version<1 or not isinstance(self.evidence,OcrEvidence) or not all(isfinite(x) for x in (self.captured_at_s,self.stable_at_s)):
            raise ValueError('Invalid source turn')

@dataclass(frozen=True)
class EvidenceRef:
    source_id: int
    quote: str
    def __post_init__(self):
        if type(self.source_id) is not int or self.source_id<1 or not isinstance(self.quote,str) or not 0<len(self.quote)<=160:
            raise ValueError('Invalid evidence reference')

def _tuple(value, kind, limit):
    if type(value) is not tuple or len(value)>limit or any(not isinstance(x,kind) for x in value):
        raise ValueError('Invalid immutable collection')

def _text(value, limit, *, empty=False):
    if not isinstance(value,str) or len(value)>limit or (not empty and not value.strip()): raise ValueError('Invalid metadata text')

@dataclass(frozen=True)
class EntityRecord:
    entity_id: str
    name: str
    aliases: tuple[str,...] = ()
    evidence: tuple[EvidenceRef,...] = ()
    def __post_init__(self):
        _text(self.entity_id,80); _text(self.name,80); _tuple(self.aliases,str,4); _tuple(self.evidence,EvidenceRef,2)
        for alias in self.aliases: _text(alias,80)

@dataclass(frozen=True)
class RelationRecord:
    speaker_id: str
    addressee_id: str
    self_form: str
    other_form: str
    status: Literal['candidate','supported','conflicted'] = 'candidate'
    evidence: tuple[EvidenceRef,...] = ()
    def __post_init__(self):
        _text(self.speaker_id,80); _text(self.addressee_id,80); _text(self.self_form,40,empty=True); _text(self.other_form,40,empty=True); _tuple(self.evidence,EvidenceRef,2)
        if self.status not in ('candidate','supported','conflicted'): raise ValueError('Invalid relation status')

@dataclass(frozen=True)
class TermRecord:
    source: str
    target: str
    evidence: tuple[EvidenceRef,...] = ()
    def __post_init__(self):
        _text(self.source,160); _text(self.target,160); _tuple(self.evidence,EvidenceRef,2)

@dataclass(frozen=True)
class StyleSample:
    source_id: int
    source_text: str
    translated_text: str
    def __post_init__(self):
        if type(self.source_id) is not int or self.source_id<1:raise ValueError('Invalid style source')
        _text(self.source_text,2000)
        if not isinstance(self.translated_text,str):raise ValueError('Invalid style translation')

@dataclass(frozen=True)
class MemoryView:
    epoch: int
    scope_id: str
    turns: tuple[SourceTurn,...] = ()
    entities: tuple[EntityRecord,...] = ()
    relations: tuple[RelationRecord,...] = ()
    terms: tuple[TermRecord,...] = ()
    styles: tuple[StyleSample,...] = ()
    def __post_init__(self):
        _text(self.scope_id,160)
        if type(self.epoch) is not int or self.epoch<0:raise ValueError('Invalid memory epoch')
        for value,kind,limit in ((self.turns,SourceTurn,8),(self.entities,EntityRecord,32),(self.relations,RelationRecord,64),(self.terms,TermRecord,64),(self.styles,StyleSample,2)): _tuple(value,kind,limit)

@dataclass(frozen=True)
class ContextStamp:
    memory_epoch: int
    scope_id: str
    snapshot_digest: str
    def __post_init__(self):
        if type(self.memory_epoch) is not int or self.memory_epoch<0:raise ValueError('Invalid memory epoch')
        _text(self.scope_id,160);_text(self.snapshot_digest,64)

@dataclass(frozen=True)
class ContextSnapshot:
    stamp: ContextStamp
    current: SourceTurn
    history: tuple[SourceTurn,...] = ()
    entities: tuple[EntityRecord,...] = ()
    relations: tuple[RelationRecord,...] = ()
    terms: tuple[TermRecord,...] = ()
    styles: tuple[StyleSample,...] = ()
    context_json: str = '{}'
    def __post_init__(self):
        if not isinstance(self.stamp,ContextStamp) or not isinstance(self.current,SourceTurn):raise ValueError('Invalid context snapshot')
        for value,kind,limit in ((self.history,SourceTurn,8),(self.entities,EntityRecord,8),(self.relations,RelationRecord,8),(self.terms,TermRecord,8),(self.styles,StyleSample,2)): _tuple(value,kind,limit)
        if len(self.context_json.encode('utf-8'))>6144: raise ValueError('Context budget exceeded')

@dataclass(frozen=True)
class MemoryDelta:
    entities: tuple[EntityRecord,...] = ()
    relations: tuple[RelationRecord,...] = ()
    terms: tuple[TermRecord,...] = ()
    def __post_init__(self):
        _tuple(self.entities,EntityRecord,2); _tuple(self.relations,RelationRecord,2); _tuple(self.terms,TermRecord,2)

@dataclass(frozen=True)
class ContextOutcome:
    stamp: ContextStamp
    speaker_id: str | None = None
    addressee_id: str | None = None
    self_form: str | None = None
    other_form: str | None = None
    delta: MemoryDelta | None = None
    mode: Literal['structured','text'] = 'structured'
    degraded: bool = False
    def __post_init__(self):
        if not isinstance(self.stamp,ContextStamp) or self.delta is not None and not isinstance(self.delta,MemoryDelta) or self.mode not in ('structured','text') or type(self.degraded) is not bool:
            raise ValueError('Invalid context outcome')
        for value,limit in ((self.speaker_id,80),(self.addressee_id,80),(self.self_form,40),(self.other_form,40)):
            if value is not None:_text(value,limit,empty=True)

@dataclass(frozen=True)
class PresentationReceipt:
    request_key: tuple[int,int,int,int]
    source_text: str
    translated_text: str
    context: ContextOutcome | None = None
    def __post_init__(self):
        _tuple(self.request_key,int,4)
        if len(self.request_key)!=4 or any(type(v) is not int or v<0 for v in self.request_key):raise ValueError('Invalid receipt identity')
        _text(self.source_text,2000)
        if not isinstance(self.translated_text,str) or self.context is not None and not isinstance(self.context,ContextOutcome):raise ValueError('Invalid presentation receipt')

@dataclass(frozen=True)
class SourceKey:
    kind: str
    identity: tuple[str | int,...]
    def __post_init__(self):
        _text(self.kind,40);_tuple(self.identity,(str,int),16)

@dataclass(frozen=True)
class ScopeSpec:
    scope_id: str
    layout_key: tuple[float | str,...] = ()
    def __post_init__(self):
        _text(self.scope_id,160);_tuple(self.layout_key,(float,int,str),32)
        if any(not isfinite(v) for v in self.layout_key if type(v) in (int,float)):raise ValueError('Invalid scope geometry')

@dataclass(frozen=True)
class ContextStatus:
    phase: Literal['off','active','unsupported','text_fallback']
    revision: int
    def __post_init__(self):
        if self.phase not in ('off','active','unsupported','text_fallback') or type(self.revision) is not int or self.revision<0:raise ValueError('Invalid context status')
