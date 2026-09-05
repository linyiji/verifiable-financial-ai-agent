# Phase 4A Runtime Event and SSE Contract Draft

Status: `PROVISIONAL_CONTRACT_DRAFT`  
Version: `phase4-runtime-event/v1`  
Freeze state: `NOT_FINAL`  
Inspected backend: `codex/phase3-contracts@11fe8173a25ff7ac08bae42340ba7c6fae591be5`

This is an adapter/projection contract. It does not rename or mutate the Phase 3 durable
`RuntimeEventType` vocabulary.

## 1. Observed wire and persistence contract

The existing route is `GET /api/research-runs/{run_id}/events`. It serializes each record as:

```text
id: <RuntimeEvent.sequence>
event: <RuntimeEvent.type>
data: <complete RuntimeEvent JSON>

```

The JSON has `event_id`, `run_id`, optional `task_id`, `type`, `timestamp`, positive per-Run
`sequence`, and unversioned `payload`. Heartbeats are the comment `: heartbeat` and consume no
sequence. PostgreSQL enforces positive, unique `(run_id, sequence)` values and allocates the next
sequence atomically. Replay is ordered and supports either numeric sequence or exact same-Run
opaque `event_id`.

Observed gaps at the inspected snapshot:

- negative/unknown cursor errors arise lazily after `StreamingResponse` construction;
- a numeric cursor ahead of tail heartbeats forever;
- a cursor equal to an already emitted terminal event heartbeats forever;
- post-scheduler assurance/release failures and cancellation may have no terminal event;
- success events can commit before the released aggregate is saved;
- the default ASGI app uses in-memory events/checkpoints rather than the available PostgreSQL
  composition;
- payloads have no schema version and several declared event types have no normal producer;
- `graph.task_added` is sparse and cannot construct a Task.

## 2. `RuntimeEventNormalizedV1`

```json
{
  "event_contract_version":"phase4-runtime-event/v1",
  "event_id":"EVT-...",
  "run_id":"RUN-...",
  "task_id":null,
  "type":"run.started",
  "timestamp":"2026-09-04T00:00:00Z",
  "sequence":18,
  "payload_schema_version":1,
  "payload":{},
  "graph_version":2,
  "effect":"PATCH_PROJECTION",
  "projection_refresh_required":false
}
```

Rules:

- Successful streams carry `X-Phase4-Contract-Version: phase4-core/v1` and
  `X-Phase4-Event-Contract-Version: phase4-runtime-event/v1`; every business data object repeats
  `event_contract_version`. Absent or exact request contract token selects V1. Incompatible,
  repeated, comma-list, empty or malformed tokens return JSON HTTP 409 `SCHEMA_INCOMPATIBLE` before
  SSE headers and emit no frame.
- `type` is the exact raw backend string. The adapter may normalize payload fields, redact unsafe
  details, and add version/graph metadata; it may not create a different business event name.
- `sequence` starts at 1 and is contiguous within one Run. `event_id` is opaque; clients never parse
  the current UUID-like convention.
- `timestamp` is a server-authored RFC 3339 UTC instant.
- `event_contract_version` is the exact string `phase4-runtime-event/v1` and
  `payload_schema_version` is integer `1` for every mapping in this document. An unsupported value
  inside an accepted stream is `UNSUPPORTED_EVENT` and triggers projection recovery. Request-level
  negotiation incompatibility remains the pre-header `SCHEMA_INCOMPATIBLE` case.
- `graph_version` is always present and nullable. It is non-null for graph-semantic events and
  `run.started`, and is the actual graph version after the represented fact unless the event
  explicitly carries `version_before`; unrelated events carry null.
- Unsafe exception text, stack traces, local/internal refs, provider payloads, source code, prompts,
  and hidden reasoning are omitted.
- `effect` is exactly one of `PATCH_PROJECTION|REFRESH_PROJECTION|OBSERVATION_ONLY|TERMINAL`.
  `projection_refresh_required` is true exactly for `REFRESH_PROJECTION` and `TERMINAL`. These two
  fields may be supplied by the public projection or mechanically attached by the shared adapter
  from the frozen table below; they are not new stored business facts.

## 3. Complete raw-to-normalized mapping

Each arrow below preserves the exact name (`raw -> same normalized type`). “Refresh” always means
the atomic Run projection, never multiple unwatermarked reads or polling.

