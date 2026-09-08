# Phase 5B 单次实时 R2 — 因运行时失败停止

[English](PHASE5B_SINGLE_R2_RUNTIME_BLOCKER.md)

起始 SHA：c4a80adc1db8c83551ee8e3d97442f3a3568450b。phase4 分支干净。完整纵向切片未通过，因此无最终提交 / 标签 / 推送。实时尝试前的实现修改保留未提交，供审阅。

## 精确确认

Draft DRAFT-036cd4bd-fb8b-4c05-a9ba-25c654588342，版本 1。Scheme SCHEME-b7a81dfc-7863-59e2-afd2-0371e796a1b6。哈希 sha256:543ea7eda59287104b3cb1c2c1ca2f19da256aaa60359a3b6fa39876ab7ebf21。授权 LEASE-0e2bb5a10755b04f754bb905e1b5a8a004676c6fcbd1735ce1e92492f15a9bcf 在确认时有效；生效到期时间 2026-09-07T10:39:17.555353Z。草案于 2026-09-07T10:30:13.187274Z 被准入 ADM-315545cb-c617-45bc-ba04-b316a2c1fcf8 消耗。

实际可写应用启用运行时 worker，仅为 Incremental Scheme / 图组装选择 mimo-direct。既有 TeamoRouter 运行时策略不变。产品浏览器访问 OBJ-NVDA Memory v1，加载精确续期 Draft，并点击确认一次。不 prepare，不生成 Scheme。

图规划器在实时调用前配置为一次验证尝试和安全拒绝行为（错误输出不确定性回退）。类型化图、依赖 / skill 检查及增量新工作约束通过。然而，既有验证器不强制可执行已注册 Agent 身份：生成图并未完全兼容运行时。不能将其准入视作完整可执行图契约通过的证明。

## 观测到的供应商证据

图逻辑调用 a264db61-4d74-4dc6-acf5-bfe994082fd5：mimo-direct / mimo / mimo-v2.5，一次逻辑调用、一次 HTTP 尝试、HTTP 200，2026-09-07T10:29:53.766790Z–10:30:13.182990Z，19.416177 秒，2846 输入 token / 758 输出 token。无重试或回退。

之后 fundamentals 任务上的一次 TeamoRouter 逻辑调用也成功：gpt-5.6-sol、HTTP 200、一次尝试、10.351366 秒、1348 输入 token / 343 输出 token。此 R2 没有供应商超时证据。旧客户端没有 runtime-profile 路由元数据，不要编造。未静默迁移至 MiMo。

## 保留的 R2 与窄范围阻塞

R2 = RUN-e1b27d55-a58f-428d-b98b-0dc519577bc0。Object OBJ-NVDA，Base RUN-57aed683-75d6-4b47-acc6-a73053ea492e，Base View RVV-05bec42f-ab9b-55c5-b502-c439b8abe948。新 LLM 图含九个独立标识任务。Run 于 10:30:13.254184Z 启动，10:31:25.561199Z 失败。终止事件序号 606：TASK_EXECUTION_FAILED / TASK_EXECUTION。Peers、research-news 和 fundamentals 失败；依赖任务被阻止。

持久化规划任务的 assigned_agent 使用人类标签（Fundamental Analysis Agent、Peer Analysis Agent、Research News Analysis Agent 等）。实际运行时注册身份为 fundamental_analyst、peer_analyst、research_news_analyst、valuation_analyst、risk_analyst 和 research_lead。src/application/execution.py 调用 registry.get(task.assigned_agent)，生产注册表非空时对未知 ID 抛错。图 schema 仅要求 assigned_agent 为非空字符串。这是只读检查发现的具体分派契约不匹配。持久失败事件仅保留 TASK_EXECUTION_FAILED，没有详细原始异常堆栈。

未修复失败 Run、重写图、第二次图调用、续期租约、创建替代 Run、切换供应商或重试。已消耗草案不能再次确认以创建新 Run。

## 事实与产物

不可变草案仍等于原始 MiMo 能力产物。已确认 Scheme 除 confirmed_at 外与原始 Scheme 相同；Goal 相同。决策及精确来源仍为 0 REUSE / 1 REFRESH / 1 REVALIDATE / 1 PREVENT / 0 UNKNOWN。

R2 聚合保留 536 条证据、10 个计算、一个纠正和零个 Agent 输出。不存在 Review、Proof、canonical record、Report、ReleasedResult 或 Memory v2。此前全部 Run ID 不变，恰好新增一个 ID；R1 和 Object/View v1 指纹不变。最新记忆仍为精确 R1 / View v1。未尝试回写或 Base-vs-Current 发布比较。

浏览器显示精确失败 R2 及失败 / 阻塞任务。未到达完整生命周期 01–05 和 A/B/C 验收。部分既有终止状态文案在明确 FAILED 标记旁仍称研究完成；这是次要产品文案问题，不证明研究结果成功。

浏览器观察器在成功导航后无法读取 POST 响应正文，最终断言失败。这是观察失败，不是准入失败：服务器记录 HTTP 201、页面导航到精确 R2，且持久消耗 / 准入 / Run 记录确认成功。绝不能为了补齐响应产物而重跑受保护确认脚本。

证据目录：artifacts/phase5b_live_r2_final。永久确认保护、确认前审阅、截图和仅安全元数据 attempts.json 保留。94 项专项 Python 测试和 58 项前端检查通过，另有早前 35 项规划器 / 增量测试；计数重叠，因此专项回执仅计 152。类型检查 / 构建通过。完整端到端验收未通过。

产品理解：记住的 R1、精确来源、决策含义及 REUSE0 可见。独立 R2 身份和失败运行时可见。未到达成功 R2 Results、Base-vs-Current v2 和累积的已发布 Memory v2。

NEXT_EXACT_ACTION = PHASE_5B_RUNTIME_BLOCKER_REPAIR。STOP。
