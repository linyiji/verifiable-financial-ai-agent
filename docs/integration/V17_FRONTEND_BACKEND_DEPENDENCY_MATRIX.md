# V17 Frontend / Backend Dependency Matrix

Status: `PREPARATION_COMPLETE_BLOCKED`

```text
FRONTEND_V17_CURRENT_GATE = BLOCKED_BY_BACKEND_CONTRACT
CONTRACT_FREEZE = NOT_READY
BACKEND_DEPENDENCIES_OPEN = 12
PHASE4_IMPLEMENTATION_AUTHORIZED = NO
```

## Authority and classification

This matrix reconciles the approved V8.1 frontend contracts, the V17 package, the repository's
provisional Phase 4 pre-audit material, and the available Phase 3 backend domain/API records. The
repository records still state `CONTRACT_FREEZE = NOT_READY`; no later approved Phase 4 frontend
contract freeze was found. Existing backend models are useful source contracts but are not, by
themselves, frontend-safe projections.

Each Phase 4 contract has one primary state from the required vocabulary:

- `BACKEND_CONTRACT_AVAILABLE`: the complete required backend contract is frozen and consumable;
- `WAITING_FOR_BACKEND_FREEZE`: shape/semantics exist in draft but lack approved final freeze;
- `BACKEND_PROJECTION_REQUIRED`: authoritative records exist, but a composed frontend projection is missing;
- `BACKEND_ROUTE_REQUIRED`: projection/bytes require a safe HTTP or SSE delivery route;
- `SEMANTIC_CONFLICT`: current frontend/package semantics conflict with actual backend semantics;
- `PHASE5_DEFERRED`: not a Phase 4 real-integration dependency.

No complete Phase 4 frontend contract currently qualifies as `BACKEND_CONTRACT_AVAILABLE`.

## Frontend contract disposition

| Frontend normalized contract | Primary state | Open dependency | Available backend source | Required closure |
|---|---|---|---|---|
| `GlobalRunCollectionProjection` | `BACKEND_PROJECTION_REQUIRED` | `BD-009` | Object-scoped Runs and repositories | Freeze global collection item, stable order, pagination/filter cursor, Object summary, status/stage/progress/activity/graph version/result availability |
| `PreparedResearchDraft` | `SEMANTIC_CONFLICT` | `BD-007` | Goal + `ResearchSchemeSnapshot` draft | Choose and freeze Scheme-only honest preview or a backend-authored preview graph; bind Object/Goal/mode/as-of/version/expiry without inventing Tasks |
| `ConfirmAndStartResult` | `SEMANTIC_CONFLICT` | `BD-008` | Confirm creates a Run and planned graph | Freeze durable request-bound idempotency, exact draft/request hash, single Run/scheduler admission, retry/restart outcome, and auto-start result; no second Start |
| `RunProjection` | `BACKEND_PROJECTION_REQUIRED` | `BD-001` | Run, Tasks, graphs, events, review, canonical/result/artifacts | Freeze one event-consistent run-rooted snapshot with `last_sequence`, `graph_version`, terminal state, owner identity, and nested ownership validation |
| `NormalizedRuntimeEventV1` | `SEMANTIC_CONFLICT` | `BD-002`, `BD-012` | Durable backend `RuntimeEvent` envelope/sequence | Freeze total event and payload mapping; resolve progress scale, correction/review names, graph payload completeness, terminal events, unknown-event behavior |
| `ConnectionState` | `WAITING_FOR_BACKEND_FREEZE` | `BD-003` | Replay, numeric sequence, `Last-Event-ID`, heartbeat, terminal close primitives | Freeze snapshot/cursor handshake, browser transport, reconnect/gap/duplicate/out-of-order policy, terminal behavior, unknown/ahead cursor error |
| `FinancialReviewProjection` | `BACKEND_PROJECTION_REQUIRED` | `BD-010`, `BD-011` | Run-level `ReviewRecord`, checks, reviewed refs | Freeze per-Claim/check projection, PASS/REVIEW/BLOCK/uncertainty map, open/resolved exception history, correction path, blocking/user-action semantics |
| `ClaimTraceProjection` / `TraceBundle` | `BACKEND_PROJECTION_REQUIRED` | `BD-006` | Claim, metric, evidence, calculation, proof, review, canonical/result lineage | Freeze exact run-scoped relations, multi/primary Task rule, typed Judgment or unavailable state, and representation-scoped report/review/task/execution anchors |
| `ReportArtifactGroup` | `BACKEND_ROUTE_REQUIRED` | `BD-004` | Immutable per-representation artifact records and renderers | Freeze grouped HTML/PDF availability DTO, object/run/report/canonical binding, hash/size/media type, safe failure code, authorized opaque byte routes, Claim anchor manifest |
| `ReleasedFinancialMetric` | `BACKEND_PROJECTION_REQUIRED` | `BD-005` | Released metric, Claim, Calculation, Evidence and Proof records | Freeze lossless canonical/display semantics and lineage; React may format but never convert or infer |
| `ReleasedObjectCoreProjection` | `BACKEND_PROJECTION_REQUIRED` | `BD-001`, `BD-009` | Object identity plus exact Runs/released results | Freeze Phase 4 core overview/financial/market/latest released Run slice; explicitly omit versioned memory/comparison/writeback truth |
| `ErrorEnvelope` | `WAITING_FOR_BACKEND_FREEZE` | `BD-003`, `BD-004`, `BD-008` | Endpoint-specific exceptions/statuses | Freeze safe code, retryability, identity context, details policy, request/correlation id, and status mapping; unknown errors fail closed |
| `Availability` | `WAITING_FOR_BACKEND_FREEZE` | `BD-004`, `BD-005`, `BD-010` | Record presence and partial lifecycle signals | Freeze `AVAILABLE/PENDING/UNAVAILABLE/FAILED/NOT_GENERATED` meanings and reason codes; absence must not imply release/proof/result state |

