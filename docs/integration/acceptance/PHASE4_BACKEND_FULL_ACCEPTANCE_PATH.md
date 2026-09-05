# Phase 4 Backend Full Acceptance Path

Status: `DESIGN_ONLY - NOT_IMPLEMENTED - NOT_EXECUTED`  
Contract families: `phase4-core/v1`, `phase4-runtime-event/v1`  
Contract set: `0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741`  
Approved V17 R2: `fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19`

This is an acceptance design, not an implementation authorization, authoritative Run, or audit receipt.

## Entry inventory

The read-only inspected Phase 3 remediation worktree was clean at commit `66edc5110b6ab7d81578cef80190497a2f11e5b2`, tree `5cc1fd63d97fcb07c233b1dba73bd4d1cd16b77f`, migration head `20260904_0006`.

The target contract defines 18 Core routes. Eleven paths exist in `apps/api/routes.py` but require Phase 4 versioning/strengthening; seven are absent: global Run collection, atomic projection, Claim detail, Trace, artifact metadata, artifact content and released Object state. The default `apps/api/main.py` composition is in-memory SQLite, current public response models are thin, and the current raw event envelope lacks Phase 4 version fields. These are implementation gaps, not failed acceptance tests: current activation is `NOT_ACTIVATED`, result `null`.

## Shared acceptance corpus

Create complete colliding-label identity tuples A and B containing Object, Run, Task, Claim, metric, Review/Check, Calculation, Evidence, Proof, CER, released result, report, HTML and PDF. Only opaque IDs close relations. The corpus includes live/released/failed/cancelled/terminal-before-review Runs; at least 26 Runs; equal release timestamps; same-Task correction; approved add-Task and change-dependency Replans; six Availability states; PASS/REVIEW/BLOCK; required/non-required Proof; PDF available/not-generated/failed; retained unavailable artifacts; corrupted hashes; cross-Run refs; gaps and duplicate delivery.

## BE-L0 - Static and Contract

Bind Candidate SHA/tree/cleanliness, contract hashes, OpenAPI inventory, all DTO/schema literals, route versioning, raw/normalized enums, one migration head and test manifest.

Pass requires exactly 18 Core routes, 13 normalized contracts, `BD-001..012`, `UAC-003..018`, all 55 raw events partitioned into 47 supported and eight explicit unsupported, and no Phase 5 route/field. Hash drift, missing/duplicate route, unknown enum, unversioned response, multiple migration heads or Phase 5 leakage blocks every later layer.

## BE-L1 - Domain and Application

Exercise Object -> Goal -> Scheme-only draft -> confirmation/admission -> graph/Tasks -> scheduler -> correction/Replan -> Review -> Proof -> release.

Prepare creates no Run/Task/graph. Confirm consumes one immutable draft and creates exactly one auto-started admitted Run. Planned graph stays immutable. Self-Correction stays one Task; Replan mutates only Actual. Review PASS and declared Proof policy gate release. Unknown Object, stale draft/hash/version, provider failure, invalid graph, deferred change kind, Review BLOCK or Proof failure can never produce success.

## BE-L2 - Persistence

Target PostgreSQL only. Confirm atomically consumes the draft and persists admission, Run, planned graph, Tasks, initial events, idempotency outcome and scheduler outbox/lease. Every projection-visible transaction increments revision once and publishes a consistent event watermark.

Fault every boundary: concurrent confirm, response loss, rollback, lease expiry/redelivery, duplicate start, API/worker/database restart and finalizer retry. There is no partial state, second logical effect or request-process cache authority.

## BE-L3 - Data and Financial

Test raw provider -> validation -> normalization/conflict resolution -> accepted Evidence -> deterministic Calculation -> released metric. The FULL material set includes revenue growth, EBITDA/FCF margins, SMA50/SMA200, RSI14, MACD line/signal/histogram and volume ratio 20.

