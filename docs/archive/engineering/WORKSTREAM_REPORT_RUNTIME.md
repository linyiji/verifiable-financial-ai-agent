# Workstream C Report — Dynamic Runtime

## Outcome

Workstream C is complete on branch `ws/runtime`. The implementation provides a Python 3.11
stateful graph execution foundation while preserving the frozen distinction between the approved
Planned Task Graph and the evolving Actual Runtime Graph.

The runtime is orchestration infrastructure only. It contains no financial formula, semantic
analysis, evidence acceptance, proof decision, API route, or FinRobot import.

## Runtime baseline observed

| Runtime | Required baseline | Observed in execution environment | Result |
|---|---:|---:|---|
| Python | `>=3.11,<3.12` | `Python 3.11.16` via project `.venv` | PASS |
| Node.js | `>=24,<25` | system default `v25.9.0` | OUTSIDE WS-C; reported to Foundation owner |
| npm | project tooling | `11.12.1` | observed only |

All Python commands used the required interpreter:
`<repository-root>/.venv/bin/python`, with `PYTHONPATH=.` so the
isolated worktree sources were tested rather than the editable install from `main`.

## Delivered implementation

### Runtime state and graph separation

- `RuntimeState.create` deep-copies the approved graph into two independent snapshots.
- Runtime operations mutate only `actual_graph`.
- `planned_snapshot` provides a defensive audit copy.
- State holds run status, completed output references, evidence/workspace references,
  review/proof state, and cost for checkpoint capture.

### Task lifecycle and dependency scheduler

- Explicit validated task status transitions.
- Dependency readiness requires every dependency to be `COMPLETED`.
- Independent READY tasks are scheduled with `asyncio.gather`, providing real concurrent
  execution rather than sequential coroutine calls.
- Dependency waves preserve ordering for join tasks.
- Approved tasks added while a dependency wave is executing are admitted in the next wave.
- Failed/cancelled dependency propagation blocks downstream tasks.
- Cyclic, blocked, or otherwise unrunnable graphs fail explicitly instead of hanging.
- Cancellation moves unfinished tasks and the run to `CANCELLED` and checkpoints the state.

### Retry

- Configurable `RetryPolicy(max_attempts, backoff_seconds)`.
- Attempt count is persisted on the Task.
- Each attempt emits `task.started`.
- A retry emits a structured `task.progress` event without changing the frozen event enum.
- Terminal failure emits `task.failed` and fails the run.

### Lead-authorized graph mutation

- The mutation service accepts only an `APPROVED` Replan Request.
- Only `RESEARCH_LEAD` or `PLANNER` roles are authorized.
- The mutation actor must be the actor recorded in `decided_by`.
- Specialist attempts are rejected.
- Run ownership, duplicate IDs, and dependency references are validated before mutation.
- Actual graph version and mutation history are updated; Planned Graph is unchanged.
- `graph.task_added` and `graph.version_changed` events are emitted.

### Checkpoints

- `CheckpointStore` protocol decouples runtime code from persistence choice.
- `RuntimeCheckpoint` captures all Foundation-minimum fields.
- `InMemoryCheckpointStore` provides the test/Foundation baseline with defensive copies and
  duplicate checkpoint protection.

### Runtime event persistence

- `RuntimeEventStore` protocol decouples producers and consumers from the future SQL store.
- `InMemoryRuntimeEventStore` serializes concurrent writes per run.
- Sequences begin at 1 and are strictly monotonic per run.
- Invalid sequence and duplicate event writes are rejected.
- Replay is available after a sequence and returns defensive copies.
- Live wait uses a condition with a race-closing replay check.
- Resume positions accept either a numeric SSE `Last-Event-ID` sequence or a stored event ID.

### SSE utilities

- Runtime events are encoded with SSE `id`, `event`, and JSON `data` fields.
- Persisted replay occurs before the live wait loop.
- Idle connections receive comment heartbeats.
- HTTP route ownership was left to Integration as directed.

## Verification evidence

### Automated tests

Command:

```text
PYTHONPATH=. <repository-root>/.venv/bin/python -m pytest -q
```

Result:

```text
............                                                             [100%]
14 passed in 0.20s
```

The eight WS-C integration tests cover:

1. true parallel execution of two independent tasks (`max_active == 2`) plus a dependent join;
2. measured parallel path completion below the sequential bound;
3. retry lifecycle, attempts, event ordering, and final completion;
4. terminal failure propagation through transitive dependents and failed-state checkpointing;
5. 50 concurrent event emissions with contiguous sequences `1..50`;
6. Specialist mutation rejection and approved Lead mutation acceptance;
7. execution of an approved task added dynamically while the scheduler is running;
8. defensive checkpoint/event persistence plus SSE replay and heartbeat behavior.

### Ruff

Command:

```text
PYTHONPATH=. <repository-root>/.venv/bin/python -m ruff check \
  src/runtime tests/integration/test_runtime_execution.py
```

Result: `All checks passed!`

### Diff and boundary review

- `git diff --check`: PASS.
- Ownership review: changes are limited to `src/runtime/**`, the WS-C integration test, and this
  report.
- Import scan: no FinRobot, `third_party`, financial formula, apps/API, evidence implementation,
  calculation implementation, or proof implementation imports in WS-C.
- Frozen `src/domain/**`, `contracts/**`, and app/API files were not modified.

## Architecture decision compliance

| Decision | Compliance |
|---|---|
| ADR-005 | Scheduler consumes a complete planned graph; it does not invent planning tasks. |
| ADR-009 | Specialist graph mutation is explicitly denied. |
| ADR-010 | Only approving Research Lead/Planner can apply graph changes. |
| ADR-011 | Runtime is state/scheduling/events/checkpoint infrastructure, not an Agent. |
| ADR-012 | Planned and Actual graphs are independently retained. |
| ADR-018 | Successful task execution advances to `REVIEW`, not directly to release. |
| ADR-031 | SSE utilities expose a client-neutral runtime event protocol. |
| ADR-032 | Code and tests run on Python 3.11.16. |
| ADR-034 | Graph state changes are available as backend Runtime Events. |

## Integration notes

- The API workstream can wrap `runtime_event_stream` in the SSE route without moving runtime
  concerns into the application layer.
- A future SQL event/checkpoint implementation should satisfy the existing protocols; the
  scheduler and SSE utility should not require schema or behavior changes.
- The scheduler intentionally stops in `RunStatus.REVIEW` after all graph tasks complete. The
  Assurance/Release workstreams own later `PROVING` and `RELEASED` transitions.
- System-default Node v25.9.0 does not satisfy the frozen Node 24 baseline. This workstream made no
  Node/toolchain changes because Node configuration is outside WS-C ownership.
