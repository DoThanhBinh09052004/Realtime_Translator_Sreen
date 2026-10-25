# Custom API transport security verification

Date: 2026-10-25. Baseline: commit `3aeba01`, 503 tests passed in 59.68 s.

## Behavior

- Only Custom API changes. Remote endpoints require HTTPS; HTTP is limited to
  literal loopback addresses and exact `localhost`. HTTP localhost is sent to
  `127.0.0.1` without DNS; IPv6-only servers can use `[::1]` explicitly.
- Reject userinfo, query/fragment, malformed port, backslash, control characters,
  misleading localhost names, shorthand/integer IPv4, scoped IPv6, and mapped
  IPv6 HTTP addresses. All errors use fixed messages without echoing the URL.
- Invalid legacy endpoints appear empty in normalized settings, preserving the
  original file on read and keeping provider/model/DPAPI credentials intact.
- The service checks every direct runtime snapshot before creating a client,
  looking up cache, or logging a request. A rejected endpoint closes the previous
  service client/cache and returns permanent `invalid_endpoint`.
- The Custom API HTTPX client pins scheme/host/effective port, rewrites canonical
  request URLs before transport, keeps TLS verification, ignores environment
  proxy/CA settings, and refuses every 3xx response without following Location.
- Redirect/policy exceptions wrapped by the SDK remain permanent endpoint errors,
  not retryable network errors. SDK retries stay disabled. Other provider clients,
  translation prompts, capture behavior and DPAPI storage remain unchanged.
- Changing the Base URL updates the canonical editor value and status without
  overwriting an unapplied key draft. Invalid edits roll back without reconfiguring
  the worker or changing its current credential.

## Tests performed

All tests use temporary settings, fake keys, guarded sockets/DNS and fake HTTP
transports. SDK integration imports the real installed SDK class only for the
scoped test, passing an HTTPX MockTransport. No provider/API or desktop request
is made; no real config/key or sample video is read.

- Task 1 RED: 41 failed / 5 passed before policy; GREEN: 111 passed across URL,
  config validation/persistence, legacy migration and existing Custom API tests.
- Task 2 RED: 42 failed before client factory; GREEN: 83 passed across policy and
  guarded transport tests, including a per-call `follow_redirects=True` attempt.
- Task 3 RED: 18 failed / 7 passed before SDK/UI integration; GREEN: 188 passed
  across SDK/Qt, URL/transport, cache, retry, engine and credential regressions.
- Native SDK integration verifies exact request count, no redirect destination,
  no retry deadline, no leaked Location/body/key in errors, stale-cache rejection,
  loopback canonicalization and transport cleanup on reconfigure/constructor error.
- Proxy tests keep the real HTTPX client and replace its underlying transport
  constructor to show that environment proxies are not selected; mock transport
  injection is deliberately not used for that check.

Full suite: **611 passed in 55.68 s**, exit 0, on Windows / Python 3.10.22.
Command: `.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider`.
`git diff --check` passed. A Qt offscreen screenshot with an empty key and sample
URL verified that the endpoint help text fits the existing page. Final independent
review will be recorded after it finishes.

## Limits / compatibility

These are offline policy and dispatch checks, not a live TLS handshake or a
security certification. DNS aliases for local HTTP services are intentionally
not accepted. Redirect-based endpoints must be replaced with their final URL.
Custom API no longer consumes HTTP_PROXY/HTTPS_PROXY/ALL_PROXY or environment CA
overrides; use an endpoint trusted by the default TLS verifier. There is no
disable-TLS or allow-insecure escape hatch. This does not establish endpoint
ownership and is not a general SSRF firewall.

Implementation decisions: work in the current develop checkout with selective
staging to preserve existing private/overlay changes; reject all mapped IPv6
HTTP addresses explicitly because the installed Python IP classification differs
from the original plan's assumption. Their local alternatives are 127.0.0.1/::1.
