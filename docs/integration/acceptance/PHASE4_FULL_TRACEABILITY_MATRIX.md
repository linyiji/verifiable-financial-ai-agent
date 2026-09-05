# Phase 4 Full Traceability Matrix

Status: `PREIMPLEMENTATION / IMPLEMENTATION_PENDING`  
Machine register: `PHASE4_FULL_TRACEABILITY_MATRIX.json`

## Authority and state

| Authority | Value |
|---|---|
| Frontend V8.1 baseline | `d854c97789c98cca14fee3f4b3d7f00e0d5d137a` |
| Approved Frontend R2 SHA-256 | `fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19` |
| Backend contract-set SHA-256 | `0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741` |
| Inspected remediation candidate | `66edc5110b6ab7d81578cef80190497a2f11e5b2` (not an acceptance receipt) |
| UAC-001 | `OPEN` — remediated candidate, authoritative Run, two independent PASS audits required |
| UAC-002 | `SATISFIED` — owner-approved R2 authority |
| Phase 4 | `IMPLEMENTATION_PENDING / NOT_STARTED` |

Lifecycle is monotonic and non-substitutable: `CONTRACT_CLOSED → IMPLEMENTATION_PENDING → IMPLEMENTATION_COMPLETE → TECHNICAL_ACCEPTANCE_PASS → PRODUCT_JOURNEY_PASS → RELEASE_ACCEPTED`. Contract closure is not implementation evidence; technical PASS is not product PASS; neither is release acceptance.

## Thirteen-contract map

Every row is `CONTRACT_CLOSED`, `IMPLEMENTATION_PENDING`, Phase 4 Core, and release-blocking. Universal dependencies `UAC-001/002/003/006/018` apply unless a narrower row is explicitly shown; exact arrays are in the JSON register.

| ID / contract | Backend authority | Frontend consumer | BD / UAC | Test and product closure | Required evidence |
|---|---|---|---|---|---|
| C01 `GlobalRunCollectionProjection` | `GET /api/research-runs` → `ResearchRunCollectionV1`; stable PostgreSQL order/cursor | DataSource/client, Runs page/App | BD-001,009; UAC-008..010,016,017 | BE-001,010,028..030; FE 1,3,11,12; X 01,02,07,08; PJ-01; Scenes 01–04 | collection/detail hashes, SQL ordering, exact O/R DOM, restart ledger |
| C02 `PreparedResearchDraft` | `POST /api/research-runs/prepare` → `ResearchRunDraftV1`; durable version/hash/expiry/consumed; Scheme-only | New task + Plan snapshot | BD-007; UAC-005 | BE-002..003; FE 1,2,12; X-01; PJ/Scene-01 | request/draft hash, zero Run/Task count, DOM/a11y, expiry/restart negatives |
| C03 `ConfirmRunResponseV1` | `POST /api/research-runs`; atomic consume/freeze/create/admit/start and idempotency | New task, App, Run page | BD-007,008; UAC-005,007,011 | BE-004..006,017; FE 2–4,11,12; X 01,07,08; PJ/Scene-01 | fingerprint, one Run/admission/start, concurrency/response-loss/restart |
| C04 `RunProjection` | detail + projection → `AtomicRunProjectionV1`; one MVCC snapshot, planned/actual graphs | Run workspace/path/task drawer/store | BD-001,010,012; UAC-004,008..011,016,017 | BE-007..010,015..019; FE 3–5,8,11,12; X 02,07,08; PJ 01–03 | projection hash/revision/watermark, graph versions, SQL/DOM/race replay |
| C05 `NormalizedRuntimeEventV1` | events route; all 55 raw names dispositioned (47 supported, eight explicit unsupported) | SSE transport/reducer/store/workspace | BD-002,003,012; UAC-004,007..011 | BE-011..019; SSE-001..020; FE 4,5,11,12; X 02,07,08; PJ 01–03 | raw/normalized frames, sequence/cursor, quarantine/recovery |
| C06 `ConnectionState` | derived only from projection/SSE/cursor/error/terminal state; never business state | transport/store/Run page/App | BD-003; UAC-004,009..011 | BE-008,011..017; SSE-001..020; FE 4,11,12; X 02,07,08 | headers, heartbeat/backoff, terminal no-reconnect, fresh-context restart |
| C07 `FinancialReviewProjection` | review-view; stable Review/check IDs, original status and correction history | Financial Review/Results | BD-006,010,011; UAC-010,013,017 | BE-023..024; FE 7,9,11,12; X 04,05,08; PJ 01,03,04 | Review/check/correction SQL, projection/DOM, blocked release |
| C08 `ClaimTraceProjection / TraceBundle` | Claim + trace routes; exact O/R/X/L/C/M/K/E/T/V/P/A closure and anchors | Claim/Task drawers, Trace/Execution, routing | BD-005,006; UAC-012..014,017 | BE-022,024,030; FE 8,9,11,12; X 03,05,08; PJ/Scene-04 | identity graph, manifest/hash, route/anchor/focus/scroll, foreign-ID denial |
| C09 `ReportArtifactGroup` | artifact metadata/content; fixed HTML/PDF slots, append-only attempts, opaque authorization, integrity | Results, unavailable panel, Professional Report | BD-004,006; UAC-011,014..016 | BE-025..027,030; FE 10..12; X 05,06,08; PJ 01,04 | authorized request, bytes/type/size/SHA, storage, independence/tamper negatives |
| C10 `ReleasedFinancialMetric` | result/Claim/trace/released Object; backend Decimal/string/display and K/E/C/P lineage | Results/Review/Trace/Report | BD-005,010; UAC-012,017 | BE-020..022; FE 6,7,9,10,12; X 03–05; PJ 01,03,04 | exact finance tuple, lineage joins, DOM, zero frontend-formula scan |
| C11 `ReleasedObjectCoreProjection` | released-state; latest valid release by `(released_at DESC, run_id DESC)` | Object pages/App/Results | BD-001,009; UAC-008,011,016,017 | BE-028..030; FE 1,6,10..12; X 01,03,06..08; PJ-01 | Object/Run/result/artifact join, deterministic latest, contamination scan |
| C12 `ErrorEnvelope` | every API/SSE preflight failure → safe `ErrorEnvelopeV1` | client, DataSource, transport, shared errors/all pages | BD-003,004,008 | negative variants of all BE/FE/X; PJ 01–04 | sanitized HTTP/SSE ledger, retry class, zero-byte denial, redaction scan |
| C13 `Availability` | backend-authored availability/reason/retry embedded in projections; durable terminal state | all resource pages/adapters/unavailable UI | BD-001,004,005,010; UAC-008,010..017 | BE-007,015..030; FE 3,6..12; X 02..08; PJ 01,03,04 | transition ledger, projection/DB equality, safe reasons, no false success |

