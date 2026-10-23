"""Keyless Google web adapter. Retry and caching belong to the caller."""
import logging
import math
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
import httpx
from core.contracts import EngineError, TranslationResult

GOOGLE_ADAPTER_VERSION = 1
_URL = 'https://translate.googleapis.com/translate_a/single'
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
                if isinstance(value, httpx.URL) and value.host == 'translate.googleapis.com'
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


class GoogleTranslateClient:
    def __init__(self, *, client_factory=None, wall_clock=time.time):
        self._factory = client_factory or (lambda: httpx.Client(transport=httpx.HTTPTransport(retries=0), follow_redirects=False))
        self._clock = wall_clock
        self._client = None

    def translate(self, text, source_lang, target_lang):
        if not isinstance(text, str) or len(text) > 2000:
            return _error('invalid_input')
        if not text.strip():
            return TranslationResult()
        if source_lang not in _LANGUAGES or target_lang not in _LANGUAGES:
            return _error('invalid_input')
        try:
            if self._client is None:
                self._client = self._factory()
            response = self._client.get(_URL, params=dict(client='gtx', sl=_LANGUAGES[source_lang],
                tl=_LANGUAGES[target_lang], dt='t', q=text), timeout=8.0, follow_redirects=False)
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
            return TranslationResult(text=parse_google_response(response.json()))
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
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
