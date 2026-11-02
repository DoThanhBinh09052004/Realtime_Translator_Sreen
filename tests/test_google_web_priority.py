import json
from dataclasses import replace
from threading import Event
from urllib.parse import parse_qs

import httpx
import pytest


def test_batch_framing_rpc_and_all_segments(google_batch_response):
    from engines.google_translate import parse_batch_response
    content = google_batch_response('Xin chào. ', '世界\nDòng 2')
    unrelated = json.dumps([['wrb.fr', 'other', 'metadata, not translation', None]])
    assert parse_batch_response(")]}'\n" + unrelated + '\n' + content) == 'Xin chào. 世界\nDòng 2'
    # The matching RPC need not be the first row in a frame.
    row = json.loads(content.splitlines()[-1])[0]
    frame = json.dumps([['wrb.fr', 'other', 'metadata'], row])
    assert parse_batch_response(frame) == 'Xin chào. 世界\nDòng 2'


@pytest.mark.parametrize('content', [
    '', '<html>blocked</html>', '{}', '[]',
    '[["wrb.fr","other","metadata"]]',
    '[["wrb.fr","MkEWBc"]]',
    '[["wrb.fr","MkEWBc",null]]',
    '[["wrb.fr","MkEWBc","not json"]]',
    '[["wrb.fr","MkEWBc","[]"]]',
])
def test_batch_rejects_missing_or_malformed_rpc(content):
    from engines.google_translate import parse_batch_response
    with pytest.raises(ValueError):
        parse_batch_response(content)


@pytest.mark.parametrize('segments', [(), ('',), ('valid', None), ('valid', 1)])
def test_batch_rejects_empty_or_broken_segment_instead_of_partial_text(google_batch_response, segments):
    from engines.google_translate import parse_batch_response
    with pytest.raises(ValueError):
        parse_batch_response(google_batch_response(*segments))


def test_clients5_parser_preserves_segments():
    from engines.google_translate import parse_clients5_response
    assert parse_clients5_response(['Xin chào. ', '世界\nDòng 2']) == 'Xin chào. 世界\nDòng 2'
    for payload in (None, {}, 'text', [], [''], ['ok', None], [['nested']]):
        with pytest.raises(ValueError):
            parse_clients5_response(payload)


def test_batch_unicode_line_separators_are_text_not_protocol_frames(google_batch_response):
    from engines.google_translate import parse_batch_response
    assert parse_batch_response(google_batch_response('前\u2028後\u2029終')) == '前\u2028後\u2029終'


@pytest.mark.parametrize('space_join,segments,expected', [
    (True, ('Xin chào.', 'Bạn khỏe không?'), 'Xin chào. Bạn khỏe không?'),
    (False, ('前', '後'), '前後'),
    (None, ('Xin chào. ', '世界\nDòng 2'), 'Xin chào. 世界\nDòng 2'),
    (True, ('Một\nDòng hai', 'Câu ba'), 'Một\nDòng hai Câu ba'),
])
def test_batch_uses_protocol_separator_without_losing_literal_whitespace(google_batch_response, space_join, segments, expected):
    from engines.google_translate import parse_batch_response
    assert parse_batch_response(google_batch_response(*segments, space_join=space_join)) == expected


def request_route(request):
    return {'translate.google.com': 'batch', 'clients5.google.com': 'clients5',
            'translate.googleapis.com': 'gtx'}[request.url.host]


def test_adapter_priority_and_sticky_success(google_batch_response):
    from engines.google_translate import GoogleTranslateClient
    calls = []
    def respond(request):
        route = request_route(request)
        calls.append(route)
        return httpx.Response(503) if route == 'clients5' else httpx.Response(200, text=google_batch_response('Xin chào'))
    adapter = GoogleTranslateClient(client_factory=lambda: httpx.Client(transport=httpx.MockTransport(respond)))
    try:
        assert adapter.translate('Hello', 'English', 'Vietnamese').error.code == 'network'
        result = adapter.translate('Hello', 'English', 'Vietnamese')
        assert result.text == 'Xin chào' and result.input_tokens is result.output_tokens is None
        assert adapter.translate('New text', 'English', 'Vietnamese').text == 'Xin chào'
        assert calls == ['clients5', 'batch', 'batch']
    finally:
        adapter.close()


def test_retries_progress_to_gtx_without_looping():
    from engines.google_translate import GoogleTranslateClient
    calls = []
    def respond(request):
        calls.append(request_route(request))
        return httpx.Response(503)
    adapter = GoogleTranslateClient(client_factory=lambda: httpx.Client(transport=httpx.MockTransport(respond)))
    try:
        for _ in range(4):
            assert adapter.translate('Hello', 'English', 'Vietnamese').error.code == 'network'
        assert calls == ['clients5', 'batch', 'gtx', 'gtx']
    finally:
        adapter.close()