| Raw type(s) | V1 payload/effect |
|---|---|
| `run.created` | `{object_id}`; initialize only through exact Run projection |
| `run.started` | `{}` and `graph_version = actual_graph_version`; Run becomes `RUNNING` only after exact identity validation |
| `run.status_changed` | `{status}` through the total Run map; nonterminal unless explicitly mapped terminal |
| `run.completed` | `{status:"RELEASED"}`; terminal success after release closure |
| `run.failed` | `{status:"FAILED"|"CANCELLED", failure_code, safe_message?}`; terminal non-success |
| `scheme.generation_started` | declared but no normal producer/payload found; emission is unsupported until a versioned payload is approved |
| `scheme.generated` | `{scheme_id, generated_by, generated_at, generation_stage, retrospective}` |
| `scheme.confirmed` | `{scheme_id}` |
| `plan.generated` | `{graph_id, task_count}`; Tasks come from projection |
| `task.created` | `{task_type}`; advisory identity only, never fabricate a Task body |
| `task.ready` | `{}`; exact existing Task only |
| `task.started` | `{attempt}` |
| `task.progress` | discriminated `PROGRESS {progress, progress_scale:"RATIO_0_1", stage?, message_code?}` or `RETRY_SCHEDULED {attempt,error_code}`; retry form does not change progress |
| `task.waiting_for_capability` | `{gap_id}`; same Research Task |
| `task.resumed` | `{gap_id, registration_id, status:"RUNNING"}`; same Research Task |
| `task.self_correcting` | `{problem_code}` plus exact Correction refresh; no raw exception as a reason |
| `task.correction_resolved` | `{correction_id}`; same Task and graph |
| `task.completed` | `{attempt,result_ref?}`; ref only if approved for public use |
| `task.failed` | `{attempt,failure_code,status?,retry_suppressed?}` |
| `replan.requested` | `{replan_id,decision}`; enrich only from exact Replan record |
| `replan.approved` | `{replan_id,decided_by}` |
| `replan.rejected` | declared but no normal producer/payload found; fail closed until approved |
| `graph.task_added` | `{replan_id}`, top-level `graph_version`; quarantine and refresh; frame is not a Task body |
| `graph.edge_added`, `graph.edge_removed` | `{replan_id,source_task_id,target_task_id}`, top-level `graph_version`; refresh graph |
| `graph.version_changed` | `{replan_id,version_before}`, top-level `graph_version = version_after`; refresh establishes one atomic mutation |
| `evidence.accepted` | safe allowlist `{evidence_id,field,producer_task_id?,source_endpoint?,evidence_purpose?,evidence_category?}`; detail comes from accepted Evidence projection |
| `evidence.conflict` | declared but no stable normal payload found; do not infer Review state; refresh or reject unsupported payload |
| `calculation.started` | `{capability_id}` |
| `calculation.completed` | `{calculation_id,capability_id?}`; never display a financial value from this event |
| `capability.gap_detected` | `{gap_id,capability_id,skill_id,requested_by}` |
| `capability.build_requested` | `{gap_id,build_id,attempt,max_attempts,approved_by}` |
| `capability.build_started` | `{build_id,attempt}` |
| `capability.generated` | safe `{build_id,generated_capability_id,implementation_hash}` |
| `capability.static_validated` | `{build_id,implementation_hash}` |
| `capability.sandbox_started` | `{build_id,implementation_hash}` |
| `capability.test_passed` | `{build_id,implementation_hash}` |
| `capability.test_failed` | `{build_id,attempt,failure_code}` |
| `capability.financial_validated` | `{build_id,implementation_hash}` |
| `capability.approved` | `{build_id,registration_id,approved_by,scope}`; approval alone does not resume Task |
| `capability.registered` | `{registration_id,capability_id,capability_version,scope}` |
| `capability.build_failed` | `{gap_id?,build_id?,attempt?,max_attempts?,failure_code,terminal}`; `terminal:false` cannot fail the Task |
| `workspace.created` | declared supporting activity; payload unsupported until reviewed; never a Research Task |
| `capability.generation_started`, `capability.tested`, `capability.validated` | legacy/alternate declared names; preserve raw values but fail closed until producer and payload schemas are approved |
| `review.started` | `{}`; Review stage only |
| `review.required` | declared without a stable normal producer; no exception is fabricated |
| `review.resolved` | `{review_id,status}`; run-level Review completed, not “one exception repaired” |
| `proof.required` | `{proof_id,calculation_id,formula_id,policy_id}` |
| `proof.started` | `{proof_id,backend}`; commitments remain controlled detail |
| `proof.generated` | `{proof_id,backend}`; generation is not verification |
| `proof.verified` | `{proof_id,image_id,receipt_hash,journal_hash,verified,dev_mode}` |
| `proof.failed` | `{proof_id,failure_code,status}` |
| `release.completed` | `{canonical_record_id,result_id}`; release records committed, but not stream terminal |

