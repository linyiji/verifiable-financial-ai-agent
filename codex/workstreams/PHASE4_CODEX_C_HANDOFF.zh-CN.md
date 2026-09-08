# Phase 4 Wave 1 — Codex C 交接

[English](PHASE4_CODEX_C_HANDOFF.md)

状态：`C-OWNED ACCEPTANCE PASS; PARENT INTEGRATION REQUIRED`

- 计划分支：`phase4/run-sse`
- 主协调方授权的实际分支：`p4-run-sse`
- 工作树：`<workspace-root>/run-sse`
- 基准 SHA：`4b6721b6db433aae300f94750e1a405b6b450501`
- 基准树：`35c47508ed65220c26620f5ec4bdd14cb798480d`
- C 实现前置 SHA：`ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86`
- 最终分支 SHA：本交接文档提交后，已签认的 `origin/p4-run-sse` HEAD 记录在最终必需任务输出中。

未修改任何仅主协调方可写的源文件。六个 C 前端文件在语义修改前，已从获批 V17 R2 提交 `d854c97789c98cca14fee3f4b3d7f00e0d5d137a` 逐字节实体化。

## 修改文件

- 前端运行时/路径：`apps/web/scripts/runtime-reducer.test.mjs`、
  `apps/web/src/components/research-path/ResearchPath.tsx`、
  `apps/web/src/components/tasks/TaskDetailDrawer.tsx`、
  `apps/web/src/runtime/RuntimeTransport.ts`、
  `apps/web/src/runtime/SSERuntimeTransport.ts` 和
  `apps/web/src/state/runtimeEventReducer.ts`。
- 事件/运行时后端：`contracts/events/runtime_event.schema.json`、
  `src/application/events.py`、`src/domain/runtime_event.py`、
  `src/infrastructure/database/checkpoints.py`、
  `src/infrastructure/database/postgresql_events.py`、
  `src/runtime/checkpoint.py`、`src/runtime/events.py`、
  `src/runtime/lifecycle.py`、`src/runtime/scheduler.py`、`src/runtime/sse.py` 和
  `src/runtime/state.py`。
- 测试/文档：`tests/unit/test_phase4_event_contract.py`、
  `tests/unit/test_phase4_research_path.py`、
  `tests/unit/test_phase4_sse_recovery.py`、
  `codex/workstreams/PHASE4_CODEX_C_INTERNAL_OWNERSHIP.md`、
  `codex/workstreams/PHASE4_CODEX_C_EVENT_SUPPORT_MATRIX.md` 及本交接。

## 已实现行为

- **快照：** `createRunRuntimeState` 对 B 已解码的一个 `phase4-run-projection/v1` 进行第二次封闭集合检查：Run/Object/Goal/Scheme、计划图和实际图 ID、规范记录、图/任务成员与依赖、路径变化、生命周期、终态标记、投影修订和事件水位。绝不从 Scheme 或事件捏造 Task。
- **SSE：** 精确 `/research-runs/{runId}/events` fetch 流传输、冻结契约头、增量 UTF-8/SSE 解析、类型化公开错误解码、精确同 Run 准入，以及终态游标的零帧闭环。有效 REFRESH 事件立即关闭其流，防止后续帧推进越过待处理原子快照边界。
- **事件：** 完整冻结清单含 55 个原始名称：47 个支持，8 个以 `UNSUPPORTED_BY_FRONTEND` 失败关闭。解码器、身份检查、效果与安全呈现记录在 `PHASE4_CODEX_C_EVENT_SUPPORT_MATRIX.md`。
- **序列/游标：** 仅精确下一序列可应用。规范相同的重放无操作；冲突的重复 ID/序列、未见过的旧帧、缺口、终态后帧、格式错误/不支持帧及错误 Run/Task/图身份既不推进投影也不推进游标。数字游标是规范有符号 64 位字符串；不透明游标必须绑定同一 Run 上已接受的事件。
- **恢复：** 类型化无效/超前游标处理、有界确定性重连退避、流代次隔离、过期但可见的先前投影，以及完整同 Run 快照对账。替换经验证后原子交换；修订、水位、图、终态及全部嵌套身份不得倒退或跨 Run。
- **研究路径：** 仅呈现权威实际图的 Task/依赖，使用完整冻结生命周期映射。任务详情使用安全公开字段，并从状态映射派生终态显示。
- **自我纠正：** 在相同 Task、相同图上投影 `task.self_correcting`；持久纠正详情来自权威替换快照。绝不改变拓扑。
- **重规划：** 待定/拒绝决定不改变拓扑。只有 Lead 批准的重规划事件加上已验证替换快照，才可推进图版本并显示新增 Task/边。不存在专家直接修改图。
- **终态：** 终态事件停止流，并要求同 Run 权威终态替换快照。断连/退避绝不改变 Run 业务状态；无效终态后事件被隔离。
- **安全：** 载荷使用封闭允许列表；事件回执/错误仅保留有界 ID、枚举、代码和不透明 SHA-256 指纹。不暴露提供方载荷、凭据、异常文本、提示词、隐藏推理、财务值或不安全结果定位符。

