# Phase 6 Evaluation 数据契约 V1

[English](PHASE6_EVALUATION_DATA_CONTRACT_V1.md)

状态：**父任务冻结的准备契约**，2026-09-08。仅文档；未实现新运行时模型、表、API、提取器、评分或路由策略。既有存储 / API 及安全保留遥测足以支持 R5 纵向切片。基线：`85962ecb9148c5a93bfd855ee6bffe554967db9b`。配套[Alpha 依据](USER_ALPHA_READINESS.zh-CN.md)和 [R5 验收](PHASE5B_R5_ADAPTIVE_ACCEPTANCE.zh-CN.md)。

## 1. 评估对象、身份与证据纪律

`EvaluationObservationV1` 是未来调用的只读投影，以既有 `(run_id, task_id, attempt_id)` 为键。规范尝试身份为 `RecoveryEvidence.attempt_id`（`ATT-UUID`），不是新 evaluation ID。`record_id`（`REC-UUID`）标识账本事件。仓库当前**没有**名为 `TaskExecutionAttempt` 的独立类型 / 表。

按精确 ATT ID 及完整 Scope 配对 ATTEMPT_STARTED 和 ATTEMPT_COMPLETED，并保留两个 REC ID。DECISION/TERMINAL 事件是单独关联的证据，不是假尝试。缺少完成表示不完整 / 未知，不预设失败。冲突 scope、重复且冲突的完成记录或歧义关联均隔离，不静默合并。不要给旧 Run 回填 ATT ID。

每个承载证据的字段都使用以下封装，包括可选字段和派生分组键。投影 schema / 版本标签是元数据，不是证据。

```text
EvidenceValue<T> {
  value: T | null
  evidence_class: OBSERVED | DERIVED | NOT_OBSERVED
  source_refs: [{authority, run_id?, record_id?, field_path, artifact_digest?}]
  derivation: null | {rule_id, definition, input_refs}
  missing_reason: null | closed missingness code
  native_classification: null | source classification, when different
}
```

- OBSERVED = 标识明确的权威来源实际记录的值。运行时分类器的观测分类不证明供应商 / 代理根因。
- DERIVED = 有显式输入 / 规则的确定性结果，不是猜测的质量。
- NOT_OBSERVED 要求 `value=null`，绝不是 `0`、`false`、空成功或猜测枚举。缺失代码：`ABSENT_SOURCE_FIELD`、`NO_EXACT_JOIN`、`NO_BILLING_AUTHORITY`、`NO_DIRECT_QUALITY_LINK`、`LEGACY_NO_ATTEMPT_LEDGER`、`NOT_APPLICABLE`、`NOT_YET_COLLECTED`。须说明适用哪一项。
- 引用的权威来源内部可能包含私有材料；导出字段只能是允许列表中的 ID / 代码 / 哈希 / 数值及范围限定的安全证据。不含提示词、原始响应、草稿推理、CoT、凭据、连接 URL 或敏感反馈。
- 不新增供应商：使用既有 RouteId/ModelId 注册约定。

## 2. 最小字段契约与当前权威来源

除非另有说明，路径指向既有 `src/domain/recovery.py` 类型。