`correction.resolved`, `capability.validating`, `claim.materialized`, `report.started`, and
`result.prepared` are not backend events and must not appear in the real normalized stream. UI
grouping may use presentation labels without claiming those labels are events.

### 3.1 Exact event-effect disposition

The following grouping is normative for every supported raw type. It is a total reducer contract,
not permission to rename stored events.

| Effect | `projection_refresh_required` | Exact raw types |
|---|---:|---|
| `PATCH_PROJECTION` | false | `run.started`, `run.status_changed`, `task.ready`, `task.started`, `task.progress`, `task.waiting_for_capability`, `task.resumed`, `task.self_correcting`, `task.completed`, `task.failed` |
| `REFRESH_PROJECTION` | true | `run.created`, `scheme.generated`, `scheme.confirmed`, `plan.generated`, `task.created`, `task.correction_resolved`, `replan.requested`, `replan.approved`, `graph.task_added`, `graph.edge_added`, `graph.edge_removed`, `graph.version_changed`, `review.started`, `review.resolved`, `proof.required`, `proof.started`, `proof.generated`, `proof.verified`, `proof.failed`, `release.completed` |
| `OBSERVATION_ONLY` | false | `evidence.accepted`, `calculation.started`, `calculation.completed`, `capability.gap_detected`, `capability.build_requested`, `capability.build_started`, `capability.generated`, `capability.static_validated`, `capability.sandbox_started`, `capability.test_passed`, `capability.test_failed`, `capability.financial_validated`, `capability.approved`, `capability.registered`, `capability.build_failed` |
| `TERMINAL` | true | `run.completed`, `run.failed` |

The declared-but-unsupported values `scheme.generation_started`, `replan.rejected`,
`evidence.conflict`, `workspace.created`, `capability.generation_started`, `capability.tested`,
`capability.validated`, and `review.required` do not produce a normalized event. They yield
`UNSUPPORTED_EVENT`, mutate no projection, do not advance the committed browser cursor, retain the
last valid snapshot as stale, and trigger authoritative recovery. The final UAC-001 reconciliation
must compare this inventory to the accepted parent's complete enum before binding the table.

## 4. Total status normalization

### 4.1 Run

The raw Run value remains public `status`; stage mapping is:

```text
DRAFT -> PREPARE
SCHEME_GENERATING -> PREPARE
AWAITING_CONFIRMATION -> CONFIRM
PLANNING -> PLANNING
RUNNING -> RESEARCH
REVIEW -> REVIEW
PROVING -> PROVING
RELEASED -> COMPLETE (terminal success, release closure required)
FAILED -> FAILED (terminal failure)
CANCELLED -> CANCELLED (terminal non-success)
```

### 4.2 Task

| Raw `TaskStatus` | Projected task stage | Terminal |
|---|---|---:|
| `CREATED`, `WAITING` | `QUEUED` | no |
| `READY` | `READY` | no |
| `RUNNING` | `ACTIVE` | no |
| `WAITING_FOR_CAPABILITY` | `WAITING_SUPPORT` | no |
| `SELF_CORRECTING` | `CORRECTING` | no |
| `BLOCKED` | `BLOCKED` | no; Run may later fail |
| `REVIEW` | `REVIEW` | no |
| `COMPLETED` | `COMPLETE` | yes |
| `FAILED`, `CAPABILITY_BUILD_FAILED` | `FAILED` | yes for Task; latter retains its raw status |
| `CANCELLED` | `CANCELLED` | yes |

### 4.3 Review

`PASS -> PASS`; `REVIEW -> NEEDS_REVIEW`; `BLOCK -> BLOCKED`. Only PASS can satisfy release.
Neither `REVIEW` nor `BLOCK` implies that a user action endpoint exists. Check exception state
(`NONE|OPEN|RESOLVED`) requires an explicit same-Run check/correction relation; the
`review.resolved` event does not establish per-check resolution.

### 4.4 Proof policy and status

`ProofRequirement.NOT_REQUIRED -> NOT_REQUIRED`; `MUST_PROVE -> MUST_PROVE`. Absence of a record is
never a policy.

