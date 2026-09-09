# Advanced / developer installation

[简体中文](ADVANCED_INSTALLATION.zh-CN.md)

This page describes native direct-provider BYOK for developers. API integrations are built in; API keys are not embedded. Investors may instead use the Docker [Guided Installation](INSTALL_EVALUATOR.md) with a privately supplied encrypted `.vfacred` bundle. Its packaged Proof and governed Sandbox runtimes do not depend on the optional, currently undeployed Owner gateway.

Use Python 3.11, Node.js 24 and PostgreSQL 16-compatible storage. Full required-proof research needs Rust/RISC Zero SDK 3.0.6; generated-capability validation needs Docker. Follow the [proof workspace](../../zk/revenue_growth/README.md), build its accepted host and retain existing proof gates. Do not set development/fake-proof flags.

## macOS / Linux shell

From your source checkout:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,postgres]'
cp .env.example .env.local
cd apps/web
npm ci
cd ../..
```

Provision your own PostgreSQL database and set DATABASE_URL in ignored `.env.local`. For BYOK, explicitly set `VFA_CREDENTIAL_MODE=byok` and privately supply your own FMP, TeamoRouter and MiMo credentials. See [complete BYOK configuration](LOCAL_DEPLOYMENT.md). For native evaluator mode, keep provider keys empty, set `VFA_CREDENTIAL_MODE=evaluator`, and receive the Owner-issued encrypted bundle.

```bash
python scripts/postgresql_migrate.py
./zk/revenue_growth/build-host.sh
# BYOK backend, with VFA_CREDENTIAL_MODE=byok:
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8010
```

Optional native gateway mode uses this alternative instead, only after gateway deployment
and after setting VFA_CREDENTIAL_MODE=evaluator:

```bash
python scripts/evaluator_start.py --bundle "/path/to/evaluation.vfaeval"
```

In another terminal, from apps/web:

```bash
npm exec vite -- --host 127.0.0.1 --port 4173 --strictPort
```

## Advanced Windows native / WSL2

For native Windows, use `py -3.11 -m venv .venv`, activate `.\.venv\Scripts\Activate.ps1` (or invoke its python.exe directly), use `Copy-Item .env.example .env.local`, and otherwise follow the same Python/npm and PostgreSQL setup. The native session launcher accepts quoted Windows bundle paths.

Full proof evaluation is recommended through WSL2. In Administrator PowerShell, `wsl --install`, restart as needed, verify `wsl --list --verbose`, then enter `wsl`. Inside your distribution, install the versions above and follow the Linux commands. Docker Desktop integration supplies Docker access; proof tooling is still required. See Microsoft's [WSL installation reference](https://learn.microsoft.com/en-us/windows/wsl/install). Native Windows full-proof parity is not claimed.

No Owner database or historical research is included. Gateway readiness checks permission, not provider capability/health. New research may incur provider costs; failure is a real outcome and cannot bypass release gates.
