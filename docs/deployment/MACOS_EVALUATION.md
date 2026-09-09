# macOS evaluator installation

[简体中文](MACOS_EVALUATION.zh-CN.md)

The installer supports encrypted direct credentials (`.vfacred`) separately from `.vfaeval` gateway mode. Privately receive `VFA-Investor-Access.vfacred` and copy it to `<unpacked-repository>/credentials/active.vfacred` before installation. Direct mode does not require an Owner gateway. The Docker image packages the verified Linux/amd64 Proof Runtime and governed Sandbox Runtime. See [credential instructions](../../credentials/README.md).

From the supplied unpacked installer source package:

```bash
bash scripts/install-evaluator.sh
```

Follow Docker Desktop guidance if it is missing or stopped. No manual Python, Node or PostgreSQL setup is required. Enter the direct bundle passphrase at the hidden `Credential passphrase:` prompt. Legacy gateway users may instead put `.vfaeval` in Downloads. A successful first installation starts services and opens the default browser.

In a new terminal, relaunch with `vfa start`. [Guided instructions and troubleshooting](INSTALL_EVALUATOR.md).

Public installer URL remains **PUBLICATION_REQUIRED** and the real Owner gateway is **NOT_DEPLOYED**. Source/portable tests and any Docker build checks are distinct from a clean-machine macOS E2E test, which is not claimed.

Native developer/BYOK deployment remains under [Advanced Installation](ADVANCED_INSTALLATION.md).
