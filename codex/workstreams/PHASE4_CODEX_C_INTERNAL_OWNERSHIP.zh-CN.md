# Phase 4 Wave 1 — Codex C 内部职责

[English](PHASE4_CODEX_C_INTERNAL_OWNERSHIP.md)

状态：`LOCKED`

本文件仅适用于 Codex C Run Snapshot / SSE / Research Path 工作树。
主协调方授权的 Git 引用前缀恢复将计划分支 `phase4/run-sse` 映射到实际分支 `p4-run-sse`；工作树仍为 `<workspace-root>/run-sse`。

## 已记录前置条件

- 主协调方就绪：`YES`
- Wave 1 就绪：`YES`
- Wave 1 工作树就绪：`YES`
- Wave 1 职责锁定：`YES`
- 已识别共享热点文件：`YES`
- 基准 SHA：`4b6721b6db433aae300f94750e1a405b6b450501`
- 基准树：`35c47508ed65220c26620f5ec4bdd14cb798480d`
- 初始工作树状态：`CLEAN`

## 单一写入者映射

### Codex C 协调者

- 本职责记录与最终 C 交接/事件支持矩阵；
- 已批准基线的实体化提交；
- `apps/web/src/state/runtimeEventReducer.ts`（C 共享语义汇合点）；
- 多名 C 专家需要同一 C 所有文件时，仅做集成层协调；
- 仅主协调方可实施的语义补丁提案。

### C1 — SSE 运行时

- `contracts/events/runtime_event.schema.json`
- `src/domain/runtime_event.py`
- `apps/web/src/runtime/RuntimeTransport.ts`
- `apps/web/src/runtime/SSERuntimeTransport.ts`
- `tests/unit/test_phase4_event_contract.py`（如需要则新增）

### C2 — 恢复/对账

- `src/application/events.py`
- `src/runtime/events.py`
- `src/runtime/sse.py`
- `src/runtime/checkpoint.py`
- `src/infrastructure/database/postgresql_events.py`
- `src/infrastructure/database/checkpoints.py`
- `tests/unit/test_phase4_sse_recovery.py`（如需要则新增）

### C3 — 研究路径

- `src/runtime/state.py`
- `src/runtime/graph.py`
- `src/runtime/lifecycle.py`
- `src/runtime/scheduler.py`
- `apps/web/src/components/research-path/ResearchPath.tsx`
- `apps/web/src/components/tasks/TaskDetailDrawer.tsx`
- `tests/unit/test_phase4_research_path.py`（如需要则新增）

### C4 — 动态路径/验收

- `apps/web/scripts/runtime-reducer.test.mjs`
- `tests/unit/test_phase4_dynamic_path_acceptance.py`（如需要则新增）
- 只读审查所有 C1–C3/协调者实现；
- 将负面矩阵与验收发现交还所属写入者，不修改其他负责人的文件。

## 串行化规则

1. 专家不得修改分配给其他专家的路径。
2. 协调者是 `runtimeEventReducer.ts` 的唯一写入者，因为 SSE、恢复、图投影和验收都在这里汇合。
3. 在语义修改前，通过仅包含基线的提交，从 `d854c97789c98cca14fee3f4b3d7f00e0d5d137a` 逐字节实体化基线前端文件。
4. 不修改 `PARENT_ONLY` 路径，包括 API 路由、前端根组合、共享契约类型、包/锁/配置文件和 `ResearchRunPage.tsx`。所需集成以语义补丁提案返回。
5. 生产代码没有演示/夹具回退，绝不从稀疏事件或 Scheme 内容捏造 Task。
