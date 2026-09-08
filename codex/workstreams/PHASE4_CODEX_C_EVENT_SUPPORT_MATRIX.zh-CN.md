# Phase 4 Wave 1 — Codex C 事件支持矩阵

[English](PHASE4_CODEX_C_EVENT_SUPPORT_MATRIX.md)

契约：`phase4-runtime-event/v1` / 载荷模式 `1`

处置：`47 SUPPORTED`、`8 UNSUPPORTED_BY_FRONTEND`、`0 NOT_APPLICABLE_WAVE1`。
本矩阵遵循最终契约冻结与冻结的 Phase 4 后端事件映射。不接受仅原型使用的别名。

## 验证与效果图例

- `E`：封闭信封；精确契约/载荷版本、事件 ID、精确 Run ID、RFC 3339 UTC 时间戳、正序列、传输 `id == sequence`、传输事件名称、冻结效果、刷新位及允许列表载荷。
- `T`：必须有精确 Task ID，且存在于当前精确 Run 投影。`graph.task_added` 是唯一新增 Task 提示例外；其帧仍不能捏造 Task。
- `G`：要求正图版本。边端点必须是权威同 Run Task ID。图主体始终来自替换快照。
- `PATCH`：仅更新指定且已验证的生命周期/进度覆盖层。
- `REFRESH`：将此前原子投影保留为过期，停止该流代次，获取并验证一个同 Run 替换投影，再原子交换。
- `OBSERVE`：仅保留有界安全事件回执；规范活动详情仍归快照所有，不改变生命周期或财务值。
- `TERMINAL`：要求权威终态替换投影；停止重连。
- 安全呈现限于类型化 ID、枚举/状态值、原因/消息/失败代码、已批准安全消息、时间戳和引用数组。绝不接受或呈现提供方载荷、凭据、文件系统数据、异常文本、提示词和隐藏推理。

## 完整原始事件处置

