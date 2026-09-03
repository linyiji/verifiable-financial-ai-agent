# Phase 2 Backend Acceptance Report

Date: 2026-09-04

Baseline: Python `>=3.11,<3.12`; Node.js `>=24,<25`

Frontend: `DEFERRED_PENDING_FINAL_UX_BASELINE`

## A. Environment

- Python: `3.11.16`
- Node.js: `v24.18.0`
- npm: `11.6.2`
- Backend: continued
- Frontend: deferred; no framework or prototype was promoted to final/canonical

## B. Secret and Config Safety

| Check | Result |
|---|---|
| `.env.local` ignored | PASS |
| `.env.local` tracked | NO |
| `FMP_API_KEY` | SET |
| `TEAMOROUTER_API_KEY` | SET |
| Langfuse credentials | NOT SET |
| Configured secret bytes in Git diff | NO |
| Unified Settings precedence (`.env`, then `.env.local`) | PASS |
| Secret-safe Settings representations | PASS |

Keys, previews, hashes, request authorization headers, and raw secret values are not included in
source, tests, logs, RuntimeEvents, artifacts, this report, or Git.

## C. Workstream Results

| WS | Result | Commit | Module gate |
|---|---|---|---|
| H FinRobot Exact Audit | PASS / MERGED | `44c8f18` | 9 focused; 86 branch full |
| I Live FMP | PASS / MERGED | `deb654f` | 16 focused; 92 branch full |
| J PostgreSQL | PASS / MERGED | `759ee30` | 4 passed; 1 expected environment skip |
| K TeamoRouter | PASS / MERGED | `275220c` | 10 focused; 87 branch full |
| L Langfuse | PASS / MERGED | `73121fa` | 9 focused; 84 branch full |

Each module passed Ruff, contract/ownership checks, secret scans, and its workstream report gate.

## D. Live FMP Endpoints Tested

The final integrated NVDA run made one bounded request per endpoint.

| Endpoint | HTTP | Result | Accepted |
|---|---:|---|---:|
| Company Profile | 200 | PASS | 12 |
| Income Statement | 200 | PASS | 4 |
| Balance Sheet | 200 | PASS | 3 |
| Cash Flow Statement | 200 | PASS | 3 |
| Stock Peers | 200 | PASS | 9 |
| Quote | 200 | PASS | 3 |
| Historical EOD Price | 200 | PASS | 10 |
| Analyst Consensus | 200 | PASS | 5 |
| Stock News | 402 | ENTITLEMENT_BLOCKED | 0 |
| Earnings Transcript | 402 | ENTITLEMENT_BLOCKED | 0 |

Provider connectivity, plan entitlement, and code status are reported independently. The two 402
responses are not code failures and no substitute data was fabricated.

## E. Real LLM Integration

- Provider: `teamorouter`
- Requested primary model: `gpt-5.6-sol`
- Configured fallback: `gpt-5.6-luna`
- Research Lead Planner actual model: `gpt-5.6-sol`
- Planner structured validation: PASS
- Planner graph: 10 planned tasks, schema/dependency/acyclic/skill/domain checks PASS
- Scheme requested model: `gpt-5.6-sol`
- Scheme result: deterministic fallback after `LLMProviderUnavailableError`
- Scheme schema/domain validation: PASS for the fallback snapshot

The Scheme provider outcome is deliberately not represented as a live-model success. Financial
numbers remain outside both Scheme and Planner schemas.

## F. Real Financial Vertical Slice

Final run: `RUN-5a4066f7-daaa-479f-8c5c-ff9720dba1f6` (`RELEASED`)

```text
Live FMP responses
  -> RawDataEnvelope / raw artifacts
  -> freshness / validation / normalization / conflict resolution
  -> 49 Accepted Evidence records
  -> native financial capabilities
  -> 2 CalculationRecords
  -> independent review PASS
  -> CanonicalExecutionRecord
  -> ReleasedResearchResult
```

| Capability | Live Evidence IDs | Calculation ID | Live result |
|---|---|---|---:|
| Revenue Growth | `EVD-5befb05f-941d-591b-9e48-363cb02d20c9`, `EVD-d4635248-dcb8-5e25-8d1a-52bf6270b5f0` | `CALC-RUN-5a4066f7-daaa-479f-8c5c-ff9720dba1f6-GROWTH` | `0.6547353579009479145114447075` |
| EBITDA Margin | `EVD-2797cdc5-5115-5bb2-8020-651ba55552f5`, `EVD-d4635248-dcb8-5e25-8d1a-52bf6270b5f0` | `CALC-RUN-5a4066f7-daaa-479f-8c5c-ff9720dba1f6-MARGIN` | `0.6694143689392325574933545740` |

Fixture comparison:

