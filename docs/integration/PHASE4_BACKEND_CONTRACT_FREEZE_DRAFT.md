# Phase 4A Backend Contract Freeze Draft

Status: `PROVISIONAL_CONTRACT_DRAFT_READY`  
Freeze state: `NOT_FINAL`  
Scope: Phase 4A Core contract/design only  
Frontend authority: `FRONTEND_BASELINE_V8.1@d854c97789c98cca14fee3f4b3d7f00e0d5d137a`

```text
PHASE4_BACKEND_CONTRACT_DRAFT_READY = YES
PHASE4_BACKEND_CONTRACT_FREEZE = NOT_FINAL
PHASE4_PRODUCTION_IMPLEMENTATION_AUTHORIZED = NO
WAITING_FOR_APPROVED_PHASE3_BACKEND = YES
```

This package converts the V17 readiness blockers into an implementation-ready provisional
contract. It does not claim that the inspected backend implements the contract, that Phase 3 is
accepted, or that any production work may begin.

## 1. Snapshot discipline

The real backend candidate worktree, not the documentation checkout, was the inspection authority.

| Field | Start | End |
|---|---|---|
| path | `/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-coordinator` | same |
| branch | `codex/phase3-contracts` | same |
| `HEAD` | `11fe8173a25ff7ac08bae42340ba7c6fae591be5` | same |
| tree | `b5f7bf960853c43344516031058f043ba45aaac5` | same |
| `git status --short` | empty / clean | empty / clean |
| working-state fingerprint | `39ce26c1ee4f0cb9091d048318f5938501af596fdc7441979dfeb9e60ccc1f41` | same |

Fingerprint algorithm, run from the candidate worktree:

```sh
{
  git rev-parse HEAD
  git status --porcelain=v2
  git diff --binary HEAD
  git ls-files --others --exclude-standard -z |
    sort -z |
    xargs -0 -I{} shasum -a 256 "{}"
} | shasum -a 256
```

The user-supplied earlier coordinate was
`6280938b15bc43b2d7ca9793137e60c60c2fb86a`; the branch had advanced by two commits before this
inspection began. It did not change during the bounded review.

```text
BACKEND_CHANGED_DURING_REVIEW = NO
PROVISIONAL_MOVING_BACKEND = false
```

`PROVISIONAL_MOVING_BACKEND=false` describes only the recorded review window. The result remains
provisional because `11fe8173...` is not an independently accepted immutable Phase 3 candidate.
The documentation was written in the separate pre-existing dirty `main` checkout at
`ed8af4ba8c51ada227f433582654ced0e16ca3c4`; no main or backend production source was edited.

### 1.1 Candidate log recorded at inspection

```text
11fe817 Harden live provider and generated capability retries
6280938 Fix Phase 3 financial negative review harness
0e6aee9 Adapt generated capability schema for strict LLM output
0cf3cc5 Complete Phase 3 backend candidate
5e84632 fix: harden proof release and long history collection
557cc3e feat: integrate real revenue growth proof workflow
e8c026f feat: add real RISC Zero revenue growth proof
ee492b3 fix: derive generated margin from authoritative inputs
07049c2 feat: enforce phase 3 runtime assurance boundaries
61bc089 feat: activate phase 3 financial capabilities
7852969 feat: add deterministic FinRobot peer helper port
779c7e4 feat: add controlled professional report renderers
933a425 feat: integrate phase 3 task calculations
c77be9c feat: add controlled FinRobot SVG charts
ebb1e60 feat: collect technical indicator history
294499f feat: validate and scope generated capabilities
5ef3209 feat: port FinRobot technical indicators
3d14324 feat: persist generated capability workflow
54dfd3f feat: enforce phase 3 proof and capability lifecycle gates
4afb0c3 feat: add generated capability Docker sandbox
```

### 1.2 Worktree inventory recorded at inspection