## BD closure

| BD | Contract IDs | Primary technical surface | Product surface |
|---|---|---|---|
| BD-001 | C01,C04,C11,C13 | coherent projection/watermark | PJ 01–03; Scenes 01–04 |
| BD-002 | C05 | event normalization | PJ 01–03; Scenes 01–03 |
| BD-003 | C05,C06,C12 | cursor/recovery/terminal | PJ 01–04 recovery |
| BD-004 | C09,C12,C13 | artifact delivery | PJ 01,04; Scenes 01,04 |
| BD-005 | C08,C10,C13 | metric/Claim | PJ 01,03,04 |
| BD-006 | C07,C08,C09 | Trace/manifest | PJ-04 |
| BD-007 | C02,C03 | Scheme-only prepare | PJ/Scene-01 |
| BD-008 | C03,C12 | confirm/auto-start | PJ/Scene-01 |
| BD-009 | C01,C11 | global collection/latest release | PJ-01; Scenes 01–04 |
| BD-010 | C04,C07,C10,C13 | total maps | PJ 01–04 |
| BD-011 | C07,C08 | review projection | PJ 01,03,04 |
| BD-012 | C04,C05 | graph mutation | PJ 02,03; Scenes 02,03 |

## UAC closure

`UAC-001` remains the hard blocker for IG-00. `UAC-002` is satisfied. `UAC-003..018` are contract-closed and implementation-pending: API/event versioning; cursor family; confirm replay; access/identity; admission/start; graph ownership; atomic watermark; total maps; exactly-one failure; Claim closure; Review identity/history; Trace anchors; authorized artifact lifecycle; HTML/PDF independence; latest release/lossless finance; total error/retry/recovery. Each is covered by its applicable BE/SSE/Core-ID/FE/X negative and positive variants in the machine register and linked acceptance catalogs.

## Frontend, cross-layer and product closure

| Family | Coverage |
|---|---|
| `FE-E2E-1..12` | Object/New; Scheme/Confirm; Run; SSE; Dynamic Path; Results; Review; Execution; Claim Trace; Report; Recovery; Error/unavailable |
| `X-E2E-01..08` | Create; Live Run; Result; Review; Trace; Artifact; Recovery; Failure |
| `PJ-01 / SCENE-01` | C01–C13 full research |
| `PJ-02 / SCENE-02` | C04–C06,C12,C13 dynamic replan |
| `PJ-03 / SCENE-03` | C04,C05,C07,C10,C12,C13 correction/review |
| `PJ-04 / SCENE-04` | C04–C10,C12,C13 Claim trace |
| `PJ-05 / SCENE-05` | no frozen Phase 5 memory/version/comparison contract; `DEFINED_NOT_ACTIVATED`, `result=null` |
| `PJ-06 / SCENE-06` | no frozen incremental seed/freshness/reuse contract; `DEFINED_NOT_ACTIVATED`, `result=null` |

## Machine-enforced rules

1. Each C01–C13, BD-001–012, and UAC-001–018 occurs in the corresponding JSON register.
2. Every contract row owns authority, backend DTO/route disposition, frontend boundary, tests, product mapping, evidence, activation and lifecycle.
3. `UAC-001 != SATISFIED` blocks IG-00 and every production transition.
4. `IMPLEMENTATION_PENDING` forbids technical, product or release PASS.
5. `DEFINED_NOT_ACTIVATED` requires `result=null` and `release_blocking_phase4=false`.
6. Phase 4 release requires executed technical evidence and at least one applicable real Product Journey receipt; Demo evidence is never substitutable.

```text
CONTRACTS_MAPPED=13/13
BD_MAPPED=12/12
UAC_MAPPED=18/18
FE_E2E_MAPPED=12/12
X_E2E_MAPPED=8/8
PRODUCT_JOURNEYS_MAPPED=6/6
SCENES_MAPPED=6/6
SOURCE_MODIFIED=NO
```
