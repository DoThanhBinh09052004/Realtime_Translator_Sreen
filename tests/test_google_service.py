from dataclasses import replace
from unittest.mock import Mock
from core.contracts import RuntimeSettings, ProviderSettings, TranslationResult, EngineError


def settings():
    return RuntimeSettings('English','Vietnamese',ProviderSettings('Google Translate','','',None),500)


def test_google_bypasses_sdk_and_caches_with_metadata(monkeypatch):
    from engines import translator
    sdk = Mock(side_effect=AssertionError('No SDK for Google'))
    monkeypatch.setattr(translator,'OpenAI',sdk)
    google = Mock()
    google.translate.return_value = TranslationResult('Xin chào')
    service = translator.TranslationService(google_factory=lambda: google)
    try:
        first = service.translate('Hello',settings())
        second = service.translate('Hello',settings())
        assert first.text == second.text == 'Xin chào'
        assert not first.from_cache and second.from_cache
        assert google.translate.call_count == 1
        service.translate('Hello',replace(settings(),source_lang='Japanese'))
        assert google.translate.call_count == 2
        sdk.assert_not_called()
    finally: service.close()
    google.close.assert_called_once()


def test_google_errors_are_not_cached_and_fifo_is_bounded():
    from engines.translator import TranslationService
    calls = []
    class Google:
        def translate(self,text,*a):
            calls.append(text)
            return TranslationResult(error=EngineError('network','fail',True)) if text == 'fail' else TranslationResult(text)
        def close(self): pass
    service = TranslationService(google_factory=Google)
    try:
        for _ in range(2): service.translate('fail',settings())
        assert calls == ['fail','fail']
        for i in range(300): service.translate(str(i),settings())
        assert service.translate('0',settings()).from_cache
        service.translate('300',settings())
        assert not service.translate('0',settings()).from_cache
        assert len(service._cache) == 300
    finally: service.close()


def test_switch_google_ai_closes_clients_and_isolates_cache(fake_translator):
    from engines.translator import TranslationService
    google = Mock()
    google.translate.return_value = TranslationResult('Google result')
    service = TranslationService(google_factory=lambda: google)
    ai = replace(settings(),provider=ProviderSettings('OpenAI','fake-model','fake-key',None))
    try:
        assert service.translate('Hello',ai).text == 'fake translation'
        assert service.translate('Hello',settings()).text == 'Google result'
        assert service.translate('Hello',ai).text == 'fake translation'
        assert fake_translator.call_count == 2
        google.close.assert_called_once()
    finally: service.close()