Revenue growth is `(current-prior)/prior` with positive prior. Explicit half-even Decimal profiles bind precision 28 for fundamental ratios and MACD subtraction and 50 for technical averaging/EMA. Reject unvalidated data, nonpositive prior, period/actuality/currency/series mismatch, nonfinite values, unknown methodology, unresolved price basis/corporate action, float drift, client arithmetic, field loss or incomplete material lineage.

## BE-L4 - Events and SSE

Snapshot at N and stream strictly N+1. Numeric and exact same-Run opaque cursors yield identical suffixes. Heartbeat is comment-only and consumes no sequence. The terminal event is last and closes promptly.

The eight explicit unsupported values are `scheme.generation_started`, `replan.rejected`, `evidence.conflict`, `workspace.created`, `capability.generation_started`, `capability.tested`, `capability.validated`, and `review.required`. Unsupported/unknown type, bad payload/version, R/T mismatch, conflicting duplicate, gap, disorder, negative/noncanonical/unknown/foreign/ahead cursor causes zero business mutation and cursor advance, followed by typed pre-header error or snapshot recovery.

## BE-L5 - Identity

Every endpoint closes exact O/R/T/C/M/K/E/V/Q/P/X/L/report/artifact ownership. Substitute each B ID into each A route, body and reference; repeat after restart with cold caches. Missing/reparented rows, same-label collisions, cache poisoning and all latest/first/text/symbol/name fallbacks must fail safely, atomically and without foreign fragments or mutation.

Core identity scope is `P4-ID-001..020,023..028`; `021..022` remain Phase 5 inactive.

## BE-L6 - Review and Trace

Review exists independently of release and has one stable Review ID, stable Check IDs, typed subjects, input hash and correction/exception history. Aggregate `review.resolved` does not resolve an individual Check. No synthetic per-Claim Review exists.

A/B/C share one canonical ID. Trace follows exact Claim -> Review Check -> Task(s) -> Calculation(s) -> Evidence -> Execution -> Proof -> originating representation anchor. Review/Task/Execution anchors remain plural; `primaryTaskId` requires an explicit durable relation. Missing retained detail keeps identity plus Availability. No DOM/text/latest/singleton repair.

## BE-L7 - Artifact and Release

HTML is required. PDF is independently AVAILABLE, NOT_GENERATED or FAILED. Artifact attempts are append-only. Available bytes match content type, length, digest, ETag and semantic source. `authorizedRef` is a non-bearer locator and each GET rechecks scope, state and integrity.

Reject raw/internal locator, reused HTML/PDF ID, swapped/tampered/truncated/wrong-type bytes, range/redirect, cross-Run artifact, PENDING terminal slot or required HTML failure with zero protected bytes. Latest eligible release uses `(released_at DESC, run_id DESC)` and cannot select a newer failed/running/invalid Run.

## BE-L8 - Failure and Recovery

Inject planner/provider, FMP, generated-capability, Task, Review, Proof, artifact, persistence and application failures, plus restart/duplicate delivery. One idempotent terminal finalizer owns terminal state, component Availability, revision/watermark and exactly one final event.

Every unsuccessful admitted Run ends FAILED/CANCELLED with one `run.failed`, zero `run.completed`, no later business event and no result. Optional PDF failure is nonterminal. Provider/model is selected before Run and locked: no mid-Run switch or live-to-fixture splice. Errors are allowlisted and reveal no secrets, raw provider body, prompt, path, SQL, stack or hidden reasoning.

## Layer and gate map

| Layer | Principal gates |
|---|---|
| L0 | Guards all `P4-BE-001..030`, `P4-SSE-001..020`, Core P4-ID, BD and UAC evidence |
| L1 | `P4-BE-002..006`, `015..016`, supporting `018..024` |
| L2 | `P4-BE-001`, `004..010`, `017`; persistence/restart SSE variants |
| L3 | `P4-BE-020..021`, supporting `015/022..024/028` |
| L4 | `P4-BE-008/011..019`; `P4-SSE-001..020` |
| L5 | `P4-BE-030` plus IDN variants of every gate |
| L6 | `P4-BE-022..024`; trace-related Core P4-ID |
| L7 | `P4-BE-015/025..029`; artifact/release Core P4-ID |
| L8 | `P4-BE-016..017` plus MIS/RST/INT variants of all gates |

