# macOS 评估安装

[English](MACOS_EVALUATION.md)

安装器支持加密直连凭据 `.vfacred`，并保留独立 `.vfaeval` 网关模式。私下取得 `VFA-Investor-Access.vfacred`，复制为 `<解压仓库>/credentials/active.vfacred`，再执行下述安装命令。直连模式不依赖 Owner 网关。Docker 镜像已打包验证过的 Linux/amd64 Proof Runtime 与受治理 Sandbox Runtime。详见[凭据说明](../../credentials/README.zh-CN.md)。

在解压后的安装器源码包中执行：

```bash
bash scripts/install-evaluator.sh
```

如果 Docker Desktop 缺失或未运行，请遵循相应提示。无需手动配置 Python、Node 或 PostgreSQL。在隐藏的 `Credential passphrase:` 提示中输入直连包口令。旧网关模式仍可将 `.vfaeval` 放入 Downloads。首次安装成功后会启动服务并打开默认浏览器。

另开终端，用 `vfa start` 再次启动。[引导步骤与故障排查](INSTALL_EVALUATOR.zh-CN.md)。

公开安装器 URL 仍为 **PUBLICATION_REQUIRED**，真实 Owner 网关为 **NOT_DEPLOYED**。源码 / 可移植测试及任何 Docker 构建检查，都不等同于全新 macOS 环境的 E2E 测试；此处不作该声明。

原生开发者 / BYOK / 完整证明部署请参阅[高级安装](ADVANCED_INSTALLATION.zh-CN.md)。