## Twelve open dependency records

| ID | Priority | Dependency | State | Frontend consumers | Closure evidence |
|---|---:|---|---|---|---|
| `BD-001` | P0 | Coherent Run projection + event watermark | `BACKEND_PROJECTION_REQUIRED` | Runs, Run, Results, Object core, reducer | Approved schema/route; snapshot/replay race test; nested same-Run ownership checks |
| `BD-002` | P0 | Versioned raw-event normalization contract | `SEMANTIC_CONFLICT` | transport, reducer, Run/Review/Execution | Approved total event/payload table; real-event reducer fixture; unknown fails closed |
| `BD-003` | P0 | Browser SSE cursor/recovery/terminal protocol | `WAITING_FOR_BACKEND_FREEZE` | `RuntimeTransport`, `SSERuntimeTransport`, `ConnectionState` | `P4-SSE-001..020` design mapped to one frozen wire protocol and error envelope |
| `BD-004` | P0 | Frontend-safe artifact group and authorized delivery | `BACKEND_ROUTE_REQUIRED` | Results/Professional Report/download actions | Group DTO + Claim anchors; cross-object rejection; byte hash/size/type checks for independent HTML/PDF |
| `BD-005` | P0 | Lossless released metric/Claim projection | `BACKEND_PROJECTION_REQUIRED` | Results, Financial Review, Object core | Canonical/display/unit/period/actuality/as-of/currency/lineage contract; `0.6547 RATIO → 65.47%` fixture |
| `BD-006` | P0 | Exact Claim Trace bundle and anchor manifest | `BACKEND_PROJECTION_REQUIRED` | Report, Review, Execution, Claim/Task drawers | End-to-end Report→Claim→Review→Task→Calculation→Evidence→Execution→Report Anchor; negative substitutions |
| `BD-007` | P1 | Prepare boundary | `SEMANTIC_CONFLICT` | New Task, Plan Snapshot | Approved Scheme-only or graph-preview decision; immutable draft/version/expiry and honest labels |
| `BD-008` | P1 | Confirm-and-auto-start idempotency | `SEMANTIC_CONFLICT` | New Task, Run landing | Durable key/request binding and restart retry; exactly one Run, `run.created`, scheduler admission, `run.started` |
| `BD-009` | P1 | Global Run collection | `BACKEND_PROJECTION_REQUIRED` | Shell, Runs, Object detail | Approved global route/projection with order/cursor/filter and list/detail revision consistency |
| `BD-010` | P1 | Total Run/Task/Review/Proof enum maps | `WAITING_FOR_BACKEND_FREEZE` | types, adapters, reducer, all state UI | Exhaustive mapping with cancelled/waiting/capability failure/uncertainty/resolved history/unknown behavior |
| `BD-011` | P1 | Financial Review UI projection | `BACKEND_PROJECTION_REQUIRED` | Financial Review, Results, Trace | Per-Claim/check and exception-history schema with exact refs and authoritative decisions |
| `BD-012` | P1 | Complete graph mutation semantics | `SEMANTIC_CONFLICT` | reducer, Research Path, Task drawer | Choose complete event payload or mandatory projection refresh; never fabricate labels/dependencies/Tasks |

