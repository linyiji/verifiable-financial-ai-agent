# 文档导航

[English](README.md)

## 产品

- [产品概览](product/PRODUCT_OVERVIEW.zh-CN.md)
- [产品导览](product/PRODUCT_WALKTHROUGH.zh-CN.md)
- [当前状态与能力边界](product/PRODUCT_STATUS.zh-CN.md)

## 安装与部署

投资者和测试员当前应使用 BYOK，自行配置 Key 或使用 Owner 私下提供的测试 Key。
内置 MiMo、TeamoRouter、FMP 的对接能力不等于公开安装包内置了 API Key。
网关安装器仍是独立的源码基础版，不代表真实托管服务已上线。

- [评估者快速开始](deployment/EVALUATOR_QUICKSTART.zh-CN.md)
- [高级 / BYOK 安装](deployment/ADVANCED_INSTALLATION.zh-CN.md)
- [本地部署](deployment/LOCAL_DEPLOYMENT.zh-CN.md)
- [网关模式引导安装](deployment/INSTALL_EVALUATOR.zh-CN.md)
- [Windows](deployment/WINDOWS_EVALUATION.zh-CN.md) · [macOS](deployment/MACOS_EVALUATION.zh-CN.md)
- [Owner 网关](deployment/EVALUATOR_GATEWAY.zh-CN.md)
- [安装器设计](deployment/EVALUATOR_INSTALLER_DESIGN.zh-CN.md)

## 架构与安全

- [系统架构](architecture/SYSTEM_ARCHITECTURE.zh-CN.md)
- [Phase 6A 可靠性与完成性](architecture/PHASE6A_RELIABILITY_COMPLETION.zh-CN.md)
- [自适应运行时（Adaptive Runtime）](architecture/ADAPTIVE_RUNTIME.zh-CN.md)
- [研究记忆（Research Memory）](architecture/RESEARCH_MEMORY.zh-CN.md)
- [评估凭据安全](architecture/EVALUATOR_CREDENTIAL_SECURITY.zh-CN.md)

## 验收

- [产品验收](validation/PRODUCT_ACCEPTANCE.zh-CN.md)
- [自适应恢复验收](validation/ADAPTIVE_RECOVERY_ACCEPTANCE.zh-CN.md)
- [本地部署验收](validation/LOCAL_DEPLOYMENT_ACCEPTANCE.zh-CN.md)
- [网关基础能力验收](validation/EVALUATOR_GATEWAY_ACCEPTANCE.zh-CN.md)
- [安装器基础能力验收](validation/EVALUATOR_INSTALLER_ACCEPTANCE.zh-CN.md)
- [发布安全](validation/PUBLICATION_SAFETY.zh-CN.md)

## 外部里程碑与法律状态

- [Flux 赛道铜奖](recognition/AIX_ORIGIN_SUMMIT.zh-CN.md)
- [许可证决策](LEGAL_AND_LICENSE_STATUS.zh-CN.md)

## 双语文档规范

英文文档使用 `FILE.md`，简体中文镜像使用 `FILE.zh-CN.md`。
每组文档在标题下提供互相切换的链接。中文文档优先跳转中文文档，
代码、图片和机器证据文件保持共享。
命令、参数、路由与模型 ID、SHA 和权威状态标识不翻译。
历史验收记录保留当时的失败与限制，不改写成当前能力声明。

`docs/archive/engineering/` 中未进入当前导航的历史工程文件免于全文翻译。
它们不是当前评估者的操作说明；归档清单及校验和描述的是原始交付包。
如果将某份归档文件加入当前产品阅读路径，应先补充中文镜像。
