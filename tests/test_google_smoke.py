import httpx


def test_smoke_helper_closes_adapter_and_never_reads_config(monkeypatch, google_batch_response):
    from tools.smoke_google_translate import run_smoke
    from engines.google_translate import GoogleTranslateClient
    from core import config
    monkeypatch.setattr(config,'load_config',lambda: (_ for _ in ()).throw(AssertionError('No config')))
    calls=[]
    client=httpx.Client(transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(200,text=google_batch_response('Xin chào'))))
    result=run_smoke('Hello','English','Vietnamese',adapter_factory=lambda:GoogleTranslateClient(client_factory=lambda:client))
    assert result.text=='Xin chào' and len(calls)==1 and client.is_closed
