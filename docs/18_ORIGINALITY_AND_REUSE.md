# 18 — Originality & Reuse

## Purpose

用于黑客松提交、开源归因、工程边界和后续商业审查。

## Third-party / existing

### FinRobot

Usage:

- selected financial code
- data processing
- charts
- rendering
- adapter-wrapped functions

Must record:

- repository URL
- pinned commit
- exact reused modules
- license / NOTICE
- modifications, if any

Do not claim its existing code as new competition work.

### Langfuse

Usage:

- observability SDK / OpenTelemetry trace

Our new work:

- finance semantic mapping
- canonical business record
- runtime instrumentation boundaries
- B/C projection

### RISC Zero

Usage:

- proof infrastructure

Our new work:

- proof policy
- finance proof boundary
- input commitments
- report / review linkage
- release behavior

### RD-Agent

Usage:

- architecture reference only unless later explicitly integrated

Borrowed idea:

- research → code → experiment → feedback

Our application:

- financial Capability Workshop

### MCP

Usage:

- protocol / SDK if/when MCP backend is enabled

Our new work:

- Tool Runtime abstraction
- native/MCP/generated routing
- permissions and financial capability semantics

## New project-specific implementation

- Research Object model
- Object state versioning
- Goal → AI Scheme flow
- Scheme confirmation
- Research Run
- Research Lead planning
- Planned vs Actual Graph
- parallel Dynamic Runtime
- Task Self-Correction
- Controlled Replanning
- Evidence hard gate
- deterministic financial number hard gate
- financial Calculation Record
- Agent / Skill / Capability boundary
- Generated financial capability lifecycle
- independent Financial Review
- Proof Policy
- Canonical Execution Record
- Released Research Result
- A/B/C output semantics
- Object Writeback Gate
- cross-object comparison
- POT / evaluation integration

## Competition workflow

Before coding:

```text
git tag PRE_HACKATHON_BASELINE
```

Keep full history.

At final submission:

- final commit
- diff from baseline
- originality / reuse statement
- third-party NOTICE
- dependency versions

## Phase-1 integration reuse audit

The executable integration follows `REUSE → WRAP → ADAPT → TEST`. API routes map HTTP contracts to
`ResearchApplicationService`; they do not reimplement planning, scheduling, evidence validation,
financial formulas, review, proof policy, canonical projection, or report logic.

| Existing module | Decision | Reuse method | Compatibility | Integration action |
|---|---|---|---|---|
| `src/agentic/**` | DIRECT_REUSE | fallback Scheme, Lead Planner, replan decider | Python 3.11 PASS | compose |
| `src/runtime/**` | DIRECT_REUSE | scheduler, graph mutation, checkpoints, event log/SSE encoding | Python 3.11 PASS | compose |
| `src/data/**` | ADAPTER_REUSE | fixture Provider → ingestion → accepted evidence bundle | Python 3.11 PASS | wrap with explicit historical freshness policy |
| `src/capabilities/**`, `src/tooling/**` | DIRECT_REUSE | CapabilityRegistry + ToolRuntime | Python 3.11 PASS | compose |
| `src/assurance/**` | DIRECT_REUSE | independent review, proof policy, ReleaseGate | Python 3.11 PASS | compose in control plane |
| `src/output/**` | DIRECT_REUSE | canonical record, B/C projection, result/report/writeback | Python 3.11 PASS | compose after release gate |
| `src/adapters/risc0/pending.py` | ADAPTER_REUSE | explicit pending proof boundary | Python 3.11 PASS | preserve `NOT_IMPLEMENTED` semantics |
| `src/adapters/fmp/**` | ADAPTER_REUSE | provider boundary | Python 3.11 PASS in unit tests | live credentials deferred |
| `src/adapters/finrobot/**` | PORT_REQUIRED | narrow adapter protocol | implementation absent | audit exact modules when source is added |
| prior frontend prototype | PORT_REQUIRED | contract reference only | source absent from checkout | do not select/rewrite a framework |

Integration-owned persistence adds only `research_objects`, `research_run_drafts`, and
`research_runs` aggregate tables in `src/application/persistence.py`. Normalized evidence continues
to use the existing `evidence_records` mapping. This is a Phase-1 SQLite/PostgreSQL-compatible
repository boundary, not a competing business implementation.
