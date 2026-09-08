# Phase 5B — 显式重执行契约

[English](PHASE5B_REEXECUTION_CONTRACT.md)

起始：分支 `phase4`，工作树干净，commit `3cc8d9d7d7713762031564300993efadcbcbad20`，tree `d6595a8020718ce3b2dcb81785ec1f38ae78f1a7`。

## 三种独立身份

- `base_run_id` / `base_research_view_version`：已发布知识基线 R1/v1。
- `scheme_id` / 已确认 Scheme 指纹：不变的已审阅研究意图。
- `reexecution_of_run_id`：直接失败执行前驱，绝不是知识基线。

可选 Run 字段持久化于既有聚合 JSON，由既有重建路径读取，并与两个基线标识一起暴露在既有 Run 详情投影中。不回填历史。首次失败 R2 没有执行前驱，这是正确状态。不存在按时间戳推导的序号、重复别名、尝试计数器或独立尝试组系统。

## 显式授权，不是另一份草案

两个操作扩展既有 Run API 族：

1. `POST /api/research-runs/{run_id}/reexecution-authorizations` 仅接受 `research_object_id` 和 `authorize_reexecution: true`，以及既有契约和幂等头。记录显式本地 Owner 授权，完全在后端解析已确认 Scheme。
2. `POST /api/research-runs/{run_id}/reexecute` 仅接受 `research_object_id` 和 `authorization_id`，以及幂等信息。不接受调用者传入 Goal、Scheme、基线覆盖或可执行图。

授权记录绑定精确前驱 / Object / Scheme 哈希 / Goal 哈希 / Base Run / Base View、本地单用户权限、创建及到期时间。到期使用既有 30 分钟授权窗口；没有续期端点或隐式刷新。授权重放返回相同记录及原始到期时间。原始已消耗 Draft 仅作为经哈希检查的确认证据读取，绝不续期、解除消耗、重写或再次确认。

完整已确认 Scheme 和 Goal 使用既有规范 JSON SHA-256 哈希，在准入时再次比较。存储的 Scheme/Goal 快照必须与失败聚合及原始不可变草案一致。直接前驱链须到达原始已消耗 Run，不得有环、跨 Object 或跨 Scheme 链接。来源必须 FAILED；精确已发布基线和当前 Memory 指针 / 视图仍须一致。同一意图已有 RELEASED 执行时，此路径禁止再授权 / 准入。

## 原子准入与规划器边界

准入使用既有 PostgreSQL 工作单元、全局准入栅栏、权威行锁及待调度 outbox。创建新 Run 和新 Graph，不复用旧无效 Graph。既有增量规划器须配置一次逻辑验证尝试、安全拒绝行为及实际运行时 Agent 注册表。每次准入最多调用该规划器一次，不生成 Scheme，不自动重试验证。

生成后检查精确 Scheme/Goal、新 Run/Graph 身份、规范 Agent ID、profile/skill/dependency 有效性及增量绑定。规划前和准入前均检查到期。图失败不留下 Run、任务 / 事件行、调度准入或授权消耗。未消耗授权持久保留至原到期时间。这不是自动重试策略，也不授权另一次实时模型操作。

新聚合、图记录、任务、事件、独立 `REEXECUTION` 幂等结果、待调度记录和授权消耗一同提交。不创建合成 Draft 准入。精确准入重放返回相同新 Run；不同键不能复用已消耗授权。并发相同请求串行化为一次准入。前端在 POST 失败后停止，不自动重试或 prepare Scheme。

初始 Scheme 生成事件使用既有明确回溯性事件表示；本次执行不生成 Scheme。未来调度处理使用既有 Run 重建与持久化。重执行运行时保存不能重写共享已确认 Scheme。Memory 回写仍要求新 Run RELEASED，并使用新 Run 作为 v2 来源，绝不是失败 R2。

## 增量持久化迁移

`20260907_0011_reexecution_authorizations` 创建授权表、原始和消耗 Run 引用、唯一授权 / 准入键摘要，以及全有或全无消耗约束。触发器阻止授权重定向、消耗重写及既有 Run 执行血缘重写。重执行 Run 的 Scheme/Goal/base 快照在后续更新中也不可变。

迁移已在一次性 PostgreSQL schema 中测试，包含真实触发器拒绝测试。**尚未应用于生产。**未签发生产授权。未来经 Owner 授权的实时切片须先应用迁移 0011，再调用这些端点；应用迁移本身不构成实时 Run 授权。

## 产品行为

失败的增量 Run 提供“重新执行”。首次操作创建显式授权，随后“确认沿用方案并重新执行”提交授权。文案说明保留的研究意图 / 基线及新执行记录。新执行详情链接前一个失败尝试。技术标识符不作为主要按钮标签。错误响应身份阻止导航；抑制双击；错误后停止当前挂载组件的后续提交。

## 验收证据

- 243 项专项 Python 测试通过：241 项范围内后端 / 领域 / 供应商 / Memory / Draft / Graph 测试，加 2 项新增公开边界测试。供应商响应和图规划均为本地夹具；不启动调度器或实时供应商。
- 125 项前端检查通过：6 项用确定性 hook/network 适配器执行实际新组件事件处理器的测试，加 119 项既有 M3/M7-R1/M4/M5/M6 检查。未点击生产浏览器操作。
- 新持久化覆盖：新身份、精确 Scheme/Goal/base 保留、失败历史与已消耗 Draft 保留、单次及并发重放、无效图回滚、注入提交失败、规划调用前到期、错误 Object/Scheme/base/view、未知 / 非失败前驱、链续接、已发布意图排除和数据库不可变性约束。
- TypeScript 类型检查、Vite 构建、范围内 Ruff 和差异空白检查通过。
- 扩展诊断：**710 passed, 2 failed**。`test_top_level_projection_builders.py` 中两个未改动基线测试未通过既有 Calculation-unit 完整性门禁（先前修复回执记录了基线复现）。未弱化生产投影完整性或这些夹具。路由清单测试已更新，涵盖两个显式重执行路由及此前已接受的精确 Draft / 租约路由。

## 历史安全与边界

只读 `python -m scripts.verify_phase5b_runtime_repair_history` 在修复前后通过。生产清单仍为 37 个 Run。失败 R2 保持 FAILED；新授权解析器也仅通过 SELECT（含事务范围授权锁）在精确历史 R2 上通过，随后回滚。未签发授权，未准入。其聚合、精确图、任务 / 事件证据及已消耗 Draft 绑定不变。完整修复时哈希与先前检查点匹配：

- R2 聚合：`5e402fe19eef90df2a853a50619b6aa21772b6dbb2a0e7e718f108db9dd03dc5`
- R2 任务：`9069f8af0b4b754d181f1122c9048179202f342872f1cdfbca9e7698adb879cd`
- R2 事件：`20f9dddc04ca3cc9d8588243e74d382f715108a64a221f3f138cfee5efb29bb7`
- Draft 载荷：`04df3abd6661341575d7aa47d41ecfe793207e1bae2c791ffc0cb989cfab0dca`

R1/v1 指纹不变。最新已发布 Run 仍为 `RUN-57aed683-75d6-4b47-acc6-a73053ea492e`，视图版本 1。两个 Memory 表均无版本 2。历史供应商仍是成功且非致因的操作；本契约修复进行零次供应商 / 模型调用、创建零个生产 Run。

`NEW_RUN_AUTHORIZED = NO`。
`NEXT_EXACT_ACTION = PHASE_5B_FAILED_R2_REEXECUTION_AUTHORIZATION`。
不创建最终 Phase 5B 标签，不推送。
