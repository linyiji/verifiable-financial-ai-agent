# V17 Frontend Test and Fixture Preparation

Status: `TEST_DESIGN_READY_IMPLEMENTATION_NOT_AUTHORIZED`

```text
PLAYWRIGHT_IMPLEMENTED = NO
TEST_FIXTURES_IMPLEMENTED = NO
PHASE4_E2E_EXECUTED = NO
FRONTEND_V17_IMPLEMENTATION_AUTHORIZED = NO
```

## Purpose and test authority

This document prepares future tests and fixture contracts only. It does not select or create a
Playwright path, mutate application code, start Phase 4, or convert any Demo result into integrated
evidence. The actual repository has no approved browser-test file or Playwright configuration; FE-E
must choose a real path only after implementation is authorized.

Test authority is append-only:

- `P4-E2E-001..100` retain their existing definitions;
- `P4-E2E-015` remains the retired tombstone;
- `P4-E2E-101..106` retain the V8.1 interaction-delta definitions;
- V17 reserves `P4-E2E-107..112` for interactions `071..076`;
- `P4-SSE-001..020` and `P4-ID-001..028` remain unchanged;
- document-local `V17-TP-*` and `V17-FX-*` IDs below organize preparation and are not replacements
  for stable release gates.

## Activation boundary

| Scope | Future execution rule |
|---|---|
| Phase 4 Core | Real backend, no request fulfillment/intercepts, exact frozen candidate/backend; all applicable gates must pass |
| Phase 5 | `DEFINED_NOT_ACTIVATED`; no release blocker in Phase 4 |
| Deployment | Runs only when its separately frozen deployment condition is activated |
| Demo | Separate `@demo-contract`/Presenter result; never included in real-backend aggregate |

Phase 4 Core selection is:

- `P4-E2E-001..057`, excluding tombstone `015`;
- Full/Core variants of `058..061`;
- `063..096` and `098`;
- `101`, `102`, `105`, `106`, `107`, and `108`;
- `P4-ID-001..020` and `023..028` (26 Core assertions) plus all `P4-SSE-001..020`.

`P4-ID-021..022` remain `PHASE5_ACTIVATED` and `DEFINED_NOT_ACTIVATED` for Phase 4.

Phase 5 remains inactive for Incremental/versioned Object behavior, including the Incremental variant
of `058`, versioned-view variant of `059`, `062`, `097`, `103`, `104`, and real Scenes 05/06.
Deployment `099..100` retains its separate activation. Presenter `109..112` executes only in an
explicit Presenter-enabled Demo build and never contributes to the Phase 4 Core result.

Proposed namespace reconciliation after the six append-only additions:

```text
P4_E2E_DEFINED_IDS = 112
P4_E2E_PHASE4_CORE_UNIQUE_IDS = 101
P4_E2E_PHASE5_ONLY_IDS = 4
P4_E2E_DEPLOYMENT_ONLY_IDS = 2
P4_E2E_DEMO_ONLY_IDS = 4
P4_E2E_TOMBSTONES = 1
P4_SSE_DEFINED = 20
P4_SSE_PHASE4_CORE = 20
P4_ID_DEFINED = 28
P4_ID_PHASE4_CORE = 26
P4_ID_PHASE5 = 2
PRODUCTION_INTERACTIONS = 71
PRESENTER_ENABLED_DEMO_INTERACTIONS = 75
HISTORICAL_INTERACTION_UNION = 76
```

The four Phase 5-only unique E2E IDs are `062`, `097`, `103`, and `104`; shared IDs `058` and `059`
also carry Phase 5 variants without ceasing to have Phase 4 Core variants. Deployment-only IDs are
`099..100`; Presenter Demo-only IDs are `109..112`; `015` is the tombstone.

## Prepared acceptance suites

