# Phase 2.1 + Infrastructure Real-Integration Acceptance Report

[简体中文](PHASE2_1_INFRASTRUCTURE_ACCEPTANCE_REPORT.zh-CN.md)

Date: 2026-09-04 (Asia/Shanghai)<br>
Decision: **PASS**<br>
Frontend / Generated Capability / RISC Zero / POT / Comparison: **DEFERRED / OUT OF SCOPE**

## A. Baseline HEAD

- Execution baseline before WS-R/WS-S integration: `aa003c9`
- Integration code and status baseline before this report: `d6b06a6`
- Runtime baseline: project `.venv` Python `3.11.16`; Node.js `24.18.0`; npm `11.6.2`
- `pyproject.toml` remains Python `>=3.11,<3.12`.

## B. PostgreSQL

- Existing container: `verifiable-financial-postgres`; running; no `docker run`, volume deletion,
  schema drop, or downgrade was performed.
- Server: PostgreSQL `16.15`; database `verifiable_financial_agent`; application user `vfa`.
- Unified Settings loads `DATABASE_URL` from ignored `.env.local`; file mode `0600`;
  `.env.example` retains the blank `DATABASE_URL=` template.
- Alembic migrated the existing database from no revision through `0001`, `0002`, and append-only
  `20260904_0003`; the final schema has 18 tables.
- Migration `0003` adds durable planned/actual `TaskDependency` rows without rewriting prior
  revisions.
- Real PostgreSQL suite: 9 passed.
- Fifty concurrent event writers produced one contiguous, unique per-run sequence without gaps or
  duplicates; an explicit skipped sequence was rejected.
- The authoritative NVDA run persisted 120 RuntimeEvents with sequence `1..120`, graph version 2,
  15 planned and 16 actual dependency rows, checkpoint, Evidence/Calculation lineage, corrections,
  replan, review, canonical record, and released result.
- A new engine/session composition restored aggregate, checkpoint, event replay, canonical record,
  and released result by complete model equality. SSE replay resumed at sequence 1.
- P2-019 and INFRA-001..007: PASS.

## C. Langfuse

- Region: `https://jp.cloud.langfuse.com`.
- Credentials are loaded through Unified Settings and are never printed, committed, or written to
  artifacts.
- Official Python SDK: 3.15.0 optional runtime dependency installed in the project environment.
- Connectivity smoke: CONNECTED; authentication and flush passed. Smoke trace:
  `b2f5e49bfbd4831c2c9d428fd00bbd08`.
- Authoritative Research Run trace: `b335fc3bd1765aa5dcf9e6da50dd73ed`.
- One root trace contains 57 identifier references across: scheme/planner generation, planning,
  run, task, agent, skill, tool, Evidence batch, calculation, self-correction, replan, review, and
  release.
- LLM generations use the SDK's native generation observation. Requested/actual model, provider,
  measured latency, and provider-returned token counts are mapped; absent cost is omitted rather
  than fabricated.
- Prompts, model output, raw FMP JSON, normalized values, environment variables, and secrets are
  excluded. Evidence observations contain metadata summaries only.
- CanonicalExecutionRecord stores only owned trace-reference IDs.
- A prior non-authoritative run experienced Japan exporter read timeouts and continued to release,
  demonstrating fail-open behavior. The authoritative run completed and flushed without exporter
  error.
- TRACE-001..012: PASS.

## D. Phase 2.1 Workstreams

| Workstream | Result | Integration evidence |
|---|---|---|
| WS-M Evidence ownership/events | PASS | scoped producer ownership; exactly-once accepted Evidence events |
| WS-N Replan dependency integrity | PASS | atomic Risk → Follow-up → Synthesis rewiring; graph v2 |
| WS-O Calculation provenance | PASS | reproducible source hashes; Evidence/Review/Canonical lineage |
| WS-P TeamoRouter scheme route | PASS | real structured Scheme and Planner provenance; no deterministic fallback |
| WS-Q Peer/normalization | PASS | 9 candidates and 9 explicit decisions; employee unit `COUNT` |
| WS-R PostgreSQL | PASS / MERGED | real PostgreSQL 16 migrations, concurrency, restore, SSE |
| WS-S Langfuse | PASS / MERGED | Japan connectivity, native generations, fail-open, trace refs |
| WS-T0 FinRobot activation | PASS | 13-module runtime activation matrix; zero false `ACTIVE_REUSE` claims |

## E. Evidence ownership fix

Company, peer, and research-news acquisition are separate scopes. Task outputs contain only
Evidence produced by that task, consumers retain references, and each accepted Evidence identity
emits one event. The authoritative run contains 40 company Evidence records and 9 peer Evidence
records. News and transcript returned HTTP 402 and produced no Evidence.

The downstream research-news task now reports `entitlement_blocked` with an explicit limitation;
it cannot masquerade as completed analysis or cite unrelated company Evidence.

## F. Replan graph fix

The actual graph replaces the direct Risk-to-Synthesis edge with Risk-to-Follow-up and
Follow-up-to-Synthesis. Edge add/remove events and the version transition from 1 to 2 are persisted
and replayable. Synthesis started only after the runtime-added mandatory follow-up completed.

## G. Calculation provenance

Both Revenue Growth and EBITDA Margin records carry reproducible SHA-256 source hashes, Python
runtime/source references, accepted Evidence inputs, and Review/Canonical IDs. Calculation values
remain deterministic Financial Code outputs; no LLM or FinRobot valuation result bypasses the
CalculationRecord boundary.

