# Guided evaluator installation

[简体中文](INSTALL_EVALUATOR.zh-CN.md)

## 1. Thirty-second overview

This installer supports encrypted direct credentials (`.vfacred`) separately from `.vfaeval` gateway mode. Direct mode needs neither individual provider key entry nor an Owner gateway. The Docker runtime includes the locked RISC Zero 3.0.6 proof host and a governed generated-capability sandbox broker; [native BYOK installation](ADVANCED_INSTALLATION.md) remains available for developers.

Privately receive `VFA-Investor-Access.vfacred`, copy it to `credentials/active.vfacred` within the unpacked repository, then run the platform command below. The installer prepares the local database, migrations, backend and frontend. Direct readiness validates configuration only, without paid calls.

**Delivery status:** use an accepted GitHub release archive and its evaluator manifest. The installer verifies the package SHA-256 and binds services to the immutable image digest and exact source revision. It never follows a mutable `develop` image or silently falls back to a cached `vfa-evaluator:source` image.

**Gateway status:** the real Owner gateway is **NOT_DEPLOYED**. Software installation can be prepared; gateway-mode Owner-funded live research remains **BLOCKED_BY_GATEWAY_DEPLOYMENT**. This does not block separately configured BYOK test keys. A valid bundle must reference a separately deployed gateway.

## 2. Windows

From the unpacked source package in PowerShell:

```powershell
& .\scripts\install-evaluator.ps1
```

If Docker Desktop is missing, the installer asks before using Windows Package Manager to install it. Complete Docker's setup prompts. If a restart is required, restart once and run the same command again. If Docker is installed but stopped, start it and rerun. The normal evaluator path stays in PowerShell; no manual WSL distribution or Ubuntu setup is required.

The per-user installation lives in LocalAppData → Verifiable Financial Agent, protected by a current-user ACL. If corporate PowerShell policy blocks scripts, use your approved IT process; the installer does not change machine execution policy.

## 3. macOS

From the unpacked source package in Terminal:

```bash
bash scripts/install-evaluator.sh
```

The installer detects Docker Desktop. If absent, it offers the official installation guide. Complete Docker installation and rerun the same command. It never performs silent privileged installation. Application state is in Library → Application Support → Verifiable Financial Agent under your user account.

First-time image preparation downloads dependencies and can take several minutes. Private build details are retained under the installation's logs directory. The package's runtime images are pinned by digest. You do not install Python, Node or PostgreSQL manually.

## 4. Where to place the credential

Direct credentials have one fixed location: `<unpacked-repository>/credentials/active.vfacred` (Windows: `<unpacked-repository>\credentials\active.vfacred`). Rename the privately received `VFA-Investor-Access.vfacred` when copying. The installer records the selected product path as non-secret metadata and mounts its credential directory read-only. Keep the unpacked directory; rerun the platform installer from a new release when changing versions.

The fixed direct bundle takes precedence; conflicting explicit paths fail. Invalid direct credentials never fall back. Without a direct bundle, legacy `.vfaeval` discovery in Downloads/Desktop remains available. Direct bundles are never searched recursively. Native BYOK stays separate and is never merged into direct mode.

Enter the passphrase at the hidden `Credential passphrase:` prompt. It is not a command argument or persisted setting. Direct provider keys are decrypted only in process memory and private socket handoff; gateway bundles still provide gateway authorization only. See [credential scope and security boundaries](../../credentials/README.md).

## 5. First startup

