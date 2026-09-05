# Phase 4 Core Acceptance Architecture

Status: **ACCEPTANCE DESIGN READY — NOT IMPLEMENTED — NOT EXECUTED**

Authority date: `2026-09-04` (Asia/Shanghai)

```text
PHASE4_ACCEPTANCE_DESIGN_READY=YES
PHASE4_ACCEPTANCE_IMPLEMENTATION_AUTHORIZED=NO
PHASE4_ACCEPTANCE_EXECUTED=NO
```

This package is the independent acceptance-design authority for Phase 4 Core. It defines what a later candidate must prove; it does not change Backend or Frontend source, create routes, implement Playwright, connect REST/SSE, change persistence, or authorize Phase 4 production work.

`DESIGN_READY=YES` means the namespaces, ownership, activation, required variants, evidence and decision algorithm are complete enough to govern the final-freeze delta. It does not mean draft-dependent wire details are frozen: the 18 enumerated conflicts below deliberately prevent harness implementation and execution.

## 1. Authority and reconciled inputs

Authority is applied in this order when two inputs differ:

1. approved product/domain, release, identity, financial, and persistence semantics;
2. final frozen Backend Phase 4 wire and event contracts, once approved;
3. this gate catalogue and its activation/crosswalk records;
4. approved Frontend baseline plus an approved V17 Change Request and Candidate;
5. suite implementation details.

| Input | Coordinate inspected | Design disposition |
|---|---|---|
| Approved Frontend V8.1 manifest and interaction ledger | `codex/frontend-v8-1-baseline-promotion` at governance carrier `e2aef1edc22631dc988c862c18972f0fd7630625`; approved source `d854c97789c98cca14fee3f4b3d7f00e0d5d137a` | Authoritative and immutable |
| Frontend Change Protocol / Delta Audit Policy | `docs/frontend-governance/` | Authoritative candidate and audit governance |
| V17 Integration Readiness Review | no final review record present | Mandatory execution-entry input; no approval inferred |
| V17 preparation outputs | `V17_FRONTEND_CONTRACT_PREPARATION.md` and `V17_FRONTEND_BACKEND_DEPENDENCY_MATRIX.md` appeared during reconciliation; status remains provisional and blocked, with nine conflict clusters | Design input only; no V17 implementation authority |
| Phase 4 Backend contract package | `PHASE4_BACKEND_CONTRACT_FREEZE_DRAFT.md` plus the API schema, runtime-event, identity/error/availability, blocker-closure and acceptance-mapping companions appeared during reconciliation; the package says `PROVISIONAL_CONTRACT_DRAFT_READY` / `NOT_FINAL` and binds inspected Backend `11fe8173a25ff7ac08bae42340ba7c6fae591be5` | Concrete design input only; its local `P4-BC-001..018` case labels are subordinate variants mapped into `P4-BE-001..030`, not a second gate namespace |
| Phase 4 Backend Final Contract Freeze | approved final freeze not present; the freeze *draft* remains `NOT_FINAL` | Mandatory before harness implementation |
| Phase 3 Backend candidate | moving workstream `codex/phase3-contracts`; not accepted here | Informational architecture inventory only; cannot supply Phase 4 evidence |
| Existing E2E, activation, Scene, identity, SSE, preaudit, mapping and blocker documents | `docs/integration/PHASE4_*` | Reconciled into this package |
| V8.1 E2E append-only delta | immutable baseline branch; `P4-E2E-101..106` | Authoritative; `015` remains tombstoned |

The missing final V17 readiness decision and Backend freeze are execution-entry prerequisites. The draft blocker matrix folds the twelve preaudit `P4-CB-001..012` rows into eight open V17 Backend blocker groups; none is implemented or waived. The freeze draft's `UNRESOLVED_PHASE4_SEMANTIC_CONFLICTS=0` means its provisional design choices are internally decision-complete; it does not make those choices final. This acceptance package therefore separately records 18 unresolved final-freeze/executable-oracle conflicts that prevent a harness from treating draft choices as approved wire authority.

## 2. Acceptance ownership

