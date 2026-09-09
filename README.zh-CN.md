<img src="docs/product/logo.png" alt="Verifiable Financial Agent 橙色 Logo" width="76">

# Verifiable Financial Agent

[English](README.md)

当前 Alpha 仅支持 Bocha Web Search 证据与发现能力。Owner 已明确授权 FMP 使用
**四个不同的 Key**，不再要求第五个。Provider 凭证仅私下配置，不包含在本仓库中。

加密投资者凭据：私下取得 `VFA-Investor-Access.vfacred`，复制为
`<解压仓库>/credentials/active.vfacred`，完成[平台安装](docs/deployment/INSTALL_EVALUATOR.zh-CN.md)
后运行 `vfa start`，在隐藏提示中输入口令。详见[凭据范围与交付门禁](credentials/README.zh-CN.md)。
此路径不依赖 Owner 网关。Docker 运行时包含锁定的 RISC Zero 3.0.6 Proof 与受治理 Sandbox Broker；配置成功仍不等于 Provider 实时认证。

向风行 AI：能够自主执行、验证、恢复、记忆并持续积累的金融研究 Agent。

Local Deployable Alpha · Controlled Alpha Ready

多 Agent 研究 · 可验证结果 · 自适应恢复 · 研究记忆

[评估 / 本地运行](docs/deployment/EVALUATOR_QUICKSTART.zh-CN.md) · [产品导览](docs/product/PRODUCT_WALKTHROUGH.zh-CN.md)

