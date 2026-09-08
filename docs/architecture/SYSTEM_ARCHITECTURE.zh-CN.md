# 系统架构

[English](SYSTEM_ARCHITECTURE.md)

React/TypeScript 界面 → FastAPI 产品 API → 应用／领域契约 → 依赖感知运行时 → 财务数据／模型／证明适配器 → PostgreSQL 和已验证产物存储。

- Object + Goal 定义研究问题。持久化的 Scheme 记录已确认的研究意图。
- Planned Graph 与 Actual Graph 区分计划工作和已观测到的执行及获准变更。
- Research Lead 和专业 Agent 产生与 Run/Task/actor 及精确产物引用绑定的结构化输出。
- 财务证据进入确定性计算；独立审查和有界证明门决定是否具备发布资格。
- 已发布结果成为类型化 Research Memory 和带版本的 Current Research View。
- 恢复机制包裹的是一次有界的专业 Agent 调用，而非整个研究工作流。

## 权威边界

PostgreSQL 中的领域／运行时记录与已验证产物引用才是权威来源。投影缓存是派生数据，不是研究事实。普通 get_projection 在内存中计算，不执行 upsert 或 commit；显式 materialize_projection 仍是独立的写操作。generated_at 是响应生成元数据，而不是研究事实。

恢复期间，Run 身份、已确认的 Scheme 身份和知识基线保持不变。未来的重新执行会拥有新的 Run，并显式引用其执行前序；它不会复活失败的 Run，也不会挪用 base_run_id 表示执行前序。

系统不暴露隐藏思维链。公开执行轨迹描述声明的输入、已观测动作、输出、检查和策略决策。

[API 组装](../../apps/api/main.py) · [后端／读取边界](../../src/phase4_product/postgresql_backend.py) · [自适应运行时](ADAPTIVE_RUNTIME.zh-CN.md) · [Memory](RESEARCH_MEMORY.zh-CN.md)。
