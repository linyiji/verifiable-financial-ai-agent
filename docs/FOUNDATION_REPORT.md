# Foundation Gate Report

[简体中文](FOUNDATION_REPORT.zh-CN.md)

## Scope

Foundation freezes the repository skeleton, Python/Node baselines, domain and transport contracts,
runtime events and statuses, capability/trace/proof interfaces, database base, repository protocol,
and test fixture baseline. Business implementations remain owned by parallel workstreams.

Frontend implementation remains `DEFERRED_PENDING_FINAL_UX_BASELINE`. Retained HTML prototypes are
draft/reference assets and are not final or canonical frontend baselines.

## Runtime baseline

- Python: `>=3.11,<3.12`
- Node.js: `>=24,<25`
- Correction authority: `ARCHITECTURE_BASELINE_CORRECTION_001`

## Existing Logic Reuse Matrix

| Existing Module | Decision | Reuse Method | Compatibility | Action |
| --- | --- | --- | --- | --- |
| Design documents and frozen ADRs | DIRECT_REUSE | direct | Runtime-neutral PASS | keep as source of truth |
| `frontend_reference/financial_agent_workspace_v3.html` | ADAPTER_REUSE | preserve prototype structure/styles/interactions for later Web work | Node 24 review deferred; static asset retained | wrap into future Web app, do not rewrite in Foundation |
| `diagrams/金融研究agent平台全流程图.png` | DIRECT_REUSE | direct documentation asset | Runtime-neutral PASS | keep |
| Financial calculation implementation | PORT_REQUIRED | no implementation was present; reuse candidates must be audited in FinRobot before integration | Not present locally | implement only minimum native vertical slice; audit FinRobot separately |
| FMP processing implementation | PORT_REQUIRED | provider adapter boundary | Not present locally | add fixture provider first; real provider later |
| Agent / Skill implementation | PORT_REQUIRED | frozen contracts plus adapter/registry boundaries | Not present locally | implement bounded workstream; no framework rewrite |
| Report implementation | PORT_REQUIRED | output adapter/builder boundary | Not present locally | implement minimum JSON output only |
| `third_party/FinRobot` | PORT_REQUIRED | planned FinRobot adapter | checkout absent; Python 3.11 range aligns with upstream metadata | do not block Foundation; audit exact modules when available |

No pre-existing backend, financial, Agent, utility, package, or framework source code was found in
the project root at Foundation start. The available implementation-like asset is the preserved HTML
prototype; it is not modified during backend Phase 1.

## Contract ownership

- Coordinator: `pyproject.toml`, `package.json`, `contracts/**`, `src/domain/**`,
  `apps/api/main.py`, database base, global settings.
- Workstreams consume these contracts and submit `CONTRACT_CHANGE_REQUEST` rather than editing them.

## Foundation verification

- Python: `3.11.16`
- Node.js: `v24.18.0`
- npm: `11.6.2`
- pytest: `6 passed, 0 failed, 0 skipped`
- Ruff: `All checks passed`
- FastAPI import / application title: PASS
- DB mode: SQLite async default; PostgreSQL-compatible URL supported through SQLAlchemy config
