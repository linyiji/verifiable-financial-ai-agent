# 评估 Verifiable Financial Agent

[English](EVALUATOR_QUICKSTART.md)

现阶段投资者和测试员请从[直连供应商 BYOK](LOCAL_DEPLOYMENT.zh-CN.md)和[原生环境安装](ADVANCED_INSTALLATION.zh-CN.md)开始。产品内置 API 集成，但不内置 API 密钥。请使用自己的密钥，或由 Owner 私下提供独立限定权限、可撤销的测试密钥。此路径不依赖尚未部署的网关，但不免除供应商权限要求或证明 / 发布门禁。

独立的[引导安装](INSTALL_EVALUATOR.zh-CN.md)仅准备网关模式的 Docker 服务，不是开箱即用的 BYOK 安装器。完成该安装后，另开终端运行 `vfa start`。使用 `vfa stop`、`vfa status`、`vfa doctor`、`vfa update` 和 `vfa open` 管理该安装器的日常运行。

公开安装器 URL：**PUBLICATION_REQUIRED**。真实 Owner 网关：**NOT_DEPLOYED**。这些运维前提具备之前，可使用源码包验证安装器；不能据此认为网关模式的 Owner 付费研究已经可用。独立配置的 BYOK 是另一条路径。

标准容器交付保留所有证明 / 发布门禁，仅支持有限工作流，未打包完整证明工具链。完整强制证明 / 生成能力执行须采用[高级安装](ADVANCED_INSTALLATION.zh-CN.md)。网关模式的评估者无需在本机配置上游供应商密钥；当前 BYOK 测试员则须在本地后端配置私有密钥，绝不能放入前端。

[Windows](WINDOWS_EVALUATION.zh-CN.md) · [macOS](MACOS_EVALUATION.zh-CN.md) · [凭据安全](../architecture/EVALUATOR_CREDENTIAL_SECURITY.zh-CN.md)。
