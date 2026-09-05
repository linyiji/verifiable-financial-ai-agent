# Phase 4 SSE Event Mapping

Classification: `PROVISIONAL_CONTRACT_PREAUDIT`

Backend source: dirty Phase 3 candidate fingerprint `sha256:f0101a685d10b801466f9dad9bd3b8e74221b8bd5ec0b1e9e1b5e4f176fcc592`.

Frontend source: clean remediation candidate `a850bce3cf0b8a72bc28c7ce16a67e9f83be0c84`.

## 1. Actual transport and envelope

Backend SSE serialization is:

```text
id: <event.sequence>
event: <event.type>
data: <complete RuntimeEvent JSON>
```

The event JSON fields are `{event_id, run_id, task_id?, type, timestamp, sequence, payload}`. Heartbeats are comments (`: heartbeat`) and therefore are not RuntimeEvents. The API uses `completed_run_event_stream`, which intends to close after `run.completed` or `run.failed`.

Important browser detail: because the server sets a named SSE `event:` field, a production `EventSource` transport must use `addEventListener(<event-name>, ...)` (or normalize server output to unnamed `message` events). An `onmessage`-only implementation would silently miss these events.

| Concern | Backend actual | Frontend actual | Assessment | Required Phase 4 contract |
|---|---|---|---|---|
| Event id | JSON `event_id`; SSE `id` is numeric sequence | dedupes JSON `event_id` | Partial match | Preserve both meanings; cursor is sequence, domain identity is `event_id`. |
| Run id | Required JSON `run_id`; stores and routes are per-Run | reducer rejects a different `run_id` | `MATCH` | Keep cross-Run rejection and validate subscription Run before dispatch. |
| Task id | Optional JSON `task_id` | optional; used to locate Task | `MATCH` | Event-specific rules must say when required. |
| Sequence | Positive per-Run integer; append enforces next value; PostgreSQL has unique constraint/trigger | stores/sorts it but applies out-of-order events immediately | `SEMANTIC_CONFLICT` | Apply only the next expected sequence; gap triggers recovery. |
| Timestamp | Backend timezone-aware datetime serialized as RFC 3339 | string | `RENAMING_ONLY` at type boundary | Freeze RFC 3339 UTC and retain server time. |
| Payload | Unversioned JSON, different per event | reducer assumes specific fields and defaults missing values | `SEMANTIC_CONFLICT` | Version and validate normalized payloads; no production fallbacks that invent domain state. |
| Graph version | Absent from envelope; appears inconsistently as `actual_graph_version`, `graph_version`, or `version_after` in payload | reducer expects `payload.graph_version` for one event | `SEMANTIC_CONFLICT` | Put one normalized `graph_version` in affected event payloads or require snapshot refresh. |
| Last-Event-ID | Resolves numeric sequence or JSON event id | transport signature has no initial cursor | `PARTIALLY_RESOLVED` | Add an initial cursor/watermark contract and define browser-compatible delivery. |
| Heartbeat | Comment every 15 seconds while idle | placeholder has no health/reconnect state | Compatible transport detail | Ignore as domain data; use only for connection liveness. |
| Terminal | Stream closes when it emits `run.completed`/`run.failed` | union omits both; completion handled through `release.completed` | `SEMANTIC_CONFLICT` | Make terminal event names authoritative and expose terminal callback/state. |

## 2. Events with a direct or near-direct frontend mapping

“Projection refresh” means re-read the coherent Run projection and continue after its sequence watermark. It does not mean issue several uncoordinated endpoint reads.

