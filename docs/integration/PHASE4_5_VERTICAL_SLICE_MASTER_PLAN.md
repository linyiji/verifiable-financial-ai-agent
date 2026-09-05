# Phase 4/5 Vertical Slice Master Plan

Status: `DESIGN_READY - IMPLEMENTATION_PENDING - NOT_EXECUTED`  
Inspected Backend layout: clean `66edc5110b6ab7d81578cef80190497a2f11e5b2`  
Frontend parent: `FRONTEND_BASELINE_V8.1@d854c97789c98cca14fee3f4b3d7f00e0d5d137a`

The delivery unit is a user-testable vertical slice, not a Backend or Frontend layer. `[E]` means an existing extension point, `[P]` a proposed Phase 4 path, and `[TBD-P5]` an intentionally unfrozen Phase 5 surface. All seven slices are planning only.

## Dependency map

```text
IG-00
  -> VS-01 start/live Run -> IG-01
       -> VS-02 result/review (+ minimal VS-04/05 release spine) -> IG-02
       -> VS-03 dynamic path -> IG-03
       -> VS-04 trace <-> VS-05 report/artifact -> IG-04/05
  -> PJ/technical/system gates -> IG-06..10

accepted Phase 4 + future Phase 5 freeze
  -> VS-06 object accumulation -> IG-11
  -> VS-07 incremental return -> IG-12
```

## VS-01 - Research Start and Live Run

Activation: `PHASE4_CORE_REQUIRED`; state: `IMPLEMENTATION_PENDING`; gate: `IG-01`, the earliest real product test.

- Routes: strengthen `GET/POST /api/objects`, add global `GET /api/research-runs`, strengthen `POST /api/research-runs/prepare` and `POST /api/research-runs`, add `GET /api/research-runs/{run_id}/projection`, strengthen `/events` and the light Run read.
- Backend: sole-writer changes around `[E] apps/api/routes.py`, `contracts/api/models.py`, `src/application/service.py`, `src/application/persistence.py`; compose durable PostgreSQL through `src/infrastructure/database/composition.py`, not the in-memory default in `apps/api/main.py`. Prefer isolated `[P]` admission/projection/UOW modules.
- Persistence/transactions: prepare draft; confirm plus draft consumption, one Run/plan/Tasks, initial events, admission/outbox/lease; each runtime mutation plus event, projection revision and watermark; lease/start. Cursor errors complete before SSE headers.
- Frontend: unknown JSON -> private DTO -> decoder -> adapter -> `HttpFrontendDataSource`/`SSERuntimeTransport` -> Run store/reducer -> `NewResearchTaskPage`, `ResearchRunsPage`, `ResearchRunPage`, plan/workspace components. Production `App.tsx` cannot reach Demo sources.
- Runtime: all 55 raw names have total disposition (47 supported, 8 explicit unsupported); fetch-stream SSE uses incremental UTF-8 parsing, named events, `Last-Event-ID`, dedupe/order/gap recovery, snapshot reconciliation, heartbeat no-op and terminal close.
- Parallel lanes: admission/UOW; projection/SSE; frontend shared-contract/transport; creation/workspace UI; acceptance fixtures.
- Acceptance: `P4-BE-001..019`, `P4-SSE-001..020` as applicable, create/runtime `P4-E2E`, and the start half of `PJ-01`.
- Failures: expired/consumed draft, changed request under same key, double confirm, lost response, lease redelivery, wrong O/R, noncanonical/foreign/ahead cursor, gap/unknown event, restart loss. All fail closed without duplicate Run or local truth.

## VS-02 - Result and Financial Review

Activation: `PHASE4_CORE_REQUIRED`; gate: `IG-02`.

- Routes: version `/result`, add exact `/claims/{claim_id}`, expand `/review-view`. Claim IDs originate in Backend result/projection; do not invent a collection route.
- Backend: extend deterministic financial/released-result/review/release primitives and add isolated result/review projection modules. One Run-scoped UOW persists complete Review/Checks, material metrics/Claims, canonical/result identities and release-validation inputs.
- Frontend: versioned private DTOs/adapters feed `ResultsPage.tsx` and `components/review/FinancialReview.tsx`; render Backend `display_value`/`display_unit` and never calculate PASS, ratios, proof sufficiency, or release eligibility.
- Acceptance: `P4-BE-020..023`, finance/review browser gates, `PJ-01` result/review and `PJ-03` positive/blocked branches.
- Dependency correction: IG-02 cannot call a result released until a minimal VS-04 anchor-manifest and VS-05 required-HTML/release-validation Backend spine is merged. Full browser trace/artifact closes later.
- Failures: lossy decimal/unit/period/as-of, incomplete checks, cross-Run Claim/Review, Review BLOCK presented as released, client percent conversion.

