# Phase 4 SSE / Runtime Chaos Acceptance Plan

Status: **AUTHORITATIVE ACCEPTANCE DESIGN — NOT IMPLEMENTED — NOT EXECUTED**  
Owner: **D2 — SSE / Runtime Chaos Acceptance**  
Scope: `P4-SSE-001..020`, their end-to-end browser execution, and their Backend support dependencies

```text
P4_SSE_GATES_DEFINED=20
P4_SSE_GATES_REFERENCED=20/20
P4_SSE_IMPLEMENTED=NO
P4_SSE_EXECUTED=NO
PHASE4_ACCEPTANCE_IMPLEMENTATION_AUTHORIZED=NO
```

This plan specifies future executable acceptance tests. It does not authorize a production route,
transport, reducer, proxy, Playwright suite, database change, or test implementation. All twenty
SSE gates are `PHASE4_CORE_REQUIRED`. Once activated for a release candidate, each result is
exactly `PASS` or `FAIL`; `NOT_IMPLEMENTED` is a preparation status only.

## 1. Authority and input reconciliation

The acceptance Coordinator owns gate IDs, activation, evidence sufficiency, binary results, and the
release aggregate. This D2 plan preserves, rather than weakens, those decisions.

| Input | Coordinate / state | Use in this plan |
|---|---|---|
| Coordinator brief | supplied 2026-09-04 | Current activation, source-class, candidate-binding, chaos, restart, and stop rules |
| Approved Frontend V8.1 | `FRONTEND_BASELINE_V8.1@d854c97789c98cca14fee3f4b3d7f00e0d5d137a` | Immutable parent behavior and interaction ledger |
| V8.1 E2E deltas | Git object `codex/frontend-v8-1-baseline-promotion`; parent hashes declared in the delta files | `015` tombstone; `101..106` append-only definitions and activation |
| Existing SSE design | `docs/integration/PHASE4_SSE_BROWSER_ACCEPTANCE.md` | Frozen gate meanings `P4-SSE-001..020` and fetch-stream decision |
| Existing E2E / Scene / identity design | `docs/integration/PHASE4_E2E_ACCEPTANCE_SPEC.md`, activation matrix, browser scenario matrix, identity matrix | Parent gate and exact identity crosswalk |
| Phase 4 Backend drafts | API schema, runtime-event, identity/error/availability and blocker-closure documents, all `NOT_FINAL` | Provisional expected wire shapes only; never treated as a final contract |
| V17 preparation outputs | `V17_FRONTEND_CONTRACT_PREPARATION.md` and dependency matrix; provisional/blocked | Proposed transport and normalized-state input only; no Candidate authority |
| Contract preaudit and blockers | `PHASE4_CONTRACT_PREAUDIT.md`, `PHASE4_CONTRACT_BLOCKERS.md` | Open implementation-entry blockers `P4-CB-001..003`, `010`, and `012` |
| Repository implementation and tests | API route, SSE serializers, event stores, PostgreSQL tests, V8.1 transport/reducer | Architecture inventory and gap evidence only; no existing result is grandfathered |

The V8.1 append-only delta is authoritative over the older working-tree parent documents:

- interaction `015` / `P4-E2E-015` is `RETIRED_TOMBSTONE` and is never executed or reused;
- interactions `065..070` map to `P4-E2E-101..106`;
- `101`, `102`, `105`, and `106` are Phase 4 Core; `103` and `104` are Phase 5 activated;
- interaction `069` / `P4-E2E-105` (real-read retry preserving route identity) is the only V8.1
  addition directly mapped by this SSE plan. Dismiss (`070` / `106`) remains a browser-alert
  contract and is not claimed as SSE recovery proof.

The final V17 Integration Readiness Review, governed V17 Candidate, and final Phase 4 Backend
Contract Freeze are not available. The tests below remain contract-parametric at the explicitly
named uncertainty points and must not be implemented until those inputs exist.

## 2. Non-negotiable end-to-end contract

Final SSE proof is this entire chain:

```text
manifested browser build
  -> production fetch-stream transport
  -> actual Backend GET /api/research-runs/{run_id}/events
  -> durable PostgreSQL RuntimeEvent log
  -> disconnect / replay / permitted complete-frame chaos
  -> identity, cursor, duplicate, order, and gap guards
  -> authoritative atomic snapshot reconciliation
  -> terminal lifecycle and durable reopen
```

A Backend replay unit test, serializer test, reducer test, fixture replay, JSON poll, mocked stream,
HAR, fulfilled browser request, service worker response, or Demo transport is useful lower-layer
evidence but cannot pass a `P4-SSE` gate.

The frozen stream choice is browser `fetch`, `Accept: text/event-stream`, explicit
`Last-Event-ID`, a standards-compliant incremental SSE parser, bounded reconnect, and abort support.
Native `EventSource` is not the Phase 4 transport because the first subscription after an atomic
snapshot must carry an explicit cursor and the Backend emits named `event:` fields.

### 2.1 Authoritative frame

For every business frame the final event contract must preserve:

```text
id: <decimal RuntimeEvent.sequence>
event: <RuntimeEvent.type>
data: <complete RuntimeEvent JSON>

```

The JSON envelope has exact `event_id`, `run_id`, optional `task_id`, `type`, RFC 3339 timestamp,
positive integer `sequence`, and object `payload`. Wire `id` is the numeric replay cursor;
`data.event_id` is the opaque durable event identity. They are never conflated. Heartbeats are SSE
comments and never domain events.

No payload schema, event alias, graph-version field, failure code, or terminal-reopen status not
present in the final freeze may be invented by the harness.

### 2.2 Source classes

| Source class | D2 use |
|---|---|
| `INTEGRATED` | Direct actual Backend SSE, cursor compatibility, terminal behavior, and browser projection |
| `CHAOS_SSE` | The same actual Backend stream through the byte-preserving fault proxy |
| `PUBLIC_REAL`, `LIMITED_REAL`, `OFFLINE_INTEGRATED` | Rerun applicable baseline behavior for an activated deployment profile; these labels retain their declared truth |
| `DEMO_UX_ONLY` | May regress Demo interaction/reducer behavior; cannot satisfy any `P4-SSE` gate |