| Capability | Phase-1 fixture | Phase-2 live | Delta (percentage points) |
|---|---:|---:|---:|
| Revenue Growth | `0.6544061302681992337164750958` | `0.6547353579009479145114447075` | `+0.0329227633` |
| EBITDA Margin | `0.6600277906438165817508105604` | `0.6694143689392325574933545740` | `+0.9386578295` |

Provider-derived ratios and metrics remain `provider_reference_*`; neither live calculation above
uses an FMP-calculated ratio as the authoritative result.

## G. Tests

Final integration gate:

- pytest: 123 passed, 0 failed, 1 skipped
- skipped: real PostgreSQL test, environment prerequisites absent
- Ruff: PASS
- compileall: PASS
- warnings: 2 dependency deprecation warnings from FastAPI/Starlette TestClient

Changed-path format validation and the final secret scan also passed. Repository-wide format was
not mechanically rewritten because older accepted files predate the current formatter output.

## H. Phase 1 Regression

PASS. The fixture provider remains the default composition and the complete Phase-1 acceptance
chain still releases a canonical result. Phase-1 artifacts remain separate under
`artifacts/acceptance/latest`; Phase-2 artifacts use `artifacts/phase2/acceptance/latest`.

## I. Phase 2 Acceptance Matrix

| ID | Result | Evidence |
|---|---|---|
| P2-001 | PASS | `.env.local` is ignored |
| P2-002 | PASS | Unified Settings reports FMP credential SET |
| P2-003 | PASS | Unified Settings reports TeamoRouter credential SET |
| P2-004 | PASS | configured secret bytes absent from Git diff |
| P2-005 | PASS | live FMP connectivity |
| P2-006 | PASS | NVDA Profile HTTP 200 |
| P2-007 | PASS | NVDA income/balance/cash-flow HTTP 200 |
| P2-008 | PASS | raw FMP responses traversed Evidence Pipeline |
| P2-009 | PASS | 49 Accepted Evidence records |
| P2-010 | PASS | Revenue Growth produced by native capability |
| P2-011 | PASS | EBITDA Margin produced by native capability |
| P2-012 | PASS | provider-calculated metrics remain reference-only |
| P2-013 | PASS | TeamoRouter connectivity proven by real Planner response |
| P2-014 | DEFERRED_PROVIDER_UNAVAILABLE | real Scheme call exhausted bounded provider route; fallback used |
| P2-015 | PASS | resulting Scheme validates frozen Pydantic/domain schema |
| P2-016 | PASS | Research Lead Planner used real `gpt-5.6-sol` |
| P2-017 | PASS | 10-task Planned Graph validates |
| P2-018 | PASS | CalculationRecords contain only native capability outputs from Evidence IDs |
| P2-019 | DEFERRED_ENVIRONMENT_ABSENT | local PostgreSQL and asyncpg unavailable; code/offline migration gate PASS |
| P2-020 | PASS | complete Phase-1 regression suite remains green |

No required acceptance item is falsely reported as PASS. P2-014 and P2-019 retain their explicit
external-environment classifications.

## J. Known Gaps

- Real Scheme generation remains unavailable on the bounded provider route; deterministic fallback
  is functioning and a real Planner response proves TeamoRouter connectivity.
- News and transcript are blocked by the configured FMP plan entitlement.
- Live PostgreSQL concurrency/SSE verification requires a disposable PostgreSQL service and the
  already-declared `postgres` optional dependency.
- Langfuse is `NOT_CONFIGURED`; Noop/fail-open is active and tested.
- FinRobot renderer reuse is pinned/audited but its isolated optional dependency backend is not
  activated.
- Frontend, Generated Capability Sandbox, full MCP backend, RISC Zero, POT/evaluation, and
  comparison remain outside this phase.

## K. Git Commits and Merges

- Config / Secret Safety Gate: `0a58386`
- WS-H commit `44c8f18`; merge `15d1437`
- WS-K commit `275220c`; merge `76254aa`
- WS-I commit `deb654f`; merge `dfc3254`
- WS-L commit `73121fa`; merge `f748669`
- WS-J commit `759ee30`; merge `67bcd05`
- Integration / Acceptance implementation: `113a0a5`

## L. Next Recommended Step

Do not start Frontend. First re-run the real Scheme call when TeamoRouter availability permits and
run the conditional PostgreSQL suite against a disposable service. Both can close the two deferred
acceptance rows without changing the frozen contracts.

## Saved Acceptance Evidence

Regenerate with:

```text
PYTHONPATH=. .venv/bin/python scripts/run_phase2_acceptance.py
```

Ignored, local-only artifacts:

- `artifacts/phase2/acceptance/latest/acceptance_summary.json`
- `artifacts/phase2/acceptance/latest/accepted_evidence.json`
- `artifacts/phase2/acceptance/latest/calculation_records.json`
- `artifacts/phase2/acceptance/latest/runtime_events.json`
- `artifacts/phase2/acceptance/latest/canonical_execution_record.json`
- `artifacts/phase2/acceptance/latest/released_research_result.json`