Installation automatically prepares the database, applies migrations, checks permission, starts backend and frontend, waits for their health, then opens [VFA](http://127.0.0.1:4173). It requires ports 4173 and 8010; competing applications cause an actionable error instead of being stopped. The database is not published on a host port.

Readiness uses zero paid provider/data calls and shows route permission, not provider health certification. Restricted/expired/revoked credentials or exhausted quotas do not bypass authorization.

**Runtime assurance:** the product image contains the verified Linux/amd64 RISC Zero host, locked r0vm 3.0.6 and the bound guest method. Proof execution requires no runtime network. Generated capabilities run through a private Unix-socket broker into disposable, network-disabled, read-only, resource-bounded containers. Only the broker receives Docker daemon authority; the API and child containers do not. Proof/review/release gates remain unchanged. A fresh installation contains no Owner research history.

## 6. Subsequent startup

Open a new terminal after the first installation so the per-user PATH is loaded:

```text
vfa start
```

Unlock the bundle when prompted. Services restart and the browser opens after health checks. Use `vfa start --no-open` to suppress opening. `vfa open` reopens the healthy product.

## 7. Update

```text
vfa update
```

Updates resolve the latest stable accepted GitHub release with an evaluator manifest, verify SHA-256, build the selected runtime, apply migrations and restart. Technical evaluators may use `vfa update --version <accepted-release-tag>`; explicit prerelease selection is allowed. It never follows develop. Until installer assets are published, update returns `PUBLICATION_REQUIRED`. Failed migration preserves data and returns an error; it does not attempt destructive rollback. Back up your Docker research volume and matching artifacts before upgrading.

## 8. Stop

```text
vfa stop
```

Only this installation's services stop. Research storage and volumes remain. No reset/delete-data command is supplied.

## 9. Status and diagnosis

```text
vfa status
vfa doctor
```

Status reports local service state. Doctor checks Docker, installed version, exact expected/running API and Broker revision/digest, database, backend, frontend, packaged Proof Runtime, governed Sandbox Runtime and zero-cost credential readiness. Identity mismatch fails closed with `STALE_RUNTIME_IMAGE`; unresolved identity fails with `RUNTIME_IMAGE_IDENTITY_NOT_RESOLVED`. It does not make paid FMP/MiMo/TeamoRouter calls. Normal errors show an owned code and next action; no stack traces or raw service logs are printed.

## 10. Troubleshooting

| Code | Next action |
| --- | --- |
| DOCKER_NOT_INSTALLED / DOCKER_NOT_RUNNING | Install/start Docker Desktop and rerun the same command. |
| REBOOT_REQUIRED | Restart Windows once and rerun the original installer. |
| PUBLICATION_REQUIRED | Ask the Owner for an accepted release containing the evaluator manifest and package. |
| STALE_RUNTIME_IMAGE / RUNTIME_IMAGE_IDENTITY_NOT_RESOLVED | Reinstall from one accepted release; do not admit research on a mutable or mismatched image. |
| DOWNLOAD_FAILED / INTEGRITY_FAILED | Check GitHub connectivity; for checksum failure contact the Owner and do not execute the package. |
| PORT_4173_IN_USE / PORT_8010_IN_USE | Close the competing application yourself, then run vfa start. |
| DATABASE_START_FAILED / MIGRATION_FAILED | Run vfa doctor; check Docker storage. Data is retained. |
| NO_EVALUATOR_CREDENTIAL / INVALID_EVALUATOR_CREDENTIAL | Put the issued file in Downloads; check the passphrase; run vfa start. |
| GATEWAY_NOT_DEPLOYED / GATEWAY_UNREACHABLE | Ask the Owner to deploy/check the gateway; run vfa start once available. |
| CREDENTIAL_EXPIRED / CREDENTIAL_REVOKED / QUOTA_EXHAUSTED | Ask the Owner to resolve authorization; run vfa start. |
| HEALTH_TIMEOUT | Run vfa doctor. Do not disable financial/release gates. |
| PROOF_RUNTIME_NOT_READY / SANDBOX_RUNTIME_NOT_READY | Re-run `vfa start`; if the locked runtime still fails, stop and report the code. |

Installer metadata contains only stage, version, image and safe credential filename. Local DB passwords live in a separate protected runtime file. The CLI container needs Docker control to manage services; it is trusted installation software. Research API containers receive no Docker control socket. No evaluator token is written to disk; it is transferred through stdin and a container-local Unix socket. Privileged local users can inspect in-memory credentials.

## 11. Advanced installation

[Advanced / BYOK](ADVANCED_INSTALLATION.md) · [Owner Gateway](EVALUATOR_GATEWAY.md) · [Installer design](EVALUATOR_INSTALLER_DESIGN.md).

The 2026-09-09 snapshot includes accepted macOS/Docker local install, doctor and one isolated NVDA Live. Windows clean-machine E2E remains a separate unverified gate.

## Independent financial branches and default object

Independent financial analyses run concurrently; a data-shortfall limitation does not block findings without that dependency. The financial extension bounds concurrency at three branches; not every Agent Task is fully parallel. Each validated calculation is persisted independently. Missing inputs produce INSUFFICIENT_DATA, no number and no dependent claim; genuine execution errors still fail. A Task may complete with structured limitations.

Technical branches in the general preset are SUPPORTING; canonical capability IDs explicitly listed in Scheme.calculation_requirements are REQUIRED. Existing full-formula Financial Review / Proof / Release controls remain unchanged: task continuation does not authorize release, and missing formulas can still block Release. Task details show branch status and available/required input counts. This change has not yet earned new-version host publication acceptance; Alpha 2 must not be described as published.

After PostgreSQL migration, product API startup idempotently creates an empty NVIDIA / NVDA Research Object, preserving any existing object with that ticker. No Run, Scheme, evidence, report or Research Memory is seeded and no provider is called. BYOK / Owner gateway credential and deployment boundaries are unchanged.
