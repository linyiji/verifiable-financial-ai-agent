# Frontend Change Request — V17 Phase 4 Core Integration

```yaml
change_id: FRONTEND_V17_PHASE4_CORE_INTEGRATION
record_revision: DRAFT-01
status: DRAFT_CHANGE
title: Frontend V17 Phase 4 Core authoritative backend integration

previous_baseline_id: FRONTEND_BASELINE_V8.1
previous_baseline_sha: d854c97789c98cca14fee3f4b3d7f00e0d5d137a
previous_baseline_tree: 50114fa04c2a0ad81597283f5a487806e2e640cd
previous_frontend_manifest_sha256: d48a33b381ddd719867707d81c2d687ed7d9e8b95a5930d2353c94b0526c230c
promotion_governance_carrier: e2aef1edc22631dc988c862c18972f0fd7630625
promotion_carrier_apps_web_equivalent: true

candidate_sha: PENDING
candidate_tree_fingerprint: PENDING
candidate_build_sha256: PENDING
audit_result: NOT_RUN
audit_id: PENDING
implementation_authorized: false
current_gate: BLOCKED_BY_BACKEND_CONTRACT
```

## Reason and intended outcome

Replace the approved V8.1 pre-integration Demo projection path with an authoritative Phase 4 Core
HTTP/SSE path while preserving V8.1 navigation, Object/Run identity, Initial Plan versus Actual Path,
Claim Trace, financial authority, accessibility, responsive behavior, and Demo/real provenance
boundaries. Adopt only the reviewed V17 UX/product delta; the V17 scaffold is not source authority.

The Candidate must remain blocked until the backend Phase 4 contract family, corrected V17 reference
manifest, and this Change Request are frozen and approved.

## Change-type classification

| Type | Selected | Rationale |
|---|---:|---|
| `BACKEND_CONTRACT` | yes | Real REST/SSE adapters, normalized projections, enum maps, availability/errors, identity, artifacts, trace, and recovery |
| `PRODUCT_SEMANTIC` | yes | Data authority changes from Demo to backend; prepare/start/release/financial/A-B-C meaning is frozen |
| `INTERACTION` | yes | Prepare, retry, reconnect, artifact, trace, history, focus, scroll, disabled/unavailable, filter/search behavior changes |
| `SCENARIO_CHANGE` | yes | Real variants of Scenes 01–04 become Phase 4 acceptance; Demo and integrated evidence separate |
| `ACCESSIBILITY` | yes | New busy/stale/error/unavailable/live/overlay/tab/filter states require keyboard and announcement contracts |
| `RESPONSIVE` | yes | V17 composition/state density affects all six pages at every governed viewport |
| `UX_VISUAL` | yes | V17 introduces a reviewed visual/component hierarchy delta |
| `BUG_FIX` | yes | Focused fixes are required for known pre-integration gaps and to prevent scaffold regressions in reducer ordering, unknown handling, idempotency, identity fallback, SSE named events, and Demo isolation; each needs a reproduction test |

The regression scope is the union of all selected types.

## Affected pages

| Page | Declared Phase 4 delta |
|---|---|
| `NewResearchTaskPage` | Exact Object selection; backend-authored honest Scheme preview; regenerate; one confirm/start; exactly-once recovery |
| `ResearchRunsPage` | Global authoritative Run collection, ordering/cursor, state/progress/activity, loading/error/empty/retry |
| `ResearchRunPage` | Atomic Run projection, immutable plan, actual graph, runtime state, review/result availability; tabs own presentation only |
| `ResultsPage` | A Professional Report, B Financial Review, C Execution Record, exact Claim Trace, artifact availability/integrity |
| `ResearchObjectsPage` | Authoritative Object collection and creation; no symbol/name fallback |
| `ResearchObjectDetailPage` | Released Object Core only: exact Object, Run history/latest released Run, released metrics/artifacts, Full Research entry |

Production navigation remains New Task / Runs / Research Objects. Presenter is never production
navigation.

