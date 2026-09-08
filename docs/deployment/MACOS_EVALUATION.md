# macOS evaluator setup

Install Python 3.11, Node.js 24, PostgreSQL 16-compatible server and Git using trusted distributions. Provision an evaluator-owned database. Docker is needed for generated capability validation; full required-proof Runs need Rust and [RISC Zero SDK 3.0.6](../../zk/revenue_growth/README.md). Gateway credentials do not install local dependencies.

In Terminal, substitute the Owner-supplied clone URL/directory:

```bash
git clone <repository-clone-url>
cd <repository-directory>
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,postgres]'
cp .env.example .env.local
cd apps/web
npm ci
cd ../..
```

Edit `.env.local`: configure DATABASE_URL, keep `VFA_CREDENTIAL_MODE=evaluator`, leave upstream keys empty. Optional gateway URL must match the bundle. Never copy tokens into config. Confirm the new database before migration:

```bash
python scripts/postgresql_migrate.py
./zk/revenue_growth/build-host.sh
python scripts/evaluator_start.py --bundle "$HOME/Downloads/evaluation.vfaeval"
```

The proof build requires its installed toolchain; do not skip it for required-proof Runs. The launcher prompts without echo, checks authority without upstream calls and starts the backend. Quoted paths support spaces/Unicode. No Keychain setup is needed: optional integration is **NOT_IMPLEMENTED**. The token is session-only, not unextractable from privileged memory inspection.

In another Terminal, enter the clone's `apps/web` directory:

```bash
npm exec vite -- --host 127.0.0.1 --port 4173 --strictPort
```

Open [127.0.0.1:4173](http://127.0.0.1:4173) and follow the [research journey](EVALUATOR_QUICKSTART.md). The gateway must first be deployed by the Owner; this task validated fake-upstream transport, not new paid research or fresh proof-toolchain installation.