| Owner | Exclusive responsibility | Required outputs |
|---|---|---|
| Acceptance Coordinator | gate IDs, activation, evidence sufficiency, binary decision rules, crosswalk, independence and aggregate release decision | this architecture, evidence spec, audit protocol and crosswalk |
| D1 Backend contract suite | HTTP/domain/projection/restart contracts | `P4-BE-*` catalogue and contract matrix |
| D2 SSE/runtime chaos suite | real stream, replay, disorder, convergence and terminal behavior | `P4-SSE-001..020` plan and mapped Backend support gates |
| D3 identity/security suite | exact joins, authorization, A/B contamination negatives | `P4-ID-001..028` negative plan |
| D4 finance/trace/artifact suite | lossless metric, A/B/C, Claim Trace and artifact bytes | finance/trace/artifact plan |
| D5 browser/interaction suite | V8.1/V17 regression, navigation, focus, responsive and console | browser execution plan |
| Implementation teams | build candidates and self-test | may not declare final acceptance |
| Independent auditor | authenticate candidates, rerun critical gates, inspect raw evidence and decide | exactly `PASS` or `FAIL` |

Sub-suite owners may add test cases under an existing gate but may not renumber a gate, narrow its oracle, change activation, substitute Demo evidence, or create a qualified pass.

### Package index

| File | Authority |
|---|---|
| `PHASE4_ACCEPTANCE_ARCHITECTURE.md` | scope, ownership, activation and aggregate decision |
| `PHASE4_BACKEND_ACCEPTANCE_GATE_CATALOG.md` | full `P4-BE-001..030` gate contracts and final-freeze conflict register |
| `PHASE4_BACKEND_CONTRACT_TEST_MATRIX.md` | seven mandatory variant classes for every Backend gate |
| `PHASE4_SSE_CHAOS_ACCEPTANCE_PLAN.md` | `P4-SSE-001..020` end-to-end and chaos execution |
| `PHASE4_IDENTITY_NEGATIVE_TEST_PLAN.md` | `P4-ID-001..028`, A/B contamination and fallback rejection |
| `PHASE4_FINANCIAL_TRACE_ARTIFACT_ACCEPTANCE.md` | financial, A/B/C, Trace, Proof and representation-byte closure |
| `PHASE4_BROWSER_ACCEPTANCE_EXECUTION_PLAN.md` | E2E, Scene, interaction, navigation, a11y, responsive and console execution |
| `PHASE4_ACCEPTANCE_EVIDENCE_MANIFEST_SPEC.md` | candidate-bound evidence and failed-attempt schema |
| `PHASE4_INDEPENDENT_AUDIT_PROTOCOL.md` | independent rerun and binary audit decision |
| `PHASE4_ACCEPTANCE_GATE_CROSSWALK.md` | authoritative namespace/Scene/interaction mapping |

## 3. Proof stack

Acceptance closes from independent sources, not from one component restating itself:

```text
Domain and persisted truth
  -> Backend contract test
  -> Backend integration/restart test
  -> Frontend adapter contract test
  -> Browser integrated/chaos test
  -> Independent audit
```

Passing a lower layer is necessary where mapped but never sufficient for a higher layer. In particular, a reducer test cannot prove SSE recovery, a route test cannot prove browser identity, and a DOM-to-DOM comparison cannot prove financial truth.

## 4. Source classes

Every attempt declares exactly one `source_class`:

| Source class | Permitted proof |
|---|---|
| `DEMO_UX_ONLY` | baseline interaction, layout, accessibility and scripted Demo semantics only |
| `INTEGRATED` | real Backend HTTP/SSE and durable state using controlled acceptance records |
| `PUBLIC_REAL` | integrated path plus permitted live public-provider behavior |
| `LIMITED_REAL` | integrated path under the frozen limited-network policy |
| `OFFLINE_INTEGRATED` | real Backend/PostgreSQL/SSE with a manifested Backend fixture and truthful fixture label |
| `CHAOS_SSE` | integrated stream through a byte-preserving fault proxy |

No source-class promotion is allowed. `DEMO_UX_ONLY` cannot satisfy a real Backend or integrated browser gate. `OFFLINE_INTEGRATED` is not `LIVE`. A public Run that falls back to a fixture fails.

## 5. Activation and result model

### Activated Phase 4 Core