## Affected components and files

The exhaustive ownership and path map is in `V17_FRONTEND_FILE_CHANGE_MATRIX.md`. Declared shared
files are `types/domain.ts`, `data/FrontendDataSource.ts`, and `runtime/RuntimeTransport.ts`, all owned
by the Shared Contract Owner. `App.tsx` and final composition remain Coordinator-owned.

Phase 4 reaches the six pages; `App.tsx`; `AppShell`; HTTP/data/runtime adapters; the reducer/status
maps; Research Plan, Runtime Workspace, Research Path, Professional Report, Financial Review,
Execution Record, Trace Chain, Claim/Task drawers; routing/history; availability overlays; applicable
modular styles; and focused adapter/runtime/acceptance tests.

`ResearchMemory` and `ResearchCompare` are Phase 5. Presenter and all Demo data/scenario/runtime
material are Demo-only.

## Affected contracts

```text
Backend DTO
→ HttpFrontendDataSource
→ normalized Frontend projection
→ reducer/store
→ Page/Component
```

| Frontend contract | Intended backend authority | Current gate |
|---|---|---|
| `GlobalRunCollectionProjection` | `ResearchRunCollectionV1` | Projection/route required |
| `PreparedResearchDraft` | `ResearchRunDraftV1` | Semantic conflict/freeze required |
| `ConfirmAndStartResult` | `RunAdmissionV1` | Durable idempotency/admission required |
| `RunProjection` | `AtomicRunProjectionV1` | Atomic projection/watermark required |
| `NormalizedRuntimeEventV1` | Versioned Phase 4 SSE mapping | Semantic conflict/freeze required |
| `ConnectionState` | Snapshot/cursor/reconnect/gap/terminal protocol | Freeze required |
| `FinancialReviewProjection` | `FinancialReviewProjectionV1` | Projection/fields required |
| `ClaimTraceProjection` / `TraceBundle` | `TraceBundleV1` | Projection/route/anchors required |
| `ReportArtifactGroup` | Group projection + authorized byte routes | Projection/routes required |
| `ReleasedFinancialMetric` | Lossless release projection | Enrichment/freeze required |
| `ReleasedObjectCoreProjection` | Released Object Core V1 | Projection/route required |
| `ErrorEnvelope` | Typed Phase 4 error | Freeze required |
| `Availability` | `AvailabilityV1` | Projection/freeze required |

Pages never consume raw JSON. Dynamic mutation support remains exactly `SELF_CORRECTION`, `ADD_TASK`,
and `CHANGE_DEPENDENCY`; the deferred names `RETURN_TO_STEP`, `WAIT_FOR_USER`, and `RESUME`, plus any
unknown value, fail closed.

## Backend dependency

```yaml
backend_dependency:
  required: true
  target_contract_family: phase4-core/v1
  freeze_state: NOT_FINAL
  inspected_backend: codex/phase3-contracts@11fe8173a25ff7ac08bae42340ba7c6fae591be5
  readiness: BLOCKED
  preaudit: READY_WITH_GAPS
  contract_freeze: NOT_READY
  fallback_and_provenance: >-
    Production fails safely or shows a typed unavailable/error state. It never
    substitutes DemoFrontendDataSource, DemoRuntimeTransport, another Object/Run,
    locally calculated financial values, or fixture artifacts.
```

All twelve `BD-001..012` / `P4-CB-001..012` dependency records in the backend dependency matrix must
close before this record may advance to `CHANGE_APPROVED`. Closure must bind an exact backend SHA,
clean-tree fingerprint, schema/event-map hashes, routes, authorization, persistence/restart semantics,
and passing contract tests.

## Before/after semantic contract

### Current approved behavior

V8.1 is an approved pre-integration Demo baseline. It preserves UX, interaction, identity, trace,
focus/history, financial-authority, and six-Scene contracts, but makes no live REST/SSE claim.

### Proposed behavior