| Backend event | Backend actual payload/meaning | Frontend handling now | Phase 4 mapping |
|---|---|---|---|
| `plan.generated` | `{graph_id, task_count}` after confirm | Moves Run to research | Keep name; snapshot supplies actual Tasks and stage. |
| `task.created` | `{task_type}` and `task_id` | Accepted but no-op | Treat as advisory; insert only from authoritative graph/Task payload or refresh. |
| `task.started` | `{attempt}` | Marks Task RUNNING | Direct after Task exists. |
| `task.progress` | e.g. `{progress: 0.1, stage, message}` or retry metadata | Assigns progress as if percent | Normalize progress `0..1 → 0..100`; payload union must distinguish progress/retry forms. |
| `task.waiting_for_capability` | `{gap_id}` on original Task | Expects `capability_id`/message and creates supporting activity | Join/aggregate the preceding gap event; never create a Research Task. |
| `task.self_correcting` | `{problem_code, error}` | Expects reason/change id | Map to a correction/path projection; do not display raw exception type as the business reason. |
| `task.completed` | `{attempt, result_ref}` | Marks completed and optionally uses message | Direct status; keep safe result ref only if approved for UI. |
| `replan.requested` | `{replan_id, decision}` | Expects change id/type/reason/affected ids | Use `replan_id`; enrich from `ReplanRequest` or refresh path projection. |
| `replan.approved` | `{replan_id, decided_by}` | Expects change id/type/reason/affected ids | Mark approved by exact `replan_id`; mutation completion waits for graph version event. |
| `graph.task_added` | event `task_id`; `{replan_id, graph_version}` | Fabricates a default Task from absent fields | Never fabricate; refresh actual graph or include a complete Task projection. |
| `graph.version_changed` | `{replan_id, version_before, version_after}` | Reads `graph_version` and optional dependency map | Normalize `version_after → graph_version`; refresh graph for dependencies. |
| `review.started` | no payload | Moves Run to Review | Direct stage signal. |
| `review.required` | Enum exists; no normal candidate emission found | Builds an exception from assumed payload | Keep only after payload/producer is frozen; otherwise projection refresh. |
| `capability.approved` | `{build_id, registration_id, approved_by, scope}` on original Task | Marks supporting activity complete and Task RUNNING | Mark approval only; Task becomes RUNNING on `task.resumed`, not here. |
| `release.completed` | `{canonical_record_id, result_id}` | Attempts guarded atomic completion | Treat as “release records committed/available”; refresh result/review/report projection. Final stream terminal remains `run.completed`. |

## 3. Name or meaning conflicts

| Frontend event expectation | Backend actual | Conflict | Required resolution |
|---|---|---|---|
| `correction.resolved` | `task.correction_resolved` with `{correction_id}` | Name and payload differ | Choose the backend name as source or normalize in one transport adapter; fetch correction reason/history. |
| `capability.validating` | Detailed static/sandbox/test/financial events | Frontend collapses distinct lifecycle and uses a non-backend name | Replace with explicit lifecycle mappings or one documented projection-only synthetic event. |
| `review.resolved` means exception repaired | Backend `review.resolved` means run-level review completed and includes `{review_id, status}` | Same string, materially different semantics | Do not feed raw backend event to current reducer case. Rename normalized meanings or make reducer consume a typed discriminator. |
| `claim.materialized` | No backend event | Frontend expects whole Claim + Review in payload | Populate Claims from coherent snapshot/release projection; add an event only if deliberately frozen. |
| `report.started` | No backend event | Frontend uses it for artifact pending state | Derive pending state from a backend-owned report job/status projection, not a timer. |
| `result.prepared` | No backend event | Frontend expects a complete `ReportArtifact` in the event | Refresh projection after `release.completed`; do not put large report DTOs into SSE unless explicitly chosen. |
| guarded completion on `release.completed` | Backend emits `release.completed`, then terminal `run.completed` | Frontend does not accept terminal event and release event lacks artifact/review/execution bodies | Snapshot at `release.completed`, then accept `run.completed` only when watermark-consistent projection is release-complete. |

## 4. Backend events absent from the frontend union

