# 07 — 动态运行时、图与事件 V1

[English](07_DYNAMIC_RUNTIME_EVENTS_V1.md)

## 1. 运行时定义

Dynamic Runtime = 状态化执行引擎，不是 Agent。

职责：

- 执行计划图
- 依赖解析
- 并行调度
- 任务状态
- 重试
- 自纠生命周期
- 重新规划生命周期
- 图变更
- 检查点
- 工作区
- 运行时事件流
- 预算／超时

## 2. 计划与实际

Planned 是初始获准路径。

Actual 记录实际发生的过程。

重新规划时绝不覆盖 Planned Graph。

## 3. 调度器

所有必需依赖均为 COMPLETED 时，Task 才是 READY。

MVP 可使用 `asyncio` 实现并行执行。

未来的队列后端不得改变领域事件 schema。

## 4. 检查点

最小检查点：

```text
run status
task states
actual graph version
completed outputs refs
evidence refs
workspace refs
review/proof state
cost
```

## 5. 运行时事件封装

```json
{
  "event_id": "EVT-001",
  "run_id": "RUN-023",
  "task_id": "TASK-A",
  "type": "task.started",
  "timestamp": "2026-09-03T20:31:04+08:00",
  "sequence": 18,
  "payload": {}
}
```

每个 Run 的 `sequence` 应单调递增，以保证 Web 回放可靠。

## 6. 事件族

### Run

- run.created
- run.started
- run.status_changed
- run.completed
- run.failed

### Scheme／规划

- scheme.generation_started
- scheme.generated
- scheme.confirmed
- plan.generated

### Task

- task.created
- task.ready
- task.started
- task.progress
- task.self_correcting
- task.correction_resolved
- task.completed
- task.failed

### 重新规划（Replan）

- replan.requested
- replan.approved
- replan.rejected
- graph.task_added
- graph.version_changed

### 数据／计算

- evidence.accepted
- evidence.conflict
- calculation.started
- calculation.completed

### Capability

- capability.gap_detected
- workspace.created
- capability.generation_started
- capability.tested
- capability.validated

### 保障

- review.started
- review.required
- review.resolved
- proof.started
- proof.verified
- release.completed

## 7. SSE

MVP:

`GET /api/research-runs/{run_id}/events`

功能：

- 通过 `Last-Event-ID` 或序号恢复
- 心跳
- 从数据库回放事件
- 不以前端轮询作为主要方式

## 8. Web 渲染规则

前端任务块 = Task 领域实体。

Skill 步骤属于详情层级，不要把每次函数调用都展开成顶层块。