def test_gtx_success_is_sticky_and_get_routes_keep_language_and_text():
    from engines.google_translate import GoogleTranslateClient
    calls = []
    def respond(request):
        calls.append(request)
        if request_route(request) != 'gtx': return httpx.Response(503)
        return httpx.Response(200, json=[[['Xin chào. '], ['世界\nDòng 2']]])
    adapter = GoogleTranslateClient(client_factory=lambda: httpx.Client(transport=httpx.MockTransport(respond)))
    try:
        for _ in range(2): adapter.translate('原文 日本語', 'Japanese', 'Vietnamese')
        assert adapter.translate('原文 日本語', 'Japanese', 'Vietnamese').text == 'Xin chào. 世界\nDòng 2'
        assert adapter.translate('New source', 'English', 'Korean').text == 'Xin chào. 世界\nDòng 2'
        assert [request_route(r) for r in calls] == ['clients5', 'batch', 'gtx', 'gtx']
        assert dict(calls[0].url.params) == dict(client='dict-chrome-ex', sl='ja', tl='vi', q='原文 日本語')
        assert dict(calls[2].url.params) == dict(client='gtx', sl='ja', tl='vi', dt='t', q='原文 日本語')
        assert dict(calls[3].url.params) == dict(client='gtx', sl='en', tl='ko', dt='t', q='New source')
    finally:
        adapter.close()


@pytest.mark.parametrize('failure', ['timeout', 'network', 408, 429, 503])
def test_retryable_failures_prepare_next_route_without_hidden_request(failure, google_batch_response):
    from engines.google_translate import GoogleTranslateClient
    calls = []
    def respond(request):
        calls.append(request_route(request))
        if len(calls) == 1:
            if failure == 'timeout': raise httpx.ReadTimeout('private', request=request)
            if failure == 'network': raise httpx.ConnectError('private', request=request)
            return httpx.Response(failure, headers={'retry-after': '90'})
        return httpx.Response(200, text=google_batch_response('ok'))
    adapter = GoogleTranslateClient(client_factory=lambda: httpx.Client(transport=httpx.MockTransport(respond)))
    try:
        result = adapter.translate('Hello', 'English', 'Vietnamese')
        assert result.error.retryable and calls == ['clients5']
        if failure == 429:
            assert result.error.retry_after_s == 90
        assert adapter.translate('Current source', 'English', 'Vietnamese').text == 'ok'
        assert calls == ['clients5', 'batch']
    finally:
        adapter.close()


@pytest.mark.parametrize('status,body', [(400, ''), (403, ''), (302, ''),
                                       (200, '<html>blocked</html>'), (200, '[]')])
def test_nonretry_errors_do_not_advance_route(status, body):
    from engines.google_translate import GoogleTranslateClient
    calls = []
    def respond(request):
        calls.append(request_route(request))
        return httpx.Response(status, text=body)
    adapter = GoogleTranslateClient(client_factory=lambda: httpx.Client(transport=httpx.MockTransport(respond)))
    try:
        for _ in range(2):
            assert not adapter.translate('Hello', 'English', 'Vietnamese').error.retryable
        assert calls == ['clients5', 'clients5']
    finally:
        adapter.close()


def test_invalid_input_does_not_reset_prepared_fallback(google_batch_response):
    from engines.google_translate import GoogleTranslateClient
    calls = []
    def respond(request):
        calls.append(request_route(request))
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, text=google_batch_response('ok'))
    adapter = GoogleTranslateClient(client_factory=lambda: httpx.Client(transport=httpx.MockTransport(respond)))
    try:
        adapter.translate('Hello', 'English', 'Vietnamese')
        assert adapter.translate('x'*2001, 'English', 'Vietnamese').error.code == 'invalid_input'
        assert not adapter.translate('', 'English', 'Vietnamese').text
        assert calls == ['clients5']
        assert adapter.translate('Current', 'English', 'Vietnamese').text == 'ok'
        assert calls == ['clients5', 'batch']
    finally:
        adapter.close()


def test_closed_client_restarts_with_clients5(google_batch_response):
    from engines.google_translate import GoogleTranslateClient
    calls, clients = [], []
    def respond(request):
        route = request_route(request)
        calls.append(route)
        return httpx.Response(503) if route == 'clients5' else httpx.Response(200, text=google_batch_response('ok'))
    def factory():
        client = httpx.Client(transport=httpx.MockTransport(respond))
        clients.append(client)
        return client
    adapter = GoogleTranslateClient(client_factory=factory)
    try:
        adapter.translate('Hello', 'English', 'Vietnamese')
        adapter.translate('Hello', 'English', 'Vietnamese')
        adapter.close()
        assert clients[0].is_closed
        adapter.translate('Hello', 'English', 'Vietnamese')
        assert calls == ['clients5', 'batch', 'clients5']
    finally:
        adapter.close()