| Plan ID | Future suite | Required oracle | Stable gates |
|---|---|---|---|
| `V17-TP-001` | Clean toolchain/candidate custody | Exact Node/npm/lock/source/build fingerprints; clean candidate; Node 24 commands pass | build/typecheck/runtime; Change Request freeze |
| `V17-TP-002` | Object/Run identity and contamination | Every Phase 4 O/R/T/C/V/A/K/E/X/L/P ID closes under exact Run/Object; B substitution fails closed | E2E 005–009, 057–061, 063, 070–073; ID 001–020/023–028; ID 021–022 Phase 5 only |
| `V17-TP-003` | Prepare/regenerate | Request/response retain exact Object/Goal; honest Scheme-only preview; new draft on regenerate; no Tasks/Run/start | E2E 017–024, 074; ID 001–003 |
| `V17-TP-004` | Confirm and exactly-once auto-start | One click/key/body creates one Run, one `run.created`, one scheduler admission/start across double click, response loss and backend restart | E2E 025, 075, 102; ID 004–005 |
| `V17-TP-005` | Global list and Run projection | List/detail revision consistency; atomic snapshot/watermark; immutable plan; actual graph/version; status/progress/result availability | E2E 002, 005–007, 026–036, 076–077, 088–091; ID 006–010 |
| `V17-TP-006` | SSE source/reconnect/reconcile | Real event stream; named events; one exact-Run subscription; replay after watermark; duplicate/gap/order/race/terminal/restart convergence | E2E 068, 077–088; SSE 001–020; ID 009–010/023–024 |
| `V17-TP-007` | Claim Trace round trip | Report→Claim→Review→Task→Calculation→Evidence→Execution→same original report anchor; no first/latest/text fallback | E2E 042–043, 048–055, 063, 094; ID 011–020/024–027 |
| `V17-TP-008` | A/B/C consistency and safe C | A/B/C share Object, Run, canonical record and released refs; C contains safe observable facts and no hidden reasoning | E2E 047, 053–054, 069, 095; ID 015–020/028 |
| `V17-TP-009` | ReportArtifact group/delivery | Separate HTML/PDF identity/availability; authorized exact bytes match type/size/hash; tamper/cross-owner rejected | E2E 045–046, 072–073, 096; ID 019/025–027 |
| `V17-TP-010` | Released financial equality | Visible value/unit/period/actuality/as-of equal backend display projection; no financial formula/unit inference in frontend | E2E 069, 092–093, 095; ID 012–018 |
| `V17-TP-011` | Focus, overlays, scroll, history | Topmost Escape, focus trap/restore, exact invoking control, background scroll, Back/Forward, refresh and tab/anchor context restore | E2E 010–011, 037–039, 044, 049–055, 063–064; SSE 014; ID 020/023–024 |
| `V17-TP-012` | Deep links and missing targets | Exact URL tuple opens exact entity/anchor; absent/mismatched target is typed unavailable and never repaired with latest/first | E2E 048–055, 060–064, 073, 094, 098; ID 020/023–027 |
| `V17-TP-013` | Disabled/unavailable/error/retry | Backend reason is adjacent/programmatic; retry repeats exact read and retains identity; dismiss is presentation-only | E2E 046, 051–052, 067, 086, 103, 105–106 |
| `V17-TP-014` | Execution filter/search | Filter/search only safe normalized same-canonical rows; combined state, empty state, keyboard, clear and focus are correct; no domain mutation | E2E 107–108; E2E 047/054/063/069/095 |
| `V17-TP-015` | Presenter and Demo isolation | Default false; production navigation/bundle/authority graph excludes Presenter/Demo; enabled controls mutate Demo presentation only | E2E 065–066, 109–112; separate Demo result |
| `V17-TP-016` | Accessibility and responsive | Name/role/value, roving tabs, status/live regions, keyboard/focus, disabled reasons, no content/action loss at governed viewports | all affected interactions; E2E 010–012, 026–055, 059, 101–112 |
| `V17-TP-017` | Runtime/console/network hygiene | Zero application console exceptions/warnings, unhandled rejections, failed unexpected requests, duplicate subscriptions or leaked timers | every real Scene and negative suite |
| `V17-TP-018` | Interaction and file-delta completeness | Production 71/71, Presenter-enabled 75/75, all-mode historical union 76/76; actual file delta within approved matrix | interaction audit; independent Delta Audit |

## Fixture contracts

Fixtures are immutable, versioned contract inputs with source class and identity manifest. A Demo
fixture is always watermarked `DEMO` and cannot appear in a real suite.

### Common fixture envelope

```ts
interface V17FixtureEnvelope<T> {
  fixtureId: `V17-FX-${string}`;
  fixtureVersion: 1;
  fixtureKind: "BACKEND_CONTRACT" | "NEGATIVE_CONTRACT" | "DEMO";
  backendContractVersion: string;
  schemaVersion: string;
  objectId: string | null;
  runId: string | null;
  projectionRevision: number | null;
  projectionSequence: number | null;
  sha256: string;
  value: T;
}
```

`fixtureKind` describes the seed/decoder fixture only. Browser-result provenance remains a separate
field with the approved values `INTEGRATED`, `PUBLIC_REAL`, `LIMITED_REAL`, `OFFLINE_INTEGRATED`,
`CHAOS_SSE`, or `DEMO`. A backend seed fixture never turns an integrated browser result into a fixture
or Demo result.

Real-suite contract fixtures must be generated/approved against the frozen backend schema and then
used at decoder/adapter unit boundaries. Browser real suites must observe actual backend responses;
they may seed backend state through an approved setup API but may not intercept/fulfill frontend
requests.

### Required fixture set

