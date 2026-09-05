# Phase 4 SSE Browser Acceptance

Status: **AUTHORITATIVE DESIGN — FROZEN — NOT YET IMPLEMENTED**  
Applies to: real Backend Phase 3 runtime semantics and the future Phase 4 browser adapter  
Activation authority: `PHASE4_E2E_GATE_ACTIVATION_MATRIX.md`

All `P4-SSE-001..020` cases and their parent gates `P4-E2E-068`, `077..088` have
`activation_scope = PHASE4_CORE_REQUIRED`. Disconnect, `Last-Event-ID`, resume, ordering,
duplicates, terminal close, browser refresh, and projection reconciliation are therefore Phase 4A
Core requirements. Later Phase 5 and deployment candidates rerun the applicable SSE baseline; no
SSE assertion is deferred merely because a future Scene or deployment mode is inactive.

## 1. Authoritative wire semantics

The observed Phase 3 SSE endpoint is the Run-scoped stream
`GET /api/research-runs/{run_id}/events` with media type `text/event-stream` and
`Cache-Control: no-cache`.

Each business frame is:

```text
id: <RuntimeEvent.sequence>
event: <RuntimeEvent.type>
data: <complete RuntimeEvent JSON>

```

The JSON envelope requires:

```text
event_id: opaque, non-empty, unique within the Run log
run_id: exact owning Run
task_id: null or exact owning Task
type: backend RuntimeEventType
timestamp: date-time
sequence: integer >= 1
payload: object
```

`id:` is the numeric per-Run sequence, while `data.event_id` is the opaque durable event identity.
Both are tested. The browser must not conflate them.

Because the server emits named `event:` fields, a native `EventSource` implementation would need an
explicit listener for every supported event type; an `onmessage`-only client would miss them. More
importantly, native `EventSource` cannot set the initial `Last-Event-ID` header needed after a fresh
snapshot/browser reload. Phase 4 therefore freezes a **fetch-stream SSE transport**: browser `fetch`
with `Accept: text/event-stream`, an explicit `Last-Event-ID` request header, a standards-compliant
SSE frame parser, bounded reconnect policy, and abort support. This remains an actual SSE source;
it is not JSON polling.

The store contract is:

- sequences are per Run, start at 1, and are contiguous/monotonic in a persisted valid log;
- replay returns events with `sequence > resolved Last-Event-ID`;
- a numeric `Last-Event-ID` resolves directly to that sequence;
- an opaque `Last-Event-ID` resolves by exact `event_id` within the requested Run;
- unknown opaque IDs and negative numeric IDs fail; they do not replay from zero;
- no events during the heartbeat interval yields the comment `: heartbeat`, which changes no
  business state;
- a successful stream closes after emitting `run.completed`;
- a failed stream closes after emitting `run.failed`;
- successful release order is `release.completed` before terminal `run.completed`.

## 2. Browser projection contract

Race-free recovery requires an authoritative projection with the event cursor it represents. The
future integrated API must provide either one atomic composite projection or an equivalent
transactionally consistent snapshot containing:

```text
Run + Tasks + planned graph + actual graph + graph version
+ Review/result/artifact availability
+ projection_sequence (last RuntimeEvent sequence included)
+ projection_revision or immutable equivalent
```

The currently observed Phase 3 separate Run/Tasks/Graph reads do not expose a shared cursor. Until
`projection_sequence` or an equivalent atomic protocol exists, refresh/reconnect acceptance is
**BLOCKED**, not approximated with request timestamps.

The required browser algorithm is:

1. Bind the route to exact Run R.
2. Fetch and install atomic snapshot S at cursor N.
3. Open the fetch-stream SSE request with `Last-Event-ID: N`.
4. Validate and apply only live/replayed frames for R with sequence greater than N, in sequence
   order. Events committed after S and before stream admission are replayed by the backend.
5. Track both the last committed sequence and applied `event_id` set.
6. On a duplicate, ignore the state mutation but retain diagnostic evidence.
7. On a gap, out-of-order frame, identity mismatch, parse error or reducer error, mark the projection
   stale and fetch a new authoritative snapshot. Do not guess the missing state.