[能用](#能用--make-it-useful) · [敢用](#敢用--make-it-trustworthy) · [越用越好](#越用越好--make-it-better-with-use)

## 能用 · Make It Useful

用户提出研究目标，Agent 负责组织和执行研究。

Research Object → Research Goal → AI Research Scheme → Research Lead + Specialist Agents → Dynamic Research Path → Financial Research Result。

先审阅并确认研究方案，再观察专家协作、任务内纠错与受控重规划，而不是只收到一段生成文字。

**Agent 处理不确定性，代码执行确定性。** Agent 解释目标、判断证据、拆解任务、分析风险，并决定何时纠错、重规划或请求有限恢复。Agent 决定需要分析或计算什么；受支持的确定性能力规定权威计算如何执行：类型化输入、期间与单位检查、带版本的计算记录和 Financial Review 关联。当前生成能力流程可构建并验证缺失的局部计算能力；尚不是通用 Formula Registry 或全局生产能力认证。

## 敢用 · Make It Trustworthy

在已支持的范围内，检查：Claim → Evidence → Calculation → Financial Review → Proof → Execution Record。

确定性计算、独立财务复核、有限范围的必需证明与精确执行身份，让研究结果可检查。证明只覆盖明确计算，不证明每句文字都正确，也不保证投资适用性。

Provider / Model Failure → Recovery Decision → Policy Gate → Same-Run Recovery。

恢复受预算和策略约束，有公开可观察的记录。Report ↔ Execution 仅使用已持久化的精确映射；来源和贡献覆盖仍为 **PARTIAL**，完整 Claim Trace drawer 尚不可用。

信任由四个独立层次组成：

- 结果可验证：Claim → Evidence → Calculation → Review。
- 确定性执行：类型化输入 → 确定性代码 → Calculation Record → Review → 已支持范围内的 Proof。
- 执行可审计：Task → Agent → Input → 可观察过程 → Structured Output → 已有的 Report Contribution 映射；不暴露隐藏思维链。
- 过程合规：初始计划 + 授权 Correction / Replan / Recovery → 实际执行。产品已记录初始/实际 Graph 版本、纠错、重规划批准、恢复决策、策略门、执行尝试以及 Review / Proof / Release 状态变化。

**路径可以变化，改变路径的规则不能被绕过。** 当前 RISC Zero 证明仅覆盖有限计算。ZK Agent Execution Conformance Proof 属于下一信任层：承诺已批准的图与策略转换，再证明实际动作和状态转换符合初始计划及授权变化。目前不证明完整 Agent 执行路径，未来也不以证明私有模型推理为目标。

## 越用越好 · Make It Better With Use

以下研究记忆闭环已经实现，不是路线图：

已发布研究 → Research Memory → 增量研究 → 更新 / 重新验证 / 避免重复问题 → 新的已发布研究 → Memory v2 → Base vs Current。

历史帮助决定哪些材料需更新、哪些结论需独立重验、哪些问题不应重复。新的研究不继承上次批准。这是研究资产积累，不是模型训练，也不承诺投资收益自动改善。

智能积累分为三个阶段：

| 阶段 | 状态与作用 |
| --- | --- |
| Phase 5 — 研究记忆 / 增量研究 | 已实现。紧凑且受治理的历史上下文通过 Refresh / Revalidate / Prevent 改变下次计划，减少重复研究；已发布 Memory v2 支持 Base vs Current。 |
| Phase 6 — 自适应运行时 → 完整评估 | 执行尝试、失败分类、Provider Detector、Recovery Supervisor、Policy Gate、RecoveryBudget 和同 Run 恢复已实现并有已验收的真实运行证据。TaskProfile × ProviderRoute × Model → Evaluation → POT → Provider / Model / Context / Path 建议属于下一层；尚未实现学习式路由。 |
| Phase 7 — 能力认证 | 规划中。通过版本化能力注册、重复成功证据和人工/策略批准，治理全局可复用的确定性及 Agent 能力。当前局部能力验证不等同于这套生产认证。 |

对可比的重复研究，优化目标是降低边际输入 Token、不必要的输出 Token、延迟、提供方费用、失败尝试和恢复开销。研究记忆和增量研究是现有基础；通用上下文压缩、渐进检索、任务图优化、基于证据的模型选择和已认证能力复用属于下一层。不宣称未经测量的节省比例。目标是在保留必需 Financial Review、Proof Policy、Evidence Coverage、Safety 和 Release Gates 的前提下降低边际研究成本。

## Real Product Screenshots · 真实产品截图

当前本地 React 产品、真实持久化研究与已验收的橙色 Logo；不是原型或生成的效果图。

### 自主研究

![自主研究](docs/product/screenshots/autonomous-research.png)

### 财务复核

![财务复核](docs/product/screenshots/financial-review.png)

### 自适应恢复

![自适应恢复](docs/product/screenshots/adaptive-recovery.png)

### 研究记忆

![研究记忆](docs/product/screenshots/research-memory.png)

### 历史与当前对比

![Base vs Current](docs/product/screenshots/base-vs-current.png)

[截图来源与能力边界](docs/product/screenshots/PROVENANCE.zh-CN.md)。截图反映历史验收结果，不保证每次新调用都成功。

## What Works Today · 当前可用能力

- Research Object、研究目标、模型生成 Scheme、确认后创建 Run。
- Research Lead 与专家 Agent、动态任务图、Self-Correction 与受控 Replan。
- 同一个 Run 内的有限 provider/model 恢复。
- 真实财务数据、确定性计算、财务复核与有限范围的必需 Proof。
- 财务报告及已映射部分的 Report ↔ Execution 追踪。
- Research Memory v2、Incremental Research、Base vs Current。
- PostgreSQL 持久化和真实 React/TypeScript 界面。

[能力状态](docs/product/PRODUCT_STATUS.zh-CN.md)明确区分可用、部分可用和未实现。

## Adaptive Runtime · 自适应运行时

Provider / Model 恢复允许在策略预授权模型集合内进行受控动态替换；Preferred Model 与真实 Actual Model 分开记录，包含 MiMo Provider / mimo-v2.5 授权，超出授权集合仍会被拒绝。

系统基于自有错误分类提出恢复决策，独立策略检查身份、路由权限、能力证据和剩余预算，再允许下一次调用。恢复不会重生成 Scheme、更换知识基线或悄悄新建 Run。

注册路由仅包括 `teamorouter-sol`、`teamorouter-luna`、`mimo-direct`。[运行时架构与预算](docs/architecture/ADAPTIVE_RUNTIME.zh-CN.md)。

## Evaluate / Run Locally · 评估与本地运行

**投资者和测试员当前建议使用 BYOK 直连模式。** 产品已内置 MiMo、TeamoRouter、FMP 的 API 对接能力，但公开安装包不包含可用密钥。使用自己的 Key，或由 Owner 私下提供测试 Key。请从 [BYOK 安装](docs/deployment/ADVANCED_INSTALLATION.zh-CN.md)开始。

另有网关模式的一键安装器源码基础版，可在解压目录运行以下命令。它需要已部署的 Owner 网关及 `.vfaeval` 凭据，不是 BYOK 一键启动器：

Windows（PowerShell）：
```powershell
& .\scripts\install-evaluator.ps1
```

macOS（Terminal）：
```bash
bash scripts/install-evaluator.sh
```

该安装器后续用 `vfa start` 启动。公共安装器交付仍为 **PUBLICATION_REQUIRED**，真实 Owner 网关尚未部署；受阻的是网关模式零配置评估，不是独立配置的 BYOK。标准模式保留全部证明与发布门，完整证明流程需要高级环境。

[引导安装 / 故障排查](docs/deployment/INSTALL_EVALUATOR.zh-CN.md) · [高级 / BYOK 部署](docs/deployment/ADVANCED_INSTALLATION.zh-CN.md) · [Evaluator Gateway](docs/deployment/EVALUATOR_GATEWAY.zh-CN.md)

## Architecture & Validation · 架构与验证

[系统架构](docs/architecture/SYSTEM_ARCHITECTURE.zh-CN.md) · [研究记忆](docs/architecture/RESEARCH_MEMORY.zh-CN.md) · [产品验收](docs/validation/PRODUCT_ACCEPTANCE.zh-CN.md) · [恢复验收](docs/validation/ADAPTIVE_RECOVERY_ACCEPTANCE.zh-CN.md) · [部署验收边界](docs/validation/LOCAL_DEPLOYMENT_ACCEPTANCE.zh-CN.md)。

## Current Status / Roadmap · 状态与路线图

**LOCAL DEPLOYABLE = YES · CONTROLLED ALPHA READY = YES**

Controlled Alpha 指有引导的评估就绪，不代表已验证规模化用户使用。尚不宣称 Public SaaS、企业级安全、Auth/RBAC/SSO、完整来源覆盖或投资建议适用性。

未来：Evaluation → POT → 基于证据的 Provider / Model Selection。完整 Evaluation/POT 尚未实现；研究记忆和增量研究已实现。

[产品状态](docs/product/PRODUCT_STATUS.zh-CN.md) · [许可证待 Owner 决策](docs/LEGAL_AND_LICENSE_STATUS.zh-CN.md)。

## Recognition · 外部里程碑

🥉 **AIx Origin Summit Hong Kong · Flux 赛道铜奖**

Owner 已确认这一早期外部验证里程碑。当前产品身份和能力边界仍以上述实现与验证为准。

[Recognition 记录](docs/recognition/AIX_ORIGIN_SUMMIT.zh-CN.md)。