The Candidate must:

1. select/create one exact Research Object and retain its ID through the journey;
2. prepare a backend-authored draft and label a Scheme-only preview honestly;
3. never invent Tasks or graph contents before backend confirmation creates them;
4. make one Confirm/Start action freeze the exact input, create exactly one Run, and auto-start it;
5. retry an ambiguous confirmation with the same request-bound durable idempotency key/body;
6. bootstrap from one event-consistent Run projection and apply normalized same-Run events only via
   `runtimeEventReducer`;
7. recover deterministically across disconnect, duplicate, gap, out-of-order, refresh, terminal reopen,
   Back/Forward, and deep links;
8. display backend-released financial values without arithmetic or semantic inference;
9. bind Report A, Review B, and Execution C to the same Object, Run, and canonical record;
10. navigate Claim Trace only through backend-owned relations and exact scoped anchors;
11. expose typed observable process facts but no hidden Chain-of-Thought;
12. fail closed on schema/event/status unknowns, identity mismatch, unavailable detail, or integrity failure.

## Scene declaration

| Scene | Impact | Phase 4 disposition |
|---|---|---|
| `SCENE-01` Full Financial Research | `AFFECTED` | Real variant `PHASE4_CORE_REQUIRED`: prepare/start, runtime, released finance, A/B/C, trace, artifacts |
| `SCENE-02` Dynamic Research Path | `AFFECTED` | Real variant `PHASE4_CORE_REQUIRED`: immutable plan, authoritative actual graph, bounded mutations, replay/recovery |
| `SCENE-03` Self-Correction and Review | `AFFECTED` | Real variant `PHASE4_CORE_REQUIRED`: same-Task correction, exact recalculation/review/release closure |
| `SCENE-04` Claim Trace | `AFFECTED` | Real variant `PHASE4_CORE_REQUIRED`: exact round trip through all relations and original anchor |
| `SCENE-05` Object Accumulation | `AFFECTED` — compatibility only | Shared frontend/Demo regression; real Object Memory/version behavior remains `PHASE5_ACTIVATED` |
| `SCENE-06` Incremental Return | `AFFECTED` — compatibility only | Disabled/unavailable and Demo regression; real Incremental remains `PHASE5_ACTIVATED` |

No Phase 4 evidence may claim real Scene 05/06 behavior.

## Interaction impact and reservations

The authoritative starting ledger remains 69 active exposed interactions, tombstone `015`, and a
70-row historical union. Existing IDs `001..070` and gates `P4-E2E-001..106` retain their identity.

The inspected V17 target contains two distinct Execution Record intents and four Presenter intents,
so this Change Request reserves:

| Interaction | Gate | Contract | Activation |
|---|---|---|---|
| `071` | `P4-E2E-107` | Execution actor-type filter | `PHASE4_CORE_REQUIRED`; same Run/canonical record, presentation only |
| `072` | `P4-E2E-108` | Execution free-text search | `PHASE4_CORE_REQUIRED`; same Run/canonical record, presentation only |
| `073` | `P4-E2E-109` | Presenter Scene selector | `DEPLOYMENT_ACTIVATED`; Demo source/result class only |
| `074` | `P4-E2E-110` | Presenter reset | `DEPLOYMENT_ACTIVATED`; Demo source/result class only |
| `075` | `P4-E2E-111` | Presenter previous | `DEPLOYMENT_ACTIVATED`; Demo source/result class only |
| `076` | `P4-E2E-112` | Presenter next | `DEPLOYMENT_ACTIVATED`; Demo source/result class only |

Presenter activation requires `VITE_ENABLE_PRESENTER=true`; production default is `false`. Its gates
never enter `PHASE4_CORE_E2E_RESULT` and cannot produce real-backend evidence.

Projected inventories are 71/71 classified in production default, 75/75 in Presenter-enabled Demo,
and 76/76 for the all-mode historical union including tombstone `015`. Exact existing-row
`UNCHANGED/CHANGED` dispositions are in `V17_INTERACTION_IMPACT_MATRIX.md`.

