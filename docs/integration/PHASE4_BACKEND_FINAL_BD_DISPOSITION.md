# Phase 4 Backend Final BD Disposition

Status: `FINAL_SEMANTIC_DISPOSITION_COMPLETE`  
Contract family: `phase4-core/v1`  
Authority namespace: existing `BD-001..012` only

## Decision rule

A BD is `CONTRACT_CLOSED` when its route, schema, ownership, unknown handling, persistence rule and
acceptance oracle are semantically exact. A missing Phase 4 route or missing executable evidence is
recorded separately as implementation work and does not reopen the contract.

## Final disposition

| BD | Decision | Frozen contract | Primary UACs | V17 consumer contract(s) | Implementation evidence |
|---|---|---|---|---|---|
| `BD-001` | `CONTRACT_CLOSED` | One `AtomicRunProjectionV1` with exact Object/Run closure, monotonic revision and same-snapshot event watermark. | `001..003`, `006`, `008..011`, `016..018` | `RunProjection`, `ReleasedObjectCoreProjection`, `Availability` | `PENDING`: projection route, MVCC publication, race/restart tests. |
| `BD-002` | `CONTRACT_CLOSED` | All 55 raw RuntimeEvent enum values have one supported effect/payload schema or explicit `UNSUPPORTED_EVENT`; raw name is preserved. | `001..004`, `010`, `011`, `018` | `NormalizedRuntimeEventV1` | `PENDING`: public version fields, decoder/reducer fixtures. |
| `BD-003` | `CONTRACT_CLOSED` | Snapshot-at-N, strict numeric/opaque same-Run cursor, pre-header errors, gap recovery, heartbeat and terminal-close behavior. | `001..004`, `006`, `009..011`, `015`, `018` | `ConnectionState`, `NormalizedRuntimeEventV1`, `ErrorEnvelope` | `PENDING`: strengthened SSE route and `P4-SSE-001..020`. |
| `BD-004` | `CONTRACT_CLOSED` | Fixed independent HTML/PDF artifact slots; non-bearer authorized path; exact identity and integrity before byte delivery. | `001..003`, `006`, `014..018` | `ReportArtifactGroup`, `Availability`, `ErrorEnvelope`, trace anchors | `PENDING`: metadata/content routes, attempt persistence, authorization/integrity/restart tests. |
| `BD-005` | `CONTRACT_CLOSED` | Lossless released metric and Claim projection with exact Decimal strings, units, periods, method, technical/corporate fields, proof policy and lineage. Revenue growth is `(current-prior)/prior`; every material operation uses an explicit half-even Decimal profile: precision 28 for fundamental-ratio division and MACD line/histogram subtraction, precision 50 for technical averaging/EMA recurrence. | `001..003`, `006`, `012`, `017`, `018` | `ReleasedFinancialMetric`, `ClaimTraceProjection` | `PENDING`: Phase 4 projection and exact release-join/display evidence. The bound Phase 3 independent financial receipt fails these implementation semantics. |
| `BD-006` | `CONTRACT_CLOSED` | Exact Claim/Trace routes and immutable representation-scoped anchor manifest; generated source and test bytes are retained, resolvable and content-hash/implementation-hash verifiable; no text/first/latest fallback. | `001..003`, `006`, `012..014`, `017`, `018` | `ClaimTraceProjection`, `TraceBundle`, `FinancialReviewProjection`, `ReportArtifactGroup` | `PENDING`: routes, typed detail, generated-byte retention, manifests, substitution/restart tests. The bound Phase 3 independent receipt reports missing generated FCF bytes. |
| `BD-007` | `CONTRACT_CLOSED` | Prepare returns an immutable, hashed `SCHEME_ONLY` draft with explicit not-generated planned-graph availability and no Tasks. | `001..003`, `005`, `006`, `018` | `PreparedResearchDraft` | `PENDING`: strengthened prepare/idempotency/draft persistence tests. |
| `BD-008` | `CONTRACT_CLOSED` | Confirm consumes one exact draft and returns immutable admission plus replay metadata; same key+request replays, key+different request conflicts. | `001..003`, `005..007`, `011`, `018` | `ConfirmAndStartResult`, `ErrorEnvelope` | `PENDING`: durable admission/outbox/lease and response-loss/restart evidence. |
| `BD-009` | `CONTRACT_CLOSED` | Global Run collection route, fixed `(updated_at DESC, run_id DESC)` order, opaque filter-bound cursor and list/detail consistency. | `001..003`, `006`, `008..010`, `016..018` | `GlobalRunCollectionProjection`, `ReleasedObjectCoreProjection` | `PENDING`: additive route, durable updated-at/revision and multipage identity tests. |
| `BD-010` | `CONTRACT_CLOSED` | Total Run/Task/Review/Proof/availability maps; unknown value fails closed with no mutation and snapshot recovery. | `001..003`, `006`, `008`, `010`, `011`, `013`, `017`, `018` | `RunProjection`, `FinancialReviewProjection`, `ReleasedFinancialMetric`, `Availability` | `PENDING`: exhaustive map fixtures and release consequences. |
| `BD-011` | `CONTRACT_CLOSED` | Release-independent Review projection with nullable absence, stable Check IDs, typed subjects and exact correction/exception history. | `001..003`, `006`, `012..014`, `017`, `018` | `FinancialReviewProjection`, `ClaimTraceProjection`, `TraceBundle` | `PENDING`: durable Check schema, route expansion and history/nullability tests. |
| `BD-012` | `CONTRACT_CLOSED` | `PathChangeProjectionV1` supports exactly `SELF_CORRECTION`, `ADD_TASK`, `CHANGE_DEPENDENCY`; sparse graph events refresh and never fabricate Tasks. | `001..004`, `008..011`, `018` | `RunProjection`, `NormalizedRuntimeEventV1` | `PENDING`: projection/reducer and graph mutation evidence. |

