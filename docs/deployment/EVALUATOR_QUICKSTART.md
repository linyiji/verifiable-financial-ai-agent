# Investor / platform evaluator quickstart

Recommended mode: **Evaluator**. You receive one encrypted `evaluation.vfaeval` privately from the Owner and its passphrase through a separate channel. This opaque credential grants bounded gateway access; it contains no FMP, TeamoRouter or MiMo keys. Do not configure upstream keys locally.

**Deployment prerequisite:** this foundation was tested with fake upstreams only. No real Owner gateway was deployed by this task. Ask the Owner for a deployed HTTPS gateway and bundle before live evaluation. No usable credential or public service is bundled in Git.

## 1. Install for your platform

Follow [macOS](MACOS_EVALUATION.md) or [Windows / WSL2](WINDOWS_EVALUATION.md). Use the actual repository URL supplied by the Owner; publication/branch promotion is separate. Prerequisites: Python 3.11, Node.js 24, PostgreSQL 16-compatible server. Generated capability validation requires Docker; full required-proof Runs require the [RISC Zero toolchain](../../zk/revenue_growth/README.md), SDK 3.0.6. Do not enable development/fake proof mode.

## 2. Configure your database, not provider keys

Copy `.env.example` to ignored `.env.local`. Keep `VFA_CREDENTIAL_MODE=evaluator`. Set DATABASE_URL to a newly provisioned evaluator-owned database, not the Owner's historical database. URL-encode password special characters. Leave provider and telemetry keys empty. Optional `VFA_EVALUATOR_GATEWAY_URL` pins the public HTTPS origin; otherwise the authenticated bundle supplies it. Never place a bearer token in dotenv or environment variables.

From repository root in the active virtual environment:

```bash
python scripts/postgresql_migrate.py
```

This changes your configured database. A fresh clone contains no Owner production data, capability certifications, reports or Research Memory. Research/release gates remain unchanged.

## 3. Open the bundle and start

```bash
python scripts/evaluator_start.py --bundle "/path/to/evaluation.vfaeval"
```

Use a real interactive terminal. Enter the passphrase at the hidden prompt, never as a command argument. The launcher decrypts in process memory, checks gateway authority, then starts the backend on `127.0.0.1:8010`. It does not save the token, spawn a credential-bearing subprocess, use a reload worker, or contact upstream during readiness. Restarting requires the bundle and passphrase again. A failed replacement import clears prior session authority.

Readiness displays credential PASS, gateway CONFIGURED, allowed routes, data access, expiry (Unix UTC seconds) and remaining quotas. CONFIGURED does **not** mean providers are live-verified or capability-certified. Zero quota/restricted scope is shown explicitly. Local DB/proof/Docker prerequisites are separate. Add `--readiness-only` for a handshake without backend startup.

In a second terminal:

```bash
cd apps/web
npm exec vite -- --host 127.0.0.1 --port 4173 --strictPort
```

Open [the local product](http://127.0.0.1:4173). Keep both terminals running; Ctrl+C stops them. Exact loopback host/ports match CORS. Backend `/health` means liveness, not paid-provider health. Do not expose this local Alpha to the Internet.

## 4. Evaluate real research

1. Create a Research Object with accurate company identity; define its goal/as-of date.
2. Generate a Scheme (a quota-limited model operation), review and confirm exact intent.
3. Confirmation can call graph planning and admit a real Run. Follow research, data, financial review, proof and bounded recovery.
4. If RELEASED, inspect Report / Financial Review / Execution and Research Memory. A later incremental study uses the released base; inspect Base vs Current.

Failure is a real outcome. Do not bypass proof, certification, release, Scheme or recovery gates. Expired/revoked credentials, exhausted quotas or lost gateway authority stop access; they do not trigger other-provider attempts or direct local fallback. Ask the Owner to resolve authorization. Do not post credentials, passwords or raw diagnostic payloads to issues.

Gateway quotas are protective evaluation limits, **not billing, commercial credits, subscriptions or paid-plan entitlements**. Cost is `NOT_OBSERVED`; live research can incur Owner upstream costs. Readiness consumes zero model/data quota. [Owner operations](EVALUATOR_GATEWAY.md) · [Security](../architecture/EVALUATOR_CREDENTIAL_SECURITY.md).

## Advanced options

[BYOK / independent deployment](LOCAL_DEPLOYMENT.md) is preserved with explicit `VFA_CREDENTIAL_MODE=byok`; it is not an evaluator fallback. Optional macOS Keychain and Windows Credential Manager persistence are **NOT_IMPLEMENTED**. Session-only import is universal, including WSL2 without a keychain.

For facilitated read-only Alpha with a separately supplied accepted database and matching artifacts, existing `scripts.readonly_product_server:app` and private `VFAS_ACCEPTANCE_ENV_FILE` remain available. They cannot create research or populate an empty clone with screenshot data. [License status](../LEGAL_AND_LICENSE_STATUS.md).
