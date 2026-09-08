# Workstream F Report — Canonical Record & Output

## Status

**COMPLETE** for the Phase-1 Workstream F scope.

The implementation keeps the Foundation domain models frozen and adds the output/application
layer under `src/output/**`. Financial Review View (B) and Execution Details (C) are projections
of a caller-supplied `CanonicalExecutionRecord`; neither projection queries repositories or
recomputes business data.

## Authoritative baseline used

- Python: `3.11.16` via the shared project virtual environment
  `<repository-root>/.venv`
- `pyproject.toml`: unchanged at `requires-python = ">=3.11,<3.12"`
- Node: not required by this backend-only workstream. The shell default observed during the
  boundary check was Node `v25.9.0`, which is outside the frozen Node `>=24,<25` baseline and
  should be resolved by the integration/environment owner before frontend verification.

## Implemented interfaces

### Canonical record

- `CanonicalExecutionRecordBuilder.build(...) -> CanonicalExecutionRecord`
- Deep-copies mutable graph inputs to publish a detached execution snapshot.
- Stable-deduplicates lineage references and rejects blank references.
- Uses, rather than modifies, the frozen Foundation domain model.

### Same-source B/C projections

- `build_financial_review_view(record) -> FinancialReviewView`
- `build_execution_details(record) -> ExecutionDetails`
- `build_canonical_record_projections(record) -> CanonicalRecordProjections`

The combined builder accepts one record object and publishes the same `canonical_record_id` on
both views. The financial view exposes decision, evidence, calculation, review, and proof lineage.
The execution view exposes planned/actual graphs, task/capability/correction/replan/trace lineage,
and cost/token/latency outcome data. Projection inputs are deep-copied so later mutation of the
working record cannot silently change an already-published view.

### Released research result

- `ReleaseGateSnapshot`
- `ReleasedResearchResultBuilder.build(...) -> ReleasedResearchResult`

Publication requires:

1. Financial Review `PASS`;
2. no hard block; and
3. every supplied `MUST_PROVE` status to be `VERIFIED`.

An empty `must_prove_statuses` list implements the current Phase-1 no-MUST-PROVE case while
retaining the future proof boundary.

### Financial report

- `FinancialReport`
- `FinancialReportRenderer.render(...) -> FinancialReport`

The renderer emits the minimum Phase-1 JSON sections:

- `research_object`
- `financial_summary`
- `fundamental_result`
- `peer_result`
- `valuation_result`
- `risk_result`
- `investment_thesis`
- `limitations`

It maps released data without performing financial recalculation. PDF/layout rendering remains
outside Phase 1.

### Object writeback

- `ValueType`: `FACT | CALCULATION | FORECAST | JUDGMENT`
- `WritebackTarget`: explicit target per value class
- `ObjectWritebackItem`
- `ObjectWritebackProposal`
- `ObjectWritebackProposalBuilder.build(...)`

Enforced mappings and lineage:

| Value type | Required target | Required lineage |
|---|---|---|
| FACT | `CANONICAL_STATE` | source evidence reference(s) |
| CALCULATION | `VERSIONED_METRIC` | `calculation_id` |
| FORECAST | `VERSIONED_FORECAST` | `assumption_set_id` |
| JUDGMENT | `VERSIONED_JUDGMENT` | versioned `judgment_ref` |

This validation prevents an AI judgment from overwriting canonical fact state.

## Existing Logic Reuse Matrix

| Existing Module | Decision | Reuse Method | Compatibility | Action |
|---|---|---|---|---|
| `src/domain/canonical_execution_record.py` | DIRECT_REUSE | direct model output | Python 3.11 PASS | keep frozen |
| `src/domain/released_research_result.py` | DIRECT_REUSE | direct model output | Python 3.11 PASS | keep frozen |
| `src/domain/enums.py` review/proof statuses | DIRECT_REUSE | direct enum import | Python 3.11 PASS | keep frozen |
| `src/domain/base.py` domain model aliases | DIRECT_REUSE | direct base import | Python 3.11 PASS | keep frozen |
| Existing report/writeback implementation | PORT_REQUIRED | no implementation existed in current tree | N/A | implement at output boundary |

No existing financial calculation, FinRobot, FMP, Agent, or frontend logic was rewritten or
copied by this workstream.

## Tests

Added `tests/unit/output/test_output.py` with 13 tests covering:

- canonical source detachment and stable reference handling;
- B/C shared canonical record ID;
- projection snapshot behavior/no independent source recomputation;
- release gate review, proof, and hard-block behavior;
- Released Research Result construction;
- exact minimum Financial Report JSON mapping;
- all four writeback value classes;
- rejection of Judgment-to-canonical-state writes;
- per-type lineage requirements.

Verification results:

```text
PYTHONPATH=. .../.venv/bin/python -m pytest tests/unit/output -q
13 passed

PYTHONPATH=. .../.venv/bin/python -m pytest -q
19 passed

PYTHONPATH=. .../.venv/bin/python -m ruff check .
All checks passed!

PYTHONPATH=. .../.venv/bin/python -m ruff format --check src/output tests/unit/output
8 files already formatted
```

The full-repository Ruff format check reports 32 pre-existing Foundation files that would add a
trailing newline. Those files are outside this workstream's ownership and were not modified.

## Boundary review

- Modified owned implementation: `src/output/**`
- Modified owned tests: `tests/unit/output/**`
- Added required report: `WORKSTREAM_REPORT_OUTPUT.md`
- Frozen `src/domain/**`: **no changes**
- Frozen `contracts/**`: **no changes**
- `pyproject.toml` / runtime baseline: **no changes**
- External source, FinRobot, FMP, frontend: **no changes**

## Contract deviations

**NONE.**

## Known gaps / integration notes

- The Canonical Execution Record currently stores references, so these Phase-1 projections expose
  reference lineage rather than hydrating referenced objects. Hydration should happen upstream
  before record construction or in a separately approved read model, never via independent B/C
  queries.
- `ReleaseGateSnapshot` is a boundary input; the assurance workstream remains responsible for
  producing its authoritative review/proof statuses.
- Persistence, API routes, and end-to-end orchestration are integration-workstream concerns.
- Financial Report output is JSON data only; attractive PDF/UI rendering is intentionally deferred.