- real `SCENE-01..04`;
- the 99 unique `PHASE4_CORE_REQUIRED` `P4-E2E` IDs, including `101`, `102`, `105`, and `106`;
- all Phase 4 Core `P4-BE` gates in the Backend catalogue;
- `P4-SSE-001..020`;
- core identity assertions `P4-ID-001..020` and `023..028`;
- 69/69 current Frontend interactions as a separate complete baseline regression corpus;
- persistence/restart, cross-object, finance, release, artifact and browser-negative variants mapped by the crosswalk.

### Defined but inactive

- real `SCENE-05..06`;
- `P4-E2E-062`, `097`, `103`, `104` and the Phase 5 variants of mixed gates `058` and `059`;
- `P4-ID-021..022`;
- ResearchObjectVersion, ResearchViewVersion, ComparisonDataset, IncrementalResearchSeed, Object Writeback and Reuse/Refresh/Revalidate/Prevent;
- `P4-E2E-099..100` until a Phase 4B/RP2/Competition deployment profile is explicitly activated.

An inactive gate has `activation_state=DEFINED_NOT_ACTIVATED` and `result=null`. It is absent from PASS/FAIL/BLOCKED/SKIPPED counts and all current denominators.

### Tombstone

`P4-E2E-015` is `RETIRED_TOMBSTONE`, has `result=null`, remains in the 70-row historical interaction union, is excluded from the current executable denominator, and is never reused.

### Binary release outcomes

During preparation, `NOT_IMPLEMENTED` may describe harness status only. Once a required gate is activated, its result is exactly `PASS` or `FAIL`. Missing, blocked, skipped, not-run, flaky-only or qualified results evaluate to `FAIL` in the release aggregate.

## 6. Candidate binding

One final execution manifest must bind all of:

```text
approved_phase3_backend_parent_sha
backend_phase4_candidate_sha
backend_clean_tree_fingerprint
frontend_baseline_id = FRONTEND_BASELINE_V8.1
frontend_baseline_sha = d854c97789c98cca14fee3f4b3d7f00e0d5d137a
approved_frontend_change_request_revision
frontend_v17_candidate_sha
frontend_clean_tree_fingerprint
database_revision
contract_schema_version + hashes
event_contract_version + hash
route_version
backend/frontend build hashes
runtime/deployment mode
fixture/provider manifest where applicable
browser/toolchain/environment identity
```

Browser evidence is invalid if it mixes different Backend or Frontend candidates. Any source, lockfile, generated asset, contract, migration, build configuration or oracle change creates a new Candidate and requires applicability analysis plus reruns.

## 7. Execution topology

The later harness must provision an isolated PostgreSQL database, artifact store and Backend per run; a control browser; a chaos browser/proxy when required; and an independent record-capture client. The record client captures authoritative HTTP records and persisted event sequences without using the DOM as truth.

Each activated Scene follows:

1. create distinct Objects A and B and capture their IDs;
2. prepare and confirm a Run with request-bound durable idempotency;
3. capture Run projection and its `last_sequence` before subscribing;
4. consume actual `text/event-stream`, applying permitted chaos only to complete real frames;
5. reconcile browser state with fresh Backend projections;
6. close the released metric/Claim/Review/Task/Calculation/Evidence/Proof/CER/report/artifact chain;
7. restart the Backend and open a new browser context;
8. execute cross-object and missing/unknown negative variants;
9. retain the evidence bundle and a binary gate result.

## 8. Mandatory negative architecture

Every applicable contract has a positive case and at least one independent negative oracle. The shared negative corpus includes:

- wrong Object/Run/Task/Claim/Review/Artifact/Evidence/Calculation IDs using Objects A and B;
- missing record, missing required field, unknown schema/event/status/version and unauthorized caller;
- same idempotency key with different request/draft;
- negative, unknown opaque and ahead-of-stream cursors;
- duplicate, delayed, out-of-order, gapped and snapshot-race stream delivery;
- unavailable, cross-owned, wrong-media, wrong-size and wrong-hash artifacts;
- semantic financial mismatch, proof/review/release failure and structurally present but unavailable report;
- stale/deep URLs, refresh, Back/Forward and shared browser-state contamination;
- browser console error, unhandled rejection and unexpected HTTP failure.

All identity mismatches fail closed. There is no nearest, latest, first, symbol, title or metric-name repair outside an explicitly object-overview-only `latest_released_run_id` lookup.

## 9. Release and financial authority