`OFFLINE_INTEGRATED` uses the real Backend, PostgreSQL, and SSE with a manifested Backend fixture. It
is never called live. No public/limited Run may silently fall back to a fixture.

## 3. Future harness topology

One attempt provisions a clean, isolated environment bound to the evidence manifest:

```text
                         +--> control browser --> Backend SSE (direct)
Run R / PostgreSQL ------|
                         +--> chaos browser --> byte-preserving SSE proxy --> Backend SSE

independent capture client --> atomic projections / terminal records / read-only persisted log
restart supervisor ---------> Backend process and PostgreSQL service lifecycle
```

### 3.1 Control browser

The control browser uses the manifested production Frontend build and production transport with no
frame fault. It observes the exact same Run as the chaos browser. It is a useful differential
witness, not the final truth oracle. A control browser defect cannot bless an equally defective
chaos browser.

### 3.2 Chaos browser and proxy

The chaos browser uses the same build, identity, authorization scope, route, locale, and Run. Its
SSE URL alone is routed through a loopback proxy controlled outside the application bundle. The
proxy has no application button, event generator, reducer hook, database writer, or business-state
backdoor.

The proxy reassembles arbitrary network chunks until a complete SSE frame boundary, records the
upstream bytes, then applies only the declared rule. A disconnect is a transport close immediately
after a recorded complete-frame boundary; it is not an operation on the frame body.

### 3.3 Independent oracle client

The oracle client captures the atomic Run projection and the durable RuntimeEvent log through a
reviewed read-only acceptance boundary. If the final contract uses a database query rather than an
API for the event-log witness, the exact migration revision, table/column set, transaction isolation,
and query must be frozen and content-hashed. It cannot mutate events or repair the candidate.

### 3.4 Restart supervisor

The supervisor records process/container IDs, image/build hashes, stop/start times, exit reasons,
health transitions, database revision, and storage-volume identity. It may stop and start the
manifested Backend and PostgreSQL services; it may not rebuild or change either candidate during an
attempt.

## 4. Allowed and forbidden chaos

The only frame operations are:

| Operation | Exact permission |
|---|---|
| `DROP` | Withhold one observed complete real frame from the downstream connection |
| `DELAY` | Hold one observed complete real frame without editing it |
| `DUPLICATE` | Deliver an already observed complete real frame more than once, byte-for-byte |
| `REORDER` | Release two or more held complete real frames in an order different from upstream arrival |

`PASS` is a ledger classification for an unmodified delivery, not a fault operation. Closing the
connection after complete frame N is the disconnect trigger used by resume tests.

Forbidden operations include creating a frame, changing any byte, truncating a delivered frame,
combining frames, changing line endings, changing `id`/`event`/`data`, changing a payload or
timestamp, inserting a Demo event, fulfilling an SSE request, replaying a frame from another Run,
or writing an event directly into the database. Deliberate cross-Run frame substitution is not
accepted as a consumer-defense test because it violates the allowed fault boundary; Run isolation
is tested using genuine simultaneous Run A and Run B streams and fail-closed route/identity tests.

Rules are selected by observed connection number, exact sequence, exact event type, or a predicate
over already parsed allow-listed envelope fields. A rule never chooses or edits a business outcome.
Capability, graph, success, and failure events must be caused by normal Backend execution from
authorized acceptance inputs.

## 5. Evidence ledgers

Every attempt conforms to `PHASE4_ACCEPTANCE_EVIDENCE_MANIFEST_SPEC.md` and retains failed attempts.
The following D2 fields are mandatory.

### 5.1 Connection ledger

One row per request/connection records:

```text
connection_id, browser_context_id, page_id, route_run_id
request URL/template, method, Accept, Last-Event-ID presence/value
authorization decision without credential material
response status, Content-Type, Cache-Control, Backend build identity
opened_at, first_byte_at, closed_at, close initiator/reason
terminal event observed, reconnect attempt number/backoff decision
proxy rule-set hash, source_class
```

Unexpected polling, response fulfilment, service workers, multiple active subscriptions for one
page/Run, wrong Run URLs, or a build-identity mismatch fails the affected gate.

### 5.2 Complete-frame hash ledger

`complete_frame_hash = SHA-256` over the exact upstream bytes from the first byte after the previous
frame boundary through the terminating blank line. Business frames and comment frames are typed
separately. Each row adds:

```text
upstream_occurrence_id, upstream_arrival_index, upstream_hash
downstream_occurrence_id(s), downstream_delivery_index(es), downstream_hash(es)
proxy_operation, delay duration, drop/duplicate/reorder parent relation
wire_id, wire_event, data.event_id, run_id, task_id, sequence
payload_semantic_hash, parse disposition, client disposition
browser projection hash before/after, reconciliation request reference
```

Every delivered hash must equal an upstream hash from that same connection/Run. `DUPLICATE` may
produce multiple downstream occurrences referring to one upstream occurrence. `DROP` produces none.
`REORDER` changes only delivery indices. Any downstream frame with no parent, or any unequal
pre/post hash, fails the entire `CHAOS_SSE` attempt.

### 5.3 Apply ledger

The production-visible browser extractor records, at every commit/reject/reconcile boundary:

```text
expected_next_sequence, observed sequence/event_id
disposition = APPLIED | DUPLICATE_IGNORED | BUFFERED | QUARANTINED | RECONCILE
last_committed_sequence, applied_event_id set hash
route Object/Run/Task/Claim identity
visible Task/path/review/result/artifact cardinalities
connection state and stale/reconnecting indicator
```

The extractor uses accessible UI plus stable, non-authoritative identity attributes. No hidden store
setter or test-only application state is allowed. Reducer-level tests may supplement this evidence
but cannot replace the browser observation.

### 5.4 Snapshot ledger

