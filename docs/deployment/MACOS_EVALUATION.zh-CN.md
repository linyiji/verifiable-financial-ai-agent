# macOS 评估安装

[English](MACOS_EVALUATION.md)

现阶段建议投资者和测试员采用[直连供应商 BYOK](LOCAL_DEPLOYMENT.zh-CN.md)及[原生环境安装](ADVANCED_INSTALLATION.zh-CN.md)。产品内置 API 集成，而不是 API 密钥：使用自己的密钥，或由 Owner 私下提供独立限定权限、可撤销的测试密钥。以下“Terminal → 引导安装器 → Docker Desktop → VFA”路径仅支持网关模式，不是开箱即用的 BYOK；标准镜像未打包完整证明工具链。

在解压后的安装器源码包中执行：

```bash
bash scripts/install-evaluator.sh
```

如果 Docker Desktop 缺失或未运行，请遵循相应提示。无需手动配置 Python、Node 或 PostgreSQL。将加密 `.vfaeval` 文件放入 Downloads，并按提示输入口令。首次安装成功后会启动服务并打开默认浏览器。

另开终端，用 `vfa start` 再次启动。[引导步骤与故障排查](INSTALL_EVALUATOR.zh-CN.md)。

公开安装器 URL 仍为 **PUBLICATION_REQUIRED**，真实 Owner 网关为 **NOT_DEPLOYED**。源码 / 可移植测试及任何 Docker 构建检查，都不等同于全新 macOS 环境的 E2E 测试；此处不作该声明。

原生开发者 / BYOK / 完整证明部署请参阅[高级安装](ADVANCED_INSTALLATION.zh-CN.md)。
