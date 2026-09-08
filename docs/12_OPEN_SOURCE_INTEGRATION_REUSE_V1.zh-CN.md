# 12 — 开源集成与复用 V1

[English](12_OPEN_SOURCE_INTEGRATION_REUSE_V1.md)

于 2026-09-03 验证／审查。

## 1. FinRobot

仓库：

https://github.com/AI4Finance-Foundation/FinRobot

当前项目用途：

> 嵌入式财务运行时／能力来源。

不要将其固定股票研究流水线用作我们的主编排器。

建议集成方式：

```text
Agent
→ Skill
→ Capability Registry
→ FinRobot Adapter
→ FinRobot source function
```

已讨论固定的当前基线：

`d221910096de87579b02f8f0674652bf1a175f51`

建议布局：

```text
third_party/
└── FinRobot/   # pinned submodule
```

复用候选：

- financial_data_processor
- FMP 连接器逻辑
- 同行聚合
- 增长率／利润率
- 技术指标
- 图表
- HTML／PDF 渲染器

需谨慎替换／封装：

- 直接 LLM 章节生成器
- 固定流水线编排
- 简化估值逻辑
- 报告生成时重新获取数据的模式

### Python 版本

FinRobot 的 `setup.py` 当前声明 Python `>=3.10,<3.12`，因此 Python 3.11 是 MVP 最稳妥的共同运行时。

### 许可证／NOTICE 注意事项

当前仓库 README／NOTICE 将项目标为 Apache-2.0，并包含商标／NOTICE 义务。但 `setup.py` 的一个元数据字段仍写着 MIT。

应将其视为仓库元数据不一致。

任何再分发／商业发布前：

1. 检查当前检出的 `LICENSE`
2. 保留 `NOTICE`
3. 遵循当前商标政策
4. 不要将“FinRobot”用作我们的产品名
5. 记录精确复用的源码／版本

黑客松提交应保留归因和固定基线。

---

## 2. Langfuse

文档：

https://langfuse.com/docs/observability/sdk/overview

仓库：

https://github.com/langfuse/langfuse

当前官方 SDK 系列基于 OpenTelemetry。

定位：

> 运行时可观测性。

实现：

```text
TraceAdapter
├── LangfuseTraceAdapter
└── NoopTraceAdapter
```

追踪错误不得中断应用执行。

埋点：

- 运行
- 规划
- 代理
- 技能
- 工具
- 计算
- 纠错
- 重新规划
- 审查
- 证明
- 渲染

Langfuse 不是 Canonical Execution Record。

---

## 3. Microsoft RD-Agent

仓库：

https://github.com/microsoft/RD-Agent

定位：

> 在 MVP 中仅作为架构参考。

官方项目面向研发型研究／开发，在许多场景下主要使用 Docker 执行代码。

借鉴：

```text
Research
→ Develop
→ Experiment
→ Feedback
→ Iterate
```

我们的映射：

```text
Capability Gap
→ Requirement
→ Code Builder
→ Sandbox
→ Tests
→ Financial Validation
→ Feedback / Fix
→ TASK_APPROVED
```

不要将 RD-Agent 引入为主运行时，除非后续实现审查证明它能显著减少工作量且不损害我们的架构。

---

## 4. RISC Zero

仓库：

https://github.com/risc0/risc0

文档：

https://dev.risczero.com/

定位：

> ZK 执行证明供应商。

RISC Zero 证明已知程序在 zkVM 中正确执行，并产生可验证 receipt。

MVP:

- 一个小型确定性证明
- 不证明完整 LLM
- 在 Release 前验证 receipt

建议边界：

```text
Python ProofPolicy
→ RiscZeroAdapter
→ Rust host / guest
→ Receipt
→ Verifier
```

固定已发布版本，而非开发中的 `main` 分支。

---

## 5. MCP Python SDK

官方文档：

https://py.sdk.modelcontextprotocol.io/

官方仓库：

https://github.com/modelcontextprotocol/python-sdk

当前稳定 Python SDK 文档描述了 Tools、Resources、Prompts 和标准传输方式。

定位：

> 可选的标准化 Tool／Resource 协议。

MVP:

- 内部原生财务能力保持 Native
- 保留 MCP 后端接口
- 不强制将每个 Python 函数封装为 MCP

未来：

- 本地文件
- 桌面运行时
- SEC
- Bloomberg／企业数据
- 外部工具
- 第三方 Agent

---

## 6. FMP

定位：

> MVP 默认财务数据供应商。

数据仍必须通过我们的 Evidence Layer。

保存供应商元数据和快照引用。

生产分发前，必须单独检查商业／展示许可。

---

## 7. 原创性边界

第三方：

- FinRobot 源码能力
- Langfuse 可观测性
- RISC Zero 证明基础设施
- RD-Agent 设计参考
- MCP 协议／SDK

我们的产品实现：

- 以 Object 为中心的状态
- Goal → AI Scheme 流程
- Research Lead 规划器
- 计划图／实际图
- 动态运行时
- 自纠
- 受控重新规划
- 财务证据硬门
- 计算记录
- 能力注册表
- 生成财务能力生命周期
- 规范执行记录
- Review／Proof／Release 组装
- B/C 双重审查投影
- 对象回写
- 比较
- POT 评估设计