Every atomic snapshot records request/response times and hashes, ETag or immutable equivalent,
`projection_schema_version`, `projection_revision`, `projection_sequence`, Run/Object identity,
graph version, terminal fields, and normalized domain projection. `projection_sequence=N` means the
same transactionally consistent body includes every projection mutation through N and none after N.
Request timestamps are diagnostic only and never substitute for the watermark.

### 5.5 Browser and error evidence

Retain route/history state, focus target, scroll position when applicable, semantic DOM snapshot,
trace, console messages, page errors, unhandled rejections, failed requests, and alert retry actions.
Expected disconnect/network messages must match an allow-listed safe code. An unexpected console or
page error fails the gate even if final pixels look correct.

## 6. Snapshot and convergence oracle

Let `S_N` be an atomic Backend snapshot at `projection_sequence=N`; `L[1..M]` the independently
captured durable event log at the final tail; `C_M` the normalized control projection; `H_M` the
normalized chaos projection; and `B_M` the final atomic Backend snapshot.

The initial handshake must satisfy:

```text
install S_N
subscribe with Last-Event-ID: N
apply only N+1, N+2, ... in order and once
on duplicate/gap/order/schema/identity error: stop reduction and reconcile
after terminal: obtain/validate B_M, then stop reconnecting
```

The final convergence oracle is conjunctive:

```text
L.sequence == [1..M] and event_id values are unique
snapshot coverage [1..N] + accepted suffix [N+1..M] == [1..M]
C_M == normalize(B_M)
H_M == normalize(B_M)
C_M == H_M
control and chaos last_committed_sequence == M
terminal snapshot/event identity agrees, when terminal
```

Normalization may remove only a reviewed allow-list of presentation state: active animation,
connection arrival timestamp, current focus, active tab when not a domain fact, and equivalent
ephemera. It must retain:

- Run status/stage/progress, timestamps, terminal outcome, and safe failure;
- Task IDs, status, progress, dependencies, results, and observable activity IDs;
- immutable planned graph; actual graph ID/version/content/mutation history;
- Correction, Replan, capability gap/build/registration identities and status;
- Review/result/proof/execution/report/artifact availability and exact IDs;
- projection revision/sequence, committed sequence, and applied event-ID set hash.

The control browser is not accepted as the sole oracle. DOM-to-DOM equality without `B_M` and
`L[1..M]` fails.

### 6.1 Duplicate and heartbeat state hash

Before and after an expected no-op, compute a canonical semantic hash from the retained browser
projection. A heartbeat requires identical hashes. A duplicate requires identical domain state and
cardinalities; connection diagnostics may change. In particular, a duplicate may not add another
Task, path mutation, review/check, Claim, capability lifecycle row, execution row, artifact, or
timeline event.

### 6.2 Recovery timing

The final contract must freeze connection, heartbeat, retry/backoff, reconciliation, and terminal
quiescence budgets. Tests wait on observable predicates rather than arbitrary sleeps. Exceeding a
required budget is a `FAIL`, not `BLOCKED` or a waived flake. Before those budgets are frozen the
harness remains unimplemented.

## 7. Mandatory execution protocols

### 7.1 Base Run protocol

1. Bind the exact manifested Backend/Frontend pair, database revision, contract hashes, and browser.
2. Create or select distinct Objects A and B through ordinary authorized APIs/UI; capture opaque IDs.
3. Prepare/confirm Run A through the normal workflow; do not insert RuntimeEvents.
4. Install the atomic projection for Run A and open direct control and chaos subscriptions.
5. Capture frames, snapshots, browser state, and durable log concurrently.
6. Execute the gate-specific fault only after its trigger frame is complete and hashed.
7. Reconcile both browsers to a fresh Backend snapshot and evaluate the exact gate oracle.
8. Preserve evidence and every failure attempt.

Where a gate requires capability, graph, or terminal failure behavior, use an acceptance input that
causes the real Backend to take that path. If the path cannot be produced without an event generator
or test-only business backdoor, the activated gate fails for missing evidence.

### 7.2 Deterministic snapshot-race protocol

To create the race without altering HTTP or fabricating events:

1. obtain and install a real nonterminal snapshot `S_N`;
2. deliberately delay only the browser's call to subscribe;
3. observe through the control/durable ledger that real event `N+1` committed;
4. subscribe with `Last-Event-ID: N`;
5. require the replay to begin at `N+1` and converge.

No projection response is delayed, edited, or fulfilled by the harness.

### 7.3 PostgreSQL and Backend restart overlay

Restart proof is mandatory, not inferred from reconstructing a repository object in one process.

**Nonterminal replay:** after chaos browser commits N, close the stream at a complete-frame boundary;
stop the Backend; stop PostgreSQL cleanly; restart PostgreSQL on the same acceptance volume and exact
revision; restart the same Backend build; wait for health; require the browser to reconnect with N,
replay the durable suffix, and converge. Run continuation/recovery must follow the final Backend
contract; the harness does not invoke an internal scheduler method.

**Terminal reopen:** after success and failure terminal variants, stop/restart Backend and PostgreSQL,
open a wholly new browser context at the exact URL, and require terminal snapshot/history/cursor
recovery with no reconnect/heartbeat loop. Review, result, A/B/C, and artifact persistence are
validated by their owning suites and referenced here for terminal convergence.

At least one nonterminal restart cut is placed at a real capability or graph lifecycle checkpoint.
The other lifecycle still receives its dedicated disconnect/replay test. If both lifecycles occur
in the restart Run, the post-restart snapshot must retain both sets of supporting identities. This
shared overlay proves restart replay without duplicating destructive environment work merely to
repeat the same persistence assertion.

## 8. Gate contracts

All mappings below are dependencies/crosswalks, not permission for one lower-layer result to pass
another gate. `P4-BE` numbers are the Coordinator's provisional namespace and remain subject to the
authoritative D1 catalogue without changing the `P4-SSE` meanings.

### `P4-SSE-001` — Actual SSE source

