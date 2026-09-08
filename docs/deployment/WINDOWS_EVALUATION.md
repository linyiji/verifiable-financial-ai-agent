# Windows evaluation: WSL2 recommended, native foundation available

Full required-proof evaluation is recommended through **WSL2** because the runtime includes Linux-oriented shell scripts, Docker and proof tooling. Native-Windows RISC Zero parity is **not claimed**. This task tested portable Python bundle/session logic on macOS, including Windows path syntax, not execution on Windows or WSL2 hosts.

## A. WSL2 — recommended full workflow

In Administrator PowerShell on supported Windows, install WSL and restart when prompted:

```powershell
wsl --install
wsl --list --verbose
wsl
```

Complete Linux account setup and verify version 2 in the listing. See Microsoft's [installation guide](https://learn.microsoft.com/en-us/windows/wsl/install) and [command reference](https://learn.microsoft.com/en-us/windows/wsl/basic-commands) for prerequisites, distributions and upgrading existing WSL1.

Inside Linux, install Git, Python 3.11 with venv, Node.js 24 and PostgreSQL 16-compatible environment using trusted distributions. Configure Docker access in WSL2; install Rust/RISC Zero per the [proof workspace](../../zk/revenue_growth/README.md). Keep the clone in the Linux filesystem.

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

Provision your database and edit `.env.local`: reachable DATABASE_URL, `VFA_CREDENTIAL_MODE=evaluator`, no upstream keys. Put the private encrypted bundle in a private Linux directory or use a quoted `/mnt/c/Users/.../evaluation.vfaeval` path. Keep its password separate.

```bash
python scripts/postgresql_migrate.py
./zk/revenue_growth/build-host.sh
python scripts/evaluator_start.py --bundle "/path/with spaces/evaluation.vfaeval"
```

Use the hidden prompt. No WSL keychain integration is required or claimed. The token remains in the Python session, not dotenv. In a second WSL terminal, from `apps/web`:

```bash
npm exec vite -- --host 127.0.0.1 --port 4173 --strictPort
```

Open [the product](http://127.0.0.1:4173) through WSL localhost access. If blocked, diagnose WSL forwarding/firewall; do not expose the Alpha publicly as a workaround.

## B. Native Windows — launcher / product foundation

Install Git, Python 3.11, Node.js 24 and PostgreSQL 16-compatible server; provision your database. In PowerShell:

```powershell
git clone <repository-clone-url>
Set-Location <repository-directory>
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,postgres]"
Copy-Item .env.example .env.local
Set-Location apps/web
npm ci
Set-Location ../..
```

If activation is blocked, use `.\.venv\Scripts\python.exe` instead of `python`; do not weaken machine-wide policy. Edit `.env.local` with PostgreSQL URL and `VFA_CREDENTIAL_MODE=evaluator`; leave provider keys empty.

```powershell
python scripts/postgresql_migrate.py
python scripts/evaluator_start.py --bundle "$env:USERPROFILE\Downloads\evaluation.vfaeval"
```

The interactive launcher starts the backend after readiness. Optional Windows Credential Manager persistence is **NOT_IMPLEMENTED**. In another PowerShell window from `apps/web`:

```powershell
npm exec vite -- --host 127.0.0.1 --port 4173 --strictPort
```

Open [127.0.0.1:4173](http://127.0.0.1:4173). This is not native full-proof certification: use WSL2. No fake proof flags or release bypasses. All paths need an Owner-deployed gateway and private bundle; see [Quickstart](EVALUATOR_QUICKSTART.md).
