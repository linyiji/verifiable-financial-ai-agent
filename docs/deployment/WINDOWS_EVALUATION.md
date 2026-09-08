# Windows evaluator installation

The default path is PowerShell → guided installer → Docker Desktop → VFA.

From the supplied unpacked installer source package:

```powershell
& .\scripts\install-evaluator.ps1
```

Follow Docker Desktop installation/restart prompts if needed. No manual WSL distribution, Python, Node or PostgreSQL setup is required. Put the encrypted `.vfaeval` in Downloads and enter its passphrase when prompted. The first successful installation starts the product and opens the default browser.

In a new terminal, relaunch with `vfa start`. [Full guided instructions and troubleshooting](INSTALL_EVALUATOR.md).

The source implementation and portable tests are available; public URL remains **PUBLICATION_REQUIRED**, Windows clean-machine execution is **NOT_OBSERVED**, and real Owner gateway deployment remains **NOT_DEPLOYED**.

Native/WSL2 developer and full-proof deployment remain under [Advanced Installation](ADVANCED_INSTALLATION.md). The default installer does not claim native proof parity.
