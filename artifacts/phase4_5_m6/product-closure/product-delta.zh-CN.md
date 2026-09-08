# Phase 4.5 M6 — 产品闭环差异

[English](product-delta.md)

## 受约束的比较

- 参考：`financial_agent_workspace_v17_1_minimal_c_execution_fanin.html`
- 参考 SHA-256：`1be45091827c6485b624f6a44bf2e0f48bc650836b1a15024a3f7c395718762e`
- 当前验收 Run：`RUN-57aed683-75d6-4b47-acc6-a73053ea492e`
- 视口：`1440 × 900`，缩放 `100%`，设备缩放 `1`
- 实质性产品偏移：`0`

分类比较产品层级、生命周期语义、主要操作与跨视图行为。后端权威数据导致的差异不视为视觉缺陷。

| 产品区域 | 分类 | 证据/处理 |
|---|---|---|
| Run 页头 | MATCH | 保留公司优先的层级、完成状态、身份和 Run 操作。当前使用精确已接受 Run。 |
| 生命周期 01 | MATCH | 五阶段生命周期保留 `01 · 研究计划`。 |
| 生命周期 02 | MATCH | `02 · AI研究` 仍为研究路径界面。 |
| 生命周期 03 | INTENTIONAL_REAL_DATA_DIFFERENCE | 当前展示共享权威复核：`PASS · READY`、54 项检查、4 个分组，而非参考演示复核卡。 |
| 生命周期 04 | INTENTIONAL_REAL_DATA_DIFFERENCE | 当前以可观察事实替代模拟章节进度：8/8 输出、报告 `PARTIAL`、一项贡献、HTML `AVAILABLE`、PDF `NOT_GENERATED`。 |
| 生命周期 05 | MATCH | 保留已发布完成摘要和结果操作；当前以 Review、Proof、Execution、Report、Result 与终态事件闭环加强它。 |
| 结果入口 | MATCH | 阶段 03/04/05 操作分别进入 B/A/A，并保留精确 Run。 |
| A 报告 | INTENTIONAL_REAL_DATA_DIFFERENCE | 保留参考报告结构，当前展示类型化 Released Result 值、一项真实来源图贡献及实际 HTML/PDF 可用性。 |
| B 复核 | INTENTIONAL_REAL_DATA_DIFFERENCE | 当前展示 54 项持久化检查和零异常；不捏造演示纠正/重规划卡。 |
| C 执行 | INTENTIONAL_REAL_DATA_DIFFERENCE | 当前展示 12 名真实参与者、7 条公开详细记录和一项报告贡献；继续披露公开详情有意不完整。 |
| A → B | MATCH | 精确作用域选择器（`review_id`、`check_code`、有序 `subject_refs`）和返回锚点可通过 URL 寻址。 |
| B → A | MATCH | 精确权威报告锚点返回 A；无文本/索引回退。 |
| A → C | MATCH | Revenue Growth 主指标打开 `fundamental_analyst`，带精确 AgentOutput 和执行事件。 |
| C → A | MATCH | 权威贡献返回 `metric-revenue-growth`。 |
| B → C 真实的部分状态 | INTENTIONAL_REAL_DATA_DIFFERENCE | 未观察到精确 Review→Execution 关系；UI 说明未观察到机器关系，不提供模糊链接。 |
| 刷新 | MATCH | A、B、C 主指标焦点和 Run 生命周期阶段通过 URL 状态在真实重载后保留。 |
| 后退/前进 | MATCH | 浏览器后退/前进恢复精确的先前 A/B 焦点与 Run 阶段，不选择最新 Run。 |

## 截图

参考：

- `reference/REF-M6-1-run-stage-03.png`
- `reference/REF-M6-2-run-stage-04.png`
- `reference/REF-M6-3-run-stage-05.png`
- `reference/REF-M6-4-results-a.png`
- `reference/REF-M6-5-results-b.png`
- `reference/REF-M6-6-results-c.png`

当前：

- `current/CUR-M6-1-run-stage-03.png`
- `current/CUR-M6-2-run-stage-04.png`
- `current/CUR-M6-3-run-stage-05.png`
- `current/CUR-M6-4-results-a.png`
- `current/CUR-M6-5-results-b.png`
- `current/CUR-M6-6-results-c.png`

## 真实浏览器闭环回执

- 阶段 03 / 结果 B：相同 Run 和 Review 身份；54 项检查、4 个分组、`PASS · READY`。
- 阶段 04 / 结果 A：相同 `report_id`、`released_result_id`、HTML 产物、投影和一项贡献。
- 阶段 05：发布闭环要求 Review、必需 Proof、Execution、Report、Released Result、`release.completed` 和 `run.completed`。
- A ↔ C 主指标：观察到精确锚点、参与者、AgentOutput、执行事件和计算。
- B ↔ C：如实为 `PARTIAL`；未观察到精确通用机器关系。
- 次级 C 参与者：未捏造报告贡献操作或复核链接。
- 刷新及后退/前进：A、B、C 和 Run 阶段 04 在真实浏览器中通过。