## Crosswalk closure

| Conflict cluster | BD coverage | Final semantic decision |
|---|---|---|
| Prepare Scheme vs Plan/Tasks | `BD-007` | Scheme-only until Confirm. |
| Confirm/start route and state | `BD-007`, `BD-008` | One Confirm/Start action; immutable admission at `PLANNING`. |
| Durable idempotency | `BD-007`, `BD-008` | Scope+route+key binds canonical request hash. |
| Progress/enums | `BD-001`, `BD-002`, `BD-009`, `BD-010`, `BD-012` | Backend fraction and total maps; adapter-only percent. |
| Runtime event semantics | `BD-001..003`, `BD-010`, `BD-012` | Raw names, versioned payloads and exact effects. |
| Browser SSE protocol | `BD-001..003`, `BD-012` | Snapshot/replay/recovery/terminal protocol is exact. |
| Financial Review | `BD-004..006`, `BD-010`, `BD-011` | Exact Review/Check/Judgment/lineage projection. |
| Artifact semantics | `BD-004`, `BD-006` | Independent slots, attempts, availability and safe delivery. |
| Financial/Object projection | `BD-001`, `BD-004..006`, `BD-009`, `BD-010` | Lossless release truth and deterministic eligible latest Run. |

## Independent-audit impact

Both independent audits failed the bound Phase 3 candidate. Missing generated preimages are a
nonconformity against `BD-006`; signed-prior/Decimal-context findings are nonconformities against
`BD-005`; the telemetry-secret leak is governed by closed `UAC-018`. These receipts block UAC-001
and Contract Freeze, but do not create a new BD or make any BD semantic choice ambiguous.

```text
BD_TOTAL=12
BD_CONTRACT_CLOSED=12/12
BD_STILL_OPEN=0
BD_IMPLEMENTATION_EVIDENCE_PENDING=12
ROUTE_ABSENCE_IS_NOT_CONTRACT_AMBIGUITY=YES
PHASE5_LEAKAGE=0
```
