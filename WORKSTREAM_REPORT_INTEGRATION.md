# Workstream G — Integration Report

## Outcome

**COMPLETE** for the Phase-1 Foundation integration gate.

The repository now has one executable offline chain:

```text
Object → Goal → fallback Scheme → user confirmation → Lead plan
→ dependency runtime (real parallel tasks) → accepted fixture evidence
→ CapabilityRegistry / ToolRuntime calculations → task-local correction
→ Specialist pending ReplanRequest → Lead approval → graph child task
→ independent Review → explicit NOT_IMPLEMENTED proof result
→ ReleaseGate → Canonical Execution Record → released A/B/C outputs
→ Object writeback proposal → ordered replayable SSE
```

API routes only translate HTTP input/output. Orchestration is centralized in
`src/application/service.py`; runtime task-to-capability/Agent adaptation is in
`src/application/execution.py`.

## Authoritative runtime baseline

| Runtime | Frozen range | Verified | Result |
|---|---:|---:|---|
| Python | `>=3.11,<3.12` | `3.11.16` | PASS |
| Node.js | `>=24,<25` | `v24.18.0` from existing fnm runtime | PASS |
| npm | Node 24 installation | `11.6.2` | PASS |

No Python 3.14 environment was used or installed. Node was checked through the existing fnm path;
the Homebrew Node 25 runtime was not used as the project baseline.

## Delivered implementation

| Path | Responsibility |
|---|---|
| `src/application/service.py` | use-case orchestration, assurance/release composition, idempotency |
| `src/application/execution.py` | Runtime Task adapter, capability calls, correction, controlled replan |
| `src/application/repository.py` | application repository protocol and in-memory implementation |
| `src/application/persistence.py` | SQLAlchemy object/draft/run aggregate persistence |
| `src/application/events.py` | terminal-aware replay/live SSE application stream |
| `apps/api/routes.py` | thin `/api` REST and SSE contract mapping |
| `apps/api/main.py` | router/lifespan/error-handler composition only |
| `tests/integration/test_application_flow.py` | API+DB, full chain, ordering/replay, projections |
| `tests/acceptance/test_phase1_acceptance.py` | minimum Phase-1 acceptance chain |

### Persistence additions

Integration owns SQLAlchemy tables defined at the application persistence boundary:

- `research_objects`
- `research_run_drafts`
- `research_runs`
- `research_goals`
- `research_scheme_snapshots`
- `tasks`
- `runtime_events`
- `calculation_records`
- `review_records`
- `canonical_execution_records`
- `released_research_results`

`research_runs.payload` remains the Phase-1 durable aggregate/checkpoint view, while the child
tables provide typed identity and `run_id` lookup boundaries over the same existing domain
payloads. Existing `SQLAlchemyEvidenceRepository` is reused through a session-factory adapter and
persists every accepted fixture record to `evidence_records`. PostgreSQL remains the target; tests
use SQLite and verify exact child-table/evidence counts plus aggregate restoration.

### Controlled historical fixture policy

The run date is `2026-09-03`, while the fixture includes FY2025 data dated `2025-01-26`. The
application injects `FreshnessPolicy(max_age_days=800)` for this explicitly controlled historical
statement fixture. Records still pass through normal validation and must have
`EvidenceStatus.ACCEPTED`; status is never bypassed or overwritten.

### Correction and replan semantics

- EBITDA Margin first receives the fixture's Q1 revenue candidate against FY EBITDA. The existing
  financial capability rejects the mismatch. The same fundamentals Task emits self-correction
  events, stores a real `CorrectionRecord`, selects aligned FY2026 evidence, and succeeds without a
  new top-level task.
- The Risk Specialist creates only a pending `ReplanRequest`. `ResearchLeadReplanDecider` approves
  it and `GraphMutationService`, acting as the Lead, adds one child Task to Actual Graph only.
  Planned Graph remains unchanged.

### Proof semantics

The Phase-1 RISC Zero adapter returns `ProofStatus.NOT_IMPLEMENTED`. The default proof policy marks
these calculations `NOT_REQUIRED`, so ReleaseGate can release after Review PASS. If a calculation
is configured as `MUST_PROVE`, the existing gate blocks `NOT_IMPLEMENTED`. No verified ZK proof is
claimed.

## Existing Logic Reuse Matrix

