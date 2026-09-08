# 05 — Agent / Skill / Capability / Tool Runtime V1（代理／技能／能力／工具运行时）

[English](05_AGENT_SKILL_CAPABILITY_RUNTIME_V1.md)

## 1. 心智模型

```text
Research Lead Agent
    ↓ plan
Task
    ↓ dispatch
Specialist Agent
    ↓
Skill
    ↓ allowed tools
Tool Runtime
    ↓
Capability Registry
    ├─ Native
    ├─ MCP
    └─ Generated
```

## 2. 多 Agent

MVP 角色：

- 研究 Lead Agent
- 基本面分析师（Fundamental Analyst）
- 同行分析师（Peer Analyst）
- 研究／新闻分析师
- 估值分析师（Valuation Analyst）
- 风险分析师（Risk Analyst）
- 代码构建 Agent

Multi-Agent 的意义不是“数量多”，而是上下文、责任、可用 Skill 和输出 Schema 分离。

## 3. 多 Skill

Agent : Skill = 多对多。

示例：

```text
Valuation Analyst
├─ Trading Multiples Skill
├─ DCF Skill
├─ Peer Valuation Skill
└─ Sensitivity Skill
```

Evidence retrieval skill 可被多个 Agent 复用。

## 4. Skill 方法包

一个 Skill 应包含：

```text
skill.yaml
instructions.md
input_schema
output_schema
allowed_tools
required_evidence
preconditions
validation_rules
correction_strategy
evaluation_rules
```

Skill 不直接承诺第三方实现。

## 5. Capability

业务执行单元：

```text
RevenueGrowthCapability
DCFValuationCapability
GetFinancialStatementsCapability
PeerDatasetCapability
```

Capability 与 Adapter 分开。

例如：

```text
Valuation Skill
→ dcf_valuation capability
→ FinRobotValuationAdapter / NativeDCF
```

## 6. Tool Runtime

统一执行 API：

```python
execute(tool_id, input, context) -> ToolResult
```

后端：

- NativeToolBackend
- MCPToolBackend
- GeneratedToolBackend

Agent 不关心 backend type。

## 7. 原生能力

MVP 中以下能力默认使用原生实现：

- 内部代码
- 封装后的 FinRobot 函数
- 经数据服务访问 FMP 适配器
- 确定性计算

## 8. MCP

MCP 不等同于外部文件。

本地／内部服务可以暴露 MCP，但 MVP 不强制所有内部代码都经 MCP 调用。

未来适合的候选：

- Bloomberg
- SEC 申报文件
- 本地文件
- 桌面本地运行时
- 企业内部研究数据库
- 第三方工具供应商

## 9. Code Builder / Capability Workshop

仅由已批准的 Capability Gap 触发。

```text
Gap
→ Requirement Spec
→ Code Builder Agent
→ Workspace
→ Generate
→ Test
→ Financial Validate
→ TASK_APPROVED
→ Register
→ Resume
```

## 10. 自纠

专业 Agent 可以调整：

- 证据选择
- 参数
- 输出格式
- 工具调用
- 生成的代码
- 重试策略

但不得：

- 直接修改顶层图
- 绕过审查
- 降低强制证明要求
- 将生成能力提升为 CERTIFIED

## 11. 重新规划（Replan）

专业 Agent 提交：

```text
ReplanRequest
reason_code
evidence
suggested_action
```

由 Research Lead 决策。

由 Graph Engine 应用变更。

## 12. Agent 输出

不保存隐藏思维链。

保存结构化决策记录：

```text
decision_type
reason_code
summary
evidence_ids
selected_skill
selected_capability
confidence?
requires_review
```
