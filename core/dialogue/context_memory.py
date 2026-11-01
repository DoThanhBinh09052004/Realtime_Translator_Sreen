"""GUI-owned bounded, source-evidence-backed hypotheses. No I/O or model calls."""
from collections import OrderedDict
from dataclasses import dataclass, field, replace
import hashlib
import unicodedata
from core.dialogue.context_models import *

def fingerprint(text):
    return hashlib.sha256(' '.join(unicodedata.normalize('NFC',text).split()).encode()).hexdigest()

@dataclass
class _Scope:
    epoch: int
    layout: tuple
    seen: float
    routes: OrderedDict = field(default_factory=OrderedDict)
    turns: OrderedDict = field(default_factory=OrderedDict)
    entities: OrderedDict = field(default_factory=OrderedDict)
    relations: OrderedDict = field(default_factory=OrderedDict)
    terms: OrderedDict = field(default_factory=OrderedDict)
    styles: OrderedDict = field(default_factory=OrderedDict)
    receipts: OrderedDict = field(default_factory=OrderedDict)
    proofs: dict = field(default_factory=dict)

class DialogueMemory:
    def __init__(self, *, policy=ContextPolicy()):
        self.policy=policy; self._scopes={}; self._source=None; self._settings=None
        self._epoch=self._source_counter=self._entity_counter=0

    def _next_epoch(self):
        self._epoch+=1
        return self._epoch

    def reconcile(self, source, settings_key, scopes, *, now_s):
        if source!=self._source or settings_key!=self._settings:
            self._scopes.clear(); self._next_epoch()
        self._source,self._settings=source,settings_key
        if source is None:
            self._scopes.clear(); return
        specs={s.scope_id:s for s in scopes[:8]}
        for key in self._scopes.keys()-specs.keys(): del self._scopes[key]
        for key,spec in specs.items():
            if key not in self._scopes: self._scopes[key]=_Scope(self._next_epoch(),spec.layout_key,now_s)
            elif self._scopes[key].layout!=spec.layout_key:
                if source.kind=='desktop': self._scopes[key]=_Scope(self._next_epoch(),spec.layout_key,now_s)
                else:
                    self.clear_scene(key,now_s=now_s); self._scopes[key].layout=spec.layout_key
            self._expire(key,now_s)

    def mark_seen(self, scope_id, *, now_s):
        if scope_id in self._scopes:
            self._expire(scope_id,now_s); self._scopes[scope_id].seen=now_s

    def _expire(self, key, now):
        s=self._scopes[key]
        if now-s.seen>=self.policy.scene_idle_s:
            self.clear_scene(key,now_s=now)

    def observe(self, scope_id, turn):
        s=self._scopes[scope_id]; key=(turn.revision,turn.track_id,turn.turn_id)
        source_id=s.routes.get(key)
        if source_id is None:
            self._source_counter+=1; source_id=self._source_counter; s.routes[key]=source_id
            while len(s.routes)>32: s.routes.popitem(last=False)
        previous=s.turns.get(source_id)
        if previous and previous.text_version!=turn.text_version:
            for records in (s.entities,s.relations,s.terms):
                for k,record in tuple(records.items()):
                    refs=tuple(r for r in record.evidence if r.source_id!=source_id)
                    if len(refs)==len(record.evidence):continue
                    # A conflicted record contains competing forms. Once one of
                    # their sources changes we cannot attach the last forms to
                    # the surviving source; discard rather than invent proof.
                    if not refs or isinstance(record,RelationRecord) and record.status=='conflicted': del records[k]
                    else: records[k]=replace(record,evidence=refs,**({'status':'candidate'} if isinstance(record,RelationRecord) else {}))
            s.styles.pop(source_id,None)
            s.receipts.pop(source_id,None)
        current=SourceTurn(source_id,turn.text_version,turn.source_text,turn.evidence,turn.captured_at_s,turn.stable_at_s)
        s.turns[source_id]=current
        s.turns.move_to_end(source_id)
        while len(s.turns)>self.policy.history: s.turns.popitem(last=False)
        self._prune(s)
        return current

    def _prune(self,s):
        for key,relation in tuple(s.relations.items()):
            if relation.speaker_id not in s.entities or relation.addressee_id not in s.entities:
                del s.relations[key]; continue
            if relation.status=='candidate' and not any(r.source_id in s.turns for r in relation.evidence): del s.relations[key]
        for records,limit in ((s.entities,self.policy.entities),(s.relations,self.policy.relations),(s.terms,self.policy.terms),(s.styles,self.policy.styles),(s.receipts,32)):
            while len(records)>limit: records.popitem(last=False)
        needed={r.source_id for records in (s.entities,s.relations,s.terms) for rec in records.values() for r in rec.evidence}
        s.proofs={key:value for key,value in s.proofs.items() if key in needed}

    def view(self, scope_id, *, now_s):
        self._expire(scope_id,now_s); s=self._scopes[scope_id]; self._prune(s)
        return MemoryView(s.epoch,scope_id,tuple(s.turns.values()),tuple(s.entities.values()),tuple(s.relations.values()),tuple(s.terms.values()),tuple(s.styles.values()))

    def commit(self, receipt, snapshot, *, now_s):
        s=self._scopes.get(snapshot.stamp.scope_id)
        if s is None: return False
        self._expire(snapshot.stamp.scope_id,now_s)
        current=s.turns.get(snapshot.current.source_id)
        if (snapshot.stamp.memory_epoch!=s.epoch or current is None or current.text_version!=snapshot.current.text_version
                or receipt.source_text!=current.source_text or not receipt.translated_text
                or receipt.context is None or receipt.context.stamp!=snapshot.stamp
                or s.receipts.get(current.source_id)==current.text_version): return False
        delta=receipt.context.delta
        sources={t.source_id:t for t in snapshot.history+(snapshot.current,)}
        def valid(refs):
            return bool(refs) and all(r.source_id in sources and r.quote in sources[r.source_id].source_text for r in refs)
        if delta is not None:
            records=delta.entities+delta.relations+delta.terms
            if not all(valid(record.evidence) for record in records): return False
            remap={entity.entity_id:entity.entity_id for entity in snapshot.entities if entity.entity_id in s.entities}
            for entity in delta.entities:
                quotes=' '.join(r.quote for r in entity.evidence)
                if entity.name not in quotes or any(alias not in quotes for alias in entity.aliases): return False
                if not entity.entity_id.startswith('new:') and entity.entity_id not in remap: return False
                match=next((e.entity_id for e in s.entities.values() if entity.name in (e.name,*e.aliases)),None)
                if match is None:
                    self._entity_counter+=1; match=f'e{self._entity_counter}'
                remap[entity.entity_id]=match
            if any(r.speaker_id not in remap or r.addressee_id not in remap for r in delta.relations): return False
            def merge_refs(old,new):
                by_fingerprint={}
                for ref in old+new:
                    text=sources[ref.source_id].source_text if ref.source_id in sources else s.proofs.get(ref.source_id,'')
                    if text: by_fingerprint[fingerprint(text)]=ref
                return tuple(by_fingerprint.values())[-2:]
            for source in sources.values(): s.proofs[source.source_id]=source.source_text
            for entity in delta.entities:
                eid=remap[entity.entity_id]; old=s.entities.get(eid)
                s.entities[eid]=replace(entity,entity_id=eid,evidence=merge_refs(old.evidence if old else (),entity.evidence))
            for relation in delta.relations:
                key=(remap[relation.speaker_id],remap[relation.addressee_id]); old=s.relations.get(key)
                refs=merge_refs(old.evidence if old else (),relation.evidence)
                conflict=old and (old.status=='conflicted' or (old.self_form,old.other_form)!=(relation.self_form,relation.other_form))
                status='conflicted' if conflict else 'supported' if len(refs)>=2 else 'candidate'
                s.relations[key]=replace(relation,speaker_id=key[0],addressee_id=key[1],status=status,evidence=refs)
            for term in delta.terms:
                old=s.terms.get(term.source)
                s.terms[term.source]=replace(term,evidence=merge_refs(old.evidence if old else (),term.evidence))
        s.receipts[current.source_id]=current.text_version
        s.styles[current.source_id]=StyleSample(current.source_id,current.source_text,receipt.translated_text)
        self._prune(s)
        return True

    def clear_scene(self, scope_id, *, now_s):
        s=self._scopes[scope_id]; s.epoch=self._next_epoch(); s.seen=now_s
        s.turns.clear(); s.routes.clear(); s.styles.clear(); s.receipts.clear()
        s.relations=OrderedDict((k,r) for k,r in s.relations.items() if r.status=='supported')
        self._prune(s)

    def reset_all(self, *, now_s):
        for key,s in tuple(self._scopes.items()): self._scopes[key]=_Scope(self._next_epoch(),s.layout,now_s)
