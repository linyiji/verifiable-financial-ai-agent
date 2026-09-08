# macOS evaluator installation

[简体中文](MACOS_EVALUATION.zh-CN.md)

Current investors and testers should use [direct-provider BYOK](LOCAL_DEPLOYMENT.md) and [native setup](ADVANCED_INSTALLATION.md). API integrations are built in, not API keys: bring your own keys or receive separately scoped, revocable test keys privately from the Owner. The following Terminal → guided installer → Docker Desktop → VFA path is gateway-only, not turnkey BYOK; its standard image does not package full proof tooling.

From the supplied unpacked installer source package:

```bash
bash scripts/install-evaluator.sh
```

Follow Docker Desktop guidance if it is missing or stopped. No manual Python, Node or PostgreSQL setup is required. Put the encrypted `.vfaeval` in Downloads and enter its passphrase when prompted. A successful first installation starts services and opens the default browser.

In a new terminal, relaunch with `vfa start`. [Guided instructions and troubleshooting](INSTALL_EVALUATOR.md).

Public installer URL remains **PUBLICATION_REQUIRED** and the real Owner gateway is **NOT_DEPLOYED**. Source/portable tests and any Docker build checks are distinct from a clean-machine macOS E2E test, which is not claimed.

Native developer/BYOK/full-proof deployment remains under [Advanced Installation](ADVANCED_INSTALLATION.md).