- **Activation/source:** `PHASE4_CORE_REQUIRED`; `INTEGRATED`.
- **Preconditions/setup:** manifested production browser and Backend; nonterminal R; Demo sources
  unreachable; no request fulfilment, HAR, service worker response, or polling.
- **Action:** open R and observe the production transport request.
- **PASS:** exact R endpoint returns success with actual `text/event-stream`, reviewed cache headers,
  and Backend build identity; at least one visible runtime change is causally tied to a captured real
  frame. The request is a streaming fetch with abort support.
- **FAIL:** Demo/static/JSON source, poll-derived runtime state, wrong R, fulfilled response, wrong
  media type, buffered whole-response behavior, or unmanifested server.
- **Evidence:** candidate and HTTP/connection ledgers, first complete frame, browser state before/after.
- **Maps:** `P4-BE-018`; `P4-E2E-065`, `068`; `P4-ID-009`; `SCENE-01..04`;
  interactions `005` and `026`.

### `P4-SSE-002` — Wire envelope and parser

- **Activation/source:** Core; `INTEGRATED`.
- **Setup/action:** capture every business/comment frame across arbitrary real network chunk
  boundaries and parse with the production parser.
- **PASS:** for every business frame, decimal wire `id == data.sequence`, wire
  `event == data.type`, required envelope fields and final frozen payload version validate, R is
  exact, timestamps are valid, and a complete frame is dispatched once. Heartbeats are comments.
- **FAIL:** truncated/coalesced data, `onmessage`-only loss of named events, wire/data mismatch,
  invented defaults, unsupported payload coerced to a known type, or heartbeat domain mutation.
- **Evidence:** raw complete-frame hashes, parsed envelope ledger, parser disposition, console errors.
- **Maps:** `P4-BE-018`; `P4-E2E-068`, `083`; `P4-ID-009`; `SCENE-01..04`;
  interaction `026`.

### `P4-SSE-003` — Run isolation

- **Activation/source:** Core; `INTEGRATED`.
- **Setup/action:** create O-A/R-A and O-B/R-B; stream both simultaneously in independent browser
  contexts and inspect exact page/network projections.
- **PASS:** every A frame owns R-A and optional Task belongs to R-A; every B frame owns R-B; neither
  browser applies or retains the other Run/Object; closing/navigating A cannot affect B.
- **Negative:** unauthorized or cross-owned stream route fails closed under the final identity/error
  contract. No cross-stream frame substitution is performed by the proxy.
- **FAIL:** mixed frames, shared-state leakage, title/symbol/latest fallback, foreign Task, or foreign
  response body exposure.
- **Evidence:** two connection/frame ledgers, O/R/T closure records, negative HTTP response, DOM scan.
- **Maps:** `P4-BE-030`; `P4-E2E-071..073`; `P4-ID-009`, `025..027`;
  `SCENE-01..04`; interactions `005`, `027`, `034`, and `042` where present.

### `P4-SSE-004` — Producer order and durable uniqueness

- **Activation/source:** Core; direct `INTEGRATED` control path.
- **Setup/action:** consume a complete uninterrupted real Run and independently read its durable log.
- **PASS:** producer sequences are the strict contiguous range `1..M`, ordered on the wire, unique
  per R, and opaque `event_id`s are non-empty/unique; frame envelopes equal persisted events.
- **FAIL:** gap, decreasing/duplicate sequence, duplicate event ID, cross-Run row, or wire/persistence
  mismatch. Fault-proxy disorder cannot be used to fail or pass producer order.
- **Evidence:** persisted-log hash, direct frame ledger, equality diff.
- **Maps:** `P4-BE-008`, `018`; `P4-E2E-083`; `P4-ID-009`; `SCENE-01..04`;
  interaction `026`.

### `P4-SSE-005` — Heartbeat is transport-only

- **Activation/source:** Core; `INTEGRATED`.
- **Setup/action:** keep a real nonterminal stream idle for the frozen heartbeat interval without
  pausing or fabricating business work.
- **PASS:** at least one real heartbeat comment is observed; semantic browser hash, committed cursor,
  Run/Task state, timeline, and progress do not change; connection liveness may change.
- **FAIL:** heartbeat parsed as an event, cursor advance, domain mutation, activity fabrication, or
  absent heartbeat when the final contract requires it.
- **Evidence:** comment frame, before/after semantic hashes, connection liveness ledger.
- **Maps:** Backend SSE transport support (D1 disposition required); `P4-E2E-083`; no direct
  `P4-ID`; `SCENE-01..04`; no exclusive interaction.

### `P4-SSE-006` — Disconnect retention

- **Activation/source:** Core; `CHAOS_SSE`.
- **Setup/action:** after browser commits a complete nonterminal frame N, close the connection at
  that boundary while the direct control continues.
- **PASS:** UI retains the last valid projection, marks connection stale/reconnecting, advances no
  domain state from timers, and starts only the bounded reconnect path.
- **FAIL:** reset to zero/planning, fabricated progress, released state, blank identity, infinite
  connection fan-out, or unexpected console failure.
- **Evidence:** frame N hash, close boundary, before/after snapshot, active connection count.
- **Maps:** `P4-BE-011`; `P4-E2E-078`; `P4-ID-009`, `023`; `SCENE-01..04`;
  interaction `026`.

### `P4-SSE-007` — Numeric `Last-Event-ID` resume

- **Activation/source:** Core; `CHAOS_SSE` plus Backend restart overlay.
- **Setup/action:** disconnect after last committed N; let real events commit; permit automatic
  production reconnect.
- **PASS:** the next request sends exact header `Last-Event-ID: N`; the first replayed business
  sequence, when present, is `N+1`; no `<=N` event mutates state; reconnect remains exact R.
- **FAIL:** missing/wrong cursor, query or local guessed cursor contrary to the final contract,
  replay from zero, skip of N+1, cross-Run suffix, or state regression.
- **Evidence:** connection pair, request header, persisted suffix, apply ledger.
- **Maps:** `P4-BE-011`, `017`; `P4-E2E-079`; `P4-ID-009`, `023`;
  `SCENE-01..04`; interaction `026`.

