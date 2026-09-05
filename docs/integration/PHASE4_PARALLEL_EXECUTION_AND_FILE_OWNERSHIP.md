# Phase 4 Parallel Execution and File Ownership

Status: `DESIGN_READY — IMPLEMENTATION_PENDING — NOT_AUTHORIZED`

```text
PARALLELIZE_BY_CONTRACT=YES
SERIALIZE_BY_GATE=YES
ONE_WRITER_PER_FILE=YES
CROSS_GATE_SPECULATIVE_MERGE=NO
PHASE5_ACTIVE=NO
```

Implementation bases and all freeze hashes are published only at IG-00. The inspected Backend remediation candidate `66edc5110b6ab7d81578cef80190497a2f11e5b2`, Frontend baseline `d854c97789c98cca14fee3f4b3d7f00e0d5d137a`, R2 hash `fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19`, and contract-set hash `0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741` are inspection inputs, not acceptance receipts. No implementation may use the dirty shared checkout.

## Parent topology

| Parent | Integration branch | Authority |
|---|---|---|
| Backend Implementation Coordinator | `codex/p4-backend-integration` | Backend production, migrations, API/contract composition |
| Frontend V17 Implementation Coordinator | `codex/p4-frontend-integration` | Production UI, decoders/adapters, routing/build |
| Acceptance Coordinator | `codex/p4-acceptance-integration` | Gates, harnesses, fixtures and evidence; cannot self-issue independent audit |
| Product Journey Coordinator | `codex/p4-product-journey-integration` | Real Scenes 01–04 browser traversal and product evidence |

The Acceptance Coordinator stewards `codex/p4-gate-integration`; every active gate needs all four parent sign-offs.

## Backend lanes

| Lane | Exclusive contract scope | Representative owned files |
|---|---|---|
| B1 | Object, Goal, Scheme, prepare/confirm/admission | domain Object/Goal/Scheme/Run; focused `application/admission*` |
| B2 | MVCC/UOW/PostgreSQL/leases/migrations | application persistence/repository; database modules; allocated Alembic revisions |
| B3 | event contract, cursor, replay, SSE | runtime event/events/SSE; event schema |
| B4 | provider data, deterministic finance, result, Review/Check/Claim | data, financial capabilities/domain, review, released result, financial metrics |
| B5 | CER, trace, exact relations, anchor manifest | canonical execution/output, trace and anchor-manifest modules |
| B6 | report artifacts, proof/release, content delivery | report/release/proof/release-gate; storage requested from B2 |
| B7 | Task graph, scheduler, correction/replan/recovery | task/correction/decision; execution; graph/lifecycle/scheduler/state/checkpoint |

Phase 3 provider, generated-capability, RISC, observability and FinRobot surfaces are inherited. Changes require a Backend Coordinator request and may not weaken pre-Run provider selection/locking, financial authority, proof scope or fail-open observability.

## Frontend lanes

| Lane | Exclusive scope | Representative owned files |
|---|---|---|
| F1 | private DTO, decoder, adapter, HTTP/SSE transport | API client, DataSources, Runtime transports, domain/status types |
| F2 | Object/New, Goal/Scheme/Confirm, released Object Core | New task/Object pages, Plan snapshot, workspace styles |
| F3 | Run collection/workspace, reducer, dynamic path, Task detail | Runs/Run pages, reducer, ResearchPath, Task drawer, runtime workspace |
| F4 | Result and Financial Review | Results page, FinancialReview, result styles |
| F5 | Claim trace and typed Execution | Claim drawer, new TraceChain/ExecutionRecord child components |
| F6 | Professional Report and artifact availability | unavailable panel and new ProfessionalReport child component |

F5 does not edit F3/F4 files; F6 does not edit `ResultsPage.tsx`. Demo data/transport/state/scenario files remain outside Core authority. Phase 5 memory, comparison, version and incremental-return paths have no Phase 4 writer.

## Acceptance and journey lanes

| Lane | Exclusive scope |
|---|---|
| A1 | `tests/phase4/backend/**`; P4-BE/contract tests |
| A2 | `tests/phase4/sse/**`; P4-SSE-001..020 |
| A3 | `tests/phase4/identity/**`; Core P4-ID |
| A4 | `tests/phase4/financial_trace_artifact/**` |
| A5 | `apps/web/e2e/phase4/**`; Core browser suite |
| A6 | `tests/phase4/system/**`; environment/evidence collectors |
| J1..J4 | one exclusive `scene-01..04.spec.ts` per lane |
| JX | recovery/accessibility/provenance review only; no J1..J4 writes |

The Acceptance Coordinator is sole writer for shared fixtures/conftest, Playwright configuration/page objects, ID registry, aggregate runners and evidence manifests. Broad legacy tests are coordinator-merge-only; lanes add focused tests.

## Shared hot-file register

