# One-command installer foundation acceptance

[简体中文](EVALUATOR_INSTALLER_ACCEPTANCE.zh-CN.md)

> Current guidance clarification — 2026-09-08: the checks below validate the gateway-only installer foundation, not a completed clean-machine or real-gateway evaluation. NOT_OBSERVED means not performed, not an observed failure. Investors/testers should currently use direct-API BYOK with locally configured private credentials; this installer does not currently provide one-command BYOK. The host-validation next step below applies to the installer workstream, not a requirement to wait for the gateway before facilitated BYOK testing.

Date: 2026-09-08. Scope: local delivery changes only; no publication, gateway deployment,
paid provider calls or production research Runs.

## Observed checks

- Installer portable contracts: 50 passed.
- Combined installer, evaluator gateway, BYOK/provider routing, read-only projections,
  API/memory and adaptive recovery regressions: 207 passed.
- Frontend read-only navigation and object workspace contracts: 32 checks passed.
- TypeScript typecheck and Vite build: passed; existing 500 kB chunk warning remains.
- Installer Ruff checks and Bash syntax: passed.
- Local Docker image build, API/installer imports, migration graph and built frontend
  asset presence: passed. Container Docker Compose executable: passed.
- Documentation links and changed-file secret/private-path scan: passed.

Tests use isolated fixtures/mocked service operations. No Owner database was mounted.
Docker image preparation is not a clean-machine install or real-gateway journey.
Windows source assertions do not substitute for native PowerShell execution.

## Explicit pending gates

WINDOWS_REAL_HOST_E2E = NOT_OBSERVED

MACOS_REAL_HOST_E2E = NOT_OBSERVED

PUBLIC_INSTALLER_URL = PUBLICATION_REQUIRED

REAL_OWNER_GATEWAY_DEPLOYED = NO

REAL_ZERO_CONFIG_LIVE_EVALUATION = NO

Standard mode is limited; full-proof container packaging is unavailable. Existing
proof, capability certification and research release authority are unchanged.

Next exact action: ONE_COMMAND_INSTALLER_HOST_VALIDATION. Use a clean Windows host
and a fresh macOS account, exercise explicit Docker installation consent/reboot,
Unicode paths, first startup, repeated startup, stop/update and browser behavior.
A deployed test gateway or isolated fake gateway acceptance harness is required
before claiming end-to-end readiness; do not substitute paid provider probes.

See the [design contract](../deployment/EVALUATOR_INSTALLER_DESIGN.md) and
[guided installation](../deployment/INSTALL_EVALUATOR.md).
