# Phase 5B 调用诊断 — PARTIAL，无 R2 授权

[English](PHASE5B_INVOCATION_BLOCKER_RECEIPT.md)

起始 HEAD `3fc3324c66ca995823f5020b9829d6f5ee9e27a8`，tree `aa6ccb1c0bc3137a448dd4312b873129986dee6f`，分支 phase4，初始干净。HEAD 和冻结标签均未改变。实时验证失败，未满足要求的成功修复提交条件，因此修改保持未提交。

## 架构发现

普通产品 prepare/confirm 使用 ResearchApplicationService 默认值：DeterministicSchemeGenerator 和 ResearchLeadPlanner。初始规划不调用模型。增量 prepare 使用 PlannerProviderSchemeGenerator；confirm 将使用 PlannerProviderResearchLeadPlanner（此处未到达）。

两个模型驱动规划类都先调用 `_complete_before_deadline`，再调用同一 TeamoRouterClient.complete_structured 适配器。运行时专家 / Research Lead 综合也使用该适配器，并在生产中共享同一客户端实例。增量路径没有绕过额外已接受的 HTTP 网关或韧性栈。其差别在于有界上下文 / schema，并拒绝确定性 Scheme 回退。

共享适配器对主 / 回退路由去重，最多两次尝试，采用一秒退避，并在读取超时后重试配置的回退路由。生效生产配置为 connect 10s、read 60s、write 30s、pool 10s、单次截止时间 90s、整体截止时间 180s。策略 dataclass 独立的 45 秒 read 默认值不是生产适配器生效默认值：适配器显式传入 60 秒。这是共享行为，不是增量配置不匹配。未更改超时、路由、调度器、验证或重试。

## 历史证据限制与窄范围变更

首次实时失败保留 READ_TIMEOUT，但无尝试记录。其进程未配置 VFA_PERFORMANCE_PATH。无法恢复实际历史尝试次数、每次时长、回退及供应商排队 / 推理时间。

为既有 INTERNAL 遥测允许列表增加七个数值超时 / 预算字段，并标注既有逻辑调用 span。不改变公开 DTO，不记录提示词 / 供应商正文。新增等价性 / 耗尽测试及一次性受保护的仅规划验证脚本。遥测仍须显式启用；验证明确启用并 flush 既有 Recorder。这改进诊断，不改善供应商可靠性，不将其描述为超时修复。

## 单次实时验证

额外执行一次规划操作。既有适配器在该操作内进行两次 HTTP 尝试。没有第二次逻辑调用或手动重复验证。验证将 Scheme 验证尝试限制为一次，无效输出即停止，同时保留生产传输重试 / 回退，以及相同严格 Scheme schema、上下文构建器和验证器。

逻辑调用：`9c1245c4-4218-4d61-9c4c-6ea6099670cc`。供应商：teamorouter。请求主模型：gpt-5.6-sol。

| 阶段 | UTC 开始 | UTC 结束 | 观测时长 | 结果 |
| --- | --- | --- | --- | --- |
| 主路由 gpt-5.6-sol | 08:12:59.184 | 08:14:00.152 | 60.968s | READ_TIMEOUT |
| 退避 | 08:14:00.152 | 08:14:01.154 | 1.002s | 已完成 |
| 回退路由 gpt-5.6-luna | 08:14:01.154 | 08:15:01.935 | 60.781s | READ_TIMEOUT |

所有时间均为 2026-09-07。总逻辑时长 122.754s，低于 180s 截止时间。两次尝试均未返回完整 HTTP 响应。实际服务模型、schema 接受情况、供应商排队 / 推理延迟及上游原因未知。最强分类为 READ_TIMEOUT_ON_PRIMARY_AND_FALLBACK，而非已证明的 schema 拒绝、短暂变慢、重试绕过或整体截止时间不足。最终安全原因为 `INCREMENTAL_MODEL_INVOCATION_READ_TIMEOUT`。

远端 schema 接受情况 NOT_OBSERVED。实时规划 FAIL。Scheme 验证及所有实际实时决策计数 NOT_REACHED。失败不是有效空 Scheme。本任务额度已耗尽，不允许继续供应商调用。

## 安全、验证与停止

脚本只读加载 PostgreSQL 中精确已发布 Object/Run/view，绝不启动应用，也不调用准入或图 / 运行时创建。全部 36 个 Run ID 和 R1/v1 记录前后指纹相同。最新仍为 RUN-57aed683-75d6-4b47-acc6-a73053ea492e / View 1（RVV-05bec42f-ab9b-55c5-b502-c439b8abe948）。未创建 R2 或 v2。

392 项专项测试 / 检查通过：66 项调用 / schema / 策略 / 遥测测试，139 项记忆 / 准入 / 结果 / 安全测试，187 项前端回归检查。类型检查 / 构建及针对性 Ruff 检查通过。供应商推理及排队时间仍为 NOT_OBSERVED；遥测或产品数据未保留原始提示词、响应、凭据或隐藏推理。

证据在 artifacts/phase5b_invocation_repair：attempts.json、result.json、verification-attempt.json（永久禁止重放保护）、history-guard.json。

此前外部操作保持分别计数：一次旧诊断、一次首次实时工作流规划操作，以及此次额外规划操作。三者新增供应商 Research Run 均为零。

LIVE_R2_AUTHORIZED = NO。不提交、打标签、推送或进一步实时操作。NEXT_EXACT_ACTION = PHASE_5B_LIVE_R2_BLOCKER_REPAIR_2。STOP。
