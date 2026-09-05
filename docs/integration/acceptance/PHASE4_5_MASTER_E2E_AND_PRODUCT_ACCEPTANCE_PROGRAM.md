# Phase 4 / Phase 5 Master E2E and Product Acceptance Program

Status: `DESIGN_READY — IMPLEMENTATION_PENDING — NOT_EXECUTED`  
Scope: documentation/read-only coordination only  
Machine matrix: `PHASE4_5_MASTER_ACCEPTANCE_MATRIX.json`

## Current Gate

Phase 4 has not started. `UAC-002=SATISFIED`; `BD-001..012` and `UAC-003..018` are contract-closed, not implemented. `UAC-001=OPEN` until the remediated Phase 3 candidate completes an authoritative Run and two independent audits both issue PASS. Final contract freeze has not been promoted.

```text
CURRENT_STATE=CONTRACT_CLOSED_WITH_UAC_001_OPEN
PHASE4_IMPLEMENTATION=IMPLEMENTATION_PENDING
PHASE4_AUTHORIZED=NO
EARLIEST_REAL_PRODUCT_TEST_GATE=IG-01
```

Authority is pinned to Frontend baseline `d854c97789c98cca14fee3f4b3d7f00e0d5d137a`, approved V17 R2 SHA-256 `fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19`, and Backend contract-set SHA-256 `0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741`. The inspected remediation candidate `66edc5110b6ab7d81578cef80190497a2f11e5b2` is not an acceptance receipt.

The mandatory maturity chain is `CONTRACT_CLOSED → IMPLEMENTATION_PENDING → IMPLEMENTATION_COMPLETE → TECHNICAL_ACCEPTANCE_PASS → PRODUCT_JOURNEY_PASS → RELEASE_ACCEPTED`. States cannot be skipped or substituted.

## Architecture

Acceptance follows the authoritative product chain:

```text
Object → Research Definition → Goal → Scheme → Run
       → Execution → LLM Call → Claim → Metric/Calculation
       → Evidence → Task → Review → Proof → Artifact
```

PostgreSQL is the durable business authority. API projections are atomic views of that state; normalized SSE is a replayable transport, not a second authority. Private frontend DTOs are decoded and adapted before stores/pages. Browser assertions join visible state back to HTTP/SSE, database rows, provider/FMP provenance, Review/Proof and authorized artifact bytes. Langfuse is non-authoritative observability.

Phase 4 proves the real Scenes 01–04 and Core system. Phase 5 Scenes 05–06 are designed without wire-schema or implementation authorization. Demo and Presenter are separate evidence domains and never count.

## Testing layers

| Layer | Scope | Owner | Environment / data | Evidence | Blocking severity | Entry → exit |
|---|---|---|---|---|---|---|
| L0 | static, schema, contract, route/event/identity completeness | Contract owners + QAO | E0 / contract fixtures | hash inventory, schema/route/event crosswalk | hard release blocker | UAC-001/002 + authority → IG-00 |
| L1 | pure unit: lifecycle, mapping, finance, policy, sanitization | producer lane + QAO | E0 / synthetic | deterministic test and mutation report | hard for affected contract | IG-00 → component-ready |
| L2 | component: repository, provider adapter, reducer, renderer | producer + boundary reviewer | E0 / synthetic/recorded | component transcript, hash/oracle | hard | L1 → integration-ready |
| L3 | Backend integration: PostgreSQL/UOW/API/SSE/provider/artifact | Backend + A1–A4 | E1, then E2 / controlled real | HTTP/SSE/SQL/provider evidence | hard | IG-00 → applicable IG-01..05 |
| L4 | frontend component/decoder/adapter/accessibility | Frontend + A5 | E0/E1 / fixtures | decoder/component/a11y evidence | hard | contract freeze → FE integration-ready |
| L5 | Backend–Frontend integration | F1 + Backend + QAO | E2 / controlled real | joined DTO/network/store/DOM ledger | hard | L3/L4 → X-E2E ready |
| L6 | real browser E2E | A5 + FEO | E2 / authoritative acceptance | Playwright trace, DOM/a11y/history/network/console | hard | IG-01 surfaces → FE 1–12 PASS |
| L7 | vertical slices VS-01..05 | four parents | E2 / controlled real | candidate-bound end-to-end bundle | hard | component gates → each slice PASS |
| L8 | Product Journeys PJ-01..04 | PJO + independent product reviewer | E2 / authoritative acceptance | user-visible receipt plus technical joins | hard | applicable technical gates → product PASS |
| L9 | Six-Scene program | PJO/QAO | E2 for 01–04; future for 05–06 | four real receipts; two null future rows | hard for 01–04 only | IG-05 → IG-06 |
| L10 | system acceptance/recovery/Phase 4A | A6/RCO/independent audit | E2/E3 / candidate-bound | full aggregate, restart/security/manifest | hard | IG-06 → IG-07/08 |
| L11 | Preview/competition/release | RCO + independent release audit | E3/E4 / release candidate | parity, reproducibility, fresh-machine bundle | hard when activated | IG-08 → IG-09/10 |