```text
/Users/mac/Verifiable_Financial_Agent_System ed8af4b [main]
/Users/mac/Verifiable_Financial_Agent_System_frontend_v8 7eed83d [ws/frontend-v8-preintegration]
/Users/mac/Verifiable_Financial_Agent_System_frontend_v8_1_baseline e2aef1e [codex/frontend-v8-1-baseline-promotion]
/Users/mac/Verifiable_Financial_Agent_System_frontend_v8_audit 7eed83d [ws/frontend-v8-independent-audit]
/Users/mac/Verifiable_Financial_Agent_System_frontend_v8_fixes d854c97 [ws/frontend-v8-preintegration-fixes]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/agentic 6f38705 [ws/agentic]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/assurance 4a6b136 [ws/assurance]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/calculation-provenance 8626111 [ws/calculation-provenance]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/data-evidence 8dc0e30 [ws/data-evidence]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/evidence-semantics e50690d [ws/evidence-semantics]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/financial-capabilities d478e7c [ws/financial-capabilities]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/finrobot-audit 44c8f18 [ws/finrobot-audit]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/finrobot-runtime-reuse 384d358 [ws/finrobot-runtime-reuse]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/integration 65dc6e1 [ws/integration]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/langfuse 73121fa [ws/langfuse]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/langfuse-real-integration b82f017 [ws/langfuse-real-integration]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/live-fmp deb654f [ws/live-fmp]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/output 5f8e752 [ws/output]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/peer-data-semantics 8cc824f [ws/peer-data-semantics]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-coordinator 11fe817 [codex/phase3-contracts]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-final-delta-audit.H0pBiW 5e84632 (detached HEAD)
/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-finrobot-charts bbc29b3 [ws/finrobot-charts]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-finrobot-peer a52f66c [ws/finrobot-peer]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-finrobot-report 5e84632 (detached HEAD)
/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-finrobot-technical 8269f54 [ws/finrobot-technical]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-generated-orchestration 5e84632 (detached HEAD)
/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-generated-sandbox 6a3d202 [ws/generated-capability-sandbox]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-generated-validation 4427799 [ws/generated-capability-validation]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-independent-audit.d5lZim/latest-A/source 5e84632 (detached HEAD)
/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-independent-audit.d5lZim/latest-B-different-absolute-path/source 5e84632 (detached HEAD)
/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-independent-audit.d5lZim/path-B-longer/source 5e84632 (detached HEAD)
/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-independent-audit.d5lZim/source 5e84632 (detached HEAD)
/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-risc-zero 5e84632 (detached HEAD)
/Users/mac/Verifiable_Financial_Agent_System_worktrees/postgresql 759ee30 [ws/postgresql]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/postgresql-real-integration a0e0ac1 [ws/postgresql-real-integration]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/replan-integrity 0ba4e84 [ws/replan-integrity]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/runtime 7ba590e [ws/runtime]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/scheme-route-repair 4ffe8d9 [ws/scheme-route-repair]
/Users/mac/Verifiable_Financial_Agent_System_worktrees/teamorouter-llm 275220c [ws/teamorouter-llm]
```

## 2. Repository authorities inspected

| Area | Actual source authorities |
|---|---|
| API routes and public models | `apps/api/main.py`, `apps/api/routes.py`, `contracts/api/models.py`, `contracts/events/runtime_event.schema.json` |
| Application orchestration | `src/application/service.py`, `execution.py`, `events.py`, `models.py`, `repository.py`, `persistence.py`, `errors.py`, `phase3_financial.py`, `phase3_proof.py` |
| Object / Goal / Scheme / Run / Task | `src/domain/research_object.py`, `research_goal.py`, `research_scheme.py`, `research_run.py`, `task.py`, `enums.py` |
| Planned/actual graph and runtime | `src/runtime/graph.py`, `state.py`, `scheduler.py`, `lifecycle.py`, `events.py`, `sse.py`, `checkpoint.py` |
| Evidence and deterministic finance | `src/domain/evidence.py`, `calculation.py`, `financial_semantics.py`, `src/data/{ingestion,validation,normalization,persistence,repository}.py`, `src/output/financial_metrics.py` |
| Claim / Review / Proof | `src/domain/released_research_result.py`, `review.py`, `proof.py`, `src/assurance/{proof_policy,release_gate,independent_financial_review,deterministic_review,semantic_review}.py` |
| Canonical / result / report / artifacts | `src/domain/canonical_execution_record.py`, `released_research_result.py`, `report.py`, `src/output/{canonical,release,report,projections}.py`, `src/adapters/finrobot/professional_reporting.py` |
| PostgreSQL / migrations / composition | `src/infrastructure/database/{models,repository,composition,migrations,postgresql_events,checkpoints,phase3_records,artifacts,generated_workflow}.py` |
| Acceptance evidence reviewed | API/application/runtime/PostgreSQL/report tests under `tests/`, Phase 3 acceptance runner, Phase 4 E2E/SSE/identity/gate documents, V8.1 interaction ledger, V17 dependency/readiness package |

