import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from engines.translator import TranslationService
from core.contracts import RuntimeSettings, ProviderSettings
from core.dialogue.context_builder import build_context
from tests.context_helpers import make_turn, make_view
from tests.test_context_protocol import response

@pytest.fixture
def transport(monkeypatch):
    create=Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(response())),finish_reason='stop')],usage=None))
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),close=Mock())
    monkeypatch.setattr('engines.translator.OpenAI',lambda **kw:client)
    return create

def settings(): return RuntimeSettings('English','Vietnamese',ProviderSettings('OpenAI','m','fake',None),500,context_enabled=True)
def snapshot(): return build_context(make_view(),make_turn(text='A: Sensei help'))

def test_context_translation_uses_exactly_one_completion_and_cache(transport):
    s=TranslationService(); snap=snapshot()
    r=s.translate(snap.current.source_text,settings(),context=snap)
    assert r.text=='Thầy giúp em.' and r.context.stamp==snap.stamp
    assert s.translate(snap.current.source_text,settings(),context=snap).from_cache
    assert transport.call_count==1
    other=build_context(make_view(scope_id='other'),snap.current)
    s.translate(other.current.source_text,settings(),context=other)
    assert transport.call_count==2

def test_plain_text_downgrades_without_repair_call(transport):
    transport.return_value.choices[0].message.content='Xin chào'
    s=TranslationService(); snap=snapshot()
    assert s.translate(snap.current.source_text,settings(),context=snap).context.degraded
    assert transport.call_count==1
    second=build_context(make_view(),make_turn(2,'A: next'))
    s.translate(second.current.source_text,settings(),context=second)
    assert 'Return only the translated text' in transport.call_args.kwargs['messages'][0]['content']

def test_malformed_json_has_nonretryable_format_error(transport):
    transport.return_value.choices[0].message.content='{"translation":'
    s=TranslationService(); snap=snapshot(); result=s.translate(snap.current.source_text,settings(),context=snap)
    assert result.error.code=='invalid_response' and not result.error.retryable
    assert result.context is None and result.text=='' and result.context_degraded
    assert transport.call_count==1

def test_context_text_mismatch_never_calls_transport(transport):
    assert TranslationService().translate('different',settings(),context=snapshot()).error.code=='invalid_input'
    transport.assert_not_called()
