# WS-B — Agent 规划

[English](WS_B_AGENTIC.md)

负责范围：

- `src/agentic/**`
- Agent 单元测试

实现：

- SchemeGenerator 接口与确定性回退
- ResearchLeadPlanner
- PlannedTaskGraph 输出
- 专家 Agent 接口
- Skill 契约
- SelfCorrectionDecision
- ReplanRequest
- Agent / Skill 注册表
- 结构化决策

规则：

- 先有初始计划
- 专家不得修改图
- 不存储隐藏思维链
- 不在 Agent 代码中生成财务数字

编写 `WORKSTREAM_REPORT_AGENTIC.md`。