| Fixture ID | Contents and invariant | Used by |
|---|---|---|
| `V17-FX-001-OBJECT-RUN-A` | Object `O_A`, live and released Runs, exact list/detail revisions, owner fields | TP-002/005/012 |
| `V17-FX-002-CONTAMINATION-B` | Distinct `O_B/R_B/T_B/C_B/V_B/A_B`; every substitution against A must return typed rejection/unavailable | TP-002/007/009/012 |
| `V17-FX-003-PREPARE-FULL` | Goal + unconfirmed Scheme draft, version/hash/expiry, `previewKind=SCHEME_ONLY`, zero Tasks/graph/Run | TP-003 |
| `V17-FX-004-CONFIRM-IDEMPOTENCY` | Exact prepare/confirm keys, canonical request hash, first `201`, replay `200`, conflicting same-key request `409 CONFLICT`, draft consumption, one Run, one `run.created`, one admission and one effective `run.started` before/after response loss/restart | TP-004 |
| `V17-FX-005-RUN-SNAPSHOT` | List item/detail at same revision; ETag; projection revision/sequence; immutable planned graph; actual graph/version; exact Task ratios; backend aggregate fraction/percent; review/result/execution/artifact availability | TP-005/006 |
| `V17-FX-006-SSE-STREAM` | Contiguous named events with wire ID/name, opaque event ID, Run/Task, sequence, payload version/hash, connection number, cursor, client disposition, expected projection hash, heartbeat comments, replay suffix and terminal success/failure | TP-006 |
| `V17-FX-007-SSE-ADVERSARIAL` | Same SSE evidence fields plus exact/conflicting duplicate, gap, delayed/out-of-order, unknown event/schema, invalid/ahead/cross-Run/filter-mismatched cursor and snapshot race; covers SSE 001–020 | TP-006/013 |
| `V17-FX-008-TRACE-CLOSURE` | Exact O/R/T/C/V/A/K/E/X/L/M tuple; optional Proof only under backend policy; exact Review check and safe execution event IDs; multiple Tasks with nullable backend-selected primary; opaque scoped report/review/task/execution anchors and exact original report anchor | TP-002/007/008/012 |
| `V17-FX-009-FINANCIAL-06547` | `canonical_value="0.6547"`, `canonical_unit="RATIO"`, `display_value="65.47"`, `display_unit="%"`, full period/actuality/as-of/currency/lineage | TP-008/010 |
| `V17-FX-010-ARTIFACT-GROUP` | One report identity; independent HTML/PDF IDs/availability/authorized bytes, media type, byte count, digest, renderer/time and Claim anchors; wrong-Run/media/size/hash, expired authorization and unavailable-representation variants | TP-007/009 |
| `V17-FX-011-AVAILABILITY-ERROR` | All six availability states and every frozen error code/recovery directive; non-available requires stable reason, terminal `PENDING` is invalid, details are redacted | TP-003/005/009/013 |
| `V17-FX-012-EXECUTION-SAFE` | At least one row for each of eight actor types; original noncontiguous sequences; safe typed I/O/observable operation/status/duration/provider/model/usage/refs; combined actor/query, empty/pagination/stale-race expectations and synthetic private-field canary | TP-008/014/017 |
| `V17-FX-013-HISTORY-CONTEXT` | URL/history index/Object/Run/tab/Claim/Task/anchor tuple, overlay stack, invoking/destination focus, scroll and highlight before/after close, Back, Forward, refresh and cleared-storage fresh-context deep link | TP-007/011/012 |
| `V17-FX-014-DEMO-PRESENTER` | Six Demo-watermarked Scenes, stable step IDs, initial/final bounds and selector/reset/previous/next expectations; zero production HTTP/SSE/domain mutations; Demo IDs never accepted as real | TP-015 |

Every fixture manifest must state nullability, identity keys, ownership, allowed enum values, expected
unknown handling, and recovery oracle. Updating fixture data or an oracle after Candidate freeze creates
a new Candidate/evidence coordinate.

## Detailed oracles

### Prepare and exactly-once Start

The test captures exact Object, Goal, draft/version/hash, confirmation body, and idempotency key. The
Start control becomes busy after its first activation and does not generate another key. Same body/key
after lost response and backend restart resolves to the same Run. Persistence contains one Run, one
draft consumption, one `run.created`, and one scheduler admission/`run.started`. The browser lands on
that exact Run. No second Start control or request exists.

### Snapshot/SSE convergence

The snapshot includes the greatest durable sequence it represents. Events after that watermark are
buffered/replayed exactly once. A reconnect supplies the last committed cursor and yields precisely the
persisted suffix. Stale duplicates change nothing; identity-conflicting duplicates fail; gaps and
out-of-order frames pause mutation and trigger reconciliation. Success is terminal only after
`run.completed` following `release.completed`; failure uses `run.failed`; a terminal reopen does not
loop reconnect.