### `P4-SSE-008` — Opaque `event_id` resume compatibility

- **Activation/source:** Core; browser-context `INTEGRATED` fetch using actual Backend SSE.
- **Setup/action:** after R has a durable immutable suffix, issue one request with numeric sequence N
  and another authorized request with the exact opaque `event_id` at N.
- **PASS:** both resolve to byte/semantic-equivalent ordered suffixes beginning N+1. The application
  does not treat opaque ID as the emitted numeric wire `id`.
- **Negative:** use R-A's opaque ID against R-B under `P4-SSE-018`; it must not resolve.
- **FAIL:** differing suffix, prefix replay, global/cross-Run lookup, opaque coercion, or non-SSE path.
- **Evidence:** paired request/frame ledgers and suffix diff.
- **Maps:** `P4-BE-012`; `P4-E2E-080`; `P4-ID-009`, `026`; `SCENE-01..04`;
  no exclusive visible interaction.

### `P4-SSE-009` — Gap-free merge

- **Activation/source:** Core; `CHAOS_SSE` plus Backend restart overlay.
- **Setup/action:** perform snapshot handshake, disconnect at N, allow multiple real events, then
  resume to final tail M.
- **PASS:** snapshot-covered prefix plus pre-cut and replay/live suffix covers persisted `1..M`
  exactly once semantically; final committed cursor is M and browser equals `B_M`.
- **FAIL:** missing/extra event, duplicate mutation, skipped state, unexplained snapshot jump, or
  equality only to the control browser.
- **Evidence:** snapshot, frame/apply/persisted ledgers, exact range proof, final diff.
- **Maps:** `P4-BE-008`, `011`, `017`; `P4-E2E-081`; `P4-ID-009`, `023`;
  `SCENE-01..04`; interaction `026`.

### `P4-SSE-010` — Duplicate idempotence

- **Activation/source:** Core; `CHAOS_SSE`.
- **Setup/action:** duplicate an already observed complete real business frame after its first
  occurrence is committed; use a frame with an observable entity/timeline effect.
- **PASS:** the second occurrence is `DUPLICATE_IGNORED`; cursor and domain-state hash do not regress;
  all listed entity/timeline cardinalities remain unchanged; final state equals Backend.
- **FAIL:** second Task/history/review/Claim/capability/execution/artifact row, repeated status
  transition, cursor regression, or proxy byte difference.
- **Evidence:** one upstream occurrence, two equal downstream hashes, before/after hashes and counts.
- **Maps:** `P4-BE-008`, `018`; `P4-E2E-082`; `P4-ID-008..010`, `023`;
  `SCENE-01..04`; interactions `026`, `033` where the duplicated frame affects history.

### `P4-SSE-011` — Out-of-order and gap defense

- **Activation/source:** Core; `CHAOS_SSE`.
- **Subcase A:** delay N, deliver N+1, then N using complete real frames.
- **Subcase B:** drop N and deliver N+1.
- **PASS:** N+1 is not speculatively applied over an expected N; the client quarantines/buffers per
  the frozen policy, marks stale, starts one authoritative reconciliation, ignores a later stale
  frame, resumes from the snapshot cursor, and converges.
- **FAIL:** state rolls forward/backward by arrival order, gap is silent, local guessing fills a
  frame, multiple repair loops race, or final state differs from Backend.
- **Evidence:** upstream/downstream order/hash proof, apply dispositions, reconciliation snapshot,
  final diff.
- **Maps:** `P4-BE-007..009`, `018`; `P4-E2E-084`, `088`; `P4-ID-009`, `023`;
  `SCENE-01..04`; interactions `026`, `029..036` when graph frames are used.

### `P4-SSE-012` — Snapshot race closure

- **Activation/source:** Core; `INTEGRATED` (or `CHAOS_SSE` when run through the manifested proxy).
  The source class records the actual topology; client-side subscription timing alone is not
  mislabeled as frame chaos.
- **Setup/action:** execute the deterministic protocol in §7.2 using atomic `S_N`; observe real N+1
  before subscription.
- **PASS:** request carries N, replay begins N+1, every later real event is applied once, projection
  revision/sequence are coherent, and both browsers converge to Backend.
- **FAIL:** timestamp-based cursor, uncoordinated Run/Task/graph snapshots, missed N+1, double apply,
  or snapshot claiming an event whose mutation is absent.
- **Evidence:** snapshot response/timing/hash, durable commit N+1, subscription header and final diff.
- **Maps:** `P4-BE-007..009`, `011`; `P4-E2E-077`, `088`;
  `P4-ID-001`, `004`, `007..010`, `023`; `SCENE-01..04`; interaction `026`.

### `P4-SSE-013` — Nonterminal hard refresh

- **Activation/source:** Core; `CHAOS_SSE` plus Backend restart overlay.
- **Setup/action:** hard-reload the exact Run route after nonterminal N while control continues.
- **PASS:** old subscription aborts; local reducer authority is discarded; one new atomic snapshot
  installs; one new stream starts strictly after its cursor; Object/Run/Task/tab identity remains
  exact; final state equals Backend and control.
- **Negative/retry:** a transient snapshot/SSE error exposes the application alert; interaction
  `069` / `P4-E2E-105` retries the exact authoritative read with route identity retained.
- **FAIL:** local-only reconstruction, stream from zero without a frozen reason, duplicate active
  subscription, latest-Run repair, Demo substitution, or failed retry identity.
- **Evidence:** pre/post navigation/connection ledgers, snapshot, alert/retry network rows, final diff.
- **Maps:** `P4-BE-007..009`, `011`, `017`; `P4-E2E-087`, `088`, `105`;
  `P4-ID-023`, `027`; `SCENE-01..04`; interactions `063` and `069`.

### `P4-SSE-014` — Back/Forward subscription lifecycle

- **Activation/source:** Core; `CHAOS_SSE`.
- **Setup/action:** navigate R-A to another page or R-B, then Back and Forward while both Runs may
  continue.