8. After `run.completed`/`run.failed`, fetch or validate one final snapshot, then stop reconnecting.

Local reducer state is a projection cache only. It is discarded/rebuilt from the backend after a
full browser reload.

## 3. Connection state machine

| Client state | Trigger | Required transition/UX | Forbidden transition |
|---|---|---|---|
| IDLE | open nonterminal R | CONNECTING | local timer starts Run |
| CONNECTING | HTTP 200 + SSE media type | LIVE | treat JSON/static response as stream |
| LIVE | valid next event | LIVE; commit once | apply cross-Run or gap event |
| LIVE | heartbeat comment | LIVE; optional connection indicator only | progress/stage mutation |
| LIVE | network disconnect before terminal | RECONNECTING/STALE; retain last committed UI | reset to planning/zero |
| RECONNECTING | retry | send cursor; validate suffix | reconnect from zero silently |
| RECONNECTING | valid replay/live suffix | LIVE | duplicate visible rows |
| any nonterminal | identity/order/gap/parse error | RECONCILING | speculative state repair |
| RECONCILING | valid snapshot at N | CONNECTING/LIVE from N | merge unrelated Run snapshot |
| LIVE | `release.completed` | RELEASE_PENDING_TERMINAL | close/stop before `run.completed` |
| LIVE | `run.completed` | TERMINAL_SUCCESS; final reconcile; stop | reconnect loop |
| LIVE | `run.failed` | TERMINAL_FAILURE; final reconcile; stop | enable released Results |
| any | navigate to different Run | unsubscribe old R; bind new Run | simultaneous old subscription mutates new page |

## 4. Backend event-to-browser mapping

The adapter must parse the complete backend event vocabulary. Grouping several events into one
visual activity is allowed, but raw type/sequence/IDs remain available in the execution record.

| Backend events | Required semantic effect |
|---|---|
| `run.created`, `scheme.generated`, `scheme.confirmed`, `plan.generated`, `task.created` | establish the created Run and immutable plan; no duplicate entities on replay |
| `run.started`, `run.status_changed` | project backend run lifecycle; presentation labels may be mapped |
| `task.ready`, `task.started`, `task.progress`, `task.completed`, `task.failed` | update the exact Task only; backend progress `0..1` is formatted, not time-inferred |
| `task.self_correcting`, `task.correction_resolved` | one same-Task correction loop and durable history; no new Task |
| `replan.requested`, `replan.approved`, `replan.rejected` | exact Replan state/authority; no graph change before approved graph events |
| `graph.task_added`, `graph.edge_added`, `graph.edge_removed`, `graph.version_changed` | mutate Actual Graph only and then reconcile exact version/edges |
| `capability.gap_detected`, `task.waiting_for_capability` | same Task becomes WAITING_FOR_CAPABILITY with exact gap/capability identity |
| build/static/sandbox/test/financial validation events | append exact capability lifecycle to the same Task's supporting activity |
| `capability.approved`, `capability.registered`, `task.resumed` | approval precedes scoped registration; original Task returns to RUNNING; graph unchanged |
| `evidence.accepted`, `evidence.conflict`, calculation events | update availability/activity only from backend refs; no frontend financial computation |
| Review events | enter Review and expose exact Review record after snapshot/detail read |
| Proof events | show exact policy/status; MUST_PROVE cannot be upgraded by UI |
| `release.completed` | release artifacts/refs are available for final reconciliation; not stream terminal |
| `run.completed` | success terminal and intentional stream close |
| `run.failed` | failure terminal and intentional stream close |

Important translation rules:

- Frontend Demo `correction.resolved` maps from backend `task.correction_resolved`; the wire event
  remains the backend name.
- Frontend Demo `capability.validating` is a UI grouping of static/sandbox/test/financial validation
  events; it is not a backend event.
- Backend `review.resolved` means the run-level Review completed and carries the real Review ID and
  status. It must not be fed into the Demo meaning “one exception was repaired.” Resolved exception
  history is projected from exact Correction/Review records.
