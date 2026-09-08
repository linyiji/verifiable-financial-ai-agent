# Phase 4 VS01 frontend acceptance

[简体中文](README.zh-CN.md)

This isolated Playwright package observes the production frontend journey:

```text
Research Object -> Research Goal -> AI Research Scheme -> Confirm
-> automatic exact Run -> Run Workspace -> Research Path
```

The seven production-counting specs use real frontend, Backend HTTP, and Backend SSE traffic. They do
not install Playwright response routes, fulfil responses, seed a private store, create a service
worker, or fabricate a business payload. Chromium DevTools Protocol is used only to add latency to
one exact, already-observed projection URL; the delayed response body still comes from the real
Backend.

Reachable frontend module discovery is fail-closed: at least one same-origin module must be found,
every selected module must be fetched successfully, and its exact bytes receive a harness-computed
SHA-256. No self-reported build hash is accepted as source evidence. The browser ledger scans
bounded public request headers/bodies plus public business-response headers and every finite body
asynchronously. Fetch/XHR
and JSON responses outside the known Object/Run routes are scanned too, while binding evidence stays
limited to the reviewed API base and known frozen routes. Only sizes and deterministic hashes are
retained. Active `text/event-stream` bodies are deliberately not buffered without bound; their
headers are scanned and their Run/cursor/event behavior is asserted by the live SSE specs.

## Clean bootstrap and commands

Use Node 24 exactly. The package has `engine-strict=true`, and each runnable entry point also checks
the Node major. From a clean checkout in this directory:

```sh
node --version # must print v24.x.x
npm ci
npm run install:chromium
npm run check
VS01_FRONTEND_URL=http://127.0.0.1:4173 \
VS01_BROWSER_SCENARIO_FILE=/absolute/path/to/generated-scenario.json \
VFAS_VS01_SECRET_SENTINEL=<runner-random-secret-sentinel> \
npm run test:real
```

`npm run check` runs the pure contract/scenario tests, audits the real spec for forbidden mocking,
collects (but does not execute) the seven Playwright specs, and verifies the JSON annotation map.
`test:real` is strict: unavailable product prerequisites and malformed scenarios fail rather than
skip. The orchestrator may set `VS01_BROWSER_ARTIFACT_DIR` to relocate the JSON, HTML, trace,
screenshot, and video artifacts.

## Scenario input

The runner writes a non-secret JSON file outside the source tree. IDs must be captured from the
isolated PostgreSQL-backed setup, never inferred from display labels:

```json
{
  "schemaVersion": "phase4-vs01-frontend-scenario/v1",
  "object": {
    "objectId": "OBJ-A-...",
    "symbol": "...",
    "companyName": "..."
  },
  "goalText": "...",
  "asOf": "2026-09-05",
  "missingRunId": "RUN-...-ABSENT",
  "missingErrorCode": "NOT_FOUND",
  "alternate": {
    "objectId": "OBJ-A-...",
    "runId": "RUN-A-ALTERNATE-...",
    "taskId": "TASK-A-ALTERNATE-..."
  },
  "foreign": {
    "objectId": "OBJ-B-...",
    "runId": "RUN-B-...",
    "taskId": "TASK-B-...",
    "sentinels": ["a B-only safe display sentinel"]
  },
  "financial": {
    "objectId": "OBJ-C-...",
    "runId": "RUN-C-RELEASED-...",
    "metricId": "METRIC-C-ADVERSARIAL-...",
    "adversarialProperty": "NUMBER_STRING_ROUNDTRIP_CHANGES"
  },
  "backendUnavailableFrontendUrl": "http://127.0.0.1:4174",
  "primaryApiBaseUrl": "http://127.0.0.1:8080/api",
  "unavailableApiBaseUrl": "http://127.0.0.1:18080/api"
}
```

`primaryApiBaseUrl` and `unavailableApiBaseUrl` are reviewed expected public API bases. The request
ledger proves that every observed business request uses the appropriate exact origin and path
prefix. The harness deliberately does not prescribe a runtime-config endpoint, binding identifier,
or frontend build-hash schema.

The frontend deployment may bind its API at runtime or at compile time. For compile-time binding,
the runner must build and review two separate frontend artifacts and serve them at the two frontend
origins. Changing `VITE_*` while serving an already-built bundle is not a rebind and is not evidence.
For runtime binding, deployment provenance is runner-specific; this harness imposes no runtime-config
endpoint, artifact, ordering, or schema requirement.

`financial` identifies a C/Parent-provided real released Product target. It deliberately contains no
expected numeric value. The test captures `canonical_value` from the exact public result response and
requires that string itself to satisfy `NUMBER_STRING_ROUNDTRIP_CHANGES` (for example, precision or
trailing fractional zeroes that a JavaScript `Number` string round-trip would lose). The runner must
select this real target from reviewed setup/capture evidence; the browser harness does not seed,
rewrite, or fabricate a metric.

