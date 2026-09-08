# Phase 4.5 M5 — V17.1 执行协作视觉差异

[English](visual-delta.md)

全部截图视口：**1440 × 900**，设备缩放因子 **1**，浏览器缩放 **100%**。

参考权威：已接受 V17.1 交接中的 `financial_agent_workspace_v17_1_minimal_c_execution_fanin.html`（SHA-256 `1be45091827c6485b624f6a44bf2e0f48bc650836b1a15024a3f7c395718762e`）。所要求的 `(3)` 文件不存在；本文件是 M3/M4 已接受的逐字节相同规范资产。当前权威：真实 Phase 4 后端提供的精确已发布 Run `RUN-57aed683-75d6-4b47-acc6-a73053ea492e`。

## 对应证据

| 状态 | 参考 | 当前 |
| --- | --- | --- |
| C1 · 执行顶部 | `reference/REF-C1-execution-top.png` | `current/CUR-C1-execution-top.png` |
| C2 · 参与者协作 | `reference/REF-C2-actor-collaboration.png` | `current/CUR-C2-real-actor-rail.png` |
| C3 · 基本面分析师 | `reference/REF-C3-fundamental-analyst.png` | `current/CUR-C3-real-fundamental-analyst.png` |
| C4 · 输入/过程/输出 | `reference/REF-C4-input-process-output.png` | `current/CUR-C4-real-input-process-output.png` |
| C5 · 报告贡献 | `reference/REF-C5-report-contribution.png` | `current/CUR-C5-hero-report-contribution.png` |
| C6 · 次级记录模式 | `reference/REF-C6-timeline.png` | `current/CUR-C6-observable-records.png` |

## 视觉差异矩阵

| 区域 | 分类 | 证据/决定 |
| --- | --- | --- |
| 外壳 | MATCH | 藏蓝研究导航、白色工作区页头、居中界面与紧凑卡片语言保留受约束的产品外壳。 |
| 结果页头 | MINOR_DRIFT | 当前页头更密集，包含 M2 确立的精确 Run、Object、As-of 身份。 |
| A/B/C 标签页 | MATCH | 三个等宽标签、白色激活状态与各界面可用性保留参考导航模型。 |
| 执行页头 | MATCH | C 是明确的业务界面，带简短的参与者中心描述和可见 PARTIAL 状态。 |
| 工具栏 | MATCH | 协作为主；次级记录模式加参与者搜索替代仅用于参考演示的原始/完整筛选。 |
| 参与者侧栏 | MATCH | 左侧吸附栏驱动右侧选中参与者详情，URL 持久保留仅参与者选择。 |
| 参与者分组 | INTENTIONAL_REAL_DATA_DIFFERENCE | 当前精确展示此 Run 观察到的 1 名研究负责人、5 名专家和 6 名支持执行参与者；不复制参考演示名单。 |
| 选中参与者页头 | MATCH | 参与者类型、展示角色、稳定参与者 ID、状态与可观察摘要计数具有明确视觉区别。 |
| 执行卡片 | MATCH | 各公开参与者详情以任务为中心，按输入 → 可观察过程 → 输出 → 报告贡献阅读。 |
| 输入列 | INTENTIONAL_REAL_DATA_DIFFERENCE | 当前仅使用类型化公开引用 ID。既不展开提供方载荷，也不把参与者级引用分配给捏造的隐藏序列。 |
| 过程列 | INTENTIONAL_REAL_DATA_DIFFERENCE | 当前有 7 个公开 `task.completed` 详情事件。仅显示事件类型/状态/ID，因为公开契约不含时间戳、序列、时长和私有推理。 |
| 输出列 | MATCH | AgentOutput ID、状态、安全摘要与按需展示的结构化发现/风险/限制使用真实 DTO 字段，遵循参考层级。 |
| 报告贡献 | INTENTIONAL_REAL_DATA_DIFFERENCE | 仅显示一条权威关系：`fundamental_analyst` 到 `metric-revenue-growth`；所有其他参与者明确显示未观察到关系。 |
| 次级时间线 | INTENTIONAL_REAL_DATA_DIFFERENCE | 当前有意使用 7 行可观察记录表。公开界面没有时间戳或序列，按时间排列会捏造顺序。 |
| 响应式/溢出 | MATCH | ≤900px 时 I/P/O 纵向折叠；≤760px 时侧栏、页头和控件变为单列，长 ID 换行或留在有限溢出容器中。 |

## 验收

- 结构性实质偏移：**0**
- 轻微视觉偏移：**1**（受约束的精确 Run 页头密度）
- 有意真实数据差异：**5**（真实参与者名单、仅引用输入、安全过程投影、一项权威贡献、非时间顺序的次级表格）
- V17.1 执行对齐程度：**HIGH** — 恢复以参与者为中心的协作、I/P/O 阅读顺序与报告汇聚，不暴露隐藏思维链，也不制造不可用的 Execution/Review 关系。