## 验证

- C 负责的 Python 验收：`51 passed`。
- 精确 Node `24.18.0` 下的浏览器运行时验收：`117/117` 项检查。
- 完整 Python 单元套件：`405 passed`（最终重跑记录在任务输出）。
- 集成套件：`38 passed, 1 Parent-owned legacy fixture failed`，因为它发出 `task.started` 时缺少冻结字段 `attempt: 1`。
- PostgreSQL 模式契约测试：`5 passed`。
- 完整 Python 收集：`519 passed, 1 Parent-owned fixture failed, 11 skipped`；唯一失败仍为上述冻结 `task.started.attempt` 夹具不匹配。
- Ruff lint/format、Python compileall、JSON schema 加载及 `git diff --check`：通过。
- 隔离的严格 TypeScript C 界面：提供下述两个已声明 B 接缝类型后通过。真实 C+B 接缝仍被这两个 B 类型的六项缺少导出诊断，以及一个既有 B 所有 `ErrorEnvelope.resource.type` 赋值诊断阻塞；提供冻结声明后不剩 C 所有 TypeScript 诊断。
- 完整生产构建：未运行，因为本子分支有意不包含主协调方专有的前端引导/包/根组合文件。

## 主协调方语义补丁提案（9）

### C-P01 — 在响应头发送前预检 SSE

```text
SEMANTIC_PATCH_PROPOSAL
target_path: apps/api/routes.py
required_semantic_change: await prepare_completed_run_event_stream before constructing StreamingResponse
required_imports_or_types: prepare_completed_run_event_stream; CursorPreflightError; frozen public error mapper
required_behavior: map INVALID_CURSOR to 400 and CURSOR_AHEAD to 409 before headers; pass prepared.body and merge prepared.response_headers with Cache-Control; preserve terminal-at-cursor zero-frame headers
required_tests: malformed/ahead/foreign cursor envelopes; exact suffix; terminal-at-cursor headers and zero frames
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P02 — 组合精确 Run 前端控制器

```text
SEMANTIC_PATCH_PROPOSAL
target_path: apps/web/src/App.tsx
required_semantic_change: compose B snapshot/data source with C reducer and SSERuntimeTransport for the selected exact Run
required_imports_or_types: B FrontendDataSource and RunProjection; C transport/reducer APIs
required_behavior: snapshot N before SSE N+1; synchronously retain REFRESH as pending, fetch/reconcile one same-Run snapshot, then resubscribe; cancel old subscription on Run switch/unmount; no demo fallback
required_tests: exact Run switch, reconnect, refresh, terminal, and stale callback integration
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P03 — 将 Run 工作区绑定到权威投影

```text
SEMANTIC_PATCH_PROPOSAL
target_path: apps/web/src/pages/ResearchRunPage.tsx
required_semantic_change: consume selected C runtime projection/connection and render the C ResearchPath and TaskDetailDrawer contract
required_imports_or_types: RunProjection; ConnectionState; selectRunProjection; ResearchPath; TaskDetailDrawer
required_behavior: render actual graph Tasks/path changes/terminal state only; expose stale/recovery/failed transport state without changing Run state; no Scheme-derived Task fallback and no Results/V17.1 UI
required_tests: snapshot, recovery, self-correction, replan, terminal, and empty authoritative path rendering
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P04 — 集成研究路径样式

```text
SEMANTIC_PATCH_PROPOSAL
target_path: apps/web/src/styles/research-run.css
required_semantic_change: add scoped layout/state styles required by the C ResearchPath and TaskDetailDrawer markup
required_imports_or_types: none
required_behavior: distinguish active/correcting/blocked/terminal and stale/recovery states accessibly without encoding business truth in CSS
required_tests: production build plus focused visual/keyboard smoke check at desktop and narrow widths
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P05 — 原子/幂等终态最终化

