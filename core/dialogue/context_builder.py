"""Select small immutable context and produce the one canonical prompt payload."""
from dataclasses import asdict
import hashlib
import json
from core.dialogue.context_models import *

def context_available(settings):
    return settings.overlay_mode=='subtitle' and settings.provider.name!='Google Translate'

def context_supported(settings):
    return settings.context_enabled and context_available(settings)

def canonical(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),sort_keys=True)

def build_context(view,current,*,policy=ContextPolicy()):
    history=list(t for t in view.turns if t.source_id!=current.source_id)[-policy.history:]
    relevant=current.source_text+' '+' '.join(line.text for line in current.evidence.lines)
    entities=sorted(view.entities,key=lambda e:(not any(a in relevant for a in (e.name,*e.aliases)),e.entity_id))[:policy.selected]
    ids={e.entity_id for e in entities}
    relations=[r for r in view.relations if r.speaker_id in ids and r.addressee_id in ids][-policy.selected:]
    terms=[t for t in view.terms if t.source in relevant][-policy.selected:]
    styles=list(view.styles[-policy.styles:]); lines=list(current.evidence.lines)
    def turn_data(t): return dict(source_id=t.source_id,text_version=t.text_version,text=t.source_text,lines=[asdict(l) for l in t.evidence.lines])
    def payload():
        return canonical(dict(schema=CONTEXT_SCHEMA_VERSION,current=dict(source_id=current.source_id,text_version=current.text_version,lines=[asdict(l) for l in lines]),
                              original_history=[turn_data(t) for t in history],entities=[asdict(e) for e in entities],relations=[asdict(r) for r in relations],terms=[asdict(t) for t in terms],style_only_not_evidence=[asdict(s) for s in styles]))
    encoded=payload()
    while len(encoded.encode('utf-8'))>policy.context_bytes:
        if styles: styles.pop(0)
        elif history: history.pop(0)
        elif relations: relations.pop()
        elif terms: terms.pop()
        elif entities:
            removed=entities.pop(); relations[:]=[r for r in relations if removed.entity_id not in (r.speaker_id,r.addressee_id)]
        elif lines: lines.pop()
        else: raise ValueError('Context policy cannot fit required fields')
        encoded=payload()
    digest=hashlib.sha256(canonical(dict(text=current.source_text,context=encoded,schema=CONTEXT_SCHEMA_VERSION)).encode('utf-8')).hexdigest()
    return ContextSnapshot(ContextStamp(view.epoch,view.scope_id,digest),current,tuple(history),tuple(entities),tuple(relations),tuple(terms),tuple(styles),encoded)