## VS-03 - Dynamic Path

Activation: `PHASE4_CORE_REQUIRED`; gate: `IG-03`.

- Authority remains `/projection` plus `/events`; existing `/tasks` and `/graph` are diagnostic, not bootstrap truth.
- Backend extension points: `src/runtime/graph.py`, `state.py`, `scheduler.py`, `src/application/execution.py`, `src/domain/correction.py`, `task.py`; add an isolated path-change projection. Persist immutable planned graph, actual versions, corrections, replans, dependencies and source event IDs.
- Atomicity: correction/replan/graph operation, Task state, event append and projection revision commit together.
- Frontend: shared decoder/adapter/store plus `ResearchPath.tsx`, `TaskDetailDrawer.tsx`, `ResearchRunPage.tsx`. Self-Correction stays one Task; sparse or unknown mutation forces snapshot recovery and never constructs a Task.
- Acceptance: dynamic `P4-BE`, `P4-SSE-019..020`, `P4-E2E-031..036/089..091`, `PJ-02`, `PJ-03`, real `SCENE-02..03`.
- Failures: planned graph change, unauthorized/duplicate/cyclic dependency, split commit, out-of-order graph events, invented reason/Task or deferred mutation type.

## VS-04 - Claim Trace and Execution

Activation: `PHASE4_CORE_REQUIRED`; gate: `IG-04`.

- Routes: Claim detail, `/trace/{claim_id}`, expanded review, versioned execution, and exact result/artifact reads for the return anchor.
- Backend: combine canonical execution, Review, Claim, Calculation, Evidence, Proof and released-result records in an isolated trace projection. Persist an immutable hash-bound anchor manifest with representation-scoped HTML/PDF anchors and plural Review/Task/Execution anchors. Observability refs never substitute.
- Frontend: private Claim/Trace/Execution DTOs; `ClaimTraceDrawer.tsx`, `TaskDetailDrawer.tsx`, `FinancialReview.tsx`, new Trace/Execution components; `routing/history.ts` retains exact O/R/C/T/V/K/E/A plus tab, focus and origin anchor.
- Acceptance: `P4-BE-022..024/030`, trace browser and applicable identity gates, `PJ-04`.
- Integration waits for VS-02 Claims/Checks and VS-05 representation IDs, though fixture-driven development may proceed in parallel.
- Failures: inferred/singularized relation, first/latest/title/DOM lookup, cross-Run child, raw execution JSON or CoT, wrong representation return.

## VS-05 - Report and Artifact Delivery

Activation: `PHASE4_CORE_REQUIRED`; gates: `IG-05` then downstream IG-06.

- Routes: `/artifacts`, `/artifacts/{artifact_id}/content`, result and `/objects/{object_id}/released-state`.
- Backend: extend report/output/artifact/release primitives with isolated artifact delivery, release validation and durable artifact records. Persist fixed HTML/PDF slots, append-only per-format attempts, availability/reason, type/hash/size, non-bearer safe ref, anchor manifest and ReleaseValidationRecord.
- Transaction rule: artifact bytes may use an external store, but state/outbox/event/revision publication is atomic. Internal paths never cross the API.
- Frontend: artifact DTO/decoder/adapter; `ResultsPage.tsx`, `ArtifactUnavailablePanel.tsx`, Phase 4-only released slice of `ResearchObjectDetailPage.tsx`, and a professional report component. Browser verifies type/size/hash.
- Policy: HTML is required. PDF is independent/optional. Terminal has no PENDING. Only release coordinator emits `release.completed` then one final `run.completed`.
- Acceptance: terminal/restart/artifact/latest-release Backend gates, report/Object Core browser gates, completion of PJ-01/PJ-04.
- Failures: exposed path, mutable/tampered/cross-Run bytes, PDF absence blocking valid HTML release, two terminal events, newer failed Run selected as current.

## VS-06 - Object Accumulation (future Phase 5)

Activation: `DEFINED_NOT_ACTIVATED`; result: `null`; gate: `IG-11`; Phase 4 release effect: none.

