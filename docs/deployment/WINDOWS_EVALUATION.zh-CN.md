# Windows 评估安装

[English](WINDOWS_EVALUATION.md)

现阶段建议投资者和测试员采用[直连供应商 BYOK](LOCAL_DEPLOYMENT.zh-CN.md)及[原生环境安装](ADVANCED_INSTALLATION.zh-CN.md)。产品内置 API 集成，而不是 API 密钥：使用自己的密钥，或由 Owner 私下提供独立限定权限、可撤销的测试密钥。以下“PowerShell → 引导安装器 → Docker Desktop → VFA”路径仅支持网关模式，不是开箱即用的 BYOK；标准镜像未打包完整证明工具链。

在解压后的安装器源码包中执行：

```powershell
& .\scripts\install-evaluator.ps1
```

如有需要，请遵循 Docker Desktop 安装 / 重启提示。无需手动配置 WSL 发行版、Python、Node 或 PostgreSQL。将加密 `.vfaeval` 放入 Downloads，并按提示输入口令。首次安装成功后会启动产品并打开默认浏览器。

另开终端，用 `vfa start` 再次启动。[完整引导步骤与故障排查](INSTALL_EVALUATOR.zh-CN.md)。

源码实现与可移植测试已具备；公开 URL 仍为 **PUBLICATION_REQUIRED**，Windows 全新环境运行状态为 **NOT_OBSERVED**，真实 Owner 网关部署仍为 **NOT_DEPLOYED**。

原生 / WSL2 开发者及完整证明部署请参阅[高级安装](ADVANCED_INSTALLATION.zh-CN.md)。默认安装器不宣称原生证明能力的等价支持。
