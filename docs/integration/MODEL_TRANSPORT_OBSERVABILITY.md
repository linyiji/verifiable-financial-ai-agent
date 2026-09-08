# Model transport observability

[简体中文](MODEL_TRANSPORT_OBSERVABILITY.zh-CN.md)

The shared OpenAI-compatible HTTP boundary records bounded transport metadata
for both TeamoRouter and MiMo Direct. Existing `VFA_PERFORMANCE_PATH` opt-in
performance recording enables it; the existing recorder snapshot/flush path
retains the enriched `model.http` span. No independent logging sink is added.

## Evidence semantics

- Session ID, logical call ID, parent attempt ID, process ID, stable client ID,
  provider/model/route, task profile, dependency versions and monotonic span
  duration correlate the observed attempt. An unavailable route is `UNKNOWN`.
- Owned client creation time is observed immediately after construction;
  caller-owned creation time is `UNKNOWN`. Completion records actual closed
  state without closing caller-owned clients.
- Effective proxy metadata is read from the selected HTTPX transport mount,
  not from a second environment lookup. Only host and port are retained.
  Unsupported/custom transport inspection yields `UNKNOWN`. Private HTTPX
  inspection is best-effort and covered against the installed HTTPX stack.
- TCP establishment may be to a proxy, not the provider origin. TLS completion
  alone does not establish provider health. Reused connections can leave TCP
  establishment `UNKNOWN` for the current request.
- Trace events distinguish request sent, response headers, body reading and
  complete response. Unobserved stages remain `UNKNOWN`, never inferred as
  failure or success. Proxy CONNECT headers are not provider response headers.
- `concurrent_http_attempts` counts instrumented in-flight HTTP attempts in
  this process/event loop, including the current attempt; it is not a count
  of all tasks, logical calls, or calls across workers.
- Exception classes and chains use known library class identities only.
  Unknown subclasses remain `UNKNOWN`. Raw exception strings, credentials,
  headers, prompts and response bodies are never retained by this instrumentation.

Routing, trust_env, timeout/retry/fallback settings, HTTP versions, client
ownership, pooling and research/product contracts are unchanged.

## Verification receipt

Focused suite: **82 passed**, including **19 new transport tests**. Coverage
includes both providers, loopback response stages/timeouts/disconnects,
incomplete bodies, mocked transport errors, credential-bearing system proxy
selection without requests, safe redaction, concurrency, client lifecycle and
disabled-instrumentation request equivalence. Ruff and `git diff --check` pass.
No frontend surfaces changed; frontend typecheck/build was not required.

Read-only historical integrity checks pass; production Run inventory remains
38 and no Memory v2 exists. This task made zero real provider/model calls and
created zero production Runs. Historical R3 is not a new Run from this task.

Observability overhead: **NOT_OBSERVED** (no benchmark performed).
These tests do not identify the cause of historical real transport failures.

Next separately authorized action: `MODEL_TRANSPORT_DISCRIMINATING_PROBE`.
No real probe or automatic retry is part of this enhancement.