| Existing Module | Decision | Reuse Method | Compatibility | Action |
|---|---|---|---|---|
| `src/domain/**` contracts | DIRECT_REUSE | direct | Python 3.11 PASS | keep frozen |
| `src/agentic/scheme.py` | DIRECT_REUSE | fallback generator | Python 3.11 PASS | compose |
| `src/agentic/planner.py` | DIRECT_REUSE | Lead initial plan | Python 3.11 PASS | compose |
| `src/agentic/decisions.py` | DIRECT_REUSE | Lead replan decision | Python 3.11 PASS | compose |
| `src/runtime/scheduler.py` | DIRECT_REUSE | dependency scheduling | Python 3.11 PASS | compose |
| `src/runtime/graph.py` | DIRECT_REUSE | authorized mutation | Python 3.11 PASS | compose |
| `src/runtime/events.py`, `sse.py` | ADAPTER_REUSE | application terminal stream | Python 3.11 PASS | wrap |
| `src/data/**` | ADAPTER_REUSE | fixture ingestion | Python 3.11 PASS | inject controlled policy |
| `src/capabilities/**` | DIRECT_REUSE | registered deterministic calculations | Python 3.11 PASS | compose |
| `src/tooling/**` | DIRECT_REUSE | native backend routing | Python 3.11 PASS | compose |
| `src/assurance/**` | DIRECT_REUSE | independent review/proof/release | Python 3.11 PASS | compose |
| `src/output/**` | DIRECT_REUSE | canonical/release/report/writeback | Python 3.11 PASS | compose |
| `src/adapters/risc0/pending.py` | ADAPTER_REUSE | proof boundary | Python 3.11 PASS | preserve NOT_IMPLEMENTED |
| `src/adapters/fmp/**` | ADAPTER_REUSE | provider boundary | Python 3.11 PASS (unit) | live use later |
| FinRobot implementation | PORT_REQUIRED | adapter protocol only | source absent | exact-module audit later |
| `frontend_reference/financial_agent_workspace_v3.html` | ADAPTER_REUSE | structure/style/interaction mapping for later Web | not exercised beyond Node 24 baseline | preserve; no framework rewrite |

No existing business-equivalent implementation was rewritten for directory-layout reasons.

## Acceptance matrix

| ID | Result | Evidence / note |
|---|---|---|
| AC-001 | PASS | REST + service create Research Object |
| AC-002 | PASS | deterministic fallback Scheme from Object + Goal |
| AC-003 | PASS | explicit confirmation timestamp before planning |
| AC-004 | PASS | persisted Research Run aggregate |
| AC-005 | PASS | full initial graph created before scheduler |
| AC-006 | PASS | real `asyncio.gather`; integration peak `>=2` |
| AC-007 | PASS | capability rejects non-ACCEPTED evidence; run consumes accepted bundle only |
| AC-008 | PASS | Revenue Growth through ToolRuntime |
| AC-009 | PASS | CalculationRecords link accepted evidence IDs |
| AC-010 | PASS | correction events + `CorrectionRecord`, no top-level task |
| AC-011 | PASS | Specialist result carries pending ReplanRequest |
| AC-012 | PASS | Lead approval + GraphMutationService child Task |
| AC-013 | SKIP | capability-gap product flow deferred beyond minimum Phase-1 chain |
| AC-014 | SKIP | generated capability lifecycle deferred; API returns honest NOT_IMPLEMENTED |
| AC-015 | PASS | PASS/REVIEW/BLOCK covered by assurance tests; chain independently PASSes |
| AC-016 | PASS | proof policy and ReleaseGate tests |
| AC-017 | SKIP | real ZK explicitly later phase |
| AC-018 | PASS | NOT_IMPLEMENTED blocks MUST_PROVE; current NOT_REQUIRED release passes |
| AC-019 | PASS | Canonical Execution Record generated |
| AC-020 | PASS | B/C use the same canonical record ID |
| AC-021 | PASS | Financial Report rendered from released result |
| AC-022 | PASS | typed Fact/Calculation writeback proposal with lineage |
| AC-023 | PASS | monotonic persisted event store + `Last-Event-ID` resume test |
| AC-024 | PASS | fail-open trace adapter unit tests; Noop used by default |
| AC-025 | PASS | runtime checkpoint suite + SQL aggregate restore test |
| AC-026 | SKIP | multi-object comparison gate is outside Phase-1 minimum scope |

Phase-1 minimum acceptance in `docs/14_ACCEPTANCE_TEST_PLAN_V1.md` is fully PASS.

The ordered critical event-family assertion covers `run.created`, `scheme.generated`,
`plan.generated`, `task.started`, `task.progress`, `task.self_correcting`, `task.completed`,
`review.started`, `release.completed`, and `run.completed`. `scheme.generated` truthfully records
that generation happened during prepare before the Run identity existed; `task.progress` is emitted
after actual runtime dispatch, before task-specific work begins.

## Verification

All commands ran from the isolated `ws/integration` checkout with
`PYTHONPATH=.` and the shared Python 3.11 virtual environment.

```text
$ python -m pytest -q
75 passed, 2 warnings in 0.72s

$ python -m ruff check .
All checks passed!

$ python -m compileall -q src/application apps/api
PASS

$ git diff --check
PASS
```

The two warnings are deprecations originating inside the installed FastAPI/Starlette TestClient
dependency surface; there are no application warnings or test failures.

## Known gaps

- The default API composition uses in-memory SQLite and in-process background execution. A later
  deployment can supply PostgreSQL and a durable job worker without changing API routes.
- Live Runtime event fanout/checkpoints remain the existing in-memory protocol implementations;
  every completed event is additionally persisted to the Integration-owned `runtime_events` table,
  and the released aggregate persists graph/artifact state. Hydrating an in-memory live stream from
  SQL after a process restart remains a later event-store adapter.
- Live FMP, FinRobot modules, LLM scheme generation, generated capabilities, semantic/human review,
  real RISC Zero proofs, frontend implementation, and comparison are intentionally deferred.
- The API manual review and capability-gap routes return the documented error envelope with
  `NOT_IMPLEMENTED`; they never fabricate success.

## Contract deviations

**NONE** for the Phase-1 minimum acceptance chain.
