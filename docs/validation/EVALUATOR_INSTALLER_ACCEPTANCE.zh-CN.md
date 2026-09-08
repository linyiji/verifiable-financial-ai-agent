# 一键安装器基础验收

[English](EVALUATOR_INSTALLER_ACCEPTANCE.md)

> 当前指引澄清 — 2026-09-08：以下检查验证的是仅面向网关的安装器基础，不是已完成的全新机器或真实网关评估。NOT_OBSERVED 表示未执行，而不是已观测到失败。当前建议投资者／测试员采用直接 API 的 BYOK，并在本地配置私有凭据；此安装器目前不提供一键 BYOK。以下主机验证下一步属于安装器工作线，并不要求先等待网关，才能开展有人协助的 BYOK 测试。

日期：2026-09-08。范围：仅本地交付变更；未发布、未部署网关、
未进行付费供应商调用或生产研究 Run。

## 已观测检查

- 安装器可移植契约：50 项通过。
- 安装器、评估者网关、BYOK／供应商路由、只读投影、
  API／Memory 和自适应恢复的组合回归：207 项通过。
- 前端只读导航与对象工作区契约：32 项检查通过。
- TypeScript 类型检查和 Vite 构建：通过；已有的 500 kB 分块警告仍存在。
- 安装器 Ruff 检查和 Bash 语法：通过。
- 本地 Docker 镜像构建、API／安装器导入、迁移图，以及已构建前端
  资源存在性：通过。容器内 Docker Compose 可执行程序：通过。
- 文档链接及变更文件的秘密／私有路径扫描：通过。

测试使用隔离 fixture／模拟服务操作。未挂载 Owner 数据库。
Docker 镜像准备不等于全新机器安装或真实网关流程。
Windows 源码断言不能代替原生 PowerShell 执行。

## 明确待完成的验收门

WINDOWS_REAL_HOST_E2E = NOT_OBSERVED

MACOS_REAL_HOST_E2E = NOT_OBSERVED

PUBLIC_INSTALLER_URL = PUBLICATION_REQUIRED

REAL_OWNER_GATEWAY_DEPLOYED = NO

REAL_ZERO_CONFIG_LIVE_EVALUATION = NO

标准模式受限；完整证明容器打包尚不可用。现有
证明、能力认证和研究发布权限保持不变。

精确下一步：ONE_COMMAND_INSTALLER_HOST_VALIDATION。使用干净的 Windows 主机
和全新的 macOS 账户，验证显式 Docker 安装同意／重启、
Unicode 路径、首次启动、重复启动、stop/update 及浏览器行为。
声称端到端就绪前，需要已部署的测试网关或隔离的假网关验收环境；
不要以付费供应商探测代替。

请参阅[设计契约](../deployment/EVALUATOR_INSTALLER_DESIGN.zh-CN.md)和
[引导安装](../deployment/INSTALL_EVALUATOR.zh-CN.md)。