SSE coverage remains unchanged and complete: `001..005` cover real source/envelope/isolation/order/
heartbeat; `006..009` disconnect and numeric/opaque gap-free resume; `010..014` duplicate/order/race/
refresh/Back-Forward subscription lifecycle; `015..017` success/failure terminal and terminal reopen;
`018` invalid, ahead, unknown, cross-Run, or filter-mismatched cursor; `019` same-Task generated
capability reconnect; and `020` graph lifecycle reconnect with one atomic graph version. Execution
filter/search tests never substitute for an SSE gate.

### Financial and A/B/C authority

The DOM-visible metric is `65.47%` because the backend supplies display value `65.47` and display unit
`%`. The browser/source audit rejects multiplication, ratio-to-percent inference, currency/actuality/
period/release/proof inference, or hard-coded product metrics. Report A, Review B, and Execution C all
carry the same Object, Run, canonical record, and released relations. C contains no hidden reasoning.

### Trace/navigation restoration

Each jump records the exact identity tuple and origin. Closing or browser Back restores route, tab,
overlay stack, focused invoking control, scroll position, and highlight. Forward and refresh reopen the
same target from URL plus backend state. Missing data yields the exact unavailable state; no latest Run,
first Claim, title, symbol, or text match is accepted.

### Execution actor filter — `P4-E2E-107`

The selectable values are exactly `ALL`, `AGENT`, `LLM`, `DATA`, `TOOL`, `CODE`, `RUNTIME`, `REVIEW`,
and `PROOF`, exposed as one named keyboard-operable selection group with programmatic selection.
Filtering retains exact Object/Run/canonical identity, route, text query, and original event sequence
values. It announces empty results, resets its result cursor, and prevents stale responses from
overwriting newer state. A Trace target hidden by the filter is reported as hidden; no closest event is
focused. No Run/history/release mutation or private/raw field exposure/search is allowed.

The backend freeze must choose a cursor-bound `actor_type` query or prove the complete safe execution
collection is loaded before local filtering. Client-only filtering of one page is a failing incomplete
result.

### Execution free-text search — `P4-E2E-108`

Search is limited to a frozen allowlist of normalized labels and exact Task/Evidence/Calculation/Proof
IDs; it never uses `JSON.stringify` over arbitrary input/output/meta. Query and actor filter intersect
within the exact Run/canonical record. Changes reset cursor and abort/quarantine stale responses. Clear
restores the safe collection, retains focus, and performs no domain mutation. Loading, count, empty,
error, retry, and unsupported-query states are accessible. Retry repeats the exact read/query.

A synthetic private-field canary must yield zero matches and remain absent from HTTP projections, DOM,
accessibility tree, logs, screenshots, and retained evidence. Evidence stores only its hash and absence
assertions, never actual secrets, prompts, or hidden reasoning.

### Presenter isolation

In the production-default build, navigation has only New Task, Runs, and Research Objects. Static and
runtime reachability scans find no Demo data source, Demo transport/store/fixture, Presenter scenario,
`RUN-DEMO`, data-URL artifact, or Demo fallback in authoritative code paths. Enabling Presenter creates
a separately labeled Demo build/result; selector/reset/previous/next change only presentation state and
make no production HTTP/SSE/domain mutations.

Presenter evidence records two independent axes:

```text
exposure_condition = VITE_ENABLE_PRESENTER == "true"
source_class = DEMO
result_class = DEMO_UX_ONLY
real_release_aggregate_membership = none
```

Selector chooses a valid watermarked Scene; reset returns its deterministic first step; previous/next
move exactly one step and are disabled/no-op at their respective bounds.

## Accessibility and responsive matrix

Run every affected page, overlay, loading/error/unavailable state, A/B/C tab, Execution filter/search,
and enabled/disabled Presenter control at the approved desktop viewports:

`1024`, `1280`, `1366`, `1440`, and `1920` CSS px wide × `900` high, DPR 1, 100% zoom.

Any additional V17 viewport must be added by approved reference/change revision. Verify visible focus,
logical order, keyboard operation, roving arrows where defined, topmost Escape, accessible names,
programmatic selected/disabled/busy/current/value state, status/error announcements, touch target and
overflow/content/action preservation appropriate to the governed viewport.

## Evidence requirements

Every future run records candidate/backend SHA and tree state, contract/reference/fixture/oracle hashes,
browser/OS/viewport/mode, network provenance, exact test IDs, timestamps, raw reports/screenshots/logs,
console/network output, retries, and result. Required failures, skips, `BLOCKED`, flaky retry-only pass,
Demo substitution, or qualified pass do not pass the Phase 4 aggregate.

The independent Delta Audit must rerun or authenticate all required evidence against the exact frozen
Candidate and verify that Scenes 05/06 remain Phase 5 rather than false Phase 4 claims.