## 3. Observed backend contract, not assumed contract

The inspected source already provides strong primitives: exact Run-to-Object ownership, typed
Tasks/Evidence/Calculations/Claims/Review/proof/canonical/result records, lossless released metric
semantics, per-Run event sequence and opaque/numeric replay in PostgreSQL, and separate immutable
HTML/PDF artifact records.

It does not yet satisfy the Phase 4A contract:

- no global Run collection or atomic Run projection/revision/watermark route exists;
- prepare honestly produces Goal + unconfirmed Scheme only; plan/Tasks appear on confirm, while the
  draft lacks version, expiry, request/draft hashes, consumed state, and durable prepare replay;
- confirm idempotency is optional, process-local, request-unbound, restart-unsafe, and can schedule
  execution again on a cache hit; draft consumption and scheduler admission are not durable atomic
  facts;
- cursor validation occurs inside the streaming generator, noncanonical numeric values can parse,
  and ahead/terminal-equal cursors can heartbeat forever;
- post-scheduler failures and cancellation can terminate without a durable terminal event, while
  successful events and aggregate/output persistence are not one atomic publication;
- default `apps.api.main:app` is SQLite/in-memory for aggregate/events/checkpoints rather than the
  available PostgreSQL composition needed for restart evidence;
- Review is ref-only and release-gated, stable Review check IDs/correction links and product trace
  anchors are absent, and no Claim/Trace routes exist;
- the normal service path does not publish `report_artifacts`, and no safe metadata/byte routes or
  authorization layer exist; internal artifact locators are not public URLs;
- no Released Object Core/latest valid release route exists; current `/financials` is lossy and
  `/state` includes future writeback concepts; and
- errors/statuses/events are not a total versioned browser contract; the V17 native `EventSource`
  and generic HTTP error handling are incompatible with named events, initial snapshot cursor, and
  typed recovery.

These are implementation deltas, not waived contract ambiguities.

## 4. Reconciled contract decisions

| Topic | Single Phase 4A decision |
|---|---|
| Global Run list | authoritative `GET /api/research-runs`; `(updated_at DESC,run_id DESC)`; truthful durable `updated_at`; filter-bound opaque cursor; default limit 50 |
| Prepare | FULL, `SCHEME_ONLY` Goal/Scheme preview; planned graph explicitly not generated; no fake Tasks; template remains frontend authoring only |
| Confirm/start | version/hash/Object-bound draft; durable actor/tenant/request-bound key; atomic consume/Run/plan/initial-event/admission; automatic runtime start; no execute click |
| Idempotent replay | same key/hash returns the same durable outcome/Run with replay transport metadata; changed request conflicts; different key cannot consume the same draft twice |
| Admission | durable `PENDING -> LEASED -> ACKNOWLEDGED|FAILED`; leases permit at-least-once delivery; unique Run effect makes start and `run.started` exactly once |
| Atomic projection | one committed snapshot with monotonic `projection_revision` and matching `projection_sequence`; exact revision mutation set; no mixed nested identity |
| SSE | browser fetch-stream, raw event names preserved, strict pre-header cursor checks, projection recovery on gap/disorder/sparse graph event, PostgreSQL restart replay |
| Ahead cursor | HTTP 409 `CURSOR_AHEAD`; negative/noncanonical/unknown/cross-Run cursor is HTTP 400 `INVALID_CURSOR` |
| Terminal | success is release + mandatory HTML, `release.completed`, then one `run.completed`; every failure/cancel path uses one `run.failed`; no later business event |
| Claim / trace | `run_id` join root, exact K->Task derivation, stable Review checks, policy-aware proof, O/R/X/L closure, scoped anchors, typed unavailable retained detail |
| Finance | backend projection preserves canonical/display values and all financial semantics; fixture is `0.6547 RATIO -> 65.47 %`; browser/LLM never performs authoritative arithmetic |
| Artifacts | `report_id := released_result_id`; fixed separate HTML/PDF slots; HTML required for release, PDF optional with explicit availability; same-origin non-bearer content path; no internal locator |
| Released Object | latest fully valid same-Object release by `(released_at DESC,run_id DESC)`; newer non-release never supersedes; exact historical Run opens by ID |
| Object entry | versioned searchable Object list plus durable request-bound Object creation replay; no provider/company fallback |
| Errors/availability | one total safe envelope and six-state availability model; foreign nested identity fails closed; transient state cannot advance; unknown versions/values recover |
| Version negotiation | omitted or exact `X-Phase4-Contract-Version: phase4-core/v1` selects V1; no silent downgrade/coercion |
| Execution view | sequence-ordered, Run-bound cursor/filter/search over allowlisted safe summaries; no hidden reasoning or provider-body search |

