# WS-N — Replan Dependency Integrity Report

## Outcome

**PASS** for the Phase-2.1 WS-N module gate.

An approved mandatory risk follow-up is now a dependency-preserving graph insertion rather than an
unconnected child addition. The immutable planned graph remains the approved audit snapshot; only
the Actual Runtime Graph changes.

## Delivered behavior

| Requirement | Result |
|---|---|
| `add_node` / `add_edge` / `remove_edge` / `replace_dependency` | PASS |
| atomic multi-operation validation and graph rollback | PASS |
| cycle, duplicate, unknown-node, and immutable-target rejection | PASS |
| one graph-version increment per committed mutation | PASS |
| frozen edge-added / edge-removed audit events | PASS |
| READY-state invalidation and readiness recomputation | PASS |
| mandatory risk follow-up dependency rewiring | PASS |
| checkpoint restore of graph dependencies and version | PASS |
| planned graph remains unchanged | PASS |
| no evidence behavior changes | PASS |

## Replan topology

Before:

```text
Risk ───────────────→ Synthesis
  └──→ Follow-up
```

The child and synthesis could become independently runnable after Risk, so synthesis could start
before the mandatory follow-up completed.

After:

```text
Risk → Follow-up → Synthesis → Review
```

The approved insertion is a single graph transaction consisting of node addition, edge addition,
edge removal, and edge addition. Validation occurs against a deep staged copy before the Actual
Graph reference is swapped. Invalid mutations emit no graph audit events and leave graph identity,
dependencies, history, and version unchanged. An audit-emission failure restores the prior Actual
Graph reference.

## Audit and runtime event ordering

Before WS-N:

```text
replan.approved
graph.task_added
graph.version_changed
risk task.completed
follow-up and synthesis could be scheduled in the same wave
```

After WS-N:

```text
replan.approved
graph.task_added(Follow-up)
graph.edge_added(Risk → Follow-up)
graph.edge_removed(Risk → Synthesis)
graph.edge_added(Follow-up → Synthesis)
graph.version_changed(v1 → v2)
risk task.completed
follow-up task.started
follow-up task.completed
synthesis task.started
synthesis task.completed
review.started
```

Every edge event includes `replan_id`, `graph_version`, `source_task_id`, and `target_task_id`.
`graph.version_changed` is emitted last for the mutation and records both versions.

## Concurrency integrity

Atomic graph mutation replaces the graph with a validated staged copy. The dependency scheduler now
re-resolves each in-flight task by stable task ID before every status/result write. This prevents a
parallel task from completing against a detached pre-mutation Task object while retaining true
parallel execution of an already-admitted wave.

## Checkpoint and restore

`RuntimeCheckpoint.restore(planned_graph=...)` reconstructs the Actual Runtime Graph and validates:

- checkpoint, planned graph, and actual graph run identity;
- stored version against the serialized graph version; and
- stored task-state map against task statuses in the graph payload.

Mutation history, edge dependencies, graph version, outputs, evidence/workspace references, review
and proof states, and cost survive restoration. The caller supplies the separately persisted
approved planned snapshot, so checkpoint restoration does not turn the mutated graph into a plan.

## Verification

```text
$ PYTHONPATH=. pytest -q tests/integration/test_replan_dependency_integrity.py \
    tests/integration/test_runtime_execution.py tests/integration/test_application_flow.py
17 passed, 2 dependency deprecation warnings

$ PYTHONPATH=. pytest -q
130 passed, 1 skipped, 2 dependency deprecation warnings in 1.05s

$ ruff check .
All checks passed!

$ ruff format --check <WS-N changed Python files>
7 files already formatted

$ git diff --check
PASS
```

The skipped test is the pre-existing real PostgreSQL test, which requires `TEST_POSTGRESQL_URL` and
`asyncpg`. The two warnings originate in the installed FastAPI/Starlette TestClient dependency
surface.

## Ownership, contract, and secret gates

- Frozen `GRAPH_EDGE_ADDED` and `GRAPH_EDGE_REMOVED` event types were consumed unchanged.
- `src/domain/**`, `contracts/**`, Settings, `pyproject.toml`, `apps/api/main.py`, and
  `PARALLEL_EXECUTION_STATUS.md` are unchanged.
- The application edit is limited to risk-replan dependency wiring; evidence behavior is unchanged.
- Changed-source secret scan: PASS; no credential values or credential fields were introduced.
- Contract changes or deviations: **NONE**.

## Existing logic reuse

| Existing module | Decision | Method | Action |
|---|---|---|---|
| `GraphMutationService` | ADAPTER_REUSE | atomic operation core | extend |
| `DependencyScheduler` | ADAPTER_REUSE | stable-ID rebinding | preserve parallel scheduler |
| `RuntimeCheckpoint` | ADAPTER_REUSE | validated restore constructor | extend |
| `ResearchLeadReplanDecider` | DIRECT_REUSE | existing approval authority | keep |
| `IntegratedTaskExecutor` risk branch | ADAPTER_REUSE | insert-between orchestration | rewire only |
| frozen RuntimeEvent types | DIRECT_REUSE | edge/version audit | keep unchanged |

## Deferred

- Durable checkpoint-store selection and process-level resume orchestration remain Coordinator
  composition concerns. WS-N provides and verifies the restore boundary.
- Transactional durability between an external event database and graph-state database requires a
  future shared unit-of-work/outbox contract. Current in-memory execution validates first and rolls
  back the graph on audit failure without changing frozen contracts.