No route, DTO, event, migration, or persistence schema is frozen here. After an explicit Phase 5 freeze, isolated P5 modules may implement append-only Object/View versions, atomic idempotent writeback and explicit two-version comparison. `src/output/writeback.py` currently represents only a proposal, not applied memory. Frontend future components may include version store, Research Memory/Compare and Object detail extensions, but comparison categories and financial deltas stay Backend-authored.

Future acceptance: real SCENE-05, the Phase 5 `P4-E2E-059` variant, `062`, `097`, `P4-ID-021..022`, plus Core regression. Reject mutable history, mixed R1/R2, latest fallback, proposal-as-applied state, client delta/category, or cross-Object pair.

## VS-07 - Incremental Return (future Phase 5)

Activation: `DEFINED_NOT_ACTIVATED`; result: `null`; gate: `IG-12`; Phase 4 release effect: none.

After VS-06 and a Phase 5 freeze, an incremental prepare/confirm contract may bind an exact source Run/View/hash and persist Backend decisions for reuse, refresh, revalidation and prevention. Prepare locks a source; confirm never floats to newer latest, creates a distinct current Run atomically, and never mutates the source. Event additions remain TBD. React cannot calculate savings, freshness, delta, or decisions.

Future acceptance: real SCENE-06, Incremental `P4-E2E-058`, `103..104`, `P4-ID-021..022`, and all applicable Core admission/SSE/finance/trace/artifact/restart regression. Reject frontend-only mode, cross-Object/unreleased/stale seed, reuse without lineage, copied prior Review/Proof, Demo milestones, source mutation, or nonempty UI delta for empty Backend delta.

## Shared hot surfaces

| Surface | Rule |
|---|---|
| `contracts/api/models.py`, future Phase 4 contract module, `apps/api/routes.py` | Backend Contract/Router `SOLE_WRITER` |
| `apps/api/main.py` | Backend integration `MERGE_COORDINATOR_ONLY` |
| `src/application/service.py` and release/admission orchestration entry | Run/Release `SOLE_WRITER`; feature work uses isolated modules |
| repositories, DB models/composition, migration chain | Persistence `SOLE_WRITER`; exactly one migration coordinator |
| runtime event/application event/SSE/PostgreSQL event files | Event/SSE `SOLE_WRITER` |
| frontend domain/data-source/runtime contracts/status/DTO/decoder/adapter roots | Frontend Shared Contract `SOLE_WRITER` |
| frontend HTTP/SSE client and runtime reducer | One frontend integration writer; feature owners review |
| `App.tsx`, `routing/history.ts` | Frontend `MERGE_COORDINATOR_ONLY` |
| shared CSS | One UX integrator rebases deltas; never overwrite remediation styles |
| Phase 5 paths | Dedicated P5 owners only after Phase 5 freeze |

## Slice checkpoints

| Gate | Producer/evidence summary | Rollback |
|---|---|---|
| `IG-00` | accepted Phase 3 parent/Run/two audits; promoted contract hashes; authorized candidates | No implementation merge before pass |
| `IG-01` | VS-01 admission, projection, SSE, frontend workspace, DB restart, manual start | Immutable VS-01 tag; baseline before slice |
| `IG-02` | VS-02 plus minimal release/manifest/HTML spine; finance and blocked-review evidence | IG-01 |
| `IG-03` | VS-03 graph/correction/replan and browser recovery | IG-02 |
| `IG-04` | VS-04 trace/execution identities | IG-03 |
| `IG-05` | VS-05 artifacts, bytes, release and Object Core | IG-04 |
| `IG-06..10` | PJ, technical, Phase 4A, preview and release gates | Last accepted integration tag |
| `IG-11` | Future VS-06 after separate Phase 5 freeze | Accepted Phase 4 |
| `IG-12` | Future VS-07 on accepted VS-06 | IG-11 checkpoint |

```text
VERTICAL_SLICES_DEFINED=7/7
PHASE4_SLICES=5/5
PHASE5_FUTURE_SLICES=2/2
PHASE5_SLICES_ACTIVATED=0
EARLIEST_REAL_PRODUCT_TEST_GATE=IG-01
FRONTEND_FINANCIAL_AUTHORITY=0
PHASE4_IMPLEMENTATION_STARTED=NO
PRODUCTION_SOURCE_MODIFIED=NO
```