- **PASS:** each navigation aborts the obsolete subscription; the visible route has exactly one
  active stream for its exact R; snapshot/cursor restore exact identity, focus, scroll, and tab;
  obsolete Run events cannot mutate the current page; no navigation creates a domain request.
- **FAIL:** leaked concurrent subscription, shared singleton switches identity, duplicate mutation,
  missing history restore, or latest/title fallback.
- **Evidence:** browser history and connection timelines, active-count witness, O/R state scans.
- **Maps:** `P4-BE-007`, `011`; `P4-E2E-063`, `098`; `P4-ID-024`, `025`;
  `SCENE-01..04`; interaction `063`.

### `P4-SSE-015` — Successful terminal close

- **Activation/source:** Core; direct `INTEGRATED` and restart variant.
- **Setup/action:** let a real R satisfy Backend review/proof/release gates and reach success.
- **PASS:** exactly one `release.completed` precedes exactly one `run.completed` for R; the latter is
  the last business frame; server closes; browser validates one final atomic released snapshot;
  Results enable only from valid Backend release closure; no reconnect occurs in the frozen
  quiescence window.
- **FAIL:** release after terminal, close before terminal, multiple terminal events, heartbeat/retry
  after intentional close, completed-looking UI without release closure, or mixed identities.
- **Evidence:** event/frame order, stream close reason, final projection, release identity refs,
  zero-reconnect ledger.
- **Maps:** `P4-BE-010`, `015`, `017`; `P4-E2E-076`, `085`, `088`, `098`;
  `P4-ID-009`, `015`, `017..019`, `023`; `SCENE-01..04`; interactions `026`, `040`,
  `044`, and `047` where exercised.

### `P4-SSE-016` — Failure terminal close

- **Activation/source:** Core; `INTEGRATED` and restart variant.
- **Setup/action:** use an ordinary controlled acceptance input that causes a real Backend terminal
  failure; do not inject `run.failed` or directly set status.
- **PASS:** exactly one `run.failed` for R is the last business frame and closes the stream; final
  snapshot is FAILED with a safe reason; Results/artifacts remain unavailable; browser stops
  reconnecting; fresh reads remain FAILED.
- **FAIL:** persisted FAILED without `run.failed`, success tail, raw exception leakage, released
  result availability, reconnect loop, or Demo success substitution.
- **Evidence:** causal input, event/frame log, close, final availability responses, console/network.
- **Maps:** `P4-BE-010`, `016`, `017`; `P4-E2E-076`, `086`, `088`, `098`;
  `P4-ID-009`, `023`; `SCENE-01..04` shared negative corpus; interaction `026`.

### `P4-SSE-017` — Terminal reopen and terminal cursor

- **Activation/source:** Core; `INTEGRATED` with Backend/PostgreSQL restart and new-browser variants.
- **Setup/action:** for one successful and one failed R, reopen by hard refresh and a wholly new
  browser context before and after the §7.3 restart.
- **PASS:** atomic snapshot preserves exact terminal event ID/sequence and outcome; durable event
  history is readable; the client either does not open a stream or the server immediately closes at
  an at-terminal cursor exactly as selected by the final freeze; no heartbeat/reconnect loop occurs.
- **FAIL:** terminal state depends on old browser memory, terminal cursor hangs, history disappears,
  failed becomes released, success loses release identity, or automatic latest-Run redirect.
- **Evidence:** pre/post-restart snapshot/log hashes, new-context trace, connection count and close.
- **Maps:** `P4-BE-015..017`; `P4-E2E-085..088`, `098`;
  `P4-ID-006`, `009`, `015`, `017..019`, `023`; `SCENE-01..04`; interaction `063`.

### `P4-SSE-018` — Invalid, unknown, cross-Run, and ahead cursor

- **Activation/source:** Core; browser-context `INTEGRATED` fetch.
- **Variants:** malformed cursor; negative numeric; unknown opaque ID; R-A opaque ID used on R-B;
  numeric tail+1 and a much-larger ahead cursor.
- **PASS:** error is returned before a successful stream body; no event prefix/body from R is
  exposed; no replay-from-zero, heartbeat hang, or cross-Run resolution occurs. Under the provisional
  draft, malformed/negative/unknown/cross-Run are `400 INVALID_CURSOR` and ahead is
  `409 CURSOR_AHEAD`, both with `SNAPSHOT_RELOAD`; the final freeze must select exact status/envelope
  before implementation.
- **FAIL:** HTTP 200 followed by generator exception, any business frame, cursor clamping, empty-ID
  fallback, indefinite heartbeat, raw `KeyError`/`ValueError`, or foreign metadata.
- **Evidence:** request cursor, response status/safe envelope/body length, zero-frame ledger, logs.
- **Maps:** `P4-BE-013`, `014`, `030`; `P4-E2E-073`, `079`, `080`;
  `P4-ID-009`, `026`, `027`; `SCENE-01..04` shared negative corpus; no exclusive interaction.

### `P4-SSE-019` — Capability lifecycle resume

- **Activation/source:** Core; `CHAOS_SSE`; eligible for the shared restart cut in §7.3.
- **Setup/action:** cause the real Backend to enter its approved generated-capability path for
  original Task T; cut once inside validation and once at the §7.3 restart point.
- **PASS:** the final frozen real vocabulary and payload identities replay in exact order. The
  provisional successful order is
  `capability.gap_detected -> task.waiting_for_capability -> capability.build_requested ->
  capability.build_started -> capability.generated -> capability.static_validated ->
  capability.sandbox_started -> capability.test_passed -> capability.financial_validated ->
  capability.approved -> capability.registered -> task.resumed`. All records retain R/T; approval
  alone does not resume T; registration precedes same-T resume; graph Task count/version do not
  change; final projection equals Backend.
- **Negative:** nonterminal build failure/retry may not fail or resume T prematurely; absent real
  lifecycle cannot be filled with Demo `capability.validating`.