| Surface | Write rule |
|---|---|
| `contracts/api/models.py` | sole Backend Contract Owner; frozen after IG-00 |
| event schema | sole B3; frozen after IG-00 |
| backend enums/base/exports, application models/errors/extensions/service, API routes/main, DB composition, projections, registries, settings and `pyproject.toml` | Backend Coordinator merge only |
| Alembic chain | sole B2; revision IDs allocated before branches |
| frontend types/DataSource/runtime interfaces/status | sole F1 |
| runtime reducer and its focused script test | sole F3; F1/A2 review |
| App/shell/routing/shared overlays/global CSS/HTML/main/package locks/TS/Vite/build scripts | Frontend Coordinator merge only |
| Demo frontend | future Demo owner; locked during Core implementation |
| Phase 5 production paths | no writer before IG-11/12 activation |
| shared Phase 4 fixtures/config/page objects | Acceptance Coordinator or one delegated fixture owner |
| acceptance docs/matrices/evidence schema | Acceptance Coordinator merge only |
| generated evidence manifest | sole A6, append-only and candidate-bound |

Any file newly needed by two lanes becomes `BLOCKED_SHARED_HOT_FILE` until a parent assigns exactly one writer. Transfer requires a recorded lock release, clean commit boundary, new owner and coordinator approval.

## Worktree and merge protocol

Each lane starts from the last accepted gate tag in its own clean worktree and `codex/p4-*` branch, with an allowlist, target gate, contract hash and test IDs. No uncommitted copying, cross-gate speculative merge, force-push, history rewrite or migration-chain rewrite is permitted. Dependency/lock regeneration is coordinator-only. A post-freeze contract change creates a freeze revision and invalidates all dependent evidence.

For each gate the serial merge train is: freeze IDs/fixtures/oracles/manifest → B2 persistence → backend domain → backend application/runtime → Backend Coordinator hot files → F1 boundary → frontend feature lanes → Frontend Coordinator hot files → acceptance tests → journey tests → source freeze and execution → four-parent sign-off → immutable checkpoint tag. Any failure stops the train.

## Gate ownership and rollback

| Gate | Ordered producers / evidence | Checkpoint and rollback |
|---|---|---|
| IG-00 Final Contract Freeze | Phase 3 acceptance + two independent audits → contract owners → crosswalk/steward; hashes, 13 contracts, routes/events/identity, migration head | `p4-ig00-contract-freeze`; no implementation before PASS; semantic change revises freeze and invalidates dependants |
| IG-01 Real Research Start | B2→B1→B7→B3→backend merge→F1→F2/F3→frontend merge→A1/A2/A3/A5→J1 | P4-BE 001..019 applicable, SSE/Core-ID/browser/restart/idempotency; rollback to IG-00 |
| IG-02 Result/Review | B4→minimal B5/B6→backend→F1→F4→frontend→A1/A3/A4/A5→J1/J3 | finance/review/release-negative evidence; rollback to IG-01 |
| IG-03 Dynamic Path | B2→B7→B3→backend→F1→F3→frontend→A1/A2/A3/A5→J2/J3 | graph/version/event/recovery evidence; rollback to IG-02 |
| IG-04 Trace | B4→B6 identities→B5→backend→F1→F5→frontend integration→A3/A4/A5→J4 | exact identity/anchor/history evidence; rollback to IG-03 |
| IG-05 Artifact | B2→B5→B6→backend→F1→F6→F4/F2 integration→A1/A3/A4/A5→J1/J4 | authorized HTML/PDF/integrity/restart evidence; rollback to IG-04 |
| IG-06 Scene 01–04 Product PASS | J1→J2→J3→J4→JX→A5/A6; no production merge | real E2 product evidence; repair creates new candidate and applicable reruns |
| IG-07 Technical System PASS | A1→A2→A3→A4→A5→A6 aggregate; no source merge | all activated L0–L7; retain failed evidence; rollback last valid source tag |
| IG-08 Phase 4A Accepted | four-parent and independent decision; same candidate pair | no source merge; any source change invalidates IG-06..08 and affected earlier gates |
| IG-09 Preview Parity | A6 package→coordinator config→immutable deployment→critical reruns | rollback preview to IG-08 artifact/config; config/locks coordinator-only |
| IG-10 Phase 4B Release Ready | release lane→four parents→independent decision; no deployment implied | rollback package to IG-09; READY is not DEPLOYED |
| IG-11 Scene 05 Activation | no Phase 4 producer/branch/writer; future separate freeze | inactive, `result=null`; future rollback IG-10 |
| IG-12 Scene 06 Activation | no Phase 4 producer/branch/writer; future separate freeze | inactive, `result=null`; requires accepted IG-11 |

Rollback records the prior accepted tag, migration head, Backend/Frontend SHAs, locks, contracts and fixture manifest. Post-merge defects use revert commits or a branch from the prior tag. Database/runtime/evidence histories are append-only; shared databases use forward corrections. A source/config/oracle/build change creates a new candidate and gate-applicability analysis.

```text
FUTURE_PARENT_COORDINATORS_DEFINED=4/4
BACKEND_LANES_DEFINED=7/7
FRONTEND_LANES_DEFINED=6/6
PHASE4_ACTIVE_SCENES=4/4
PHASE5_SCENES_ACTIVATED=0/2
EARLIEST_REAL_PRODUCT_TEST_GATE=IG-01
CONTRACT_PARALLEL_GATE_SERIAL=YES
MULTI_WRITER_SHARED_FILE=0
PHASE4_IMPLEMENTATION_STARTED=NO
SOURCE_MODIFIED=NO
```