`VFAS_VS01_SECRET_SENTINEL` is required at real-suite execution and is deliberately not placed in
the scenario JSON. The runner must inject the same random value into the product processes. DOM,
source, request, response, console, and page-error scans exact-match it, but evidence retains only a
finding code/path or a hash—never the sentinel value.

## Runner requirements

Before executing `npm run test:real`, the Parent runner must:

- select Node 24, run clean `npm ci`, and install the pinned Playwright Chromium;
- launch a primary frontend bound to the live PostgreSQL-backed Backend at `primaryApiBaseUrl`;
- launch a separately reviewed unavailable frontend at `backendUnavailableFrontendUrl`, bound to
  the actually closed/unreachable `unavailableApiBaseUrl`, without browser interception;
- create distinct real Object A and Object B resources, a missing Run ID, and a foreign Object-B
  Run/Task for wrong-resource quarantine (the foreign Run may already be terminal);
- provide a distinct real released `financial` Run/metric through the Product, with configured IDs
  backed by gate-side capture evidence and a wire `canonical_value` satisfying the configured lexical
  property; never put an expected canonical value in scenario JSON;
- immediately before browser execution, create `alternate`: a fresh, nonterminal, sufficiently
  quiescent Run/Task for Object A, distinct from the browser-created happy-path Run A;
- expose in-product SPA `run-navigation-item` links between the two same-Object-A Runs;
- inject one runner-random value as `VFAS_VS01_SECRET_SENTINEL` into both frontend processes, the
  Backend process, and the Playwright process;
- write the exact scenario fields above and retain deployment/build review evidence outside the
  Playwright report; and
- run on Chromium with support for `Network.emulateNetworkConditionsByRule` and
  `appliedNetworkConditionsId` correlation; and
- keep graph serialization on the approved source encoding (`graph_id`, `run_id`, `version`,
  `tasks`) unless C/Parent first reviews and binds a different public encoding. An explicit graph
  `edges` member or `add_edge`/`remove_edge` endpoint member spelling is not silently assumed by
  this harness.

## Seven real specs and control evidence

Each control is annotated exactly once as `vs01-control` in Playwright JSON:

| Real spec | Exact controls |
|---|---|
| Object -> Goal -> Scheme -> Confirm -> automatic Run | `VS01-FE-003` through `VS01-FE-007`, `VS01-DYN-001` |
| Active Run A -> same-Object alternate Run switch plus authentic delayed Run A projection | `VS01-REC-008`, `VS01-ID-003` |
| Browser-offline SSE recovery from last committed cursor | `VS01-REC-009` |
| Wrong-resource network/DOM quarantine | `VS01-FE-008` |
| Typed missing-resource retry/dismiss | `VS01-FE-009` |
| Released adversarial decimal, exact public wire-to-render equality | `VS01-FE-012` |
| Backend unavailable and public-surface/source negatives | `VS01-FE-010`, `VS01-FE-011` |

The switch spec first proves that navigating from browser-created Run A to the fresh same-Object
alternate Run ends the old live A stream, opens the exact alternate stream, and leaves no A Run/Task
state in the alternate workspace. It then uses a targeted CDP latency rule on the authentic A
projection URL, switches back to the alternate before the real A response arrives, waits for that
response and a deterministic Product lifecycle boundary, and proves the alternate URL, Run, Task
IDs, raw Task statuses, progress, parents, and dependencies remain unchanged. The required public
`projection-lifecycle` status identifies the current request epoch, exact accepted
revision/sequence, and exact discarded Run/epoch/revision/sequence with `STALE_RESPONSE`. Observer
evidence stays active until that discard/settlement signal appears; no elapsed-time window decides
acceptance. A public-attribute `MutationObserver` proves no transient A identity or Task state is
rendered while the response is consumed. This is the real integrated evidence for `VS01-ID-003`.

The offline spec proves the exact Run SSE starts at the projection cursor; browser offline moves the
public connection state to `RECOVERING` or `BACKOFF` without changing the Run, creating a Run, or
marking failure; reconnect opens the same Run from the last committed cursor and reaches `OPEN` or a
non-failed `TERMINAL` state.

The financial spec opens the real released target through normal Product UI, captures the exact
`GET /research-runs/{run_id}/result` body, locates exactly one configured metric, and carries its
canonical decimal as a string into visible DOM equality assertions. The string must be adversarial to
JavaScript numeric round-trip. This wire-to-render equality is primary `VS01-FE-012` evidence; served
source regex checks are supplemental defense-in-depth only.

`VS01-FE-008` is intentionally limited to wrong-resource network/DOM quarantine. It does not claim
stale-response behavior.

## Observable public hooks

Controls are located by accessible role/name first. Opaque identities and raw Backend values require
stable, presentation-neutral DOM attributes:

