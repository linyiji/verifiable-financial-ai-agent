# Research Memory 与增量研究

[English](RESEARCH_MEMORY.md)

已发布研究 → 类型化 Memory → 增量 Scheme → Refresh / Revalidate / Prevent → 新的已发布结果 → 新 Memory 视图 → Base vs Current。

只呈现受支持的持久化项目。已验证指标／主张必须具有实际的证明状态；发布本身并不意味着所有内容都已验证。未观测到的类别保留为 NOT_OBSERVED。零复用也是有效结果。

以下三种身份绝不能混淆：

| 字段 | 含义 |
| --- | --- |
| base_run_id | 作为知识基线使用的、此前处于 RELEASED 状态的研究 |
| scheme_id / fingerprint | 精确的、已确认的研究意图 |
| reexecution_of_run_id | 适用时，指向前一次失败的执行尝试 |

新研究会产生新的证据、计算、审查和报告。它不会继承历史批准。比较使用公式、期间、单位、主张类型等精确逻辑键。无法匹配的问题仍分别保留为历史／新增问题，不会被强行归为虚构的等价项。

已验收的当前对象具有 View v2：一个已验证指标、一个已验证主张，以及一个已解决的期间问题，并与保留的 v1 进行比较。这一闭环已经实现；完整 Evaluation/POT 属于另一项未来工作。

浏览历史只读页面不会触发 Memory 写入。现有活跃增量研究从非终态变为 RELEASED 时的观测，仍保留明确的发布触发器。失败的或重复的终态投影不会仅因被打开就创建新视图。

[产品源码](../../src/phase4_product) · [当前状态](../product/PRODUCT_STATUS.zh-CN.md)。