def test_logs_redact_all_get_queries_and_never_log_batch_source(caplog):
    import logging
    from engines.google_translate import GoogleTranslateClient
    caplog.set_level(logging.INFO, logger='httpx')
    calls = []
    def respond(request):
        route = request_route(request)
        calls.append((route, request))
        return httpx.Response(200, json=[[['ok']]]) if route == 'gtx' else httpx.Response(503)
    adapter = GoogleTranslateClient(client_factory=lambda: httpx.Client(transport=httpx.MockTransport(respond)))
    try:
        for _ in range(3): adapter.translate('private source', 'English', 'Vietnamese')
        assert [route for route, _ in calls] == ['clients5', 'batch', 'gtx']
        assert b'private' in calls[1][1].content
        assert calls[0][1].url.params['q'] == calls[2][1].url.params['q'] == 'private source'
        assert 'private' not in caplog.text and 'q=' not in caplog.text
    finally:
        adapter.close()


def test_real_adapter_queue_respects_429_after_stale_source_and_pauses_after_four(qtbot, runtime_settings):
    from core.blocks.models import BlockJob
    from core.blocks.translation_worker import BlockTranslationWorker
    from core.google_recovery import GoogleRecoveryGate
    from engines.google_translate import GoogleTranslateClient
    from engines.translator import TranslationService
    now, ticks, calls = [0.], [0], []
    entered, release = Event(), Event()
    gate = GoogleRecoveryGate()
    settings = replace(runtime_settings, provider=replace(runtime_settings.provider,
                       name='Google Translate', api_key='', model_id=''))
    def clock():
        ticks[0] += 1
        return now[0]
    def respond(request):
        if request.method == 'POST':
            rpc = json.loads(parse_qs(request.content.decode())['f.req'][0])
            source = json.loads(rpc[0][0][1])[0][0]
        else:
            source = request.url.params['q']
        calls.append((request_route(request), source))
        if len(calls) == 1:
            entered.set()
            assert release.wait(4)
            return httpx.Response(429, headers={'retry-after': '12'})
        return httpx.Response(503)
    def service():
        return TranslationService(google_factory=lambda: GoogleTranslateClient(
            client_factory=lambda: httpx.Client(transport=httpx.MockTransport(respond))))
    worker = BlockTranslationWorker(clock=clock, service_factory=service, google_recovery=gate)
    def submit(revision, source):
        job = BlockJob(revision, revision, source, settings)
        worker.replace_pending((job,), frozenset({(job.block_id, source)}), revision)
    def wait_for_queue_ticks():
        before = ticks[0]
        qtbot.waitUntil(lambda: ticks[0] >= before + 3)
    submit(1, 'Old scene')
    worker.start()
    try:
        qtbot.waitUntil(entered.is_set)
        submit(2, 'Current scene')
        release.set()
        qtbot.waitUntil(lambda: gate.snapshot(now_s=0).retries_issued == 1)
        assert not worker.drain_results()  # Stale result discarded, service failure retained.
        now[0] = 11.999
        wait_for_queue_ticks()
        assert calls == [('clients5', 'Old scene')]
        for count, at, due in ((2, 12., 14.), (3, 14., 18.)):
            now[0] = at
            qtbot.waitUntil(lambda: len(calls) == count)
            qtbot.waitUntil(lambda: gate.snapshot(now_s=at).not_before_s == due)
        now[0] = 18.
        qtbot.waitUntil(lambda: gate.snapshot(now_s=18).phase == 'paused')
        assert calls == [('clients5', 'Old scene'), ('batch', 'Current scene'),
                         ('gtx', 'Current scene'), ('gtx', 'Current scene')]
        now[0] = 10000.
        submit(3, 'New paused scene')
        wait_for_queue_ticks()
        assert len(calls) == 4 and not gate.can_dispatch(now_s=10000)
    finally:
        release.set()
        worker.request_stop()
        assert worker.wait(2000)


def test_facade_cache_hit_keeps_fallback_route_and_service_failure_budget(google_batch_response, runtime_settings):
    from core.google_recovery import GoogleRecoveryGate
    from engines.google_translate import GoogleTranslateClient
    from engines.translator import TranslationService
    calls = []
    def respond(request):
        calls.append(request_route(request))
        if len(calls) == 2: return httpx.Response(503)
        if request.method == 'POST': return httpx.Response(200, text=google_batch_response('fresh'))
        return httpx.Response(200, json=['cached'])
    service = TranslationService(google_factory=lambda: GoogleTranslateClient(
        client_factory=lambda: httpx.Client(transport=httpx.MockTransport(respond))))
    settings = replace(runtime_settings, provider=replace(runtime_settings.provider,
                       name='Google Translate', api_key='', model_id=''))
    gate = GoogleRecoveryGate()
    generation = gate.snapshot(now_s=0).generation
    try:
        assert service.translate('Cache me', settings).text == 'cached'
        failed = service.translate('Fail me', settings)
        gate.record_result(failed, generation=generation, now_s=0)
        cached = service.translate('Cache me', settings)
        assert cached.from_cache and cached.text == 'cached'
        gate.record_result(cached, generation=generation, now_s=1)
        assert gate.snapshot(now_s=1).retries_issued == 1
        fresh = service.translate('Current source', settings)
        assert fresh.text == 'fresh' and calls == ['clients5', 'clients5', 'batch']
        gate.record_result(fresh, generation=generation, now_s=1)
        assert gate.snapshot(now_s=1).retries_issued == 0
    finally:
        service.close()
