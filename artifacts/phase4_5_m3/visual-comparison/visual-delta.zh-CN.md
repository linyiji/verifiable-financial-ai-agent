# Phase 4.5 M3 — V17 HTML ↔ 当前界面视觉差异

[English](visual-delta.md)

## 比较依据

- 参考：`financial_agent_workspace_v17_1_minimal_c_execution_fanin.html`
- 参考 SHA-256：`1be45091827c6485b624f6a44bf2e0f48bc650836b1a15024a3f7c395718762e`
- 所要求的 `(3)` 文件不存在。上述规范文件与现有 `(1)` 副本及此前交接副本逐字节一致，因此属于同一参考资产。
- 当前：`/results/report` 上精确的已接受 Run `RUN-57aed683-75d6-4b47-acc6-a73053ea492e`。
- 桌面截图：Chromium，1440 × 900 CSS 像素，100% 缩放，匹配相同语义的报告区域。
- 响应式检查：760 × 900 CSS 像素；参考和当前界面均未出现文档横向溢出。

## 截图集

参考：

- `reference/REF-A1-report-top.png`
- `reference/REF-A2-source-map.png`
- `reference/REF-A3-financial-section.png`
- `reference/REF-A4-interaction.png`
- `reference/REF-A5-responsive.png`

当前：

- `current/CUR-A1-report-top.png`
- `current/CUR-A2-source-map.png`
- `current/CUR-A3-financial-section.png`
- `current/CUR-A4-execution-focus.png`
- `current/CUR-A5-responsive.png`

## 视觉差异矩阵

| 区域 | 参考 | 当前 | 匹配 | 差距 | 处理 |
|---|---|---|---|---|---|
| 外壳 | 深色研究导航、固定顶部上下文、居中内容 | 由 M2 生产外壳保留 | MATCH | 无 | 无 |
| 结果页头 | 标签页前的公司/Run 上下文、状态、操作 | 精确 Object/Run/As-of 身份和发布状态仍在标签页上方 | MATCH | 真实身份替换演示身份 | 保留生产身份 |
| A/B/C 标签页 | 三个等权视图，A 激活 | 层级相同，A 激活，各界面有可用性标记 | MATCH | 如实呈现的可用性标签不同 | 保留后端标签 |
| 报告纸张 | 窄幅居中白色报告纸张 | 940 px 纸张、桌面内边距 42/46 px、印刷式阴影 | MATCH | 无 | 无 |
| 报告页头 | 研究眉题、公司标题、元数据、强分隔线 | 层级与字体匹配，使用精确发布元数据 | MATCH | 省略评级/目标块 | 继续省略；不具备权威来源 |
| 关键指标 | 突出的横向指标条 | 精确类型化的 Revenue Growth、EBITDA Margin、FCF Margin | INTENTIONAL_REAL_DATA_DIFFERENCE | 真实指标替代演示投资观点指标 | 保留精确 DTO 值 |
| 来源图 | 纸张内的专家 → 综合/主张 → 报告流 | 一项精确的 Fundamental Analyst 贡献 → 已发布主张 → 最终报告 | INTENTIONAL_REAL_DATA_DIFFERENCE | 删除仅存在于演示的来源卡 | 明确保持 PARTIAL |
| 财务章节 | 纵向章节、表格式财务行、复核操作 | 收入/盈利/现金行、证明状态、精确复核操作 | MATCH | 多期预测表不可用 | 保留精确已发布期间的行 |
| 报告交互 | 内容链接打开相关执行上下文 | 来源卡/Revenue Growth 打开精确 C 参与者/输出/事件；返回恢复锚点 | MATCH | C 有意保持 M3 最小形态 | 仅在 M5 扩展 |
| 响应式/溢出 | 窄视口下报告仍可读 | 指标、来源流、行和标签页重排；760 px 无溢出 | MATCH | 无 | 无 |

## 实质性偏移决定

`MATERIAL_VISUAL_DRIFT=NONE`

当前界面保留了 V17 的报告纸张层级、密度、字体对比、报告内来源图、纵向报告流和内容级交互。差异来自冻结的产品权威约束：已接受 Run 的结构化投影没有评级、目标价格、市值/估值预测、同业/估值报告贡献或已生成 PDF。因此不呈现这些仅用于演示的数值和来源卡。

## 有意保留的真实数据差异

- Run 身份是已接受的 UUID Run，而非 `RUN-DEMO-FULL`。
- As-of 为 `2026-09-06`；指标级日期仍使用其类型化来源日期。
- 主指标为精确的 `65.47%`，而非参考中四舍五入的 `65.5%`。
- 来源图明确为 `PARTIAL`，仅含一项权威贡献。
- 报告没有 Buy/目标/上涨空间/同业情景主张，因为 M1 未投影这些内容。
- HTML 是可用的次级导出；PDF 以 `PDF_DEFERRED_MINIMUM_DEMO` 状态禁用。
- C 焦点是安全的精确摘要，而非参考中未来 M5 的完整执行工作区。