Execution order is L0 -> L1 -> L2 -> L3/L4/L5 in parallel -> L6 -> L7 -> L8 -> independent Backend audit. A failed prerequisite makes dependents BLOCKED, never PASS.

## Contract crosswalk

| Normalized contract | Layers | BD | UAC | Principal P4-BE |
|---|---|---|---|---|
| GlobalRunCollectionProjection | L0,L2,L5 | 009 | 008-010,017 | 001,010,029-030 |
| PreparedResearchDraft | L1,L2,L5,L8 | 007 | 005 | 002-003 |
| ConfirmRunResponseV1 | L1,L2,L5,L8 | 008 | 005,007,011 | 004-006,017 |
| RunProjection | L1,L2,L4,L5,L8 | 001,010,012 | 008-011,016-017 | 007-010,018-019 |
| NormalizedRuntimeEventV1 | L0,L4,L5,L8 | 002,012 | 003-004,009-011 | 008,011-019 |
| ConnectionState | L4,L8 | 003 | 004,009-011,018 | 011-017 |
| FinancialReviewProjection | L1,L5,L6,L8 | 006,010,011 | 010,013 | 023-024 |
| ClaimTraceProjection / TraceBundle | L5,L6,L7 | 004-006,011 | 012-014 | 022,024-027 |
| ReportArtifactGroup | L2,L5,L7,L8 | 004,006 | 014-016 | 025-027 |
| ReleasedFinancialMetric | L3,L5,L6,L7 | 005,010 | 012,017 | 020-024,028 |
| ReleasedObjectCoreProjection | L2,L5,L7,L8 | 001,009 | 008,016-017 | 028-030 |
| ErrorEnvelope | L0,L4,L5,L8 | 003,004,008 | 003,006,018 | All negatives, especially 013-016/026/030 |
| Availability | L1,L2,L5,L6,L7,L8 | 001,004,005,010 | 006,008,011-018 | 007/015-016/020/022-029 |

## Evidence and decision

Each append-only attempt binds Candidate/tree/cleanliness, contract hashes, route/schema/enum/migration inventories, sanitized environment/data/provider/model identity, HTTP ledger, DB cardinalities/revisions/watermarks, event/SSE frames, idempotency/lease delivery, A/B substitutions, independent Decimal results, Review/Proof/CER/release records, trace/manifest, artifact byte hashes, restart comparison and redaction scan. Credentials, DSNs, licensed provider bodies, prompts and internal paths are prohibited.

The machine matrix contains all `30 x 7 = 210` `P4-BE` gate/variant rows for `POS`, `IDN`, `MIS`, `VER`, `RST`, `AUT`, and `INT`.

## Current pre-freeze risks

These are `PRE_REAUDIT_ONLY`, not audit receipts or Phase 4 findings:

- `P1 PRV-001`: `InstrumentedLLMProvider` does not forward delegate provider/model identity, while scheme-generation fallback labels can default to TeamoRouter. A selected MiMo response can therefore coexist with false persisted generator identity. Relevant inspected files: `src/observability/llm_provider.py`, `src/agentic/llm_integration.py`, `src/application/service.py`, `scripts/run_phase3_acceptance.py`.
- `P1 PRV-002`: `planner_provider_order` permits subsets/permutations while the router uses the policy ID for MiMo-primary/TeamoRouter-secondary. Reversed or singleton configuration can violate or falsely label the mandated policy.

Both require remediation and independent re-audit before UAC-001 and freeze promotion.

```text
BACKEND_TEST_LAYERS=9
P4_BE_GATES=30/30
P4_BE_VARIANT_CELLS=210/210
P4_SSE_GATES=20/20
CONTRACTS=13/13
BD=12/12
UAC=18/18
PHASE4_BACKEND_ACCEPTANCE_RESULT=NOT_ACTIVATED
FINAL_AUDIT_RECEIPT=NOT_ISSUED
PRODUCTION_SOURCE_MODIFIED=NO
```
