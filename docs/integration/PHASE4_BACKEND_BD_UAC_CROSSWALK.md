# Phase 4 Backend BD / UAC Crosswalk

Status: `AUTHORITATIVE_CROSSWALK_PREPARATION — NOT_FINAL`  
Scope: `BD-001..012` mapped into the existing `UAC-001..018`, 13 normalized contracts, nine conflict clusters, eight Backend blockers, and `P4-BE-001..030`.

This document is a many-to-many crosswalk, not a second conflict register. A BD state identifies its next primary contract/implementation gate. Every row additionally depends on UAC-001 approved-parent binding and UAC-002 approved V17 input at final reconciliation. No row is `CLOSED`.

## BD disposition summary

| State | BD IDs | Count |
|---|---|---:|
| `OPEN` | none | 0 |
| `PROVISIONALLY_SPECIFIED` | `BD-002`, `004`, `005`, `007`, `010`, `012` | 6 |
| `WAITING_FOR_APPROVED_PARENT` | none as primary state; UAC-001 is universal | 0 |
| `WAITING_FOR_IMPLEMENTATION` | `BD-001`, `003`, `006`, `008`, `009`, `011` | 6 |
| final `CLOSED` | none | 0 |

`PROVISIONALLY_SPECIFIED` means the intended semantic contract is exact enough to carry into the final delta; it does not claim that code or acceptance evidence exists. `WAITING_FOR_IMPLEMENTATION` means the contract is specified but the essential route, durable field, transaction, or fault evidence is absent.

## Canonical BD rows