## Backend test path

The Backend program covers 18 target routes, `P4-BE-001..030`, `P4-SSE-001..020`, Core identity `P4-ID-001..020,023..028`, all 13 contracts, 12 BD and 18 UAC. Each P4-BE gate has POS/IDN/MIS/VER/RST/AUT/INT variants in the 210-row JSON matrix. Execution progresses E0 contract checks → E1 local PostgreSQL → E2 real runtime; it tests atomic confirm/admission, MVCC projection, cursor/replay, normalized events, graph mutation, finance/Review/trace, artifacts, latest release and total error/availability mapping.

Provider/model must be selected before admission and locked during Run. FMP follows raw→validate→normalize→conflict→accept. Proof/release is fail-closed where required. Detailed route, state, event, persistence, negative and evidence oracles are in `PHASE4_BACKEND_FULL_ACCEPTANCE_PATH.md` and `PHASE4_BACKEND_TEST_MATRIX.json`.

## Frontend test path

The real browser suite has 12 families: Object/New; Scheme/Confirm; Run Workspace; SSE progression; Dynamic Path; Financial Results; Financial Review; Execution; Claim Trace; Report/HTML/PDF; Recovery; Error/unavailable. It uses production HTTP and fetch-stream SSE, not Demo sources. Assertions cover DOM, accessible names/roles, focus, keyboard, route/history/scroll, responsive layout, network bodies/headers/cursors, console, hard refresh, new context, reconnect and component restarts.

The browser never invents IDs, availability, financial values, statuses or provider identity. Private DTO→versioned decoder→adapter→store→page boundaries must reject unknown versions/values safely. `P4-E2E-015` remains a tombstone; all 99 unique Core E2E rows retain their existing identity, and reservations 071–076 / P4-E2E-107..112 remain inactive (071–072 proposed Core, 073–076 Presenter Demo only).

## Cross-layer E2E path

`X-E2E-01..08` cover Create, Live Run, Result, Review, Trace, Artifact, Recovery and Failure. Every result joins browser action to exact request/response, normalized SSE sequence, atomic projection, PostgreSQL rows and—when applicable—FMP/LLM selection, Review/Proof, trace manifest and artifact bytes. No layer may pass from a mocked neighbor when the gate requires E2.

Races include confirm response loss, duplicate/out-of-order events, cursor ahead/family mismatch, projection/event watermark change, graph mutation, restart at commit boundaries, concurrent foreign identity, artifact tamper and browser navigation. Reconciliation must converge without duplicate business effects or false UI success.

## Product Journey

| Journey | User outcome | Activation / result | Required closure |
|---|---|---|---|
| PJ-01 Full Research | Object → Goal → Scheme → Confirm → live Run → released result/review/report | Phase 4 after IG-00; not executed | IG-01/02/05; Scene-01 |
| PJ-02 Dynamic Replan | understand evidence-driven planned→actual path change | Phase 4 after IG-02; not executed | IG-03; Scene-02 |
| PJ-03 Self-Correction/Review | see exception, correction history and justified release/block | Phase 4 after IG-03; not executed | IG-02/03; Scene-03 |
| PJ-04 Claim Trace | traverse Claim to calculation/evidence/task/execution/review/report anchor and back | Phase 4 after IG-03; not executed | IG-04/05; Scene-04 |
| PJ-05 Object Accumulation | compare durable knowledge and released versions | Phase 5 `DEFINED_NOT_ACTIVATED`; `result=null` | future IG-11 only |
| PJ-06 Incremental Research | start from prior knowledge with explicit reuse/refresh/revalidation | Phase 5 `DEFINED_NOT_ACTIVATED`; `result=null` | future IG-12 only |