| Raw proof status | Projected state | Release effect |
|---|---|---|
| `NOT_REQUIRED` | `NOT_REQUIRED` only with explicit policy | allowed if all other gates pass |
| `REQUIRED_PENDING`, `PENDING` | `PENDING` | block when MUST_PROVE |
| `PROVING` | `PROVING` | block |
| `VALID` | `GENERATED_UNVERIFIED` unless matching verification is VERIFIED | block until verified |
| `VERIFIED` | `VERIFIED` only with exact verification/commitment/Run/calculation closure | satisfies proof gate |
| `INVALID`, `FAILED` | `INVALID` | block |
| `ERROR` | `ERROR` | block |
| `UNSUPPORTED`, `NOT_IMPLEMENTED` | `UNSUPPORTED` | allowed only when explicit policy is NOT_REQUIRED |

Unknown status, policy, availability, event type, or event payload values are never direct enum
casts. An incompatible request contract token produces pre-header `SCHEMA_INCOMPATIBLE` and no
mutation. An unknown value encountered inside an accepted stream produces `UNSUPPORTED_EVENT`,
retains the last valid projection as stale, and triggers authoritative snapshot recovery.

## 5. Snapshot/SSE handshake

1. Resolve and authorize exact Run R.
2. Read `AtomicRunProjectionV1` at `(projection_revision=P, projection_sequence=N)`.
3. Install it as the only authoritative browser snapshot.
4. Open a browser `fetch` stream with `Accept: text/event-stream` and
   `Last-Event-ID: <N>`; native `EventSource` is not the Phase 4 transport because it cannot set the
   initial header after a fresh snapshot.
5. Parse incremental UTF-8 SSE correctly across chunk/line splits, LF/CRLF, comments, named events,
   IDs, and multi-line data. Abort on navigation/unmount.
6. Validate Run/Task/schema/sequence/event identity before reduction.
7. On `release.completed`, refresh release-dependent state at an authoritative watermark.
8. On a terminal event, perform/validate one final projection, close, and never reconnect.

This is SSE, not polling. PostgreSQL's short internal store wait loop is an implementation detail;
the browser sees one streaming response.

### 5.1 `ConnectionState`

The normalized transport-state vocabulary is exactly:

```text
IDLE | CONNECTING | OPEN | RECOVERING | BACKOFF | TERMINAL | FAILED
```

It is Frontend-adapter transport state, never Run lifecycle truth. `LIVE` maps to `OPEN`;
`RECONNECTING` and `STALE` map to `BACKOFF`; `RECONCILING` maps to `RECOVERING`; terminal transport
variants map to `TERMINAL` while the projection carries the business outcome. Request-level
`SCHEMA_INCOMPATIBLE` is fatal `FAILED`; an unsupported in-stream value enters `RECOVERING`.

## 6. Cursor preflight and response behavior

Cursor resolution occurs before SSE response headers are committed.

| Cursor | Required behavior |
|---|---|
| header absent | resolve to 0 |
| canonical unsigned decimal `0..tail` | resume strictly after that sequence |
| negative, signed, whitespace, malformed, or noncanonical numeric | JSON 400 `INVALID_CURSOR` |
| opaque exact `event_id` in R | resolve to that event's sequence |
| unknown or other-Run opaque ID | JSON 400 `INVALID_CURSOR`; disclose no foreign event |
| numeric `> tail` | JSON 409 `CURSOR_AHEAD`; require snapshot recovery |
| valid cursor `< terminal_sequence` | replay suffix through terminal, then close |
| valid cursor `== terminal_sequence` | HTTP 200 SSE response with `X-Run-Terminal` and `X-Terminal-Sequence`, zero business frames, immediate close |

A terminal snapshot tells the browser not to open a stream. The terminal-at-cursor behavior handles
races and manual callers without an infinite heartbeat.

## 7. Delivery, duplicate, order, and gap rules

- Apply only `event.sequence == committed_sequence + 1`.
- An exact previously applied `(sequence,event_id,canonical content)` duplicate is a no-op.
- A repeated sequence with different ID/content, repeated ID at another sequence, stale unseen
  sequence, gap, out-of-order arrival, Run mismatch, parse failure, unsupported type, or incompatible
  payload is quarantined. No state is mutated; fetch a new atomic projection.
- `graph.task_added` and all edge/version events cause projection refresh. No Task label, agent,
  skill, dependencies, status, or body is fabricated from a sparse event.
- Heartbeats affect connection liveness only.
- During reconnect/recovery, retain the last valid UI projection marked stale; never reset progress
  or regress lifecycle.