| 字段 / 组 | 当前来源 | V1 分类 / 语义 |
| --- | --- | --- |
| run_id, task_id, object_id, scheme_id, task_profile, agent_id | RecoveryEvidence.scope | OBSERVED 精确身份，不是显示名 |
| context_hash, contract_hash | Scope | OBSERVED 存储完整性哈希；contract_hash 是 response-model JSON schema 哈希 |
| base_run_id, base_research_view_version, reexecution_of_run_id | 精确 ResearchRun | 通过精确 Run 关联得到 OBSERVED 血缘；知识与执行血缘分离 |
| attempt_id, attempt_number | RecoveryEvidence | OBSERVED；编号按用途独立，不是全局传输计数 |
| invocation_purpose | capability_check | DERIVED：布尔值映射到 PRODUCTION 或 CAPABILITY_CHECK |
| provider_route, provider, model | route/provider/model | OBSERVED 账本路由身份；失败时 model 是尝试身份，不是成功供应商响应 |
| start/completion timestamps, source_record_ids | 配对账本事件 | OBSERVED UTC 字符串 / REC ID；保留原始顺序 |
| attempt_outcome | Completed.outcome | OBSERVED PASS/FAIL/CANCELLED；只有 STARTED 不表示成功 / 失败 |
| failure_class | Completed.failure_class | 存在时为 OBSERVED 系统定义 FailureClass；成功时缺失为 NOT_APPLICABLE |
| failure_stage, recoverable | 匹配 DECISION.recovery_context.failure | 只有精确同 Scope 失败关联时才是 OBSERVED 分类器值 |
| attempt_latency_ms | Completed.latency_ms | DERIVED 单调经过时间测量，规则 LATENCY_MONOTONIC_MS_V1；保留源数值 |
| input_tokens, output_tokens | Completed usage | OBSERVED 供应商报告的成功用量；缺失失败用量保持 null |
| output_hash | Completed.output_hash | OBSERVED 摘要；能力输出哈希不是生产 AgentOutput |
| recovery_action, policy_decision | DECISION.action/outcome | OBSERVED 封闭 Action 及 ALLOW/DENY；保留 REC 引用 |
| candidates, capability status/evidence | RecoveryContext.candidates | OBSERVED 历史快照及 capability_evidence_refs，不用当前状态倒替历史 |
| remaining budget and decision reason | RecoveryContext + RecoveryDecision | OBSERVED 快照；不扩大预算或修改策略 |
| terminal_reason | TERMINAL.reason_code | 存在时为 OBSERVED；不从缺失历史合成耗尽 |
| logical_latency_ms | ResearchAgentOutputRecord.duration_ms | OBSERVED 已记录完整 Agent 时长；scope 为 AGENT_INVOCATION，不是最后一次尝试时长 |
| transport latency/retry/backoff/stage | 仅无歧义关联的安全性能 span | OBSERVED 原生字段；跨源关联为 DERIVED 或 NO_EXACT_JOIN |
| cost | 无计费权威来源 | NOT_OBSERVED / NO_BILLING_AUTHORITY |
| universal quality score, route preference | 范围内无权威来源 / 评分 | NOT_OBSERVED / NOT_YET_COLLECTED；绝不从输出文本推断 |
| semantic task-contract version, normalized complexity class | 无通用权威来源 | NOT_OBSERVED；不编造默认值 |
| human feedback | 未来脱敏 Alpha 会话证据 | 收集前为 NOT_OBSERVED；使用独立真人来源及 scope |

延迟约定：恢复运行时记录 `(monotonic_end-start)*1000`。V1 将该计算标为 DERIVED 并注明方法；遥测来源原生 `classification=OBSERVED` 单独保留，不覆盖。不要把逻辑时长加到其中已包含的尝试时长上，避免双计数。失败调用 token 的 null 不是零；仅在来源实际提供时，成功报告的零才是观测值。CER 默认值 `token_usage=0`、`cost=0.0` 和 `latency_ms=0` **不是**测量 / 计费权威来源。

RecoveryContext 不提供显式失败 ATT 外键。将决策失败关联到唯一前置失败完成记录，要求 Scope 和当前路由相同、有界尝试历史及事件顺序一致。该关联标 DERIVED；保留所关联记录中的已观测分类器字段。若有歧义，failure_stage 保持 null，原因 NO_EXACT_JOIN。绝不模糊匹配文本。

## 3. 可靠性与恢复派生（定义，不是评分）

保留原始事件。派生事实需要完整一致的相关证据，否则未知。区分传输回退与 Main-Agent 恢复。

| 事实 | 定义 / 权威来源 |
| --- | --- |
| production_attempt_count | 统计唯一已完成 / 已开始 PRODUCTION ATT ID，分别报告开始及完成数 |
| capability_check_count | 单独 CAPABILITY_CHECK ATT 分母；不计为已完成研究 |
| initial_route_success | 首次生产尝试 PASS，之前无生产失败 |
| timeout/provider_unavailable/protocol_failure | 精确记录的系统失败类；不猜测供应商责任 |
| native_fallback_used / recovered | 仅精确关联传输尝试证据；配置本身不是观测到的回退 |
| main_agent_recovery_used | 同 Scope 已观测恢复 DECISION，含允许操作及关联的后续尝试 |
| provider_switch / model_switch | 独立观测操作，经验证的 route/provider/model 转换 |
| capability_check_recovery | 后续获准执行前，独立检查决策及检查结果 |
| recovery_success | 失败生产尝试 → 获准关联恢复 → 之后同 Task/Run 生产 PASS |
| recovery_failure | 观测到终止失败或耗尽，而非仅缺少完成 |
| budget_exhausted | 实际终止原因 / Gate 证据；缺失时未知 |
| end_to_end_task_attempt_window_ms | 最后成功生产完成 UTC 减首次生产开始；墙钟派生，可能包含检查 / 决策 |
| time_to_recovery_ms | 成功生产完成 UTC 减致因失败完成 UTC；墙钟派生，与前述窗口不同 |
| retry_backoff_ms | 仅记录的关联等待测量；不把配置延迟复制为实测时间 |