## Phase 5, Demo, and reference boundary

`PHASE5_EXTENSION`: real Scene 05/06; Research Memory/Compare; Research Object/View versions;
Comparison Dataset; Incremental seed; freshness/reuse/refresh/revalidate/prevent; Claim Diff; Object
Writeback. These may be disabled, unavailable, scaffolded, or clearly Demo-only but never
frontend-authored truth.

`DEMO_ONLY`: Presenter, demo data, scenario runtime/scenarios, Demo stores/transports. No Demo module
may become an authority dependency of HTTP/SSE, real Run/released result/review/artifact/Object Core.

`REFERENCE_ONLY`: both HTML references and V17 handoff/scaffold documents. HTML must never be pasted
wholesale into a production component.

## Reference relationship

```yaml
baseline_reference:
  id: UX_REFERENCE_V8
  revision: 8.1.0
  file_sha256: d4131743eb30e41e52e1b17bfa27ba485f5f79378a7ac04dcce15c5eb87beda6
  aggregate_sha256: c9813d9d0db9249b38bf2f350859e15ade28a7b1536a154f08d690981530a3a2
  relationship: APPROVED_BASELINE_PAIR

v17_reference_input:
  id: UX_REFERENCE_V17
  file_sha256: 1cc44c95017b2178e39138b1310e02c55d849dd71af50b63c074686a215ed18d
  package_sha256: b90a356d666c30a07362f080fd418a2cf051c9b80483d308eac474dc51d79f31
  current_relationship: REFERENCE_INPUT_ONLY
  target_candidate_relationship: COMPATIBLE_WITH_DECLARED_DELTA
  blocker: package manifest omits four files and has a stale README digest
```

Before Change approval, a corrected content-addressed V17 reference manifest must cover HTML,
behavior documents, component mapping, accessibility/responsive rules, Scenes, interactions,
precedence, and all Demo/Phase 5 differences.

## Required tests

- Node 24 clean `npm ci`, typecheck, runtime tests, and build.
- Runtime-decoder/adapter fixtures for every normalized DTO, null/unknown/error/availability case.
- Complete backend DTO → adapter → projection → reducer/store → component coverage.
- `P4-ID-001..028` and `P4-SSE-001..020`.
- Activated Phase 4 E2E rows from `001..108`, retaining `015` as non-executable tombstone and all
  Phase 5/deployment activation rules; Presenter `109..112` run only in the isolated Demo target.
- Real `SCENE-01..04` and separate six-Scene Demo regressions.
- Exact Object/Run/Task/Claim/Review/Artifact/Execution identity plus cross-object/run negatives.
- Prepare/regenerate/double-click/lost-response/backend-restart exactly-once behavior.
- Financial fixture `0.6547 RATIO`, backend display `65.47` + `%`, visible `65.47%`.
- A/B/C same canonical record; complete Claim Trace round trip; independent HTML/PDF integrity.
- Deep links, refresh, Back/Forward, focus trap/restore, scroll/highlight restoration.
- Keyboard/name/role/value/live announcement/disabled-reason/retry/dismiss/filter/search behavior.
- Governed `1024/1280/1366/1440/1920 × 900` viewports and any later approved V17 viewports.
- Zero application console errors/unhandled requests and production-bundle Demo/Presenter isolation.
- 100% production, Demo-enabled, and historical interaction classification.

No Playwright implementation is authorized by this record.

## Candidate freeze rules

A future Candidate must be created only from a fresh clean source at `d854c977…`; the carrier may
supply its governance records because its `apps/web` tree is identical. The freeze record must bind:

