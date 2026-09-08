# Guided evaluator installation

[简体中文](INSTALL_EVALUATOR.zh-CN.md)

## 1. Thirty-second overview

**Current investor/tester recommendation:** use [direct-provider BYOK](LOCAL_DEPLOYMENT.md) with [native setup](ADVANCED_INSTALLATION.md). API integrations are built in, not API keys. Bring your own keys or receive separately scoped, revocable test keys privately from the Owner. This page describes the gateway-only Docker installer foundation, not a turnkey BYOK installer.

Receive the installer source package and one encrypted `.vfaeval` bundle privately from the Owner. Unpack the source package, run the platform command below, and follow the prompts. Docker Desktop provides the local runtime; no separate database or language tools are needed. The installer creates local storage, migrates its own database, checks gateway permission and starts the real product. A successful first install opens your default browser.

**Delivery status:** installer source foundation; public installer URL **PUBLICATION_REQUIRED**. Publishing repository source is not the same as publishing accepted installer-specific assets and bootstrap URLs. Do not substitute a mutable develop URL into a download-and-execute command. Published installers will resolve an accepted GitHub release and verify its SHA-256 package before executing it.

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

Place the encrypted file in Downloads or Desktop. Exactly one candidate is selected automatically; multiple candidates display filenames for selection. With none present, place it in Downloads and press Enter, or enter a path. Inside the installer, these directories appear as `/credentials/downloads` and `/credentials/desktop`; use one of these paths if selecting a file manually. Other directories are not automatically searched or mounted.

Enter the passphrase at the hidden terminal prompt. It is never a command argument, environment variable or saved setting. Provider keys remain on the Owner gateway. Do not place the passphrase beside the bundle. Reopening a session requires unlocking the bundle again.

## 5. First startup

Installation automatically prepares the database, applies migrations, checks permission, starts backend and frontend, waits for their health, then opens [VFA](http://127.0.0.1:4173). It requires ports 4173 and 8010; competing applications cause an actionable error instead of being stopped. The database is not published on a host port.

Readiness uses zero paid provider/data calls and shows route permission, not provider health certification. Restricted/expired/revoked credentials or exhausted quotas do not bypass authorization.

**Standard mode limits:** the container uses the real product with unchanged proof/release policy. It does not package a certified RISC Zero host or expose Docker's control socket to research Agents. Browsing and supported limited workflows are available; tasks requiring proof or generated-capability validation cannot legitimately release through this standard image. No existing proof is fabricated and no gate is disabled. `vfa start --full-proof` currently returns `FULL_PROOF_UNAVAILABLE`; use [Advanced Installation](ADVANCED_INSTALLATION.md) for release-gated full research until an accepted full-proof image is delivered. A fresh installation contains no Owner research history.

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

Status reports local service state. Doctor checks Docker, installed version, service state and (when you unlock a bundle) the same zero-cost gateway readiness. It does not test FMP/MiMo/TeamoRouter. Normal errors show an owned code and next action; no stack traces or raw service logs are printed.

## 10. Troubleshooting

| Code | Next action |
| --- | --- |
| DOCKER_NOT_INSTALLED / DOCKER_NOT_RUNNING | Install/start Docker Desktop and rerun the same command. |
| REBOOT_REQUIRED | Restart Windows once and rerun the original installer. |
| PUBLICATION_REQUIRED | Ask the Owner for the reviewed source package or published installer release. |
| DOWNLOAD_FAILED / INTEGRITY_FAILED | Check GitHub connectivity; for checksum failure contact the Owner and do not execute the package. |
| PORT_4173_IN_USE / PORT_8010_IN_USE | Close the competing application yourself, then run vfa start. |
| DATABASE_START_FAILED / MIGRATION_FAILED | Run vfa doctor; check Docker storage. Data is retained. |
| NO_EVALUATOR_CREDENTIAL / INVALID_EVALUATOR_CREDENTIAL | Put the issued file in Downloads; check the passphrase; run vfa start. |
| GATEWAY_NOT_DEPLOYED / GATEWAY_UNREACHABLE | Ask the Owner to deploy/check the gateway; run vfa start once available. |
| CREDENTIAL_EXPIRED / CREDENTIAL_REVOKED / QUOTA_EXHAUSTED | Ask the Owner to resolve authorization; run vfa start. |
| HEALTH_TIMEOUT | Run vfa doctor. Do not disable financial/release gates. |
| FULL_PROOF_UNAVAILABLE | Use advanced full technical deployment. |

Installer metadata contains only stage, version, image and safe credential filename. Local DB passwords live in a separate protected runtime file. The CLI container needs Docker control to manage services; it is trusted installation software. Research API containers receive no Docker control socket. No evaluator token is written to disk; it is transferred through stdin and a container-local Unix socket. Privileged local users can inspect in-memory credentials.

## 11. Advanced installation

[Advanced / BYOK](ADVANCED_INSTALLATION.md) · [Owner Gateway](EVALUATOR_GATEWAY.md) · [Installer design](EVALUATOR_INSTALLER_DESIGN.md).

Platform source/portable tests do not certify Windows or macOS clean-machine E2E. Actual host validation and installer asset publication remain separate gates.