| BD | Dependency | Current state | Direct UAC mapping | Frontend contract(s) | Conflict cluster(s) | Backend blocker(s) | P4-BE owner(s) | Remaining dependency / final-close condition |
|---|---|---|---|---|---|---|---|---|
| `BD-001` | Coherent Run projection + event watermark | `WAITING_FOR_IMPLEMENTATION` | `001..003`, `006`, `008..011`, `016..018` | `RunProjection`, `ReleasedObjectCoreProjection`, `Availability` | `4`, `5`, `6`, `9` | `01`, `02`, `03`, `07`, `08` | `007..009`, `017`, `019`, `028` | Implement one MVCC projection/revision/watermark boundary, prove race/restart/nested identity, then bind approved parent/V17. |
| `BD-002` | Versioned raw-event normalization | `PROVISIONALLY_SPECIFIED` | `001..004`, `010`, `011`, `018` | `NormalizedRuntimeEventV1` | `4`, `5`, `6` | `03`, `08` | `018` | Bind complete raw-type/effect/payload inventory to accepted parent and V17; executable reducer/unknown-event evidence remains later. |
| `BD-003` | Browser SSE cursor/recovery/terminal | `WAITING_FOR_IMPLEMENTATION` | `001..004`, `006`, `009..011`, `015`, `018` | `ConnectionState`, `NormalizedRuntimeEventV1`, `ErrorEnvelope` | `5`, `6` | `03`, `08` | `008`, `011..017` | Implement pre-header cursor checks, recovery/terminal close and PostgreSQL restart behavior; prove `P4-SSE-001..020`. |
| `BD-004` | Artifact group and authorized delivery | `PROVISIONALLY_SPECIFIED` | `001..003`, `006`, `014..018` | `ReportArtifactGroup`, `Availability`, `ErrorEnvelope`, trace anchors | `7`, `8`, `9` | `05`, `06`, `07` | `024..027`, `030` | Bind UAC-006 local profile, final V17/group/anchor/error schemas; implement routes/state and pass authorization, independence, failure, restart and byte-integrity tests. |
| `BD-005` | Lossless released metric / Claim | `PROVISIONALLY_SPECIFIED` | `001..003`, `006`, `012`, `017`, `018` | `ReleasedFinancialMetric`, `ClaimTraceProjection` | `7`, `9` | `05`, `07` | `020..022`, `028` | V17 must add proof policy, method metadata, technical/corporate-action fields; later prove exact release joins and `0.6547 RATIO → 65.47%`. |
| `BD-006` | Claim Trace and anchor manifest | `WAITING_FOR_IMPLEMENTATION` | `001..003`, `006`, `012..014`, `017`, `018` | `ClaimTraceProjection`, `TraceBundle`, `FinancialReviewProjection`, `ReportArtifactGroup` | `7`, `8`, `9` | `05`, `06` | `022`, `024..027` | Add Claim/Trace routes, typed detail and immutable manifest/relations; pass `P4-BE-022`, `024..027` plus substitution/restart/integrity tests. |
| `BD-007` | Scheme-only Prepare boundary | `PROVISIONALLY_SPECIFIED` | `001..003`, `005`, `006`, `018` | `PreparedResearchDraft` | `1`, `2`, `3` | `04` | `002..003` | Bind exact draft hash/version/expiry/consume schema to V17; implementation later proves honest Scheme-only preview and no fabricated Tasks. |
| `BD-008` | Confirm-and-auto-start idempotency | `WAITING_FOR_IMPLEMENTATION` | `001..003`, `005..007`, `011`, `018` | `ConfirmAndStartResult`, `ErrorEnvelope` | `2`, `3` | `03`, `04` | `004..006`, `017` | Implement immutable admission, response metadata, key/request binding, one Run, durable outbox and restart/response-loss replay. |
| `BD-009` | Global Run collection | `WAITING_FOR_IMPLEMENTATION` | `001..003`, `006`, `008..010`, `016..018` | `GlobalRunCollectionProjection`, `ReleasedObjectCoreProjection` | `4`, `9` | `01`, `02`, `07`, `08` | `001`, `010`, `028..029` | Add global route, filter-bound cursor, stable ordering and list/detail consistency; prove two-object and multipage identity. |
| `BD-010` | Total Run/Task/Review/Proof maps | `PROVISIONALLY_SPECIFIED` | `001..003`, `006`, `008`, `010`, `011`, `013`, `017`, `018` | `RunProjection`, `FinancialReviewProjection`, `ReleasedFinancialMetric`, `Availability` | `4`, `5`, `7`, `9` | `02`, `03`, `05`, `07`, `08` | `001`, `007`, `010`, `018`, `023` | Bind total maps/unknown handling to V17 and accepted parent; later prove every raw enum and release consequence. |
| `BD-011` | Financial Review UI projection | `WAITING_FOR_IMPLEMENTATION` | `001..003`, `006`, `012..014`, `017`, `018` | `FinancialReviewProjection`, `ClaimTraceProjection`, `TraceBundle` | `7` | `05` | `023..024` | Persist stable check identity, typed subjects/corrections/exception history; expand release-independent review route and pass history/nullability tests. |
| `BD-012` | Complete graph mutation semantics | `PROVISIONALLY_SPECIFIED` | `001..004`, `008..011`, `018` | `RunProjection`, `NormalizedRuntimeEventV1` | `4`, `5`, `6` | `02`, `03`, `08` | `018..019` | Freeze exact `PathChangeProjectionV1` and type-to-effect table; sparse events always refresh and never fabricate Tasks. |

## Nine Frontend conflict clusters

