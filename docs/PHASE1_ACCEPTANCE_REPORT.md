# Phase 1 Acceptance Report

[简体中文](PHASE1_ACCEPTANCE_REPORT.zh-CN.md)

Date: 2026-09-03<br>
Baseline: Python 3.11 / Node.js 24<br>
DB target: PostgreSQL; verified local mode: SQLite + SQLAlchemy async

## Result

- Full pytest suite: 75 passed, 0 failed, 0 skipped
- Dependency warnings: 2 TestClient deprecation warnings
- Ruff: PASS
- Python compileall: PASS
- Live Uvicorn startup: PASS
- `/health`: HTTP 200
- `/openapi.json`: HTTP 200, 18 paths
- Phase-1 minimum acceptance chain: PASS

## Saved execution evidence

Run `PYTHONPATH=. .venv/bin/python scripts/run_acceptance.py` to regenerate:

- `artifacts/acceptance/latest/acceptance_summary.json`
- `artifacts/acceptance/latest/runtime_events.json`
- `artifacts/acceptance/latest/calculation_records.json`
- `artifacts/acceptance/latest/canonical_execution_record.json`
- `artifacts/acceptance/latest/released_research_result.json`
- `artifacts/acceptance/latest/financial_report.json`
- `artifacts/acceptance/latest/writeback_proposal.json`
- `artifacts/acceptance/pytest.xml`

These generated artifacts are intentionally ignored by Git. The generator and this report are
tracked; local run artifacts may contain execution-specific IDs.

## Deferred acceptance cases

- AC-013 / AC-014: generated capability product flow
- AC-017: real RISC Zero proof
- AC-026: cross-object comparison gate

All are explicitly outside the minimum Phase-1 chain. `NOT_IMPLEMENTED` is preserved for the ZK
adapter and never presented as a proof pass.