- Backend `capability.approved` records approval only. The Task is presented as resumed/RUNNING only
  after `capability.registered` and the exact same-Task `task.resumed` event.
- Frontend Demo `claim.materialized`, `report.started`, and `result.prepared` may not be fabricated in
  a real stream. Claims/results/artifacts come from authoritative backend reads or future real
  backend events.
- Unknown future event types are retained in diagnostics and trigger the reviewed compatibility
  policy. They are never coerced to a known event with guessed semantics.

## 5. Fault-injection boundary

`@chaos-sse` uses a loopback, byte-preserving stream proxy between browser and the real backend. It
may:

- close the TCP/HTTP stream immediately after a complete frame;
- delay a complete frame;
- replay an already observed complete frame;
- release two complete frames in reversed arrival order for the consumer-defense case.

It may not create, edit or fulfil an SSE frame. The acceptance record hashes every upstream and
downstream frame and proves that all delivered frames originated from the backend. Direct
`@public-real` producer-order tests bypass the chaos behavior.

The harness needs a control channel outside the application bundle to choose “disconnect after
sequence N” and inspect connection metadata. No test-only button, event generator or business
state backdoor is added to the frontend.

## 6. SSE browser gate matrix

| SSE gate | Setup/action | Pass condition | P4 gate |
|---|---|---|---|
| P4-SSE-001 Source | open nonterminal R in real suite | response is actual backend SSE for R, not Demo/poll/static | 068 |
| P4-SSE-002 Envelope | capture every frame | wire `id == data.sequence`; `event == data.type`; required JSON fields valid | 068, 083 |
| P4-SSE-003 Run isolation | run A and B concurrently | each stream contains only its exact `run_id`; pages do not cross-apply | 071–073 |
| P4-SSE-004 Producer order | uninterrupted real connection | sequences form strict contiguous suffix; opaque event IDs unique | 083 |
| P4-SSE-005 Heartbeat | keep idle stream through heartbeat | comment observed; zero reducer/domain mutation | 083 |
| P4-SSE-006 Disconnect | proxy cuts after committed nonterminal N | UI retains projection and shows reconnecting/stale state | 078 |
| P4-SSE-007 Numeric resume | automatic reconnect | request carries `Last-Event-ID: N`; first replayed sequence is N+1 | 079 |
| P4-SSE-008 Opaque resume | browser-context streaming fetch sends captured opaque event ID | suffix exactly equals suffix from corresponding numeric sequence | 080 |
| P4-SSE-009 No-gap merge | let R progress after reconnect | combined committed sequences equal persisted backend range exactly | 081 |
| P4-SSE-010 Duplicate | replay real event N, then suffix | N causes no second Task/history/review/timeline or status regression | 082 |
| P4-SSE-011 Delayed order | delay N, deliver N+1, then N | client detects order violation, quarantines and reconciles; final state equals backend | 084, 088 |
| P4-SSE-012 Snapshot race | events occur while snapshot loads | buffer/snapshot protocol applies every event after snapshot cursor exactly once | 077, 088 |
| P4-SSE-013 Refresh | hard reload after nonterminal N | authoritative snapshot installs; resume begins after snapshot cursor; convergence equals control browser | 087–088 |
| P4-SSE-014 Back/Forward | navigate R → other page/Run → Back | old connection is closed; exactly one active subscription for restored R; exact state returns | 063, 098 |
| P4-SSE-015 Success terminal | observe release and completion | `release.completed < run.completed`; stream closes after terminal; one final reconcile; no reconnect | 085 |
| P4-SSE-016 Failure terminal | execute controlled failed Run | last business event is `run.failed`; stream closes; UI failed; Results unavailable | 086 |
| P4-SSE-017 Terminal reopen | refresh/new browser after terminal | no infinite reconnect; snapshot terminal state and full event history/cursor remain readable | 085–087, 098 |
| P4-SSE-018 Bad cursor | negative numeric/unknown opaque cursor via browser fetch | safe 4xx/error; no replay-from-zero and no cross-Run resolution | 073, 079–080 |
| P4-SSE-019 Capability lifecycle | disconnect within validation sequence | after resume, exact order through registration/task resume; same T; no fake Task | 081–083, 091 |
| P4-SSE-020 Graph lifecycle | disconnect between graph events/version event | temporary stale indicator allowed; authoritative reconcile yields one atomic graph version | 081–084, 089 |