The provisional contract resolves the prior catalogue differences on collection ordering and
ahead-cursor naming. There are no remaining Phase 4 semantic choices left to an implementer in the
covered scope. Concrete persistence schemas and code structure may vary only if they preserve every
wire invariant and acceptance oracle.

## 5. Ownership and field classification

| Authority | Owns | Does not own |
|---|---|---|
| Domain/backend records | exact IDs, Object/Run ownership, raw status/events, financial values/semantics, review/proof/release/artifact facts | presentation labels or browser recovery state |
| Projection adapter | versioning, safe redaction, verified joins, stage/progress/availability normalization, grouped views | new financial arithmetic, guessed relation, missing Task fabrication |
| New durable Phase 4 fields | draft/idempotency/admission facts, projection revision, accurate update time, stable check/correction/anchor facts, artifact failure reason | Phase 5 memory/version/comparison/incremental state |
| New additive routes | global collection, atomic projection, Claim/Trace, artifact metadata/content, released Object state | duplicate domain truth or writeback |
| Browser | render supplied display values, reduce validated sequential events, request authoritative recovery | calculate finance, crawl Objects, repair identity, invent raw events |

Every field in the companion schemas is classified as `EXISTING_BACKEND`, `PROJECTION_ONLY`,
`BACKEND_FIELD_REQUIRED`, `ADDITIVE_ROUTE_REQUIRED`, `SEMANTIC_CONFLICT`, or `PHASE5_DEFERRED`.
`SEMANTIC_CONFLICT` identifies current behavior that implementation must replace; it is not an open
design decision.

## 6. Eight blocker closure result

| Blocker | Draft closure | Implementation state |
|---|---|---|
| `P4-BLOCKER-01` Global Run Collection | exact route/filter/order/cursor/item/progress/activity/availability | `OPEN` |
| `P4-BLOCKER-02` Atomic Run Projection | exact composite/revision/sequence/identity/transaction protocol | `OPEN` |
| `P4-BLOCKER-03` SSE Recovery / Terminal | exact wire/cursor/replay/recovery/terminal/restart protocol | `OPEN` |
| `P4-BLOCKER-04` Prepare / Confirm Authority | exact Scheme-only draft, durable replay/consume/admission/auto-start | `OPEN` |
| `P4-BLOCKER-05` Claim / Review / Trace | exact same-Run projections, checks, proof, canonical and anchors | `OPEN` |
| `P4-BLOCKER-06` Report Artifact Delivery | exact grouped metadata, HTML/PDF policy, authorization and byte integrity | `OPEN` |
| `P4-BLOCKER-07` Released Object Core | exact valid-release selection and historical Run identity | `OPEN` |
| `P4-BLOCKER-08` Event / Status Normalization | total raw-preserving maps and fail-closed unknown handling | `OPEN` |