| Existing cluster | Mapped UAC IDs | Mapped BD IDs | Backend blocker(s) | Provisional decision | Remaining dependency |
|---|---|---|---|---|---|
| `1` Prepare Scheme vs Plan/Tasks | `001..003`, `005`, `006`, `018` | `007` | `04` | Prepare returns immutable Scheme-only preview; graph/Tasks begin only after Confirm. | Approved parent/V17; draft implementation evidence. |
| `2` Confirm/start state and route | `001..003`, `005..007`, `011`, `018` | `007`, `008` | `03`, `04` | Confirm is the single execution action and returns nested immutable admission plus replay metadata. | Durable admission/outbox and terminal evidence. |
| `3` Durable idempotency | `001..003`, `005..007`, `011`, `018` | `007`, `008` | `04` | Scope+route+key binds canonical request hash; same request replays, different request conflicts, response loss never creates a second Run. | Persistence/crash/restart evidence. |
| `4` Progress/enums | `001..004`, `008..011`, `018` | `001`, `002`, `009`, `010`, `012` | `01..03`, `08` | Backend supplies fraction/counts/method and total raw-preserving status maps; adapter alone derives percent. | Final V17 parity and exhaustive fixtures. |
| `5` Runtime event semantics | `001..004`, `008..011`, `018` | `001..003`, `010`, `012` | `02`, `03`, `08` | Stored names remain unchanged; public V1 adds versions and an exact effect disposition; sparse graph events refresh. | Accepted-parent event re-audit and reducer evidence. |
| `6` Browser SSE protocol | `001..004`, `006`, `009..011`, `015`, `018` | `001..003`, `012` | `02`, `03`, `08` | Snapshot-at-N then fetch-stream after N; strict cursor preflight, quarantine/recovery, heartbeat and terminal close. | SSE implementation and `P4-SSE-001..020`. |
| `7` Financial Review projection | `001..003`, `006`, `010`, `012..014`, `017`, `018` | `004..006`, `010`, `011` | `05..07` | Explicit C/M/K/E/T/V/P/X/L joins, typed checks/Judgment, release-independent Review and scoped anchors. | V17 corrections plus durable check/anchor evidence. |
| `8` Artifact semantics | `001..003`, `006`, `011`, `014..018` | `004`, `006` | `05..07` | Fixed independent HTML/PDF slots, mandatory HTML, optional truthful PDF, opaque authorized path and integrity-before-delivery. | Routes, attempt state, manifest, fault/restart evidence. |
| `9` Financial/Object projection | `001..003`, `006`, `008`, `012`, `015..018` | `001`, `004..006`, `009`, `010` | `01`, `02`, `05..08` | Lossless release truth and deterministic latest eligible release; no frontend arithmetic or Phase 5 state. | Accepted-parent/V17 parity and selector/release evidence. |

## Thirteen normalized contracts

| Contract | Primary BD | Primary UAC | Current boundary |
|---|---|---|---|
| `Availability` | `004`, `005`, `010` | `006`, `008`, `011..018` | Backend-authored status/reason/retry truth; no absence inference. |
| `ErrorEnvelope` | `003`, `004`, `008` | `003`, `006`, `018` | One safe envelope and total error table. |
| `GlobalRunCollectionProjection` | `009` | `008..010`, `017` | Additive route and stable backend cursor/order. |
| `PreparedResearchDraft` | `007` | `005` | Scheme-only, immutable draft hash/version/expiry. |
| `ConfirmAndStartResult` | `008` | `005`, `007`, `011` | `RunAdmissionV1` plus `ResponseMetaV1`; no second Start. |
| `RunProjection` | `001`, `010`, `012` | `008..011`, `016`, `017` | Atomic revision/sequence snapshot with Backend path changes. |
| `NormalizedRuntimeEventV1` | `002`, `012` | `003`, `004`, `009..011` | Raw name preserved; versioned payload and exact effect. |
| `ConnectionState` | `003` | `004`, `009..011`, `018` | Adapter transport state only, never business lifecycle. |
| `FinancialReviewProjection` | `011` | `010`, `013` | Backend Review/check truth with exact nullability/history. |
| `ClaimTraceProjection` / `TraceBundle` | `006` | `012..014` | Explicit same-Run lineage and representation-scoped anchors. |
| `ReportArtifactGroup` | `004` | `014..016` | Two independent slots, immutable success and safe delivery. |
| `ReleasedFinancialMetric` | `005` | `012`, `017` | Lossless canonical/display value and release lineage. |
| `ReleasedObjectCoreProjection` | `001`, `009` | `008`, `016`, `017` | Exact latest eligible release and Phase 4-only Object Core. |

## Coverage result

```text
BD_TOTAL=12
BD_DISPOSITIONED=12/12
BD_FINAL_CLOSED=0
FRONTEND_CONTRACTS_MAPPED=13/13
FRONTEND_CONFLICT_CLUSTERS_MAPPED=9/9
BACKEND_BLOCKERS_MAPPED=8/8
P4_BE_NAMESPACE_EXTENSIONS=0
PHASE5_LEAKAGE=0
```
