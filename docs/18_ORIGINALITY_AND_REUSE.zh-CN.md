# 18 — 原创性与复用

[English](18_ORIGINALITY_AND_REUSE.md)

## 目的

用于黑客松提交、开源归因、工程边界和后续商业审查。

## 第三方／已有内容

### FinRobot

用途：

- 选定财务代码
- 数据处理
- 图表
- 渲染
- 适配器封装函数

必须记录：

- 仓库 URL
- 固定提交
- 精确复用模块
- 许可证／NOTICE
- 修改情况（如有）

不得将其已有代码声称为新增参赛成果。

### Langfuse

用途：

- 可观测性 SDK／OpenTelemetry 追踪

我们的新增工作：

- 财务语义映射
- 规范业务记录
- 运行时埋点边界
- B/C 投影

### RISC Zero

用途：

- 证明基础设施

我们的新增工作：

- 证明策略
- 财务证明边界
- 输入承诺
- 报告／审查关联
- 发布行为

### RD-Agent

用途：

- 仅作架构参考，除非后续明确集成

借鉴的理念：

- 研究 → 代码 → 实验 → 反馈

我们的应用：

- 财务能力工坊

### MCP

用途：

- 在启用 MCP 后端时使用协议／SDK

我们的新增工作：

- Tool Runtime 抽象
- native/MCP/generated 路由
- 权限与财务能力语义

## 项目专属新实现

- Research Object 模型
- 对象状态版本管理
- Goal → AI Scheme 流程
- Scheme 确认
- Research Run
- Research Lead 规划
- 计划图与实际图
- 并行动态运行时
- Task 内自纠
- 受控重新规划
- 证据硬门
- 确定性财务数字硬门
- 财务计算记录
- Agent／Skill／Capability 边界
- 生成财务能力生命周期
- 独立财务审查
- 证明策略（Proof Policy）
- 规范执行记录
- 已发布研究结果
- A/B/C 输出语义
- 对象回写门
- 跨对象比较
- POT／评估集成

## 参赛工作流

编码前：

```text
git tag PRE_HACKATHON_BASELINE
```

保留完整历史。

最终提交时保留：

- 最终提交
- 相对基线的差异
- 原创性／复用声明
- 第三方 NOTICE
- 依赖版本

## Phase-1 集成复用审计

可执行集成遵循 `REUSE → WRAP → ADAPT → TEST`。API 路由将 HTTP 契约映射到
`ResearchApplicationService`，不重新实现规划、调度、证据校验、财务公式、审查、
证明策略、规范投影或报告逻辑。

| 现有模块 | 决策 | 复用方式 | 兼容性 | 集成操作 |
|---|---|---|---|---|
| `src/agentic/**` | DIRECT_REUSE | 回退 Scheme、Lead Planner、重新规划决策器 | Python 3.11 PASS | 组装 |
| `src/runtime/**` | DIRECT_REUSE | 调度器、图变更、检查点、事件日志／SSE 编码 | Python 3.11 PASS | 组装 |
| `src/data/**` | ADAPTER_REUSE | fixture Provider → 摄取 → 已接受证据包 | Python 3.11 PASS | 以显式历史新鲜度策略封装 |
| `src/capabilities/**`, `src/tooling/**` | DIRECT_REUSE | CapabilityRegistry + ToolRuntime | Python 3.11 PASS | 组装 |
| `src/assurance/**` | DIRECT_REUSE | 独立审查、证明策略、ReleaseGate | Python 3.11 PASS | 在控制平面组装 |
| `src/output/**` | DIRECT_REUSE | 规范记录、B/C 投影、结果／报告／回写 | Python 3.11 PASS | 在发布门之后组装 |
| `src/adapters/risc0/pending.py` | ADAPTER_REUSE | 显式待实现证明边界 | Python 3.11 PASS | 保留 `NOT_IMPLEMENTED` 语义 |
| `src/adapters/fmp/**` | ADAPTER_REUSE | 供应商边界 | Python 3.11 单元测试 PASS | 真实凭据延后处理 |
| `src/adapters/finrobot/**` | PORT_REQUIRED | 窄适配器协议 | 尚无实现 | 加入源码时审计精确模块 |
| `frontend_reference/financial_agent_workspace_v3.html` | ADAPTER_REUSE | 原型结构／样式／交互映射供后续 Web 使用 | 未在 Node 24 基线以外进行验证 | 保留；不选择／重写框架 |

集成负责的持久化层在 `src/application/persistence.py` 中为对象、草稿、Run、Goal、
已确认 Scheme、Task、运行时事件、计算、审查、规范记录和已发布结果添加按身份／Run
索引的 JSON 映射。规范化证据继续通过会话工厂适配器使用现有
`SQLAlchemyEvidenceRepository`。这些表持久化现有领域载荷，不包含竞争性的业务逻辑。
