# Windows evaluator installation

[简体中文](WINDOWS_EVALUATION.zh-CN.md)

The installer supports encrypted direct credentials (`.vfacred`) separately from `.vfaeval` gateway mode. Privately receive `VFA-Investor-Access.vfacred` and copy it to `<unpacked-repository>/credentials/active.vfacred` (backslashes on Windows) before installation. Direct mode does not require an Owner gateway. The installer builds the packaged Linux/amd64 Proof and governed Sandbox runtime under Docker Desktop; native Windows live-Proof parity is not claimed. See [credential instructions](../../credentials/README.md).

From the supplied unpacked installer source package:

```powershell
& .\scripts\install-evaluator.ps1
```

Follow Docker Desktop installation/restart prompts if needed. No manual WSL distribution, Python, Node or PostgreSQL setup is required. Enter the direct bundle passphrase at the hidden `Credential passphrase:` prompt. Legacy gateway users may instead put `.vfaeval` in Downloads. The first successful installation starts the product and opens the default browser.

In a new terminal, relaunch with `vfa start`. [Full guided instructions and troubleshooting](INSTALL_EVALUATOR.md).

The source implementation and portable tests are available; public URL remains **PUBLICATION_REQUIRED**, Windows clean-machine execution is **NOT_OBSERVED**, and real Owner gateway deployment remains **NOT_DEPLOYED**.

Native/WSL2 developer deployment remains under [Advanced Installation](ADVANCED_INSTALLATION.md). The default installer does not claim native Windows proof parity.