分别保留初始及最终结果。恢复成功绝不将原超时改成 PASS。已注册健康不等于能力；后来 VERIFIED 状态不能宣称在更早尝试时已经授权。不在此生成通用费用、质量、可靠性聚合或生产偏好。

## 4. 可比性边界

主要路由切片：`task_profile × provider_route × model`（实际成功身份，或失败时明确尝试身份）。

有界同类组：`task_profile × response_schema_contract_hash × invocation_purpose
× capability_requirement_when_authoritative`。route/model 是兼容同类组**内**的比较维度，不证明无关工作负载等价。能力要求使用实际 task/profile/response-schema 权威，不是新任意标签，也不是路由当前能力状态。

相同精确 Run/Task/Scheme/base/context 是最强配对恢复切片。即使如此，后续尝试仍是在失败后选择：这是观察性恢复证据，不是随机化排名实验。Peer 与 Fundamental 不是可比工作负载。能力检查与生产是不同同类组。仅 schema 哈希相同不证明跨 Run 工作量 / 语义相同。`context_hash` 包含 Run 绑定身份，不是规范复杂度类别。语义版本 / 复杂度未知时，阻止依赖该可比性的声明。

## 5. 质量权威来源与归因

尝试 PASS 通过 `src/agentic/recovery.py` 确立类型 schema / 路由身份 / 安全输出 / 冻结输入验证，不表示财务正确。`typed_output_validation` 从已接受完成路径 DERIVED，附代码基线及完成 REC 引用。仅生成文字不等于质量。

成功**生产**尝试只有在精确 Run/Task/Agent/provider/actual-model 匹配且结构化输出哈希验证通过后，才可关联 ResearchAgentOutputRecord。不确定关联为 NOT_OBSERVED，不采用“最新输出”。能力检查不产生生产 AgentOutput，不能获得任务完成记分。

单独存储限定 scope 的 `run_context`：精确任务状态、Review ID/verdict/check subject_refs 和输入快照、计算 Proof/verification/commitment 引用、纠正 / 重规划引用及 Run 发布状态。Review（`src/domain/review.py`）不是通用 Specialist 评分；Proof（`src/domain/proof.py`）限于计算。没有精确 subject/output 关系时，直接尝试 Review/Proof 质量保持 NOT_OBSERVED / NO_DIRECT_QUALITY_LINK。最终 Run Review PASS、Proof VERIFIED 和 RELEASED 是上下文，**绝不由失败尝试或能力检查继承**。保留来源映射限制，不编造关联。

## 6. 既有证据清单与 R5 映射 — PASS

持久来源：`phase6_recovery_evidence`、类型化 RecoveryEvidenceStore；精确 `GET /api/research-runs/{run_id}/recovery`，携带 `X-Phase4-Contract-Version: phase4-core/v1`。Review/projection/results API 提供独立 Run 上下文。本地已接受导出：`artifacts/phase5b_r5_adaptive/` 下的 `recovery.json`、`performance.json`、`acceptance.json`、`terminal.json`、`memory.json`。无需新提取器。这些文件是本地审计证据，不是可以整包倾倒的公开 API 载荷；仅导出本契约允许列表字段。

精确 R5 `RUN-ab806291-8cbf-4c9b-8852-b6a54f10768d`：

| Profile / 用途 | ATT 身份 | 路由 / 模型 | 结果 | ms | 输入 / 输出 token |
| --- | --- | --- | --- | --- | --- |
| peer_analysis / 生产 1 | `ATT-13ea7340-c990-49aa-99b6-d69225bfe4e7` | mimo-direct / mimo-v2.5 | FAIL READ_TIMEOUT | 60211.85 | null/null |
| peer_analysis / 生产 2 | `ATT-9d0ed2e2-661e-4e92-8749-03afd5d6547e` | teamorouter-sol / gpt-5.6-sol | PASS | 30932.51 | 4174/563 |
| fundamental_analysis / 生产 1 | `ATT-ecc9771a-883c-4c1a-a23a-30a2618e9df5` | teamorouter-sol / gpt-5.6-sol | FAIL READ_TIMEOUT | 60412.33 | null/null |
| fundamental_analysis / 能力检查 1 | `ATT-6b43d504-5a03-42d8-a492-e8d0013dd026` | teamorouter-luna / gpt-5.6-luna | PASS | 13953.18 | 7856/617 |
| fundamental_analysis / 生产 2 | `ATT-75e8de27-e21f-4be4-9d10-64327f29f289` | teamorouter-luna / gpt-5.6-luna | PASS | 35650.23 | 7856/582 |