```yaml
candidate_freeze:
  change_request_revision_sha256: PENDING
  candidate_sha: PENDING
  candidate_git_tree: PENDING
  tree_state: CLEAN
  actual_changed_file_manifest_sha256: PENDING
  package_lock_sha256: PENDING
  node: exact Node 24.x
  npm: exact version
  build_artifact_manifest_sha256: PENDING
  backend_candidate_sha: PENDING
  backend_contract_manifest_sha256: PENDING
  v17_reference_manifest_sha256: PENDING
  scene_corpus_sha256: PENDING
  interaction_matrix_sha256: PENDING
  test_oracle_manifest_sha256: PENDING
  frozen_at: PENDING
```

Any source, lockfile, contract, reference, fixture, generated asset, Scene, interaction, or test-oracle
change creates a new Candidate and invalidates reachable evidence. No dirty historical checkout may
contribute content.

## Independent Delta Audit

The auditor must be independent of the sole material implementation author and must:

1. authenticate V8.1, Candidate, builds/toolchains/locks, reference pair, backend contracts, and evidence;
2. compare baseline→Candidate, approved request→actual delta, and frozen references/contracts→behavior;
3. account for every file, dependency, fixture, route, asset/CSS, generated output, and oracle delta;
4. test all affected consumers, selected change types, real Scenes 01–04, and separate Demo Scenes;
5. retain real Scenes 05/06 as `DEFINED_NOT_ACTIVATED` until Phase 5;
6. verify 100% interaction inventories, all required gates on the exact frozen Candidate, and zero
   unresolved P0/P1 findings;
7. return only `PASS` or `FAIL`.

A prose summary, screenshot, Demo pass, skip, conditional pass, or self-audit cannot promote a
Candidate.

## Current decision

```text
CHANGE_RECORD_DRAFT_READY = YES
CHANGE_APPROVAL_READY = NO
FRONTEND_V17_IMPLEMENTATION_AUTHORIZED = NO
FRONTEND_V17_CURRENT_GATE = BLOCKED_BY_BACKEND_CONTRACT
```

## Final Coordinator preparation review

- [x] Approved V8.1 source remains immutable; no application/backend production source was edited.
- [x] Dirty historical frontend checkouts were recorded and excluded from authority.
- [x] The V17 package is reference/scaffold only and its manifest defects are disclosed.
- [x] Phase 4 Core, Phase 5 Extension, Demo-only, reference, governance, and out-of-scope files are separated.
- [x] All 65 V17 archive files and the 33-file proposed Phase 4 footprint are classified.
- [x] Every shared file has one owner; `App.tsx` composition remains Coordinator-owned.
- [x] All 13 named frontend contracts have a dependency state; 12 backend dependencies remain open.
- [x] No frontend financial arithmetic or semantic inference is proposed.
- [x] No Demo fixture may masquerade as backend data and no cross-object/latest fallback is permitted.
- [x] No hidden Chain-of-Thought field or rendering is required.
- [x] Real Scene 05/06 behavior remains Phase 5 and is not claimed by Phase 4.
- [x] Interaction and P4-E2E IDs remain append-only; proposed additions are above `070`/`106`.
- [x] Presenter remains Demo-only behind `VITE_ENABLE_PRESENTER=false` by default.
- [x] Phase 4 implementation remains blocked until the backend contract freeze and Change approval.

```text
V17_FRONTEND_PREPARATION_READY = YES
FRONTEND_V17_IMPLEMENTATION_AUTHORIZED = NO
FRONTEND_V17_CURRENT_GATE = BLOCKED_BY_BACKEND_CONTRACT
APPROVED_PARENT_BASELINE = FRONTEND_BASELINE_V8.1
APPROVED_PARENT_SHA = d854c97789c98cca14fee3f4b3d7f00e0d5d137a
NODE24_COMPATIBILITY = PASS
V17_FILES_CLASSIFIED = 65/65
PHASE4_CORE_FILES = 33
PHASE5_DEFERRED_FILES = 2
DEMO_ONLY_FILES = 6
UNRESOLVED_FRONTEND_CONTRACT_CONFLICTS = 9
BACKEND_DEPENDENCIES_OPEN = 12
```