All twelve are open until an approved backend Phase 4 contract freeze binds exact schemas, route/event
versions, enum tables, error behavior, authorization rules, and a stable backend source coordinate.

## Available supporting backend contracts

The following lower-level material is available and must be reused rather than duplicated, but does
not close the frontend rows above:

| Available source | Usable fact | Limitation |
|---|---|---|
| `ResearchObject`, `ResearchRun` | Strong Object/Run owner identity | No complete global collection or UI projection |
| Task and planned/actual graph records | Run-scoped Tasks and versioned actual graph | Dynamic events do not provide every display field |
| `RuntimeEvent` persistence | Per-Run sequence, envelope, replay basis | Normalization and browser recovery freeze missing |
| Evidence and Calculation records | Deterministic lineage | Must be authorized and composed into run-scoped projections |
| Claim, Review and Proof records | Financial/review/proof source truth | UI associations/anchors and total status map incomplete |
| Canonical execution and released result | A/B/C and release authority | Frontend-safe grouped projection/routes missing |
| Artifact records/renderers | Immutable HTML/PDF representation facts | Internal refs are unsafe; availability and Claim anchors missing |

## Phase 5 dependency quarantine

| Contract/capability | State | Phase 4 behavior |
|---|---|---|
| `ResearchObjectVersion`, `ResearchViewVersion` | `PHASE5_DEFERRED` | Absent/disabled/unavailable or clearly Demo-only |
| `ComparisonDataset` and Claim Diff | `PHASE5_DEFERRED` | No latest fallback; exact pair required only after activation |
| `IncrementalResearchSeed` | `PHASE5_DEFERRED` | Incremental mode remains unavailable without authoritative same-Object source |
| Freshness / Reuse / Refresh / Revalidate / Prevent | `PHASE5_DEFERRED` | Never frontend-authored |
| Research Memory | `PHASE5_DEFERRED` | No production truth claim in Scene 05 |
| Object Writeback | `PHASE5_DEFERRED` | No mutation or applied-version claim |
| Real Scene 05 / Scene 06 variants | `PHASE5_DEFERRED` | Compatibility may remain; Demo evidence is separately labeled |

Future names `RETURN_TO_STEP`, `WAIT_FOR_USER`, and `RESUME` are also deferred. The Phase 4 dynamic
mutation allowlist remains `SELF_CORRECTION`, `ADD_TASK`, and `CHANGE_DEPENDENCY`; unknown values fail
closed.

## Gate rule

Phase 4 execution may begin only when all twelve dependency records have approved closure decisions,
no `SEMANTIC_CONFLICT` remains, the backend source and contract versions are frozen, and the governed
Frontend Change Request advances from `DRAFT_CHANGE` to `CHANGE_APPROVED`. This preparation performs
none of those state transitions.
