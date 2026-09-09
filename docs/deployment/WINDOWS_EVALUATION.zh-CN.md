# Windows 评估安装

[English](WINDOWS_EVALUATION.md)

安装器支持加密直连凭据 `.vfacred`，并保留独立 `.vfaeval` 网关模式。私下取得 `VFA-Investor-Access.vfacred`，复制为 `<解压仓库>/credentials/active.vfacred`（Windows 使用反斜杠路径），再执行下述安装命令。直连模式不依赖 Owner 网关。标准镜像的完整证明工具链仍待验收；完整研究暂用[原生安装](ADVANCED_INSTALLATION.zh-CN.md)。详见[凭据说明](../../credentials/README.zh-CN.md)。

在解压后的安装器源码包中执行：

```powershell
& .\scripts\install-evaluator.ps1
```

如有需要，请遵循 Docker Desktop 安装 / 重启提示。无需手动配置 WSL 发行版、Python、Node 或 PostgreSQL。在隐藏的 `Credential passphrase:` 提示中输入直连包口令。旧网关模式仍可将 `.vfaeval` 放入 Downloads。首次安装成功后会启动产品并打开默认浏览器。

另开终端，用 `vfa start` 再次启动。[完整引导步骤与故障排查](INSTALL_EVALUATOR.zh-CN.md)。

源码实现与可移植测试已具备；公开 URL 仍为 **PUBLICATION_REQUIRED**，Windows 全新环境运行状态为 **NOT_OBSERVED**，真实 Owner 网关部署仍为 **NOT_DEPLOYED**。

原生 / WSL2 开发者及完整证明部署请参阅[高级安装](ADVANCED_INSTALLATION.zh-CN.md)。默认安装器不宣称原生证明能力的等价支持。
