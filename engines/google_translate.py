"""Keyless Google web adapter. Retry and caching belong to the caller."""
import logging
import json
import math
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
import httpx
from core.contracts import EngineError, TranslationResult

GOOGLE_ADAPTER_VERSION = 2
_URL = 'https://translate.googleapis.com/translate_a/single'
_BATCH_URL = 'https://translate.google.com/_/TranslateWebserverUi/data/batchexecute'
_CLIENTS5_URL = 'https://clients5.google.com/translate_a/t'
_LANGUAGES = {'English':'en', 'Japanese':'ja', 'Chinese':'zh-CN', 'Korean':'ko', 'Vietnamese':'vi'}
_MESSAGES = {
    'invalid_input': 'Nội dung hoặc ngôn ngữ dịch không hợp lệ (tối đa 2000 ký tự).',
    'timeout': 'Yêu cầu Google Translate quá thời gian chờ.',
    'network': 'Không thể kết nối Google Translate.',
    'rate_limit': 'Google Translate đang giới hạn lượt dịch.',
    'service_unavailable': 'Hiện không thể sử dụng Google Translate.',
    'invalid_response': 'Không thể đọc kết quả từ Google Translate.',
}


class _GoogleRequestLogFilter(logging.Filter):
    """HTTPX logs request URLs at INFO; never log Google's source query."""

    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(
                value.copy_with(query=None)
                if isinstance(value, httpx.URL) and value.host in ('translate.googleapis.com', 'clients5.google.com')
                else value
                for value in record.args
            )
        return True


logging.getLogger('httpx').addFilter(_GoogleRequestLogFilter())


def _error(code, retryable=False, delay=None):
    return TranslationResult(error=EngineError(code, _MESSAGES[code], retryable, delay))


def parse_retry_after(value, *, now_epoch_s):
    if not value:
        return None
    try:
        delay = float(value)
        return delay if math.isfinite(delay) and delay >= 0 else None
    except (TypeError, ValueError):
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return max(0., date.timestamp()-now_epoch_s)
        except (TypeError, ValueError, OverflowError):
            return None


def parse_google_response(payload):
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list) or not payload[0]:
        raise ValueError('Invalid Google response')
    parts = []
    for segment in payload[0]:
        if not isinstance(segment, list) or not segment or not isinstance(segment[0], str):
            raise ValueError('Invalid Google segment')
        parts.append(segment[0])
    text = ''.join(parts).strip()
    if not text:
        raise ValueError('Empty Google response')
    return text


def parse_batch_response(content):
    """Read the MkEWBc result from Google's line-framed, nested JSON RPC."""
    if not isinstance(content, str):
        raise ValueError('Invalid Google batch response')
    for line in content.split('\n'):
        line = line.strip()
        if not line.startswith('['):
            continue  # XSSI prefix, byte counts and blank framing lines.
        try:
            rows = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, list) or len(row) < 2 or row[1] != 'MkEWBc':
                continue
            try:
                payload = json.loads(row[2])
                segments = payload[1][0][0][5]
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                raise ValueError('Invalid Google batch result') from exc
            return parse_google_response([segments])
    raise ValueError('Missing Google batch result')


def parse_clients5_response(payload):
    if not isinstance(payload, list) or not payload or any(not isinstance(part, str) for part in payload):
        raise ValueError('Invalid Google clients5 response')
    text = ''.join(payload).strip()
    if not text:
        raise ValueError('Empty Google clients5 response')
    return text


class GoogleTranslateClient:
    def __init__(self, *, client_factory=None, wall_clock=time.time):
        self._factory = client_factory or (lambda: httpx.Client(transport=httpx.HTTPTransport(retries=0), follow_redirects=False))
        self._clock = wall_clock
        self._client = None
        self._route = 0

    def translate(self, text, source_lang, target_lang):
        if not isinstance(text, str) or len(text) > 2000:
            return _error('invalid_input')
        if not text.strip():
            return TranslationResult()
        if source_lang not in _LANGUAGES or target_lang not in _LANGUAGES:
            return _error('invalid_input')
        result = self._translate(text, source_lang, target_lang)
        if result.error is not None and result.error.retryable:
            # The core schedules and counts the next attempt. Never send a
            # hidden fallback request here, including after a 429 response.
            self._route = min(self._route + 1, 2)
        return result

    def _translate(self, text, source_lang, target_lang):
        try:
            if self._client is None:
                self._client = self._factory()
            source, target = _LANGUAGES[source_lang], _LANGUAGES[target_lang]
            if self._route == 0:
                argument = json.dumps([[text, source, target, True], [None]], ensure_ascii=False)
                request = json.dumps([[['MkEWBc', argument, None, 'generic']]], ensure_ascii=False)
                response = self._client.post(_BATCH_URL, params={'rpcids': 'MkEWBc', 'rt': 'c'},
                    data={'f.req': request}, headers={
                        'content-type': 'application/x-www-form-urlencoded;charset=UTF-8',
                        'origin': 'https://translate.google.com', 'referer': 'https://translate.google.com/'},
                    timeout=8.0, follow_redirects=False)
            elif self._route == 1:
                response = self._client.get(_CLIENTS5_URL,
                    params=dict(client='dict-chrome-ex', sl=source, tl=target, q=text),
                    timeout=8.0, follow_redirects=False)
            else:
                response = self._client.get(_URL, params=dict(client='gtx', sl=source,
                    tl=target, dt='t', q=text), timeout=8.0, follow_redirects=False)
            status = response.status_code
            if status == 429:
                return _error('rate_limit', True, parse_retry_after(response.headers.get('retry-after'), now_epoch_s=self._clock()))
            if status == 408:
                return _error('timeout', True)
            if status >= 500:
                return _error('network', True)
            if status == 400:
                return _error('invalid_input')
            if status != 200:
                return _error('service_unavailable')
            if self._route == 0:
                text = parse_batch_response(response.text)
            elif self._route == 1:
                text = parse_clients5_response(response.json())
            else:
                text = parse_google_response(response.json())
            return TranslationResult(text=text)
        except httpx.TimeoutException:
            return _error('timeout', True)
        except httpx.TransportError:
            return _error('network', True)
        except (ValueError, TypeError, KeyError, IndexError):
            return _error('invalid_response')
        except Exception:
            return _error('service_unavailable')

    def close(self):
        client, self._client = self._client, None
        self._route = 0
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