| Hook | Required observable contract |
|---|---|
| `research-object-option` | `data-object-id` |
| `scheme-preview` | `data-object-id`, `data-goal-id`, `data-scheme-id`, `data-draft-id` |
| `confirm-run` | accessible Confirm/Start button with normal disabled/busy behavior |
| `run-workspace` | `data-run-id`, `data-object-id`, `data-goal-id`, `data-scheme-id`, `data-run-status`, `data-run-stage`, `data-projection-revision`, `data-projection-sequence` |
| `research-path` | exact current `data-run-id` |
| `research-task` | `data-run-id`, `data-task-id`, authoritative `data-task-status`, `data-task-progress`, nullable `data-parent-task-id` (empty for null), and `data-dependency-ids` as compact JSON preserving Backend dependency order |
| `runtime-connection` | `role=status`, `aria-live=polite`, `data-run-id`, `data-connection-state`, `data-last-sequence`, `data-stale`; states include `OPEN`, `RECOVERING`, `BACKOFF`, `TERMINAL` |
| `projection-lifecycle` | visible `role=status`; `data-run-id`, canonical integer `data-request-epoch`, `data-settled`; accepted tuple `data-consumed-run-id`, `data-consumed-request-epoch`, `data-consumed-projection-revision`, `data-consumed-projection-sequence`; stale tuple `data-last-discarded-run-id`, `data-last-discarded-request-epoch`, `data-last-discarded-projection-revision`, `data-last-discarded-projection-sequence`, `data-last-discard-reason=STALE_RESPONSE` |
| `run-navigation-item` | real SPA link with `data-run-id` and `/runs/{run_id}` href |
| `result-tab` | accessible Results tab/control that causes the normal released-result request |
| `released-financial-metric` | `data-run-id`, `data-metric-id`, exact string `data-canonical-value`; contains one visible `canonical-financial-value` whose raw text node equals the wire string byte-for-byte |
| `typed-error` | `data-error-code`, and `data-resource-id` when supplied |
| `identity-quarantine` | `data-reason` plus no foreign identity or sentinel rendered |

These are public acceptance observables, not access to reducer/store internals.

## Decoder and public-surface negatives

The draft decoder enforces the exact Goal and Scheme fields in API §5.2, including request-bound
`as_of`/preferences, all seven Scheme arrays, generator metadata, and unconfirmed nullability. The
atomic decoder enforces all 21 top-level fields; the exact eight-field Object and fourteen-field Run;
Goal/Scheme identity and timestamps; planned/actual graph closure; typed Task IDs, parent/dependency
closure, all 12 Task statuses, and progress ratios; the full lifecycle/progress tuple; exact 13-field
PathChange records; availability-wrapped Review/result/artifact/proof/execution summaries; and exact
terminal/release closure. Each projection response must also carry the exact
`"p4:<run_id>:<projection_revision>:<projection_sequence>"` ETag. Graph identity/version and Tasks
use the approved source encoding. Normalized typed
edges are a mechanical view of the authoritative Task `dependencies`; they are checked against the
top-level Task projection without inventing a second Backend edge relation. Unknown fields in shapes
that the frozen contract defines exactly, unsafe public graph members, and incoherent nullability fail
closed.

API §6 leaves the graph member objects abbreviated as `{}` and V17 §6 freezes their semantic
requirements without spelling a separate snake-case edge encoding. The approved source
`PlannedTaskGraph` supplies `graph_id`, `run_id`, `version`, `tasks`, and Task `dependencies`, but no
`edges` member. Accordingly, an explicit graph `edges` field fails closed pending C/Parent review.
API §6 shows `add_node.task_id`; it names `add_edge`/`remove_edge` operations but does not freeze their
endpoint member spelling. Such edge-operation bodies also fail closed until a reviewed Candidate
encoding is bound. This is an explicit C/Parent integration dependency, not a guessed harness schema.

Visible UI text, serialized DOM, reachable frontend source, decoded error envelopes, console errors,
and page errors are checked for Qiji, MIMO, TeamoRouter, FMP, Langfuse, bearer/API-key patterns,
hidden chain-of-thought/scratch/system-prompt terms, raw provider payloads, stack traces, SQL, and
internal paths. Evidence records retain only safe paths, counts, leak codes, and hashes—not raw
possibly sensitive error text. The source scan also rejects frontend financial-computation authority
and Demo fallback markers.

## Frozen authority

- Freeze promotion: `764d76132cfac13d47125e031b280b7894eb249f:docs/integration/FINAL_CONTRACT_FREEZE_PROMOTION.json`
- V17 R2 canonical SHA-256: `fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19`
- Phase 4 contract-set SHA-256: `0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741`
- Primary gates: `P4-E2E-009`, `017..026`, `065..075`, `088`, and `P4-ID-001..005`, `023`, `025..027`.