Product PASS is issued by a reviewer independent of the feature producer after technical prerequisites pass. A working endpoint or technical test alone is not product acceptance.

## Six Scene program

Scenes 01–04 are the only real Phase 4 numerator/denominator. All four must PASS; FAIL/BLOCKED is retained, never omitted. Scenes 05–06 are visible design rows with `activation=DEFINED_NOT_ACTIVATED`, `result=null`, `release_blocking_phase4=false`; they cannot be coerced to PASS/FAIL/BLOCKED or included in aggregates. Full business/backend/frontend/event/negative/evidence detail is in `SIX_SCENE_FULL_STACK_ACCEPTANCE_MATRIX.md`.

## Vertical slices

VS-01 Start/Live Run, VS-02 Result/Review, VS-03 Dynamic Path, VS-04 Trace/Execution and VS-05 Report/Artifact are Phase 4 active after predecessor gates. VS-06 Object Accumulation and VS-07 Incremental Research are fully defined Phase 5 slices with no Phase 4 writer, activation or result. Each slice requires backend, frontend, acceptance and journey sign-off on the same candidate.

## Test data

Data classes are: contract fixture (schema/unit only); synthetic deterministic (component/negative); controlled real (E1/E2 integration); live provider (only explicitly authorized provider gates); authoritative acceptance (same immutable E2 candidate and governed research input); Demo only (zero real-gate value). Fixtures carry schema/version/provenance/hash/expiry and cannot masquerade as LIVE. Financial golden data includes exact Decimal and display strings plus Calculation/Evidence/Claim/Proof lineage.

Test identities use disjoint Object/Run/Task/Claim/Review/Artifact namespaces and paired foreign-owner rows. Time, randomness, provider responses, event ordering and fault points are controlled where determinism is required. Authoritative Runs and release artifacts are append-only and preserved with failed attempts.

## Environment matrix

| Environment | Purpose | Permitted evidence | Prohibited claim |
|---|---|---|---|
| E0 Offline deterministic | L0–L2 contracts/components | fixture/synthetic | real integration/product/release |
| E1 Local PostgreSQL | repository/UOW/migration/API integration | synthetic/controlled real | browser Product Journey |
| E2 Full-stack real runtime | Backend–Frontend, browser, slices, PJ/Scenes 01–04, Phase 4A | controlled real/authorized live and full joins | Preview/competition readiness |
| E3 Preview parity | same candidate/config-mode parity | rerun candidate-bound Core/product/system | public access without separate auth approval |
| E4 Competition/release | reproducible fresh-machine advertised modes | canonical release bundle and independent audit | deployment merely because READY |

Environment promotion is monotonic. Evidence is bound to candidate, contracts, migrations, locks, configuration/mode, browser/runtime and data manifest; any relevant change invalidates affected evidence.

## Negative testing

Every boundary includes idempotency, identity mismatch, unknown schema/version/enum, restart/replay, authorization, integrity and unavailable/error variants. Core oracles require explicit safe classification, zero unauthorized bytes, zero foreign data, zero duplicate effect, no state regression, no frontend inference, no provider/fixture substitution, no secret/internal detail, and no qualified success. Phase 4 results use PASS/FAIL/BLOCKED; inactive future rows use NOT_ACTIVATED with null machine result.

## Failure/recovery

Network/SSE interruption resumes only with bound cursors and reconciles to projection; browser refresh rehydrates authority; lost API responses preserve idempotent admission; service/DB restart preserves exact identities and one terminal state; provider failure records locked identity and never silently switches; FMP conflict blocks or produces an explicit reviewed resolution; artifact absence/tamper yields explicit independent slot availability and zero denied bytes. Failed evidence stays append-only. Repairs create a new candidate and rerun the affected gate chain.

## Identity testing

Exact O/R/X/L/C/M/K/E/T/V/P/A ownership is asserted on every applicable route, event, projection, UI link, Review/Proof and artifact. Cross-Object/Run/Claim/Task/Review/Artifact, malformed/stale/unknown IDs and cursor families are denied without existence leaks or fallback. Core P4-ID excludes 021–022, which are Phase 5-only. An opaque `authorizedRef` never grants authority by possession.

## Provider testing