- **FAIL:** fabricated lifecycle frame, new Research Task, premature RUNNING, lost supporting IDs,
  changed graph, wrong order, or restart loss.
- **Evidence:** full lifecycle/frame/persistence ledger, T/graph before/after, restart and final diff.
- **Maps:** `P4-BE-017`, `018`; `P4-E2E-081..083`, `091`, `098`;
  `P4-ID-008`, `010`, `023`; `SCENE-01` and any activated real capability path;
  interactions `026..028`.

### `P4-SSE-020` — Graph lifecycle resume

- **Activation/source:** Core; `CHAOS_SSE`; eligible for the shared restart cut in §7.3.
- **Setup/action:** cause a real approved replan; cut after a complete graph event but before the
  corresponding `graph.version_changed`; separately apply delay/reorder to complete graph frames.
- **PASS:** sparse frames never fabricate a Task or dependencies; partial state is stale/quarantined;
  one authoritative snapshot yields the exact Backend Task/edges/mutation history and one atomic
  version increment; planned graph is byte/semantically unchanged; replay/restart creates no
  duplicate Task or mutation.
- **FAIL:** frontend template Task, planned-graph mutation, partial edge application presented as
  current, two version increments, cycle/unknown dependency, duplicate history, or restart loss.
- **Evidence:** planned/actual snapshots, graph frame hashes/order, replan/Task IDs, restart ledger,
  final graph diff.
- **Maps:** `P4-BE-007..009`, `017`, `019`; `P4-E2E-081..084`, `088`, `089`, `098`;
  `P4-ID-007..010`, `023`; `SCENE-02`; interactions `029..036`.

## 9. Backend support-gate dependency request

D2 does not redefine the Coordinator's `P4-BE` namespace. The authoritative Backend catalogue must
retain at least these dependencies or allocate an explicit equivalent with no semantic loss:

| Provisional Backend gate | Required D2 support | SSE gates |
|---|---|---|
| `P4-BE-006` runtime auto-start | normal confirm admits real runtime without a test-only execute action | `001`, lifecycle gates |
| `P4-BE-007` atomic RunProjection | one transactionally consistent, identity-closed snapshot | `011..014`, `020` |
| `P4-BE-008` projection sequence | event watermark reflects the same aggregate mutations | `004`, `009..013`, `020` |
| `P4-BE-009` projection revision | monotonic committed projection revision / immutable equivalent | `011..013`, `020` |
| `P4-BE-010` list/detail consistency | terminal list/detail state agrees after reconciliation | `015..017` |
| `P4-BE-011` numeric cursor replay | strict suffix after numeric sequence | `006`, `007`, `009`, `012..014` |
| `P4-BE-012` opaque cursor replay | exact same-Run event-ID resolution | `008` |
| `P4-BE-013` invalid cursor | typed malformed/negative/unknown/cross-Run rejection before stream success | `018` |
| `P4-BE-014` cursor ahead | typed ahead-of-tail recovery response, never wait forever | `018` |
| `P4-BE-015` terminal success | exactly one durable success event after release | `015`, `017` |
| `P4-BE-016` terminal failure | every failed terminal path emits exactly one durable failure event | `016`, `017` |
| `P4-BE-017` PostgreSQL restart replay | event/projection/terminal durability through actual service restart | `007`, `009`, `013`, `015..017`, `019`, `020` |
| `P4-BE-018` event normalization | versioned total event/payload map; unknown fails closed | `001..004`, `010`, `011`, `019` |
| `P4-BE-019` sparse graph recovery | graph event group forces exact projection reconciliation | `020` |
| `P4-BE-030` cross-object rejection | stream/cursor authorization and same-Run resolution | `003`, `018` |

Coordinator disposition: no new Backend gate is allocated. SSE HTTP framing, heartbeat
non-mutation and complete-frame normalization are mandatory subcases of `P4-BE-011` and
`P4-BE-018`; terminal-at-cursor close/reopen is a mandatory subcase of `P4-BE-015..017`. This
keeps transport behavior inside existing owners without weakening `P4-SSE-001`, `002`, `005`, or
`017`.

## 10. Consolidated crosswalk

| SSE | P4-BE | P4-E2E | P4-ID | Scene | Interaction |
|---|---|---|---|---|---|
| 001 | 018 | 065, 068 | 009 | 01–04 | 005, 026 |
| 002 | 018 | 068, 083 | 009 | 01–04 | 026 |
| 003 | 030 | 071–073 | 009, 025–027 | 01–04 | 005, 027, 034, 042 |
| 004 | 008, 018 | 083 | 009 | 01–04 | 026 |
| 005 | 011, 018 | 083 | — | 01–04 | — |
| 006 | 011 | 078 | 009, 023 | 01–04 | 026 |
| 007 | 011, 017 | 079 | 009, 023 | 01–04 | 026 |
| 008 | 012 | 080 | 009, 026 | 01–04 | — |
| 009 | 008, 011, 017 | 081 | 009, 023 | 01–04 | 026 |
| 010 | 008, 018 | 082 | 008–010, 023 | 01–04 | 026, 033 |
| 011 | 007–009, 018 | 084, 088 | 009, 023 | 01–04 | 026; 029–036 when graph |
| 012 | 007–009, 011 | 077, 088 | 001, 004, 007–010, 023 | 01–04 | 026 |
| 013 | 007–009, 011, 017 | 087, 088, 105 | 023, 027 | 01–04 | 063, 069 |
| 014 | 007, 011 | 063, 098 | 024, 025 | 01–04 | 063 |
| 015 | 010, 015, 017 | 076, 085, 088, 098 | 009, 015, 017–019, 023 | 01–04 | 026, 040, 044, 047 |
| 016 | 010, 016, 017 | 076, 086, 088, 098 | 009, 023 | 01–04 negative | 026 |
| 017 | 015–017 | 085–088, 098 | 006, 009, 015, 017–019, 023 | 01–04 | 063 |
| 018 | 013, 014, 030 | 073, 079, 080 | 009, 026, 027 | 01–04 negative | — |
| 019 | 017, 018 | 081–083, 091, 098 | 008, 010, 023 | 01 / real path | 026–028 |
| 020 | 007–009, 017, 019 | 081–084, 088, 089, 098 | 007–010, 023 | 02 | 029–036 |

