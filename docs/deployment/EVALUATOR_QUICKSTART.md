# Evaluate Verifiable Financial Agent

[简体中文](EVALUATOR_QUICKSTART.zh-CN.md)

Current investors and testers: start with [direct-provider BYOK](LOCAL_DEPLOYMENT.md) and [native setup](ADVANCED_INSTALLATION.md). API integrations are built in, but API keys are not embedded. Bring your own keys or receive separately scoped, revocable test keys privately from the Owner. This avoids dependence on the undeployed gateway; it does not waive provider entitlements or proof/release gates.

The [Guided Installation](INSTALL_EVALUATOR.md) now supports an encrypted direct-provider bundle separately from gateway mode. Privately receive `VFA-Investor-Access.vfacred`, copy it to `<unpacked-repository>/credentials/active.vfacred`, then run the platform installer. After installation, run `vfa start` and enter the hidden `Credential passphrase:`. No individual provider key entry or gateway is required for this mode. See [exact scope and precedence](../../credentials/README.md). Use `vfa stop`, `vfa status`, `vfa doctor` and `vfa open` for everyday operation.

Public installer URL: **PUBLICATION_REQUIRED**. Real Owner gateway: **NOT_DEPLOYED**. Until those operational prerequisites exist, use the source package for installer validation; do not assume gateway-mode Owner-funded research is available. Independently configured BYOK remains separate.

The guided container packages the locked RISC Zero 3.0.6 proof runtime and a private governed generated-capability sandbox broker while retaining every proof/release gate. The API receives neither the raw Docker socket nor provider secrets in child sandboxes. Gateway-mode evaluators need no upstream provider keys locally; direct encrypted credentials and native BYOK remain separate supported modes.

[Windows](WINDOWS_EVALUATION.md) · [macOS](MACOS_EVALUATION.md) · [Credential security](../architecture/EVALUATOR_CREDENTIAL_SECURITY.md).