```text
SEMANTIC_PATCH_PROPOSAL
target_path: src/application/service.py
required_semantic_change: route release, failure, and cancellation through one A-owned durable terminal finalizer
required_imports_or_types: RunProjection/event watermark persistence; RuntimeEventType.RUN_COMPLETED and RUN_FAILED; frozen availability/error types
required_behavior: atomically and idempotently publish terminal Run state, projection revision/watermark, availability, and exactly one terminal event; never emit terminal before durable state; emit safe run.failed for post-scheduler failures
required_tests: success/failure/cancellation, crash boundaries, retry/idempotency, restart, terminal snapshot/event closure
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P06 — 有符号 64 位事件行

```text
SEMANTIC_PATCH_PROPOSAL
target_path: src/application/persistence.py
required_semantic_change: change RuntimeEventRow.sequence from SQL Integer to BigInteger
required_imports_or_types: sqlalchemy.BigInteger
required_behavior: persist the complete frozen signed-64-bit sequence/cursor range
required_tests: metadata type assertion and PostgreSQL boundary migration test
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P07 — 有符号 64 位事件计数器

```text
SEMANTIC_PATCH_PROPOSAL
target_path: src/infrastructure/database/models.py
required_semantic_change: change RuntimeEventCounterRow.last_sequence from SQL Integer to BigInteger
required_imports_or_types: sqlalchemy.BigInteger
required_behavior: allocate the complete frozen signed-64-bit sequence range consistently with RuntimeEventRow and the C trigger bigint local
required_tests: metadata type assertion and allocator boundary test
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P08 — 仅追加的序列宽度迁移

```text
SEMANTIC_PATCH_PROPOSAL
target_path: alembic/versions
required_semantic_change: Parent allocates a new append-only revision widening runtime_events.sequence and runtime_event_counters.last_sequence to BIGINT and reinstalls the C allocator function/trigger
required_imports_or_types: Parent-assigned revision/down_revision; install_postgresql_runtime_event_sequence semantics
required_behavior: online-safe upgrade preserves values, constraints, uniqueness, foreign keys, and per-Run next sequence; no existing revision rewrite
required_tests: upgrade from current head with populated rows, allocator continuation, downgrade policy decision, schema inspection
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P09 — 修复并扩展共享运行时集成夹具

```text
SEMANTIC_PATCH_PROPOSAL
target_path: tests/integration/test_runtime_execution.py
required_semantic_change: make legacy public-event fixtures satisfy frozen payloads and cover prepared route behavior
required_imports_or_types: frozen RuntimeEvent payload rules and API client fixture
required_behavior: run.started carries graph version, task.started carries attempt: 1; cursor errors are pre-header envelopes and terminal cursor returns required headers with zero frames
required_tests: existing replay/heartbeat case plus invalid/ahead cursor and terminal-at-cursor route cases
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

## 跨子任务依赖与阻塞

- **后端 A：** 为同 Run 发布完整 `phase4-run-projection/v1`，具备精确身份闭合、权威计划/实际图与 Task、路径变化、单调配对的投影修订/事件水位和原子终态可用性。将 C 的持久事件/检查点存储与 A 的持久事务边界组合。
- **前端 B：** 在 `apps/web/src/types/domain.ts` 增加 `NormalizedRuntimeEventV1` 与完整 `ConnectionState` 联合类型（B 已提供 `ErrorEnvelope`、`RunProjection` 与完整状态映射）；从生产数据源返回精确解码 Run 投影，不使用演示回退。
- **迁移：** `YES`。当前主协调方所有的 PostgreSQL 事件/计数器列是 32 位，而冻结模式/游标接受 `1..9223372036854775807`。C 只将触发器局部类型改为 `bigint`；C-P06 到 C-P08 必须由主协调方实施。
- **权威冲突：** 无。缺少 B 声明、终态事务组合、路由接线及数据库宽度属于集成缺口，而非竞争的冻结契约定义。
- **VS01 已知阻塞：** C-P01/C-P05、B 的两个接缝声明和快照适配器、A 的权威原子快照/最终化器、主协调方迁移决定，以及修复后的共享夹具。Codex C 不宣称 VS01。

未创建新的 Research Run。未实现 Results A/B/C、V17.1 Collaboration、Qiji 或 Phase 5 行为。
