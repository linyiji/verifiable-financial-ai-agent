# 03 — Architecture Decisions V1

本文件优先级最高。除非用户明确修改，否则 Codex 不得自行推翻。

| ID | Frozen decision |
|---|---|
| ADR-001 | Research Object 是长期资产主体。 |
| ADR-002 | 用户发起的是 Research Run，不是内部 Task。 |
| ADR-003 | 用户输入 Object + Goal，AI 生成 Research Scheme，用户确认后固化为 run-scoped snapshot。 |
| ADR-004 | Research Scheme 当前不做独立配置中心 / 方案库。 |
| ADR-005 | Research Lead Agent 必须先生成完整 Initial Planned Task Graph，再启动正式执行。 |
| ADR-006 | Task 是 Agent 为实现 Research Goal 拆出的用户可理解研究工作单元。 |
| ADR-007 | Skill 是执行 Task 的方法包；Tool / Capability 是实际执行能力。 |
| ADR-008 | Task 内优先 Self-Correction；Self-Correction 不改变 Task Goal，不新增顶级 Task。 |
| ADR-009 | Specialist Agent 无权直接修改 Graph；只能提交 Replan Request。 |
| ADR-010 | 只有 Research Lead Agent / Planner 可以批准 Graph Mutation。 |
| ADR-011 | Dynamic Runtime 不是 Agent；它负责状态、调度、并行、Graph 执行、事件、Checkpoint。 |
| ADR-012 | Planned Task Graph 与 Actual Runtime Graph 必须同时保存。 |
| ADR-013 | 未验证数据不得进入正式金融推理。 |
| ADR-014 | Raw FMP / provider JSON 不得直接成为正式 Agent reasoning input。 |
| ADR-015 | 所有确定性金融数字必须由 Code / Financial Capability 产生。 |
| ADR-016 | LLM 可以选择计算、解释结果、形成 Judgment，但不能直接成为正式可计算数字来源。 |
| ADR-017 | Agent has autonomy over execution, not over assurance. |
| ADR-018 | Review / Proof / Release 属于 Control Plane，Agent 无权绕过。 |
| ADR-019 | Langfuse 是横切 Observability，不是 Task、不是普通 Agent Tool。 |
| ADR-020 | ZK 证明指定 deterministic execution / integrity，不证明外部数据客观真实，不证明主观投资观点正确。 |
| ADR-021 | Native internal capability 不天然等于 MCP。MCP 是 Tool Backend / protocol 之一。 |
| ADR-022 | MVP 内部金融函数优先 Native Capability，不强制 MCP 化。 |
| ADR-023 | Generated Code 只在受控 Server Sandbox 执行，不获得 host secrets / filesystem / network。 |
| ADR-024 | Generated Capability 首先是 TASK_APPROVED，不自动升级成全局 Certified Capability。 |
| ADR-025 | A Financial Report 是独立业务主输出。 |
| ADR-026 | B Financial Review 和 C Execution Details 必须来自同一 Canonical Execution Record。 |
| ADR-027 | Run 完成后通过 Object Writeback Gate 更新 Object；不是整份报告覆盖 Object。 |
| ADR-028 | AI Judgment 必须版本化保存，不能写成永久 Fact。 |
| ADR-029 | Comparison 读取多个 Object 的统一 Canonical Values，不创建一个“多对象混合执行 Task”作为默认模型。 |
| ADR-030 | POT / Evaluation 发生在 Run 后，用于未来 routing / cost / quality 优化；MVP 不夸大为成熟 RL。 |
| ADR-031 | Web 是第一种 Runtime Client；未来 Desktop / Local Runtime 可以复用相同 Runtime Protocol。 |
| ADR-032 | Backend Phase 1 使用 Python >=3.11,<3.12 + FastAPI + Pydantic + SQLAlchemy + async runtime；Web 基线为 Node.js >=24,<25。 |
| ADR-033 | 第三方源码通过 Adapter / third_party boundary 使用，不把 FinRobot 任意 import 散落在 Agent 代码里。 |
| ADR-034 | Frontend 动态 Task Graph 必须由后端 SSE Runtime Events 驱动，不能把业务 Graph 写死在前端。 |
