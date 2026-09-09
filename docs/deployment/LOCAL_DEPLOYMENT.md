# Advanced local deployment — BYOK

[简体中文](LOCAL_DEPLOYMENT.zh-CN.md)

Entry point: [Evaluator Quickstart](EVALUATOR_QUICKSTART.md). Commands run from repository root unless stated.

This page describes native direct-provider BYOK for developers. Investors may instead use the guided installer's privately supplied encrypted `.vfacred` bundle. No API keys are embedded in the repository, frontend or installer. For native BYOK, copy `.env.example` to `.env.local`, set `VFA_CREDENTIAL_MODE=byok`, provision DATABASE_URL, and privately fill FMP_API_KEY, TEAMOROUTER_API_KEY and MIMO_API_KEY. Install Python dependencies with `python -m pip install -e '.[dev,postgres]'` and frontend dependencies with `npm ci` in `apps/web`. The optional Owner gateway remains undeployed; it is not required by direct encrypted credentials or native BYOK.

## Environment contract

| Dependency | Current contract |
| --- | --- |
| Python | 3.11; pyproject requires >=3.11,<3.12 |
| Node | 24 used by local frontend checks; use npm ci with committed lockfile |
| PostgreSQL | Real product backend; accepted local server 16; provision before migration |
| FMP | Required live financial evidence; endpoint entitlement matters |
| TeamoRouter | Default primary/synthesis routes and governed alternatives |
| MiMo | Default Peer/Research News profiles and preferred Scheme planner |
| RISC Zero | SDK 3.0.6; build real host for required revenue-growth proof |
| Docker | Generated-capability sandbox/validation, when required by the task |
| Langfuse | Optional; no-op tracing without credentials |

Source contracts: [settings](../../src/infrastructure/config/settings.py), [API composition](../../apps/api/main.py), [route composition](../../src/adapters/llm/routes.py), [recovery composition](../../src/agentic/recovery_composition.py).

## Configuration and authority

Settings reads root `.env`, then `.env.local`; process environment takes precedence. Use `.env.example` only as a safe template. SQLite default is not the PostgreSQL real-product deployment—set DATABASE_URL explicitly.

Governed route IDs:
- teamorouter-sol → TEAMOROUTER_MODEL (default gpt-5.6-sol).
- teamorouter-luna → TEAMOROUTER_FALLBACK_MODEL (default gpt-5.6-luna).
- mimo-direct → MIMO_CHAT_MODEL (established direct models mimo-v2.5 / mimo-v2.5-pro).

These are repository route configurations, not universal claims of provider availability. No other provider is advertised. INCREMENTAL_PROVIDER_ROUTE and SPECIALIST_PROVIDER_ROUTES select registered routes. Base URL variables configure adapters; direct MiMo authority deliberately restricts HTTPS api.xiaomimimo.com/v1 and rejects credentials/query/fragment in the URL. It is not an arbitrary-proxy route.

MiMo direct authority uses injected BYOK Settings by default. Optional MIMO_AUTHORITY_FILE names a private file with MIMO_API_KEY, MIMO_BASE_URL, MIMO_CHAT_MODEL. An explicitly configured missing/incomplete file fails closed; it does not silently fall back to another credential. No developer-home path is required.

FMP supports the primary key or configured contiguous numbered pool. Keep provider keys server-side. A frontend variable must never contain a secret. Vite runs in apps/web and does not read the repository-root dotenv file: default API is already :8010; for an override, export VITE_API_BASE_URL in the frontend shell before starting/building.

## Commands and ports

```bash
# Provision the evaluator database separately, then apply the repository chain:
PYTHONPATH=. python scripts/postgresql_migrate.py
# Build real proof host after installing its toolchain:
./zk/revenue_growth/build-host.sh
# Writable product; starts the runtime worker:
PYTHONPATH=. uvicorn apps.api.main:app --host 127.0.0.1 --port 8010
# In a second terminal, from apps/web:
npm exec vite -- --host 127.0.0.1 --port 4173 --strictPort
```

Backend health GET /health returns status ok. Health is startup/liveness, not proof that remote services or a complete paid Run work. Frontend uses 127.0.0.1:4173; current CORS permits 4173/4174 on 127.0.0.1. Do not expose this Alpha publicly without an access-control design.

Persistent state spans PostgreSQL, ARTIFACT_ROOT and WORKSPACE_ROOT. Preserve matching artifacts with the database; a bare database copy can leave exact artifact links unavailable. Backups and secrets distribution remain the evaluator/operator's responsibility.

## Common failures

- Database connection/migration failure: check provisioned database, user permissions, URL-escaped password, asyncpg install and active virtual environment.
- MiMo authority unavailable/incomplete: provide keys in root configuration or a readable explicit private file; an old owner-local path is not portable.
- Provider authentication/unsupported model: check entitlement and route IDs. Do not invent replacement provider names.
- FMP missing/forbidden endpoint: check financial-data subscription and pool configuration.
- CORS/fetch failure: use the exact loopback host/ports, not a silently reassigned Vite port.
- Proof host missing or invalid: build using the committed wrapper; do not set RISC0_DEV_MODE or RISC0_SKIP_BUILD. A required-proof failure blocks release.
- Empty Research Object/Memory: a fresh clone has no production seed data; create research and obtain a genuine release.
- No governed recovery candidate: absent/unknown capability evidence is not automatic permission. Fresh-state recovery can differ from the accepted historical example.
- Mutation returns 403: the strict read-only acceptance entry point intentionally cannot run research; use the writable launcher only for an authorized local execution.

## Verification boundary

Current source/tests/build and BYOK composition are checked without live calls. This documentation task did not provision a fresh database, install proof tools or execute a new paid Run. See [local deployment acceptance](../validation/LOCAL_DEPLOYMENT_ACCEPTANCE.md). Docker one-command BYOK deployment is not provided; the separate installer foundation supports gateway mode only.
