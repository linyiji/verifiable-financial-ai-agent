# 07 — Dynamic Runtime, Graph & Events V1

[简体中文](07_DYNAMIC_RUNTIME_EVENTS_V1.zh-CN.md)

## 1. Runtime definition

Dynamic Runtime = 状态化执行引擎，不是 Agent。

Responsibilities:

- execute planned graph
- dependency resolution
- parallel scheduling
- task state
- retry
- self-correction lifecycle
- replan lifecycle
- graph mutation
- checkpoint
- workspace
- runtime event stream
- budget / timeout

## 2. Planned vs Actual

Planned is the initial approved route.

Actual records what really happened.

Never overwrite Planned Graph when replanning.

## 3. Scheduler

A Task is READY when all required dependencies are COMPLETED.

Parallel execution can use `asyncio` in MVP.

Future queue backend must not change domain event schema.

## 4. Checkpoint

Minimum checkpoint:

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

## 5. Runtime event envelope

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

`sequence` should be monotonic per run to make Web replay reliable.

## 6. Event families

### Run

- run.created
- run.started
- run.status_changed
- run.completed
- run.failed

### Scheme / Planning

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

### Replan

- replan.requested
- replan.approved
- replan.rejected
- graph.task_added
- graph.version_changed

### Data / Calc

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

### Assurance

- review.started
- review.required
- review.resolved
- proof.started
- proof.verified
- release.completed

## 7. SSE

MVP:

`GET /api/research-runs/{run_id}/events`

Features:

- `Last-Event-ID` or sequence resume
- heartbeats
- event replay from DB
- no frontend polling as primary approach

## 8. Web rendering rule

Frontend task block = Task domain entity.

Skill steps are detail-level; do not explode every function call into top-level blocks.