## H. Scheme route

- Scheme: TeamoRouter, requested `gpt-5.6-sol`, actual `gpt-5.6-luna`, validated structured output,
  no deterministic fallback.
- Planner: TeamoRouter, requested/actual `gpt-5.6-sol`, second semantic validation attempt passed,
  no deterministic fallback.
- Attempted-model provenance records the actual route and retry attempts.

## I. Peer selection

FMP returned nine peer candidates. The deterministic policy created nine corresponding selection
decisions and selected zero because enrichment needed for classification, business relevance,
market-cap ratio, data availability, and metric comparability was absent. Candidate discovery is
not reported as selected comparables.

## J. Real NVDA PostgreSQL + Langfuse Run

| Record | Identifier / result |
|---|---|
| Research Run | `RUN-452a94c8-e4a4-4445-816e-668ead86c8dd` — RELEASED |
| Langfuse Trace | `b335fc3bd1765aa5dcf9e6da50dd73ed` |
| Runtime Events | 120; sequence contiguous and unique |
| Accepted Evidence | 49 |
| Planned / Actual Tasks | 9 / 10; parallel peak 3 |
| Calculation 1 | `CALC-RUN-452a94c8-e4a4-4445-816e-668ead86c8dd-GROWTH` |
| Calculation 2 | `CALC-RUN-452a94c8-e4a4-4445-816e-668ead86c8dd-MARGIN` |
| Canonical Record | `CER-RUN-452a94c8-e4a4-4445-816e-668ead86c8dd` |
| Released Result | `RESULT-RUN-452a94c8-e4a4-4445-816e-668ead86c8dd` |
| PostgreSQL restart | complete aggregate/canonical/released/checkpoint/event equality PASS |
| SSE replay | first persisted event replayed at sequence 1 |

Sanitized local acceptance artifacts are under
`artifacts/infrastructure/acceptance/latest/` and are intentionally ignored by Git.

## K. Tests

- Full repository: 159 passed; one Starlette/AnyIO dependency deprecation warning.
- Phase 1 + Phase 2 regression selection: 35 passed.
- PostgreSQL + Langfuse + runtime observability + FinRobot selection: 29 passed.
- Real PostgreSQL suite: 9 passed.
- FinRobot adapter audit: 9 passed.
- Phase 2.1 real semantic evaluator: P2.1-001..013 all passed.
- Ruff lint: PASS.
- All 26 Python files changed since the infrastructure baseline pass `ruff format --check`.
- compileall: PASS.
- Git diff whitespace check: PASS.
- Exact configured-secret and credential-pattern scan: 274 tracked/acceptance files, zero leaks.

## L. Acceptance Matrix

| Gate group | Result |
|---|---|
| INFRA-001..007 | PASS |
| TRACE-001..012 | PASS |
| P2.1-001..013 | PASS |
| P2.1-014 Phase 1 regression | PASS |
| P2.1-015 Phase 2 regression | PASS |
| P2-019 real PostgreSQL | PASS; previous defer closed |
| Secret/config safety | PASS |

## M. Regression

Foundation, Phase 1, Phase 2, Phase 2.1, database, observability, and adapter suites pass together.
The project-wide Ruff lint gate is clean. Repository-wide format check still identifies 40 legacy
files outside this execution diff; they were not mechanically rewritten because they are unrelated
user/project history. Every Python file changed in this execution passes the format gate.

## N. Git commits

- `b82f017` — WS-S real Langfuse tracing.
- `b4775c3` — merge WS-S.
- `a0e0ac1` — WS-R real PostgreSQL persistence.
- `794885f` — merge WS-R.
- `221bedb`, `c0a6227`, `384d358` — News semantic fix and strengthened evaluator.
- `9a37e99`, `1236408` — trace-reference and runtime observation composition.
- `cb9121f`, `a9b1e9e` — unified real runner and combined-evidence/timeout fixes.
- `d6b06a6` — FinRobot activation matrix and final parallel status.

## O. Final HEAD

The exact final repository HEAD is the commit that adds this report and closes the acceptance
status; it is recorded in the handoff response together with `git status` cleanliness.

## P. Remaining gaps

1. FMP News and Transcript are entitlement-blocked (HTTP 402). The runtime now preserves this as a
   limitation and does not fabricate content.
2. Peer candidates lack enrichment, so no comparable is selected. This is a conservative PASS,
   not a peer-valuation result.
3. Cross-adapter database writes use independent transactions on a shared engine; a transactional
   outbox/unit-of-work remains a later resilience hardening item.
4. TeamoRouter responses did not provide monetary cost, so Langfuse cost is omitted. Token and
   latency provenance are retained when returned/measured.
5. FinRobot has zero active runtime modules. Charts are adapter-ready but lack a concrete pinned
   backend; Technical Indicators, professional HTML/PDF, and peer helpers require the ports in
   `FINROBOT_RUNTIME_REUSE_STATUS.md`.
6. The system Python command currently resolves to Python 3.14.3, while the project runs in the
   verified `.venv` Python 3.11.16 as required. No Python 3.14 project baseline is used.
7. The first unified attempt (`RUN-4d342dc0-12cb-4d5d-aa43-c8fa0d83075d`) is retained as a
   non-authoritative audit sample: business release/fail-open succeeded, but strengthened semantic
   acceptance rejected Planner fallback and the then-unfixed combined-task semantics.

No Frontend, Generated Capability, RISC Zero implementation, POT, or comparison work was started.