| Backend event | Actual meaning | Phase 4 UI mapping |
|---|---|---|
| `run.created` | Run aggregate created | Initialize via snapshot; telemetry/no-op if already present. |
| `run.started` | Scheduler started; payload has actual graph version | Map backend RUNNING to frontend research stage using the frozen status map. |
| `run.status_changed` | Currently used for transition to REVIEW | Update normalized Run status/stage. |
| `run.completed` | Durable terminal event after release | Terminal success; close subscription after final projection refresh. |
| `run.failed` | Scheduler terminal failure/deadlock | Terminal failure; refresh failure/task state and close. |
| `scheme.generation_started` | Scheme generation activity | Optional prepare-stage activity. |
| `scheme.generated` | Scheme exists; normal confirm path emits it retrospectively | Prepare/confirm activity; do not confuse with `plan.generated`. |
| `scheme.confirmed` | Scheme accepted | Prepare/confirm activity. |
| `task.ready` | Dependencies satisfied | Map Task READY. |
| `task.resumed` | Original capability-waiting Task is RUNNING again | Complete supporting activity and resume the same Task. |
| `task.correction_resolved` | Same Task correction completed | Map to correction history and Task status after exact correction lookup. |
| `task.failed` | Task terminal failure; payload may signal capability-build failure | Map Task FAILED/error summary using safe codes. |
| `replan.rejected` | Enum exists; producer semantics not found in normal path | Mark exact replan rejected after payload is frozen. |
| `graph.edge_added` | Edge mutation with source/target/version | Refresh or patch actual graph at matching version. |
| `graph.edge_removed` | Edge mutation with source/target/version | Refresh or patch actual graph at matching version. |
| `evidence.accepted` | Evidence acquisition accepted | Add safe observable Task activity; authoritative evidence comes from projection/detail. |
| `evidence.conflict` | Evidence conflict | Add warning/review activity; do not infer final Review status. |
| `calculation.started` | Calculation began; usually carries capability id | Add Task activity. |
| `calculation.completed` | Calculation record exists; carries calculation id and sometimes capability id | Add ref/activity; read typed value from result projection, never from an inferred event value. |
| `capability.gap_detected` | Gap id/capability/skill/requester | Start supporting activity under original Task. |
| `capability.build_requested` | Gap/build/attempt/approval metadata | Append supporting lifecycle. |
| `capability.build_started` | Build attempt began | Append supporting lifecycle. |
| `capability.generated` | Candidate generated with hashes/model telemetry | Append safe lifecycle; do not expose source code. |
| `capability.static_validated` | Static validation passed | Append lifecycle. |
| `capability.sandbox_started` | Disposable sandbox validation began | Append lifecycle. |
| `capability.test_passed` | Tests passed | Append lifecycle. |
| `capability.test_failed` | Validation attempt failed | Append retry/failure lifecycle. |
| `capability.financial_validated` | Financial validation passed | Append lifecycle. |
| `capability.registered` | Scoped registration is active | Append lifecycle; wait for `task.resumed` before Task RUNNING. |
| `capability.build_failed` | Attempt or terminal build failure; payload has `terminal` | Append failure; only terminal true maps Task failure/block state. |
| `workspace.created` | Workspace supporting activity | Optional Task activity, never a Research Task. |
| `capability.generation_started` | Legacy/alternate enum; current generated orchestrator uses build events | `DEFERRED` until one authoritative vocabulary is selected. |
| `capability.tested` | Legacy/alternate enum | `DEFERRED` until one authoritative vocabulary is selected. |
| `capability.validated` | Legacy/alternate enum | `DEFERRED` until one authoritative vocabulary is selected. |
| `proof.required` | Proof policy requires proof | Update backend-projected proof state. |
| `proof.started` | Proving began | Update proof state. |
| `proof.generated` | Proof artifact generated | Refresh proof record; generation is not validity. |
| `proof.verified` | Verification passed | Refresh and display valid only after exact proof/calculation binding. |
| `proof.failed` | Proof/verification failed | Update error/invalid state and release implications from backend policy. |

## 5. Capability-waiting mapping

The actual successful lifecycle is:

```text
capability.gap_detected
→ task.waiting_for_capability
→ capability.build_requested
→ capability.build_started
→ capability.generated
→ capability.static_validated
→ capability.sandbox_started
→ capability.test_passed
→ capability.financial_validated
→ capability.approved
→ capability.registered
→ task.resumed
```

