# 产品导览

[English](PRODUCT_WALKTHROUGH.md)

1. **Research Object：** 选择公司；查看 Overview、Current Research View、Memories、Compare 和 Research Records。
2. **Goal 与 Scheme：** 说明研究问题和截至日期。在确认前，生成并审查精确的 Scheme。这些是真实操作，不是演示者控制按钮。
3. **AI Research：** 检查 Lead／专业 Agent 任务以及计划路径与实际路径。纠错用于处理具体问题；重新规划则在明确权限下改变研究工作。
4. **Results A/B/C：** 阅读报告，检查财务审查项目及其公开输入／过程／结果／判定，然后打开可用的执行贡献。
5. **Recovery：** 区分供应商超时与研究缺陷。同一 Run 内的回退只能在策略批准后、剩余预算范围内执行。
6. **Memory：** 发布后，查看已持久化的已验证指标／主张和已解决问题。系统不会虚构 NOT_OBSERVED 类别。
7. **增量研究：** 保留此前已发布的知识基线，确认新的研究意图，执行 refresh/revalidate/prevent，再比较新的已发布视图。

已验收的截图谱系包括一份已发布的初始研究（v1）、历史失败尝试，以及一次较晚的已发布执行（v2）。知识谱系与执行尝试谱系是不同概念。[图库](screenshots/PROVENANCE.zh-CN.md)中的五张图片来自实际持久化结果，并非为了编写这份文档而执行的实时 Run。

报告来源／贡献映射为部分覆盖；完整 Claim Trace 抽屉和延期 PDF 功能不可用。财务验证是有界的，并不构成对投资适用性的全面验证。

## 独立金融分支与默认对象

独立金融分析并行执行；单项数据不足进入限制记录，不阻断无依赖结论。当前金融扩展采用最多三个并发分支；这不表示所有 Agent Task 都完全并行。每个已校验计算独立持久化。缺少输入的指标记录 INSUFFICIENT_DATA，不产生数值或依赖结论；真正的执行错误仍然失败。Task 可以带结构化限制完成。

默认一般研究的技术分支为 SUPPORTING；Scheme.calculation_requirements 中显式指定的规范能力 ID 为 REQUIRED。既有完整公式集合的 Financial Review / Proof / Release 规则保持不变：任务继续不等于可以发布，缺项仍可能阻止最终 Release。任务详情展示分支状态与可用/所需输入数。当前改动尚未获得新版本实机发布验收，不应宣称 Alpha 2 已发布。

PostgreSQL 迁移后，产品 API 启动会幂等创建空的 NVIDIA / NVDA Research Object，现有同 ticker 对象保持不变。不会初始化任何 Run、Scheme、证据、报告或 Research Memory，也不调用 provider。BYOK / Owner gateway 的凭证和部署边界没有改变。