A completed-looking UI is not sufficient. A released result passes only if the Backend release gate succeeded, `ReleasedResearchResult` exists, Review is valid, the Canonical Execution Record is terminal, required Proof state is satisfied, and artifacts are consistent.

The fixed financial witness is:

```text
canonical_value="0.6547" canonical_unit="RATIO"
display_value="65.47" display_unit="%"
browser_visible="65.47%"
```

The Browser must display Backend-provided display fields. `0.6547%`, unlabelled `0.6547`, a client-side multiply, or any client-side financial calculation fails.

## 10. Repository test-architecture assessment

| Existing primitive | Usable later | Current limitation |
|---|---|---|
| pytest unit/integration/acceptance suites and phase runners | domain, calculation, release and evidence seed patterns | current runners predate `P4-BE` and do not prove browser contracts |
| PostgreSQL migration/schema/restart/event tests | durable store, contiguous per-Run sequence and restore patterns | final Phase 4 schema/composition must be frozen and manifested |
| runtime SSE serializer and persisted replay tests | frame and cursor seed cases | no end-to-end browser recovery/chaos proof |
| Langfuse fake adapter and connectivity smoke | sanitized trace-reference checks | observability cannot be a business acceptance oracle |
| content-addressed raw artifact helper | integrity and safe-segment patterns | ReportArtifact authorization/delivery contract is not frozen |
| V8.1 `test:runtime` reducer script | Demo Scene and reducer regression | Demo-only; no HTTP/SSE/browser authority |
| prior browser audit evidence | baseline UX reference | no committed Playwright Phase 4 production suite or chaos proxy |
| `HttpFrontendDataSource` / `SSERuntimeTransport` | future integration boundaries | V8.1 versions are deliberately fail-closed placeholders |

No existing test result is grandfathered into a Phase 4 gate. Existing evidence may guide implementation but final results must be rerun against the manifested same-candidate pair.

## 11. Aggregate decision

The independent auditor computes:

```text
PHASE4_CORE_ACCEPTANCE =
  candidate_manifest_valid
  AND all_required_P4_BE_pass
  AND all_99_core_P4_E2E_pass
  AND all_20_P4_SSE_pass
  AND all_26_core_P4_ID_pass
  AND real_SCENE_01_04_pass
  AND current_interaction_regression_69_of_69_pass
  AND no_required_evidence_gap
  AND independent_audit_pass
```

Inactive and tombstoned rows do not enter this expression. A single false or absent required term yields `FAIL`; there is no qualified release PASS.

## 12. Execution entry and stop boundary

Harness implementation and execution remain unauthorized until all five are available:

1. immutable Phase 3 Backend Candidate;
2. Backend Independent Audit `PASS`;
3. Financial Semantics Audit `PASS`;
4. approved Phase 4 Backend Final Contract Freeze;
5. completed Frontend V17 preparation with approved Change Request and immutable Candidate.

At that point, perform a focused delta against this design. Until then, stop at documentation.

## 13. Coordinator design decision

The package resolves coordinator-owned semantics—activation, binary outcomes, source separation, fail-closed identity, financial authority, SSE convergence, candidate binding and independence. The Backend catalogue's 18 `UAC-*` rows are the authoritative unresolved final-freeze conflicts; they remain hard harness-implementation blockers and may not be guessed from the provisional drafts.

Namespace plans also record identity-, SSE-, finance- or browser-specific views of these uncertainties. Those views overlap and are not added together. The package-level count is the 18-row `UAC-*` register in the Backend gate catalogue; a final contract-freeze delta must disposition each row and show how all subordinate uncertainty rows map to it.

```text
P4_BE_GATES_DEFINED=30
P4_E2E_GATES_REFERENCED=106/106
P4_SSE_GATES_REFERENCED=20/20
P4_ID_ASSERTIONS_REFERENCED=28/28
UNRESOLVED_ACCEPTANCE_SEMANTIC_CONFLICTS=18
UPSTREAM_V17_FRONTEND_DEPENDENCIES_AWAITING_FREEZE=12
UPSTREAM_BACKEND_BLOCKER_GROUPS_AWAITING_IMPLEMENTATION=8
SCENE_01_04_COVERAGE=4/4
SCENE_05_06_STATE=DEFINED_NOT_ACTIVATED
INTERACTION_CURRENT_COVERAGE=69/69
HISTORICAL_INTERACTION_UNION=70/70
```