Phase 4 freezes MiMo preferred and TeamoRouter secondary. Ordered policy, attempted provider/model, actual selection and policy identity are persisted before Run; provider/model stay locked. The pre-audit has identified two release-blocking hypotheses requiring remediation and independent re-audit: the observability wrapper may fail to forward actual provider/model and default to a false TeamoRouter label, and configurable `planner_provider_order` may permit a policy-inconsistent subset/permutation. These are `PRE_REAUDIT_ONLY`, not audit receipts.

Controlled post-lock failover is `DEFINED_NOT_ACTIVATED`, `result=null`. Any future activation requires immutable `providerBefore/providerAfter/modelBefore/modelAfter/taskId/attemptId/failureReason/timestamp/policyId`, a new attempt, visible degraded/failover UI, restart/replay proof and separate contract/independent approval. Invisible failover is prohibited.

## Artifact testing

HTML is required; PDF is optional and independent. Metadata and byte delivery verify exact Object/Run/release/report/Artifact identity, availability, authorized state, media type, size, SHA/ETag, renderer/template and anchor manifest. Every GET reauthorizes; references are non-bearer. Cross-owned, stale, revoked, malformed, tampered, truncated, swapped or raw-path attempts return safe errors and zero bytes. Storage interruption/restart/restore cannot create partial success or make PDF satisfy HTML.

## Trace testing

Claim Trace closes Claim↔Metric/Calculation↔Evidence↔Task/Execution↔Review/Proof↔Artifact with exact identities and representation-specific anchors. Browser evidence verifies Results→drawer→trace→execution/review→exact HTML/PDF anchor and Back/Forward route, drawer, focus and scroll restoration. Missing/foreign anchors fail explicitly; raw hidden Execution/provider reasoning is not exposed.

## Evidence model

Each receipt binds candidate/backend/frontend SHAs, authority hashes, migration head, locks, environment/mode, data/fixture/provider policy, test IDs and timestamps. Evidence types include command/test transcript; request/response and raw/normalized SSE; SQL/revision/cardinality; provider/FMP safe provenance; DOM/a11y/focus/history/screenshots; console/network; Review/Proof/trace joins; artifact metadata/bytes/hash/render; restart/fault chronology; and sanitized logs/Langfuse status. Manifests are canonical, hash-linked and append-only. Missing, stale, mixed-candidate, Demo or secret-bearing evidence fails.

## Parallel execution

Work parallelizes by contract in isolated clean worktrees and serializes by gate. Backend, Frontend, Acceptance and Product Journey parent coordinators each sign. One writer owns every file; shared hot files are coordinator-merge-only; locks/dependencies/migrations have sole writers. Gate merge order is persistence → backend producer/composition → frontend boundary/features/composition → acceptance tests → journey tests → source freeze/execution → four-parent sign-off/tag. No Phase 5 production writer exists. See `../PHASE4_PARALLEL_EXECUTION_AND_FILE_OWNERSHIP.md`.

## Integration gates

| Gate | Entry and produced system | Required tests/evidence | Merge / rollback |
|---|---|---|---|
| IG-00 Final Contract Freeze | UAC-001/002 satisfied; accepted Backend/Frontend SHAs and all hashes | 13-contract, route/event/identity, schema/migration inventory | no production merge before PASS; freeze tag; semantic change invalidates dependants |
| IG-01 Real Research Start | IG-00; Object→Goal→Scheme→Confirm→Run/SSE | applicable BE 001..019, SSE, Core-ID, FE/X/PJ start, DB/app/browser restart | earliest real product gate; rollback IG-00 |
| IG-02 Result/Review | IG-01 terminal/result surface | finance/Review/release prerequisites, FE/X, PJ-01/03 | rollback IG-01 |
| IG-03 Dynamic Path | IG-02; atomic actual-graph mutation | BE graph/events, SSE chaos, FE/X, PJ-02/03 | rollback IG-02 |
| IG-04 Trace | IG-03; exact trace/anchors | identity/trace/browser navigation, PJ-04 | rollback IG-03 |
| IG-05 Artifact | IG-04; authorized report slots/content | artifact/identity/integrity/browser, PJ-01/04 | rollback IG-04 |
| IG-06 Scene 01–04 Product PASS | IG-05 and applicable technical gates | four real E2 product receipts; no Demo | no source merge; repair creates new candidate |
| IG-07 Technical System PASS | activated L0–L7 complete | all Core BE/SSE/ID/E2E, recovery/security/evidence | retain failed evidence; return last valid source tag |
| IG-08 Phase 4A Accepted | IG-06/07 same candidate | four-parent + independent acceptance, zero P0/P1/evidence gaps | no source change; otherwise invalidate affected gates |
| IG-09 Preview Parity | IG-08 plus exact release candidate | E3 parity, activated deployment gates, Core/product reruns, independent audit | rollback IG-08 build/config |
| IG-10 Phase 4B Release Ready | IG-09 | E4 fresh machine, modes, recovery, reproducibility, security, independent release audit | rollback IG-09 package; READY ≠ DEPLOYED |
| IG-11 Phase 5 Scene 05 Activation | accepted Phase 4 plus separate future freeze | future memory/version/comparison contract/evidence | inactive, `result=null`; no Phase 4 merge |
| IG-12 Phase 5 Scene 06 Activation | accepted IG-11 plus separate incremental freeze | future seed/freshness/reuse/revalidation contract/evidence | inactive, `result=null` |

