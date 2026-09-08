# Evaluate Verifiable Financial Agent

[简体中文](EVALUATOR_QUICKSTART.zh-CN.md)

Current investors and testers: start with [direct-provider BYOK](LOCAL_DEPLOYMENT.md) and [native setup](ADVANCED_INSTALLATION.md). API integrations are built in, but API keys are not embedded. Bring your own keys or receive separately scoped, revocable test keys privately from the Owner. This avoids dependence on the undeployed gateway; it does not waive provider entitlements or proof/release gates.

The separate [Guided Installation](INSTALL_EVALUATOR.md) prepares Docker services in gateway mode only, not turnkey BYOK. After that installation, open a new terminal and run `vfa start`. Use `vfa stop`, `vfa status`, `vfa doctor`, `vfa update` and `vfa open` for everyday operation of that installer.

Public installer URL: **PUBLICATION_REQUIRED**. Real Owner gateway: **NOT_DEPLOYED**. Until those operational prerequisites exist, use the source package for installer validation; do not assume gateway-mode Owner-funded research is available. Independently configured BYOK remains separate.

Standard container delivery retains every proof/release gate and has limited workflows; full proof tooling is not packaged. Full required-proof/generated-capability execution uses [Advanced Installation](ADVANCED_INSTALLATION.md). Gateway-mode evaluators need no upstream provider keys locally; current BYOK testers configure their private keys on the local backend, never in the frontend.

[Windows](WINDOWS_EVALUATION.md) · [macOS](MACOS_EVALUATION.md) · [Credential security](../architecture/EVALUATOR_CREDENTIAL_SECURITY.md).
