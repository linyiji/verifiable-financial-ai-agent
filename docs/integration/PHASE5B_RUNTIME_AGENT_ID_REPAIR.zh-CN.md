# Phase 5B 运行时 Agent 身份修复

[English](PHASE5B_RUNTIME_AGENT_ID_REPAIR.md)

确定性修复于 2026-09-07 接受。无实时供应商 / 模型调用，无新生产 Run。此检查点不代表 Phase 5B 完成或实体验收。

## 契约与准入边界

`Task.assigned_agent` 表示规范运行时 Agent ID。生产注册现在只有一个组装权威 `build_research_agent_registry`，从 API 启动原样提取。实际注册表提供规划器描述并验证分配；不存在第二份 Agent ID 允许列表或别名映射。Agent 无显示名时，显示元数据回退为 ID。

共享绑定验证器检查精确注册身份、声明的任务配置兼容性、既有 skill/profile 绑定、Run/task 身份、依赖闭包及无环性、非空图和 Scheme skill 覆盖。原生证据采集仍由应用执行，已注册 Agent 作为归属者；不宣称每个 Specialist 都可通过 LLM 执行采集。该原生 profile 授权与实际证据处理器共享。

模型规划器接收这些描述及规范 ID 指令。无效注册绑定直接拒绝，不纠正调用、不回退。PostgreSQL 确认边界在任何原子准入、事件 / 任务持久化或草案消耗前独立检查绑定（包括自定义规划器）、未变的 Scheme/Goal 及精确 Run 身份。公开失败包含系统定义分类码，而非原始供应商 / Python 异常文本。

保留此前连贯的脏工作：单调用 / 安全拒绝增量图规划、保留草案确认 UI、已消耗的一次性浏览器框架、专项测试及历史阻塞回执。未重跑框架。未修复供应商路由、超时、Scheme 生成或 Memory 决策。

## 确定性证据

- 专项 Python 验收：**206 passed**。覆盖实际生产注册表、历史标签图、规范等价图、未知 / 缺失 / 不兼容 ID、精确规划器描述及隔离 PostgreSQL 事务测试。无效图变体使 Run/task/event/admission/idempotency 计数不变、草案未消耗。有效夹具仅在一次性测试 schema 准入。拒绝 Scheme/Goal 修改、错误 skill、环、空图 / 空注册表。
- 前端：TypeScript `tsc --noEmit` 和 Vite 构建通过。M3/M7-R1/M4/M5/M6：**14 + 6 + 27 + 37 + 35 = 119 checks passed**。
- 扩展诊断套件：在最后新增三个专项修改 / 空图案例前为 **685 passed, 3 failed**。三项失败均从未改动基线 `c4a80adc1db8c83551ee8e3d97442f3a3568450b` 的归档复现：`test_router_preserves_frozen_routes_and_adds_only_phase5a_memory` 预期旧路由列表；两个 `test_top_level_projection_builders` 夹具未通过既有 Calculation-unit 完整性门禁。未更改这些测试或门禁。因此这是专项修复通过，不宣称全仓测试全部通过。
- 范围内 Phase 4.5 dispatch/A-B-C/same-run、Phase 5A Memory、MiMo foundation、incremental Scheme 和 provider-policy 回归在无实时调用下通过。

## 历史安全

Run `RUN-e1b27d55-a58f-428d-b98b-0dc519577bc0` 保持 FAILED。原始规划图逐字保留为类型化测试夹具；规范替代仅存在于测试内存中。生产 Run 清单仍为 37。不进行重试、复活、租约续期、Scheme 重写或草案消耗。

只读验证器：`python -m scripts.verify_phase5b_runtime_repair_history`。比较先前聚合指纹、原草案载荷、已消耗准入绑定、精确规划图、任务状态、事件计数 / 类型分布和已记录致因字段，以及全部 R1/v1 历史指纹。还检查两个 Memory 版本表均无 v2，最新 Memory 仍指向 R1 / 版本 1。下列完整任务 / 事件指纹记录修复时快照；更早诊断仅保存了选定致因事件。

| 产物 | SHA-256 |
| --- | --- |
| R2 聚合 | `5e402fe19eef90df2a853a50619b6aa21772b6dbb2a0e7e718f108db9dd03dc5` |
| R2 任务载荷 | `9069f8af0b4b754d181f1122c9048179202f342872f1cdfbca9e7698adb879cd` |
| R2 事件载荷 | `20f9dddc04ca3cc9d8588243e74d382f715108a64a221f3f138cfee5efb29bb7` |
| 原始草案载荷 | `04df3abd6661341575d7aa47d41ecfe793207e1bae2c791ffc0cb989cfab0dca` |

Scheme `SCHEME-b7a81dfc-7863-59e2-afd2-0371e796a1b6`、Goal 和决策不变（REUSE 0 / REFRESH 1 / REVALIDATE 1 / PREVENT 1 / UNKNOWN 0）。R1 仍为 `RUN-57aed683-75d6-4b47-acc6-a73053ea492e`，精确视图 `RVV-05bec42f-ab9b-55c5-b502-c439b8abe948`，最新版本 1。

供应商因果结论不变：MiMo 图规划在 19.416177208s 成功，TeamoRouter 生成能力在 10.351366s 成功。两者均未导致分派失败。缺陷是已接受的自由文本 Agent 标签契约，随后却执行精确运行时注册表查找。

## 只读重执行审计

`EXISTING_REEXECUTION_CONTRACT = ABSENT`。`ResearchRun` 编码 Scheme/Goal 和成对增量基线身份，但没有 retry/re-execution/supersession/attempt-group 关系。持久化不强制每个 Scheme 一个 Run，但缺少唯一性不等于具备重执行契约。草案确认拒绝已消耗草案；幂等重放返回原始准入，而不是创建替代项。Base Run 标识已发布 R1 Memory，不能重载为失败执行 R2。

建议未来语义：新 Run 显式链接失败 R2 的执行血缘，绑定相同已确认 Scheme 及精确 R1 基线 / 视图。保留失败 R2 及其已消耗草案。本任务未实现该关系。