表列遵循第 2 节证据分类；四舍五入的 ms 是从持久测量 DERIVED 的展示值，不是编造时间。失败用量为 NOT_OBSERVED。两组序列保留相同 Task/Run/Scope 哈希。

Peer 切换：`REC-cb9b362f-f235-45a3-bb02-56ca714c4a7f`，SWITCH_PROVIDER/ALLOW。Fundamental 检查：`REC-4d718d30-f970-4799-801a-a1eac9c22007`，CAPABILITY_CHECK/ALLOW；随后 `REC-8bde5ee9-d492-4776-b723-bd90c68ae01e`，SWITCH_MODEL/ALLOW。Luna 能力由 UNKNOWN，经检查变为 PASS/VERIFIED。Fundamental MiMo 保持 UNKNOWN，checks=0。

23 个账本事件 = 10 个开始 + 10 个完成 + 3 条决策。完成包括 9 次生产尝试（7 PASS、2 FAIL）及 1 次成功能力检查。七个最终 Specialist 输出成功。Run 上下文是 Review PASS/54 项检查、强制 Proof VERIFIED、RELEASED、精确 Memory v2；不是尝试级通用质量标签。尝试窗口时长 91.211766s（Peer）和 110.091807s（Fundamental）包含初始尝试；不要误标为失败后的恢复时间。

性能产物包含 **12 个 model.attempt span**，除 10 次账本调用外，还包含图规划和生成能力构建。传输 UUID 尝试 ID 与恢复 ATT ID 没有直接外键。不要把所有 model span 等同于 Specialist 执行尝试、重复计数检查或按路由 / 时间相似性静默关联遥测。缺失精确关联保持明确。请求 / 响应头的缺失不能证明供应商根因。

## 7. R2/R3/R4 旧证据 — 分类 PASS

旧 Run/task/transport 证据可在既有来源身份下保留为 `legacy_context`，ATT 身份为 NOT_OBSERVED。没有恰当尝试权威来源时，不将其插入 EvaluationObservation 调用或计入尝试分母。缺少新账本记录不表示没有失败。

| Run | 观测权威来源 | 诊断 / 分类 | 评估限制 |
| --- | --- | --- | --- |
| R2 | 持久 TASK_EXECUTION_FAILED / TASK_EXECUTION | DERIVED 已接受诊断：图显示标签与规范 Agent ID 不一致 | 确定性身份缺陷，不是模型质量；原始堆栈未持久化 |
| R3 | 保留性能 / 回执中 Peer/News Sol read_timeout 后 Luna provider_unavailable | 运行时传输 / 可用性；路由 ID 从配置派生，profile 精确关联 Task | 不是语义 / 模型质量失败；缺失 token 为 null |
| R4 | Fundamental Sol 和 Luna ReadTimeout，请求已发送，响应头 / 状态未观测 | 运行时传输 / 可用性；精确上游 / 代理原因未证实 | 独立成功能力构建操作不抹去 Specialist 失败 |

来源：`docs/integration/PHASE5B_SINGLE_R2_RUNTIME_BLOCKER.md`；`artifacts/phase5b_reexecution_authorization/r3-final-receipt.md` 和 `r3-performance.json`；`artifacts/phase5b_specialist_reverify_final/final-receipt.md`。从配置派生的路由须标 DERIVED，不是供应商报告。

## 8. 准备验收与未来实现测试

EVALUATION_DATA_CONTRACT、OBSERVED_DERIVED_NOT_OBSERVED、TASK_PROFILE_COMPARABILITY、RELIABILITY_EVIDENCE、PERFORMANCE_EVIDENCE、RECOVERY_EVIDENCE、QUALITY_EVIDENCE_MODEL、R5_EVALUATION_MAPPING、R2_R3_R4_FAILURE_CLASSIFICATION 和 COST_NOT_FABRICATED = PASS。这表示契约忠实表达现有证据及缺口，不表示所有可选字段都已观测，也不表示 Phase 6 评估引擎已经存在。

未来 Phase 6A 实现须测试精确关联、缺失 / 重复完成、歧义遥测关联、检查 / 生产分母、未知 token、CER 零默认值、跨 profile / 同类组拒绝、Run 质量不归因、旧身份缺陷保留、安全字段允许列表及零写入。仅使用既有证据；测试这些规则不需要实时供应商调用。

POT_IMPLEMENTED = NO；MODEL_PROVIDER_SCORING_IMPLEMENTED = NO；PREFERRED_ROUTE_IMPLEMENTED = NO；LEARNED_ROUTING_IMPLEMENTED = NO。未改变 RecoveryBudget、已注册供应商、财务门禁或历史状态。下一另行授权实现选项：`PHASE_6A_EVALUATION_PLANE`。
