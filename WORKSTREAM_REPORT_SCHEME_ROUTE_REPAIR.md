# WS-P TeamoRouter Scheme Route Repair Report

## Scope and baseline

- Branch: `ws/scheme-route-repair`
- Base: `5fade58` (`contracts: freeze phase 2.1 semantic hardening`)
- Runtime: Python 3.11.16
- Unified Settings loaded the ignored `.env.local`; credential presence was checked only as a
  boolean.
- No key, credential fragment, credential fingerprint, request/response body, provider request ID,
  secret-bearing header, or raw environment value was printed, logged, saved, or committed.
- No domain contract, shared Settings, dependency, API entry point, or parallel-status file changed.

## Planner versus Scheme route comparison

| Dimension | Working Planner | Previously failing Scheme | Finding / repair |
| --- | --- | --- | --- |
| URL | configured TeamoRouter `/v1/chat/completions` | identical | no route divergence |
| Method | POST | identical | no divergence |
| Headers | same credential transport and JSON content type | identical | names and values were not recorded |
| Model route | primary `gpt-5.6-sol`, eligible fallback `gpt-5.6-luna` | identical | direct-to-fallback is now rejected before HTTP |
| Production timeout | 60 seconds | identical | probes used explicit bounded 15/20/30-second windows |
| Response format | strict `json_schema` | strict `json_schema` | no format divergence |
| Schema | closed graph/task objects | v1 contained an open-ended boolean map and allowed semantic-invalid strings/false flags | v2 uses a closed assurance object plus schema-level literal invariants |
| Payload envelope | model, messages, response format | identical | only task-specific messages/schema differ |
| Messages | system + goal + confirmed Scheme | system + ResearchObject + goal | expected product difference; no hidden reasoning requested |
| Parser | response content extraction, JSON decode, Pydantic validation, graph validation | same extraction/decode/Pydantic path plus Scheme semantic validation | schema v2 closes the schema/semantic gap |

The reliable cause was not URL, credentials, model naming, method, headers, or response parsing.
The Scheme response schema permitted outputs that Pydantic accepted but the subsequent semantic gate
rejected. Specifically, the two required calculation identifiers and true assurance flags were
prompt/post-validation requirements rather than provider-visible schema invariants. The v2 schema
makes them explicit and requires all eight top-level fields.

The earlier provider request rejection is recorded as observed route evidence, not asserted as the
sole root cause: route availability varied between bounded probes. The final primary-only validation
proves the provider supports the repaired ResearchScheme schema.

## Sanitized staged real probes

No response content was retained. The ignored local evidence directory is
`artifacts/phase2_1/scheme_route/`.

| Stage | Window | Actual attempts | Classification | Result |
| --- | ---: | --- | --- | --- |
| A: plain model | 15s | `gpt-5.6-sol` | `pass` (HTTP 200, response envelope present) | primary connectivity PASS |
| B: simple structured schema | 15s | `gpt-5.6-sol` | `pass` | primary JSON-schema support PASS |
| C: original ResearchScheme v1 | 15s | `gpt-5.6-sol`, `gpt-5.6-luna` | final `request_rejected` after an eligible primary failure | FAIL, accurately classified |
| C: closed v2 before literal constraints | 20s | `gpt-5.6-sol`, `gpt-5.6-luna` | `retryable_transport_failure` | deterministic fallback remained available |
| C: closed v2, primary-only diagnostic | 30s | `gpt-5.6-sol` | `semantic_validation_failed` after schema validation | provider supports schema; semantic gap isolated |
| C: final v2 with literal invariants | 30s | `gpt-5.6-sol` | `pass` | real provider Scheme, schema + semantic PASS |

Final authoritative provider result:

- actual model: `gpt-5.6-sol`
- actual HTTP attempts: one primary attempt
- structured validation: PASS
- Scheme semantic validation: PASS
- luna attempted: no
- deterministic fallback used: no
- provider-generated Scheme: yes

## Routing provenance repair

The LLM boundary now exposes a small secret-safe failure taxonomy:

- `preflight_failure`
- `retryable_transport_failure`
- `retryable_http_failure`
- `request_rejected`
- `structured_output_invalid`
- `semantic_validation_failed`

URL validation, response-schema generation, message/schema JSON serialization, and direct-fallback
policy checks happen before model-attempt provenance is recorded. A preflight failure therefore has
`attempted_models=[]`, `preflight_failure=true`, and cannot masquerade as provider unavailability.

For an actual request, the model is added immediately before the HTTP call. Request errors and
structured-output errors retain the actual attempt list. Agentic Scheme and Planner audits aggregate
attempts across semantic-validation retries without de-duplicating them, so one entry represents one
real HTTP attempt. Validation attempt counts now report the actual loop count rather than the maximum
configured count.

The normal route always starts with sol. Luna is attempted only for retryable transport failures,
HTTP 408/429, or HTTP 5xx. Non-retryable 4xx, invalid structured responses, semantic validation, and
preflight failures do not switch models. The legacy `force_fallback` argument remains signature-
compatible but is rejected as `preflight_failure` without making an HTTP request.

## Deterministic fallback

The existing deterministic Scheme generator remains the fail-closed fallback. Tests verify it is
used after accurately classified provider/preflight failure. The final live probe did not need it,
but route failure never becomes a fabricated provider success.

## Verification

| Gate | Result |
| --- | --- |
| Focused LLM unit tests | **14 passed** |
| Full repository suite | **128 passed, 1 skipped** |
| Ruff (`ruff check .`) | **pass** |
| Diff whitespace check | **pass** |
| Boundary review | **pass** |
| Secret scan | **pass** |

The full-suite skip is the pre-existing conditional live PostgreSQL test because that optional local
environment is unavailable. It is unrelated to WS-P.

The focused suite covers primary success, eligible fallback, exhausted routes, non-retryable no-
fallback behavior, timeout behavior, direct-fallback rejection, explicit preflight classification,
attempt provenance on every HTTP call, schema/parser errors, Scheme schema invariants, retry
aggregation, deterministic fallback, and successful Scheme/Planner construction.

## Contract changes

`CONTRACT_CHANGE_REQUEST`: none.