## 7. Detailed reconnect assertions

For a disconnect after sequence N:

```text
upstream before cut     = [1..N]
browser committed       = [1..N]
reconnect Last-Event-ID = N
server replay           = [N+1..M]
browser committed final = [1..M]
backend persisted       = [1..M]
```

Equality includes event ID, sequence, type, Run/Task ID, timestamp and payload. Arrival time and
connection number are diagnostic fields and need not equal backend fields.

If the browser has received but not committed a frame when disconnected, it resumes from the last
committed sequence. Receiving that frame again is a valid duplicate and must be idempotent.

The fetch-stream transport's automatic reconnect is tested with the numeric SSE `id`. Opaque resume
is a separate compatibility assertion because the backend accepts an opaque `event_id`, while the
emitted SSE `id:` is numeric.

## 8. Duplicate and ordering assertions

Deduplication requires both protections:

- an already applied `event_id` never mutates state again;
- a sequence at or below the committed cursor never regresses state, even if the opaque ID is
  unexpected.

The following cardinalities are checked before/after a duplicate:

```text
Task IDs
path-change / graph-mutation IDs
Review IDs
Claim IDs
capability gap/build/registration IDs
observable timeline event IDs
artifact IDs
```

For producer-order acceptance, any gap, duplicate sequence, decreasing sequence, duplicate opaque
ID, or mismatched wire/data type fails the backend/SSE gate. For consumer-defense acceptance, an
intentionally reordered delivery must not be applied speculatively; reconciliation must yield the
fresh backend projection.

## 9. Terminal assertions

### Successful Run

1. `release.completed` includes exact canonical/result refs.
2. A later `run.completed` has the same R and released status.
3. The server closes the stream after that event.
4. The browser performs or validates one final authoritative read.
5. Run list/detail, A/B/C, Reviews and artifacts agree.
6. No reconnect request occurs after the intentional close.

### Failed Run

1. `run.failed` is emitted for exact R and is terminal for the stream.
2. The browser presents FAILED plus a safe backend reason/state.
3. A/B/C and downloads remain unavailable unless the backend explicitly exposes a failed-run audit
   view; they are never shown as released.
4. Refresh/new context preserves FAILED from persistence and does not replay a Demo success tail.

## 10. Refresh and projection reconciliation oracle

Run one uninterrupted control browser and one refresh/chaos browser against the same immutable event
log (or two equivalent deterministic backend runs). At each reconciliation checkpoint compare:

```text
Run status/stage and timestamps
Task IDs/status/progress/result refs
planned graph ID/content
actual graph ID/version/content/mutation history
Correction/Replan/Capability identities and status
Review/result/proof/artifact availability
last committed sequence and applied event IDs
```

The final projections must be deeply equal after removing presentation-only fields such as active
tab, focus, animation state and connection arrival timestamps.

## 11. Evidence retained

Each SSE case retains:

- backend commit/run manifest and deployment mode;
- Run ID and sanitized projection response with cursor;
- upstream/downstream frame hashes and parsed envelope ledger;
- connection start/end, disconnect trigger, request URL and `Last-Event-ID` header;
- browser console/page errors;
- final snapshot comparison diff;
- Playwright trace/video only after implementation is explicitly authorized.

Raw secrets, prompts, licensed provider payloads, DSNs and storage paths are excluded.

## 12. Entry condition

SSE browser implementation must not begin until the atomic snapshot/cursor protocol and complete
backend-event adapter mapping are reviewed. The transport choice is frozen here as fetch-stream
SSE; the snapshot wire shape and payload schemas remain integration entry blockers. Without them,
`P4-SSE-012`, refresh and projection reconciliation cannot produce authoritative results. Every
backend terminal path must also durably emit exactly one `run.completed` or `run.failed`; the
currently observed post-scheduler failure path must be proven against that rule before the failure
terminal gate can pass.
