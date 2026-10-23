import json

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
