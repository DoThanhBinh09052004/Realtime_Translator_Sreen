from dataclasses import FrozenInstanceError
import pytest
from core.contracts import RuntimeSettings, ProviderSettings, TranslationResult, EngineError
from core.blocks.models import BlockJob
from core.dialogue.context_models import ContextPolicy, ContextStamp, ContextOutcome, OcrLine, OcrEvidence
from core.dialogue.context_models import StableTurn,StyleSample,SourceKey,ScopeSpec,PresentationReceipt

def test_contract_defaults_preserve_existing_callers():
    settings = RuntimeSettings('English', 'Vietnamese', ProviderSettings('x','m','k',None),500)
    assert settings.context_enabled is False
    assert BlockJob(1,0,'Hello',settings,1,1).context is None

def test_context_values_are_deeply_immutable():
    evidence = OcrEvidence((OcrLine('A', .9, True),))
    with pytest.raises(FrozenInstanceError): evidence.lines = ()
    with pytest.raises((TypeError, ValueError)): OcrEvidence([OcrLine('A',.9,True)])

def test_error_clears_context():
    context = ContextOutcome(ContextStamp(1,'r','digest'))
    result = TranslationResult('bad', EngineError('x','error',False), context=context)
    assert result.text == '' and result.context is None

def test_policy_has_exact_resource_bounds():
    p=ContextPolicy()
    assert (p.history,p.entities,p.relations,p.terms,p.context_bytes,p.scene_idle_s)==(8,32,64,64,6144,120.)

@pytest.mark.parametrize('make',[
    lambda:ContextOutcome(ContextStamp(1,'r','d'),delta=[]),
    lambda:StableTurn(1,0,1,1,'text',[],0.,1.),
    lambda:StyleSample(1,[], 'translated'),
    lambda:PresentationReceipt([1,0,1,1],'source','translated'),
    lambda:ContextStamp(1,'r',[]),
    lambda:ContextPolicy(history=-1),
    lambda:ScopeSpec('r',(float('nan'),)),
])
def test_invalid_mutable_or_nonfinite_contracts_rejected(make):
    with pytest.raises((TypeError,ValueError)):make()