All events carry the original `run_id` and `task_id`. The runtime mutates that original Task from RUNNING to WAITING_FOR_CAPABILITY and later back to RUNNING. Tests assert that the graph still contains one Research Task. The frontend must represent this sequence as supporting activity within that Task. `gap_id`, `build_id`, `generated_capability_id`, `capability_id`, `registration_id` and `implementation_hash` are supporting identities, not `task_id`s.

Failure may produce `capability.test_failed`, one or more `capability.build_failed` events, and finally `task.failed`. `terminal: false` means another build attempt may follow; it must not mark the Research Task terminal.

## 6. Resume, ordering and recovery assessment

| Scenario | Actual behavior | Risk | Freeze requirement |
|---|---|---|---|
| Duplicate delivery | Frontend ignores duplicate JSON `event_id`; backend prevents duplicate event id and run/sequence | Good base | Also reject a duplicate sequence carrying a different id. |
| Out-of-order delivery | Backend replay is sorted; frontend applies arrival order then sorts stored history | A late stale event can roll state backward | Buffer until `lastSequence + 1`; never apply stale/gapped events. |
| Sequence gap | Backend append is contiguous; frontend accepts any larger sequence | Missing state is silently skipped | Pause reducer and recover from snapshot/replay. |
| Reconnect | Backend accepts `Last-Event-ID`; native browser automatically sends it only after it has received an SSE id on that EventSource lifecycle | Frontend cannot supply a snapshot watermark on its current interface | Freeze query cursor vs fetch-stream/custom-header approach. |
| Unknown event id | Backend raises `KeyError` | API error shape/recovery not defined | Return a typed recovery response/status that instructs snapshot reload. |
| Cursor ahead of tail | Backend waits indefinitely | Stale/corrupt client can heartbeat forever | Detect and require snapshot recovery. |
| Snapshot race | No atomic frontend projection + watermark endpoint | Events can occur between separate reads | One coherent projection must include `last_sequence`; replay strictly after it. |
| Heartbeat | Comment only | No domain mutation | Ignore; optionally update connection liveness. |
| Normal terminal | API closes only after emitting `run.completed`/`run.failed` | Frontend omits these names | Add normalized terminal events and callback. |
| Reconnect after terminal cursor | If cursor equals the terminal sequence, the stream has no event to replay and can heartbeat forever | Completed page can hang | Snapshot must state terminal; server should return/close immediately for a terminal Run at/after terminal cursor. |
| Assurance/release failure | `execute_run` catches and marks Run FAILED, but the inspected catch path does not emit `run.failed` | Stream may never close after a post-scheduler failure | Every terminal failure path must durably emit one terminal event. |
| Restart durability | PostgreSQL event store exists, but the default API composition constructs an in-memory event store and an in-memory SQLite database | Live/replay semantics are not process durable in the current app composition | Phase 4 target must compose the PostgreSQL store and verify restart replay. |
| Cross-Run isolation | Route/store/reducer are Run-scoped | Good base | Verify event `run_id`, Task ownership, projection Run, and subscription Run all match. |

## 7. Minimum safe snapshot/SSE handshake

The Phase 4 contract should freeze a handshake equivalent to:

1. `getRunProjection(run_id)` returns one coherent projection plus `last_sequence`, `graph_version`, lifecycle/terminal state and projection schema version.
2. The client subscribes strictly after `last_sequence` using a browser-compatible cursor mechanism.
3. The transport validates `run_id`, event schema, sequence and event-id uniqueness before invoking the reducer.
4. `sequence <= last_sequence` is ignored only when identity matches prior history; `sequence > last_sequence + 1` pauses reduction and triggers recovery.
5. Unknown event type or payload-schema version fails closed to projection recovery; it is not silently coerced with defaults.
6. On `release.completed`, refresh release-dependent projections at an event-consistent watermark.
7. On `run.completed` or `run.failed`, obtain/confirm the terminal projection, stop reconnecting, and unsubscribe.
8. A terminal snapshot causes an immediate no-stream or immediately closed stream response even when the cursor already equals the terminal event.

Until this handshake and the event-normalization table are frozen, FBG-002 remains `PARTIALLY_RESOLVED` and SSE wiring is blocked.
