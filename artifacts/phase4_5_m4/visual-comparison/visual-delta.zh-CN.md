# Phase 4.5 M4 — V17 财务复核视觉差异

[English](visual-delta.md)

全部截图视口：**1440 × 900**，设备缩放因子 **1**，浏览器缩放 **100%**。

参考权威：已接受 V17.1 交接中的 `financial_agent_workspace_v17_1_minimal_c_execution_fanin.html`（SHA-256 `1be45091827c6485b624f6a44bf2e0f48bc650836b1a15024a3f7c395718762e`）。所要求的 `(3)` 文件不存在；本文件是 M3 已接受的逐字节相同规范资产。当前权威：真实 Phase 4 后端提供的精确已发布 Run `RUN-57aed683-75d6-4b47-acc6-a73053ea492e`。

## 对应证据

| 状态 | 参考 | 当前 |
| --- | --- | --- |
| B1 · 结果 B 顶部 | `reference/REF-B1-results-review-top.png` | `current/CUR-B1-results-review-top.png` |
| B2 · 完整复核项 | `reference/REF-B2-complete-review-item.png` | `current/CUR-B2-real-review-item.png` |
| B3 · 异常模式 | `reference/REF-B3-exception-filter.png` | `current/CUR-B3-exception-filter.png` |
| B4 · 复核/机器关系 | `reference/REF-B4-review-machine-interaction.png` | `current/CUR-B4-review-machine-relation-not-observed.png` |
| B5 · Run 阶段 03 | `reference/REF-B5-run-stage-03-review.png` | `current/CUR-B5-run-stage-03-review.png` |

## 视觉差异矩阵

| 区域 | 分类 | 证据/决定 |
| --- | --- | --- |
| 外壳 | MATCH | 藏蓝研究导航、白色工作区页头、居中内容列和卡片体系保留参考层级。 |
| 结果页头 | MINOR_DRIFT | 当前页头更紧凑，并按 M2 约束展示精确 Run/Object/As-of 身份。 |
| A/B/C 标签页 | MATCH | 三个等宽标签页、白色激活界面与可用性状态符合参考交互模型。 |
| 复核页头 | MATCH | 保留中文优先的 B 标签、整体就绪状态和独立复核界面标题。 |
| 复核工具栏 | MATCH | `完整复核` 与 `异常筛选` 为直接的双态分段控件。 |
| 摘要 | INTENTIONAL_REAL_DATA_DIFFERENCE | 参考展示演示通过/待处理/已解决数；当前展示权威裁决、54 项检查、4 个真实分组与 0 项可处理异常。 |
| 完整复核布局 | MATCH | 摘要 → 模式工具栏 → 确定性分组 → 可展开检查，遵循相同阅读顺序，不复制演示步骤。 |
| 输入/过程/结果 | MATCH | 每项展开的真实检查在紧凑 2×2 证据网格中展示输入、可观察的复核逻辑/过程、结果和裁决。 |
| 裁决 | MATCH | 包、分组、检查层级的状态具有明确视觉区别；已接受事实保持 PASS。 |
| 异常模式 | INTENTIONAL_REAL_DATA_DIFFERENCE | 参考有两项已解决演示异常。已接受 Review 有 54 项 PASS 检查，且无检查关联的纠正/重规划关系，因此当前如实呈现无待处理项。 |
| 阶段 03 复核 | MATCH | 当前阶段 03 直接嵌入共享完整复核组件，并添加权威 Review Gate 状态。 |
| 复核 → C 交互 | INTENTIONAL_REAL_DATA_DIFFERENCE | 参考演示提供事件 ID。当前结果工作区明确报告 `EXACT_REVIEW_EXECUTION_RELATION_NOT_OBSERVED`；展示不可导航的已观察状态，不捏造事件。 |
| 响应式/溢出 | MATCH | 复核网格在 760px 以下折叠为单列；长作用域主体标识换行，不造成页面横向溢出。 |

## 验收

- 结构性实质偏移：**0**
- 轻微视觉偏移：**1**（受约束的精确 Run 页头密度）
- 有意真实数据差异：**3**（54/4/0 摘要、零关联异常、无精确 Review→C 关系）
- V17 复核对齐程度：**HIGH** — B 和阶段 03 展示相同、业务可读的复核事实；唯一不可用交互被明确说明而非捏造。
