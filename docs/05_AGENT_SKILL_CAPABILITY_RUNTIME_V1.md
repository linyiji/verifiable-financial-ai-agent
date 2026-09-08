# 05 — Agent / Skill / Capability / Tool Runtime V1

[简体中文](05_AGENT_SKILL_CAPABILITY_RUNTIME_V1.zh-CN.md)

## 1. Mental model

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

## 2. Multi-Agent

MVP roles:

- Research Lead Agent
- Fundamental Analyst
- Peer Analyst
- Research / News Analyst
- Valuation Analyst
- Risk Analyst
- Code Builder Agent

Multi-Agent 的意义不是“数量多”，而是上下文、责任、可用 Skill 和输出 Schema 分离。

## 3. Multi-Skill

Agent : Skill = many-to-many。

Example:

```text
Valuation Analyst
├─ Trading Multiples Skill
├─ DCF Skill
├─ Peer Valuation Skill
└─ Sensitivity Skill
```

Evidence retrieval skill 可被多个 Agent 复用。

## 4. Skill package

A Skill should contain:

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

Business execution unit:

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

Unified execution API:

```python
execute(tool_id, input, context) -> ToolResult
```

Backend:

- NativeToolBackend
- MCPToolBackend
- GeneratedToolBackend

Agent 不关心 backend type。

## 7. Native capability

MVP default for:

- internal code
- FinRobot wrapped functions
- FMP adapter access through data services
- deterministic calculations

## 8. MCP

MCP is not synonymous with external files.

A local / internal service can expose MCP, but MVP does not force all internal code through MCP.

Future good candidates:

- Bloomberg
- SEC filing
- local files
- desktop local runtime
- company internal research DB
- third-party tool providers

## 9. Code Builder / Capability Workshop

Trigger only on approved Capability Gap.

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

## 10. Self-Correction

Specialist Agent can adjust:

- evidence choice
- parameters
- output format
- tool call
- generated code
- retry strategy

But cannot:

- alter top-level graph directly
- bypass review
- downgrade mandatory proof
- promote generated capability to CERTIFIED

## 11. Replan

Specialist emits:

```text
ReplanRequest
reason_code
evidence
suggested_action
```

Research Lead decides.

Graph Engine applies.

## 12. Agent outputs

Do not save hidden chain-of-thought.

Save structured decision records:

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