| 原始事件 | 处置 | 解码器/身份 | 状态效果 | 研究路径效果 | 终态效果 | 安全呈现 |
|---|---|---|---|---|---|---|
| `run.created` | SUPPORTED | E; `{object_id}` | REFRESH | 仅精确快照 | 无 | 仅 Object ID |
| `run.started` | SUPPORTED | E+G; `{}` | PATCH Run=`RUNNING` | 验证后展示权威实际图 | 无 | 仅图版本/状态 |
| `run.status_changed` | SUPPORTED | E; `{status}` 非终态 | PATCH Run 生命周期 | 仅阶段/状态 | 无 | 仅枚举 |
| `run.completed` | SUPPORTED | E; `{status:"RELEASED"}` | TERMINAL | 最终权威路径 | 仅在快照发布闭环后成功 | 仅枚举/终态身份 |
| `run.failed` | SUPPORTED | E; `{status,failure_stage,failure_code,safe_message?}` | TERMINAL | 最终权威路径 | 从状态取得失败或取消 | 仅安全失败字段 |
| `scheme.generation_started` | UNSUPPORTED_BY_FRONTEND | 已声明原始名称，无已批准 V1 载荷 | 零变更/游标推进；恢复 | 无 | 无 | 仅隔离身份 |
| `scheme.generated` | SUPPORTED | E; 精确方案生成字段 | REFRESH | 无直接效果 | 无 | 仅类型化 ID/代码/时间 |
| `scheme.confirmed` | SUPPORTED | E; `{scheme_id}` | REFRESH | 无直接效果 | 无 | 仅 Scheme ID |
| `plan.generated` | SUPPORTED | E; `{graph_id,task_count}` | REFRESH | Task/图仅来自快照 | 无 | 仅图 ID/数量 |
| `task.created` | SUPPORTED | E+T-new; `{task_type}` | REFRESH | 替换可增加权威 Task | 无 | 仅 Task ID/类型 |
| `task.ready` | SUPPORTED | E+T; `{}` | PATCH Task=`READY` | 现有 Task 状态 | 无 | 仅状态 |
| `task.started` | SUPPORTED | E+T; `{attempt}` | PATCH Task=`RUNNING` | 现有 Task 状态 | 无 | 仅尝试次数/状态 |
| `task.progress` | SUPPORTED | E+T; 精确 `PROGRESS` 或 `RETRY_SCHEDULED` 格式 | 仅 `PROGRESS` 执行 PATCH 进度；重试保留进度 | 现有 Task 进度 | 无 | 仅比例/阶段/消息或错误代码 |
| `task.waiting_for_capability` | SUPPORTED | E+T; `{gap_id}` | PATCH Task=`WAITING_FOR_CAPABILITY` | 同一 Task | 无 | 仅缺口 ID/状态 |
| `task.resumed` | SUPPORTED | E+T; `{gap_id,registration_id,status:"RUNNING"}` | PATCH Task=`RUNNING` | 同一 Task | 无 | 仅 ID/状态 |
| `task.self_correcting` | SUPPORTED | E+T; `{problem_code}` | PATCH Task=`SELF_CORRECTING` | 同一 Task/同一图；持久纠正来自快照 | 无 | 仅问题代码 |
| `task.correction_resolved` | SUPPORTED | E+T; `{correction_id}` | REFRESH | 精确纠正/路径变更记录 | 无 | 仅 Correction ID |
| `task.completed` | SUPPORTED | E+T; `{attempt,result_ref?}` | PATCH Task=`COMPLETED`, progress=1 | 现有 Task 终态 | 不终结 Run | 仅尝试次数；安全 V1 适配器不提供内部/结果定位引用 |
| `task.failed` | SUPPORTED | E+T; `{attempt,failure_code,status?,retry_suppressed?}` | PATCH 精确 Task 失败 | 现有 Task 终态 | 不单独终结 Run | 仅失败代码/标记 |
| `replan.requested` | SUPPORTED | E+T; `{replan_id,decision}` | REFRESH | 显示精确待定/决定记录；不推断拓扑 | 无 | 仅 Replan ID/决定 |
| `replan.approved` | SUPPORTED | E+T; `{replan_id,decided_by}` | REFRESH | 使用 Lead 授权替换图 | 无 | 仅 ID |
| `replan.rejected` | UNSUPPORTED_BY_FRONTEND | 已声明原始名称，无已批准 V1 载荷 | 零变更/游标推进；恢复 | 无拓扑效果 | 无 | 仅隔离身份 |
| `graph.task_added` | SUPPORTED | E+G+T-new; `{replan_id}` | REFRESH | 只有替换图包含 Task 时其才存在 | 无 | 仅 ID/版本 |
| `graph.edge_added` | SUPPORTED | E+G+T; 精确源/目标 Task 引用 | REFRESH | 边仅来自替换图 | 无 | 仅 ID/版本 |
| `graph.edge_removed` | SUPPORTED | E+G+T; 精确源/目标 Task 引用 | REFRESH | 边仅来自替换图 | 无 | 仅 ID/版本 |
| `graph.version_changed` | SUPPORTED | E+G; `{replan_id,version_before}` | REFRESH | 一个原子权威图版本 | 无 | 仅 ID/版本 |
| `evidence.accepted` | SUPPORTED | E; 安全 Evidence 允许列表；可选生产者 Task 必须属于精确 Run | OBSERVE | 仅推进安全事件回执；权威活动详情仍归快照所有 | 无 | 仅已批准 Evidence 字段 |
| `evidence.conflict` | UNSUPPORTED_BY_FRONTEND | 已声明原始名称，无稳定 V1 载荷 | 零变更/游标推进；恢复 | 绝不推断 Review/路径状态 | 无 | 仅隔离身份 |
| `calculation.started` | SUPPORTED | E+T; `{capability_id}` | OBSERVE | 仅回执；活动详情仍归快照所有 | 无 | 仅 Capability ID |
| `calculation.completed` | SUPPORTED | E+T; `{calculation_id,capability_id?}` | OBSERVE | 仅回执；无财务值 | 无 | 仅 ID |
| `capability.gap_detected` | SUPPORTED | E+T; 精确缺口/能力/技能/请求者 ID | OBSERVE | 仅同 Task 回执 | 无 | 仅 ID |
| `capability.build_requested` | SUPPORTED | E+T; 精确 ID/尝试上限/批准者 | OBSERVE | 仅同 Task 回执 | 无 | 仅 ID/计数 |
| `capability.build_started` | SUPPORTED | E+T; `{build_id,attempt}` | OBSERVE | 仅同 Task 回执 | 无 | 仅 ID/计数 |
| `capability.generated` | SUPPORTED | E+T; 安全构建/能力/哈希字段 | OBSERVE | 仅同 Task 回执 | 无 | 仅 ID/哈希 |
| `capability.static_validated` | SUPPORTED | E+T; `{build_id,implementation_hash}` | OBSERVE | 仅同 Task 回执 | 无 | 仅 ID/哈希 |
| `capability.sandbox_started` | SUPPORTED | E+T; `{build_id,implementation_hash}` | OBSERVE | 仅同 Task 回执 | 无 | 仅 ID/哈希 |
| `capability.test_passed` | SUPPORTED | E+T; `{build_id,implementation_hash}` | OBSERVE | 仅同 Task 回执 | 无 | 仅 ID/哈希 |
| `capability.test_failed` | SUPPORTED | E+T; `{build_id,attempt,failure_code}` | OBSERVE | 仅同 Task 回执 | 无 | 仅 ID/计数/代码 |
| `capability.financial_validated` | SUPPORTED | E+T; `{build_id,implementation_hash}` | OBSERVE | 仅同 Task 回执 | 无 | 仅 ID/哈希 |
| `capability.approved` | SUPPORTED | E+T; 精确构建/注册/批准者/范围 | OBSERVE | 仅回执；不恢复 Task | 无 | 仅 ID/范围 |
| `capability.registered` | SUPPORTED | E+T; 精确注册/能力/版本/范围 | OBSERVE | 仅回执；不恢复 Task | 无 | 仅 ID/版本/范围 |
| `capability.build_failed` | SUPPORTED | E+T; 精确安全失败/终态及可选尝试 ID | OBSERVE | 仅同 Task 回执；`terminal:false` 不可使 Task 失败 | 无 | 仅 ID/计数/代码/标记 |
| `workspace.created` | UNSUPPORTED_BY_FRONTEND | 已声明原始名称，无已批准 V1 载荷 | 零变更/游标推进；恢复 | 无 | 无 | 仅隔离身份 |
| `capability.generation_started` | UNSUPPORTED_BY_FRONTEND | 已声明原始名称，无已批准 V1 载荷 | 零变更/游标推进；恢复 | 无 | 无 | 仅隔离身份 |
| `capability.tested` | UNSUPPORTED_BY_FRONTEND | 已声明原始名称，无已批准 V1 载荷 | 零变更/游标推进；恢复 | 无 | 无 | 仅隔离身份 |
| `capability.validated` | UNSUPPORTED_BY_FRONTEND | 已声明原始名称，无已批准 V1 载荷 | 零变更/游标推进；恢复 | 无 | 无 | 仅隔离身份 |
| `review.started` | SUPPORTED | E; `{}` | REFRESH | 无直接效果 | 不终结 Run | 状态仅来自快照 |
| `review.required` | UNSUPPORTED_BY_FRONTEND | 已声明原始名称，无已批准 V1 载荷 | 零变更/游标推进；恢复 | 无 | 无 | 仅隔离身份 |
| `review.resolved` | SUPPORTED | E; `{review_id,status}` | REFRESH | 无直接效果 | 不终结 Run | 仅 Review ID/裁决 |
| `proof.required` | SUPPORTED | E; 精确证明/计算/公式/策略 ID | REFRESH | 无直接效果 | 不终结 Run | 仅 ID |
| `proof.started` | SUPPORTED | E; `{proof_id,backend}` | REFRESH | 无直接效果 | 不终结 Run | 仅 Proof ID/后端代码 |
| `proof.generated` | SUPPORTED | E; `{proof_id,backend}` | REFRESH | 无直接效果 | 生成不等于已验证/终态 | 仅 Proof ID/后端代码 |
| `proof.verified` | SUPPORTED | E; 精确 proof/image/receipt/journal/verified/dev 字段 | REFRESH | 无直接效果 | 不终结 Run | 仅 ID/哈希/标记 |
| `proof.failed` | SUPPORTED | E; `{proof_id,failure_code,status}` | REFRESH | 无直接效果 | 不单独终结 Run | 仅 ID/代码/状态 |
| `release.completed` | SUPPORTED | E; `{canonical_record_id,result_id}` | REFRESH | 从替换中展示发布状态 | 明确非终态 | 仅精确已发布 ID |

## 失败关闭规则

未知名称、八个不支持名称、不兼容版本、格式错误载荷、错误 Run/Task/图关系、冲突重复、未见过的旧事件、缺口和终态后事件都导致零业务变更与零游标推进。客户端执行精确同 Run 快照恢复时，先前已验证投影仍作为过期状态可见。