`P4-E2E-015` and interaction `015` appear nowhere because they are tombstones.
`P4-E2E-099..100` are not activated by this plan. Phase 5 interactions `067..068` /
`P4-E2E-103..104` and real `SCENE-05..06` remain `DEFINED_NOT_ACTIVATED`. A later Phase 5 candidate
reruns applicable core SSE regression without changing these gate meanings.

## 11. Repository readiness findings

The current code is useful design evidence but cannot pass this plan:

| Observed primitive | Positive seed | Acceptance gap |
|---|---|---|
| `apps/api/routes.py` | actual Run-scoped `StreamingResponse`, `Last-Event-ID` header, SSE media type, no-cache | cursor validation occurs inside the generator after response construction; no frozen content negotiation/auth/recovery response |
| `src/application/events.py` | closes after observed `run.completed` or `run.failed` | at-terminal cursor with no suffix can heartbeat forever |
| `src/runtime/sse.py` | canonical serializer and heartbeat | generic stream never terminates; lower-level only |
| in-memory / PostgreSQL event stores | ordered replay; numeric and opaque lookup; DB sequence trigger | ahead numeric cursor is accepted; current errors are raw exceptions; exact error envelope not frozen |
| PostgreSQL runtime tests | real DB sequence allocation, replay, repository reconstruction, released restore | no HTTP, browser, chaos proxy, actual Backend process restart, PostgreSQL service restart, or terminal-cursor proof |
| default API composition | usable local API shell | in-memory SQLite plus service-default in-memory event/checkpoint stores; not Phase 4 durable composition |
| application failure path | persists FAILED Run | inspected catch path does not emit `run.failed`, so failure terminal closure is not proved |
| V8.1 `SSERuntimeTransport` | explicit fail-closed placeholder | opens no stream and has no initial cursor/reconnect/terminal callback |
| V8.1 reducer | exact Run check and opaque event-ID dedupe | applies stale/gapped events before order recovery; event/payload vocabulary conflicts; no terminal events |
| Frontend package | typecheck/runtime/build scripts in approved branch | no committed Playwright Phase 4 suite or chaos proxy |

These are implementation gaps, not reasons to lower the gates.

## 12. Uncertainties that must be frozen, not invented

| ID | Uncertainty | Required authority before harness implementation |
|---|---|---|
| `SSE-U-001` | Final event vocabulary, payload schemas/versions, task-ID requirements, and unknown-event compatibility behavior | Phase 4 Backend Final Event Contract plus V17 adapter map |
| `SSE-U-002` | Exact atomic projection route/body, commit protocol, ETag/immutable equivalent, revision semantics | Final Backend Projection Contract closing `P4-CB-001` |
| `SSE-U-003` | Exact HTTP status and versioned error envelope for malformed, negative, unknown opaque, cross-Run, and ahead cursor | Final identity/error/SSE freeze; draft `400 INVALID_CURSOR` / `409 CURSOR_AHEAD` is provisional |
| `SSE-U-004` | Exact terminal reopen protocol when cursor equals/exceeds the terminal sequence: no request, immediate successful close, or typed terminal response | Final SSE terminal contract; test must select one exact behavior, not accept an open-ended alternative |
| `SSE-U-005` | Heartbeat interval, retry/backoff limits, recovery deadline, terminal quiescence window | Final transport configuration included in Candidate manifest |
| `SSE-U-006` | Authorized read-only durable-event-log oracle and transaction isolation | Backend acceptance-observability freeze; no production mutation endpoint |
| `SSE-U-007` | Deterministic normal input that produces terminal failure and generated-capability lifecycle without a business backdoor | Final Backend acceptance corpus and runtime contract |
| `SSE-U-008` | V17 production transport state machine, abort/route ownership, stable browser observability, and alert retry integration | Approved V17 Change Request, readiness review, and immutable Candidate |
No uncertainty changes the required observable outcome. It prevents premature test implementation.
The former `SSE-U-009` gate-ownership question is resolved in §9 and is not part of the open count.

## 13. Attempt result and failure history

Each attempt declares exact candidate pair, database revision, contract hashes, source class,
environment, R/O/T identities, fault-rule hash, start/end timestamps, result, and evidence refs.
All activated `P4-SSE-001..020` are binary. A timeout, missing real path, missing ledger, proxy hash
mismatch, absent restart evidence, or absent final Backend snapshot is `FAIL`.

A deterministic failed attempt remains in the append-only bundle. A later pass does not erase it.
If source, contract, migration, build, test oracle, or fault schedule changes, it is a new Candidate
or catalogue revision. If neither changes, the rerun must prove the environmental cause; an
unexplained fail-then-pass is not acceptance.

## 14. Entry and stop conditions

Do not implement or execute this plan until all of the following exist:

1. immutable Phase 3 Backend Candidate;
2. Backend Independent Audit `PASS`;
3. Financial Semantics Audit `PASS`;
4. approved Phase 4 Backend Final Contract Freeze, including all `SSE-U-*` wire choices;
5. completed V17 preparation, approved Change Request, immutable Frontend Candidate, and delta audit.

At that time, bind one same-candidate pair, perform a focused contract delta, and implement the
harness without weakening these oracles. Until then:

```text
P4_SSE_ACCEPTANCE_DESIGN_READY=YES
P4_SSE_ACCEPTANCE_IMPLEMENTATION_AUTHORIZED=NO
P4_SSE_ACCEPTANCE_EXECUTED=NO
OPEN_ACCEPTANCE_SEMANTIC_CONFLICTS=0
OPEN_UPSTREAM_SSE_CONTRACT_UNCERTAINTIES=8
SCENE_01_04_SSE_COVERAGE=4/4
SCENE_05_06_STATE=DEFINED_NOT_ACTIVATED
```
