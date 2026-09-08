# Phase 5B — 精确增量研究

[English](PHASE5B_INCREMENTAL_CONTRACT.md)

这是增量添加的规划与记忆切片。使用既有独立 Run 准入、任务执行、复核、证明、报告和发布机制。不重写历史 Run 或版本。不推断 latest/ticker/title 基线。

## 显式基线与有界规划

`POST /api/research-runs/prepare` 可选接收成对的 `base_run_id` 和 `base_research_view_version`（不可变 RVV 身份）。仓库解析该精确 Object/Released Run/view 元组。缺失、外来或未发布来源安全拒绝。新的 as-of 不能早于基线 as-of。

服务器从该视图构建最多 32 条公开决策。不包括历史事件、原始证据 / 供应商正文、私有提示词或隐藏推理。MVP 策略采用：

- REUSE：仅限明确符合条件的上下文来源，绝不自动复用整个视图。
- REFRESH：保留的已验证指标必须在当前 Run 重新获取。
- REVALIDATE：保留的已验证论断必须重新计算 / 复核 / 证明。
- PREVENT：保留的期间不匹配纠正要求期间一致性检查。
- UNKNOWN：没有受支持预防规则的纠正不复用。

每条决策都有精确 R1 来源身份和版本化策略授权。AI 为每条决策提出新的研究方法及适用性 / 工作说明。对指标或论断可选择 REFRESH/REVALIDATE/UNKNOWN，对受支持问题可选 PREVENT/UNKNOWN，对合格上下文可选 REUSE/UNKNOWN。它不能改变来源身份、历史陈述或提升原 UNKNOWN。缺失 / 无效 AI 规划不会静默变为确定性增量验收。生产组装仅对增量请求显式注入 AI Scheme 和任务规划器；普通准入不变。

上下文属于 Scheme 快照，由既有不可变草案哈希及确认覆盖。不扩充或改作他用客户端偏好。

保留的 NVDA v1 包含一个指标、一个论断和一个 PERIOD_MISMATCH 问题。本地已验证预览有零个 REUSE、一个 REFRESH、一个 REVALIDATE 和一个 PREVENT。摘要是有界历史背景，不是虚构的复用项。记忆缺失 / 稀疏时，空类别及零条决策均有效。结构化模型输出使用封闭类型化决策记录，而非开放字典。

## 独立执行

确认通过既有原子准入事务创建新 UUID Run 及新图 / 任务 / 事件。`ResearchRun.base_run_id` 和 `ResearchRun.base_research_view_version` 经普通运行时保存持久化在聚合中。确认重放返回同一准入。已确认 Scheme 保留有界上下文。初始任务不能继承历史证据、输出或结果；其目标保留新获取 / 重新验证 / 预防约束。既有复核 / 证明 / 发布要求不变。

## Memory v2 与比较

独立发布后，既有显式物化端点使用持久化 R2 基线关系作为推进授权。在 Object 行锁下检查预期当前 Run/view、发布状态、Object 归属及连续版本。ObjectVersion、ViewVersion 和指针一同提交。任何阶段后注入失败都使 v1 保持当前。数据库不可变版本触发器保留。

返回记忆包括精确基线快照、已确认增量上下文和受治理比较行。指标键使用 category、formula、capability、period、period basis、actuality、unit 和 currency；论断键额外使用 claim type。不猜测重复 / 未知键。相等的已验证指标值为 UNCHANGED；独立验证的相等论断为 REVALIDATED；不相等值为 UPDATED。未匹配项为 NEW 或 REMOVED_FROM_CURRENT_VIEW。已解决问题没有通用跨 Run 逻辑等价性，即使措辞相似，也保持精确未匹配引用。REMOVED 表示当前视图中不存在，绝不是删除历史。

新增可选序列化字段在缺失时省略，以保持冻结历史传输载荷和草案哈希兼容性。严格前端解码器验证 Object/base/view/decision/change 身份及安全公开边界。当前和历史来源按钮保留精确 Run 和报告锚点导航。

## 验证与配额

测试覆盖策略、精确身份、草案哈希、来源隔离、AI 提示绑定、独立任务创建、真实隔离 PostgreSQL prepare/confirm 重放、原子 v2 并发 / 回滚、不可变 v1 及公式键比较。`scripts/accept_incremental_research.mjs` 记录预检、一次受保护实时工作流及最终浏览器验收。`scripts/phase5b_history_guard.py` 对 R1/v1 生成指纹并盘点 Run ID，不导出原始历史正文。

Phase5B 额度为一个新供应商 Research Run。首次启动接线错误发生在供应商调用或 Run 创建前；其窄范围组装修复及重验另行记录。真实 R2 失败必须停止该切片，使 v1 保持当前，绝不能自动引发替代 Run。
