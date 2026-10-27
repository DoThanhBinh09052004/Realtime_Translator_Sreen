"""Pinned-origin transport policy for Custom API only."""
import httpx

from core.endpoint_policy import EndpointPolicyError, normalize_custom_api_endpoint


def _origin(url: httpx.URL) -> tuple[str, str, int]:
    return url.scheme, url.host, url.port or (443 if url.scheme == 'https' else 80)


def build_custom_api_http_client(
        base_url: str, *, timeout_s: float,
        transport: httpx.BaseTransport | None = None) -> httpx.Client:
    endpoint = httpx.URL(normalize_custom_api_endpoint(base_url))
    origin = _origin(endpoint)

    def guard_request(request: httpx.Request) -> None:
        canonical = httpx.URL(normalize_custom_api_endpoint(str(request.url)))
        if _origin(canonical) != origin:
            raise EndpointPolicyError('Custom API không được gửi yêu cầu tới origin khác endpoint đã chọn.')
        # In particular, localhost must become a literal before DNS/transport.
        request.url = canonical

    def guard_response(response: httpx.Response) -> None:
        if 300 <= response.status_code < 400:
            try:
                response.close()
            except Exception:
                # Cleanup must never turn a permanent policy refusal into a
                # retryable SDK network error or expose a stream exception.
                pass
            raise EndpointPolicyError('Custom API không cho phép chuyển hướng; hãy nhập endpoint cuối cùng.')

    return httpx.Client(
        timeout=timeout_s, follow_redirects=False, trust_env=False,
        transport=transport,
        event_hooks={'request': [guard_request], 'response': [guard_response]},
    )