## Release gates

IG-07 proves the technical system; IG-06 proves real product usability; IG-08 accepts Phase 4A only when both refer to the same candidate and independent evidence is complete. IG-09 proves Preview parity without environment-specific repair. IG-10 proves release readiness across every advertised mode/platform, manifest/reproducibility, Node24 build, PostgreSQL backup/restore, cold/warm start, provider/FMP truth, Langfuse safety, RISC/sandbox, artifacts, browser/product reruns, Demo isolation and operator recovery. None deploys automatically.

## Phase 5 activation

Scene/PJ/VS-05 Object Accumulation waits for IG-11 and separately frozen memory/version/comparison schemas, migration, ownership, data and product evidence. Incremental Research waits for accepted IG-11 plus IG-12 and separately frozen seed/freshness/reuse/refresh/revalidate/prevent semantics. Until activation, both retain `DEFINED_NOT_ACTIVATED`, `result=null`, no test execution, no production writer and zero Phase 4 aggregate/release effect. Phase 4 fields/endpoints may not imply these features.

## Program readiness decision

This program is ready for execution planning, not for Phase 4 production work. The 14 artifacts define the hierarchy, Backend/Frontend/cross-layer paths, product journeys, all six scenes, data/environments, traceability, slices, parallel ownership, system release and machine matrices. Execution remains blocked at IG-00 by the explicit next production gate.

```text
FULL_E2E_PRODUCT_ACCEPTANCE_PROGRAM_READY=YES
SPECIALIST_AGENTS_COMPLETED=10/10
BACKEND_TEST_LAYERS=9
FRONTEND_E2E_FAMILIES=12
CROSS_LAYER_E2E_FAMILIES=8
PRODUCT_JOURNEYS=6
VERTICAL_SLICES=7
INTEGRATION_GATES=13
CONTRACTS=13/13
BD=12/12
UAC=18/18
PHASE5_LEAKAGE_IN_PHASE4_REAL_ACCEPTANCE=0
DEMO_AS_REAL_EVIDENCE=0
FRONTEND_FINANCIAL_AUTHORITY=0
CROSS_OBJECT_FALLBACK=0
CROSS_RUN_FALLBACK=0
BACKEND_ACCEPTANCE_PATH_READY=YES
FRONTEND_BROWSER_E2E_READY=YES
CROSS_LAYER_E2E_READY=YES
PRODUCT_JOURNEY_READY=YES
SIX_SCENE_PROGRAM_READY=YES
TEST_DATA_ENVIRONMENT_READY=YES
TRACEABILITY_READY=YES
VERTICAL_SLICE_PLAN_READY=YES
PARALLEL_EXECUTION_PLAN_READY=YES
SYSTEM_RELEASE_PLAN_READY=YES
SCENES_DEFINED=6/6
PHASE4_REAL_SCENES=4/4
PHASE5_FUTURE_SCENES=2/2
EARLIEST_REAL_PRODUCT_TEST_GATE=IG-01
PRODUCTION_SOURCE_MODIFIED=NO
PHASE4_STARTED=NO
NEXT_PRODUCTION_GATE=PHASE3_REMEDIATION_SUCCESS + TWO_INDEPENDENT_PASS_AUDITS + FINAL_CONTRACT_FREEZE
```
