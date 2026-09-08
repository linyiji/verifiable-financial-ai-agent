# Evaluate Verifiable Financial Agent locally

This is a BYOK local product, not a hosted subscription. Use your own FMP, TeamoRouter and MiMo credentials, or temporary provider credentials supplied by the owner **out of band**. Never put secrets in Git, issues, screenshots or browser VITE variables. A temporary credential is not enterprise authentication.

## 1. Clone and install

Use the clone URL of the repository you are evaluating. Until deliberate publication, the accepted product is on the local `phase4` branch; the default branch has not been changed.

```bash
git clone <repository-clone-url>
cd <repository-directory>
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,postgres]'
cd apps/web
npm ci
cd ../..
cp .env.example .env.local
```

Prerequisites: Python 3.11 (not 3.12), Node.js 24, a running PostgreSQL server, and access to the configured financial-data/model services. The accepted local environment uses PostgreSQL 16; other versions are not newly certified here.

## 2. Configure and provision

Edit ignored `.env.local` using the grouped [example](../../.env.example). Supply your own PostgreSQL URL/password, FMP key, TeamoRouter key and MiMo key. Default Peer and Research News routes require MiMo. Ensure provider accounts permit the configured model IDs and FMP endpoints; a syntactically valid key does not establish entitlement.

Create a new, evaluator-owned PostgreSQL database with the name in DATABASE_URL using your database administration tool. Do not point a first evaluation at the owner's historical database.

```bash
PYTHONPATH=. python scripts/postgresql_migrate.py
```

This command changes the configured database. The repository contains migrations, not the owner's production dump or private report artifacts.

## 3. Prepare full-execution dependencies

Install Rust and the official RISC Zero toolchain required by the [bounded proof workspace](../../zk/revenue_growth/README.md), then:

```bash
./zk/revenue_growth/build-host.sh
```

RISC Zero SDK crates are pinned to 3.0.6. Proof tooling is optional for browsing an existing deployment, but **not optional for a new Run whose required proof must pass**. Do not enable development/fake-proof mode. Docker is also required when generated-capability validation is invoked. See [deployment details](LOCAL_DEPLOYMENT.md); no one-command Docker deployment is claimed.

## 4. Start the real product

Backend, from repository root with the virtual environment active:

```bash
PYTHONPATH=. uvicorn apps.api.main:app --host 127.0.0.1 --port 8010
```

In another terminal:

```bash
cd <repository-directory>/apps/web
npm exec vite -- --host 127.0.0.1 --port 4173 --strictPort
```

Health check: `curl http://127.0.0.1:8010/health` → `{"status":"ok"}`.
Open [the local product](http://127.0.0.1:4173). Use 127.0.0.1 rather than localhost to match the current CORS policy.

## 5. Evaluate a real research workflow

1. Open Research Object and create a company object (e.g. NVIDIA / NVDA) with accurate identity fields.
2. Start new research, select the object and define the goal/as-of date.
3. Generate a Scheme. This is a real paid model operation.
4. Review and confirm the exact Scheme. Confirmation admits a real Run and starts execution; it can invoke graph planning and live data/models.
5. Follow AI Research, correction/replanning and any bounded recovery evidence.
6. If RELEASED, inspect A Report, B Financial Review and C Execution. Follow only available exact source links.
7. Inspect Research Object → Current Research View / Memories. A subsequent incremental study uses the prior released knowledge base; compare the resulting views.

Failure is a real result, not a reason to bypass gates. Fresh databases do not inherit the screenshot Run, Memory v2, provider capability evidence or authorization. Complete the first released study before expecting incremental memory. Do not invent historical certification to force a fallback route.

## Facilitated read-only Alpha

For a separately supplied, existing accepted database and matching artifact files, use `scripts.readonly_product_server:app` instead of the writable launcher. Set `VFAS_ACCEPTANCE_ENV_FILE` to your private configuration file. This disables scheduler, outbound HTTP and mutation endpoints. It cannot create research, and an empty clone does not acquire existing research by using it.

Commercial billing, credits and subscriptions are not part of Local Deployable Alpha. Read [license status](../LEGAL_AND_LICENSE_STATUS.md) before reuse.