`BLOCKERS_COVERED = 8/8`. “Covered” means specified with an oracle, not implemented or passed.

## 7. Package authority

The six documents form one contract set:

1. [Freeze draft](PHASE4_BACKEND_CONTRACT_FREEZE_DRAFT.md) — decision, snapshot, boundaries, and handoff.
2. [API schema draft](PHASE4_BACKEND_API_SCHEMA_DRAFT.md) — routes, DTO shapes, semantics, and field classification.
3. [Event contract draft](PHASE4_BACKEND_EVENT_CONTRACT_DRAFT.md) — raw-to-normalized map, SSE recovery, and terminal rules.
4. [Blocker closure matrix](PHASE4_BACKEND_BLOCKER_CLOSURE_MATRIX.md) — eight blocker deltas and proof ownership.
5. [Identity/error/availability contract](PHASE4_BACKEND_IDENTITY_ERROR_AVAILABILITY_CONTRACT.md) — fail-closed joins, safe errors, and availability behavior.
6. [Acceptance mapping](PHASE4_BACKEND_CONTRACT_ACCEPTANCE_MAPPING.md) — positive/negative/missing/restart/version/auth cases and existing gate links.

When documents are read together, the more specific event or identity rule governs its own
transport/identity domain; this freeze draft governs Phase boundaries and activation. No document
may be implemented selectively in a way that weakens another.

## 8. Final parent review

| Required check | Result |
|---|---|
| all eight V17 backend blockers covered | PASS, `8/8` |
| all Phase 4A Core contracts have exact backend/projection/browser ownership | PASS |
| every contract has positive, negative identity, missing, restart/version/auth cases where applicable | PASS |
| Phase 5 implementation excluded | PASS, `PHASE5_LEAKAGE = 0` |
| deterministic financial arithmetic remains backend Calculation authority | PASS |
| Provider -> Validate -> Normalize -> Resolve Conflict -> Accepted Evidence gate preserved | PASS |
| self-correction and replan remain distinct; generated capability remains supporting activity | PASS |
| no cross-object/latest/first/title/symbol/metric fallback | PASS |
| no internal artifact locator crosses public boundary | PASS |
| no raw provider payload or hidden chain-of-thought field is public | PASS |
| sparse graph events force projection refresh and never fabricate a Task | PASS |
| unavailable material financial output cannot become successful release | PASS |
| all SSE cursor/recovery/terminal states are exact | PASS |
| current implementation conflicts are recorded rather than described as complete | PASS |

`UNRESOLVED_PHASE4_SEMANTIC_CONFLICTS = 0`. The implementation deltas remain open and none has
been executed or accepted.

## 9. Stop and later handoff

No Backend implementation, Frontend V17 integration, database migration, runtime change, test
activation, or merge is authorized. Wait for all three prerequisites:

1. immutable Phase 3 Backend candidate;
2. Backend Independent Final Audit = PASS; and
3. Financial Semantics Final Audit = PASS.

Then perform only `PHASE4_BACKEND_FINAL_CONTRACT_DELTA_RECONCILIATION` against that approved SHA.
Only a later decision may set `PHASE4_BACKEND_CONTRACT_FREEZE_READY = YES` and authorize Phase 4
implementation.

```text
INSPECTED_BACKEND_HEAD = 11fe8173a25ff7ac08bae42340ba7c6fae591be5
INSPECTED_BACKEND_FINGERPRINT = 39ce26c1ee4f0cb9091d048318f5938501af596fdc7441979dfeb9e60ccc1f41
BACKEND_CHANGED_DURING_REVIEW = NO
BLOCKERS_COVERED = 8/8
PHASE5_LEAKAGE = 0
UNRESOLVED_PHASE4_SEMANTIC_CONFLICTS = 0
PHASE4_BACKEND_CONTRACT_DRAFT_READY = YES
PHASE4_BACKEND_CONTRACT_FREEZE = NOT_FINAL
PHASE4_PRODUCTION_IMPLEMENTATION_AUTHORIZED = NO
WAITING_FOR_APPROVED_PHASE3_BACKEND = YES
```