- Retry only transient network/5xx failures while the latest projection is nonterminal, using
  bounded backoff and the last committed cursor.

## 8. Terminal contract

Exactly one durable terminal raw event exists for every terminal Run and no business event follows
it:

```text
success: release records committed -> release.completed -> run.completed(status=RELEASED)
failure: run.failed(status=FAILED, failure_code=...)
cancellation: run.failed(status=CANCELLED, failure_code=RUN_CANCELLED)
```

Use the existing raw event names; do not add `run.cancelled`. A single terminal finalizer must be
idempotent so the scheduler's existing `run.failed` and the outer service cannot emit two terminal
events. Scheduler/deadlock, post-scheduler Review/Proof/Release/render/artifact/persistence failure,
worker cancellation, and durable admission failure all pass through it. Run row, component
availability, terminal event, and corresponding projection revision/watermark are atomically
published or proven transactionally equivalent.

`release.completed` precedes success terminal and is not terminal itself. `run.completed` is invalid
without exact released result, canonical, PASS Review, proof-policy satisfaction, material-output
closure, and an available integrity-valid HTML artifact. PDF has an independent optional
availability slot. Failure/cancellation never enables released Results.

## 9. Phase classification

| Element | Classification |
|---|---|
| raw envelope, vocabulary, per-Run sequence, replay, numeric/opaque lookup, heartbeat | `EXISTING_BACKEND` |
| PostgreSQL event counter/log durability | `EXISTING_BACKEND` |
| `payload_schema_version`, redacted payloads, top-level `graph_version` | `PROJECTION_ONLY` |
| normalized status/stage/proof/availability maps | `PROJECTION_ONLY` |
| sparse graph event as complete Task input | `SEMANTIC_CONFLICT`; refresh is the resolution |
| frontend-only synthetic event names | `SEMANTIC_CONFLICT`; presentation labels only |
| strict cursor/ahead/terminal preflight and immediate terminal close | `BACKEND_FIELD_REQUIRED` behavior |
| atomic projection route and revision/watermark | `ADDITIVE_ROUTE_REQUIRED` plus `BACKEND_FIELD_REQUIRED` consistency |
| safe terminal payload/finalizer and all-path exactly-one terminal | `BACKEND_FIELD_REQUIRED` |
| Phase 4 deployable PostgreSQL composition | `BACKEND_FIELD_REQUIRED` |
| memory/version/comparison/reuse/refresh/writeback | `PHASE5_DEFERRED` |

## 10. Acceptance oracles

| Contract | Required evidence | Acceptance IDs |
|---|---|---|
| real source/envelope/isolation | network SSE, wire/data equality, exact Run/Task owners | `P4-SSE-001..003`; `P4-E2E-068`, `071..073`, `083` |
| order/heartbeat | persisted ledger and parsed frame ledger | `P4-SSE-004..005`; `P4-E2E-083` |
| disconnect/numeric/opaque/no-gap | request headers, sequence/event IDs, database suffix | `P4-SSE-006..009`; `P4-E2E-078..081` |
| duplicate/out-of-order/snapshot race | before/after entity cardinalities and final deep projection diff | `P4-SSE-010..012`; `P4-E2E-077`, `082`, `084`, `088` |
| refresh/navigation | one exact-Run subscription and convergence after snapshot N | `P4-SSE-013..014`; `P4-E2E-063`, `087..088`, `098` |
| success/failure terminal | terminal count/order, close/no-reconnect, final availability | `P4-SSE-015..017`; `P4-E2E-085..087`, `098` |
| invalid/ahead/cross-Run cursor | typed pre-header response and zero foreign frames | `P4-SSE-018`; `P4-E2E-073`, `079..080`; `P4-ID-009`, `026..027` |
| capability/graph lifecycle | same Task, unchanged planned graph, one actual graph version | `P4-SSE-019..020`; `P4-E2E-089..091`; `P4-ID-007..010` |
| unknown values | quarantine record, stale state, projection recovery; no guessed reducer mutation | `P4-E2E-032`, `084`, `088` |
| restart durability | new backend process returns exact suffix and terminal behavior from PostgreSQL | `P4-SSE-007..009`, `017`; `P4-E2E-098`; `P4-ID-023` |

The evidence bundle retains backend SHA/migration revision, Run ID, sanitized projection P/N,
database event ledger, cursor requests/responses, parsed-frame hashes, connection close/reconnect
record, terminal-event count, and final projection diff.
