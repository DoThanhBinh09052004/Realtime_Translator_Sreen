"""Pure URL policy for user-selected OpenAI-compatible endpoints; no DNS/I/O."""
import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit


ENDPOINT_MESSAGE = 'Base URL phải dùng HTTPS; HTTP chỉ được phép cho localhost hoặc IP loopback.'


class EndpointPolicyError(ValueError):
    """Safe policy failure; never include the input URL in the message."""


def normalize_custom_api_endpoint(value: object, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise EndpointPolicyError(ENDPOINT_MESSAGE)
    # urlsplit strips some control characters: reject them before parsing.
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise EndpointPolicyError(ENDPOINT_MESSAGE)
    value = value.strip(' ')
    if not value and allow_empty:
        return ''
    if not value or any(c.isspace() for c in value) or any(c in value for c in '\\?#'):
        raise EndpointPolicyError(ENDPOINT_MESSAGE)
    try:
        parsed = urlsplit(value)
        scheme, host, port = parsed.scheme.lower(), parsed.hostname, parsed.port
        if (scheme not in ('http', 'https') or not host or parsed.username is not None
                or parsed.password is not None or '%' in host or parsed.netloc.endswith(':')):
            raise ValueError()
        if port is not None and not 1 <= port <= 65535:
            raise ValueError()
        host = host.lower()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if scheme == 'http':
            if host == 'localhost':
                host = '127.0.0.1'
            elif (address is None or not address.is_loopback
                  or getattr(address, 'ipv4_mapped', None) is not None):
                raise ValueError()
        if address is not None:
            host = address.compressed
            if address.version == 6:
                host = f'[{host}]'
        else:
            host = host.encode('idna').decode('ascii')
            # Reject malformed authorities rather than let urllib/HTTPX disagree.
            if not re.fullmatch(r'[a-z0-9._-]+', host):
                raise ValueError()
        default_port = 80 if scheme == 'http' else 443
        authority = host if port is None or port == default_port else f'{host}:{port}'
        return urlunsplit((scheme, authority, parsed.path.rstrip('/'), '', ''))
    except (ValueError, UnicodeError):
        raise EndpointPolicyError(ENDPOINT_MESSAGE) from None
