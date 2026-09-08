# Workstream B — Agentic Planning Report

## Status

**COMPLETE** for the Foundation scope on branch `ws/agentic`.

Runtime used for implementation and verification: Python `3.11.16` from
`<repository-root>/.venv/bin/python`, with `PYTHONPATH=.` so the
isolated checkout is authoritative.

## Delivered artifacts

| Artifact | Responsibility |
|---|---|
| `src/agentic/scheme.py` | `SchemeGenerator` protocol and deterministic, non-LLM fallback |
| `src/agentic/planner.py` | Research Lead complete initial plan creation |
| `src/agentic/specialist.py` | Specialist execution boundary and structured result contract |
| `src/agentic/skill.py` | Skill definition, context, result, and execution protocol |
| `src/agentic/registry.py` | Duplicate-safe Agent and Skill registries |
| `src/agentic/decisions.py` | Task-local self-correction and lead-controlled replan decisions |
| `src/agentic/__init__.py` | Public Workstream B API |
| `tests/unit/agentic/` | 18 focused unit and architecture-boundary tests |

## Behavior implemented

### Scheme generation

- `SchemeGenerator` is an async protocol over the existing frozen `ResearchObject`,
  `ResearchGoal`, and `ResearchSchemeSnapshot` domain contracts.
- `DeterministicSchemeGenerator` emits stable scheme content and a stable UUID5-based scheme ID
  for the same object, goal, and as-of date.
- The fallback describes scope, evidence, agents, skills, deterministic calculation requirements,
  assurance, and outputs. It emits no financial values.
- A goal/object mismatch fails closed.
- Confirmation is not performed by the generator; that remains an external user/workflow action.

### Initial planning

- `ResearchLeadPlanner` refuses to plan an unconfirmed scheme.
- It produces the entire V1 planned graph before execution: evidence collection; fundamental,
  peer, and research/news analyses; valuation and risk analyses; then report synthesis.
- All task dependencies point to tasks in the initial graph and are accepted by the frozen
  `PlannedTaskGraph` validator.
- All initial tasks use `TaskOrigin.PLAN`, `TaskStatus.CREATED`, and stable run-scoped IDs.
- A confirmed scheme containing a skill with no initial-plan mapping fails closed instead of
  silently producing an incomplete graph.
- Code Builder is intentionally not an initial task; ADR-024/05 requires it to be triggered only
  after an approved capability gap.

### Specialist and Skill boundaries

- Specialist execution receives only a single task, accepted evidence IDs, and task-scoped input.
  It receives no graph object or graph mutation API.
- Specialist output contains an artifact-shaped JSON result, a frozen
  `StructuredAgentDecision`, and optionally the frozen `ReplanRequest`.
- A Specialist result rejects any replan request that is already approved/rejected, has a
  `decided_by`, or contains `created_task_ids`. This prevents a Specialist from smuggling a graph
  decision or mutation through its output.
- Replan request run/task IDs must match the structured decision.
- Skill packages declare schemas, allowed capabilities, required evidence, preconditions,
  validation rules, correction strategies, and evaluation rules without embedding an adapter or
  third-party implementation.
- Agent and Skill registries reject duplicate IDs and report missing IDs explicitly.

### Structured correction and replan decisions

- `SelfCorrectionDecision` is task-local, requires a positive next attempt, and only stores a
  structured summary/reason record. It has no graph mutation fields.
- Supported correction actions stay within the ADR-008 envelope: retry a tool, change evidence,
  adjust parameters/output format, change a capability, or escalate by requesting a replan.
- `ResearchLeadReplanDecider` accepts only a pristine pending frozen `ReplanRequest` and requires
  an explicit `APPROVED` or `REJECTED` outcome.
- The decider does not mutate the input request. It returns a copied domain request with lead
  attribution plus a `StructuredAgentDecision`.
- Approval does not create tasks or apply `proposed_graph_change`; application remains exclusively
  a future Graph Engine responsibility.

## Frozen contract reuse matrix

| Existing module | Decision | Reuse method | Compatibility | Action |
|---|---|---|---|---|
| `src.domain.research_scheme.ResearchSchemeSnapshot` | DIRECT_REUSE | direct | Python 3.11 PASS | imported unchanged |
| `src.domain.task.PlannedTaskGraph` | DIRECT_REUSE | direct | Python 3.11 PASS | planner output contract |
| `src.domain.task.Task` | DIRECT_REUSE | direct | Python 3.11 PASS | initial task contract |
| `src.domain.task.ReplanRequest` | DIRECT_REUSE | direct | Python 3.11 PASS | request/decision boundary |
| `src.domain.decision.StructuredAgentDecision` | DIRECT_REUSE | direct | Python 3.11 PASS | all persisted agent decisions |
| `src.domain.enums.ReplanDecision` | DIRECT_REUSE | direct | Python 3.11 PASS | lead outcome contract |
| Financial calculations / FinRobot | ADAPTER_REUSE | future Capability adapter | not exercised in WS-B | no direct import or rewrite |

No frozen file under `src/domain/**` was modified.

## ADR and boundary review

| Decision | Evidence in this workstream | Result |
|---|---|---|
| ADR-003 | generator returns a scheme candidate; planner requires `confirmed_at` | PASS |
| ADR-005 | planner creates all initial V1 tasks and dependencies in one call | PASS |
| ADR-006 | task goals are user-understandable research units | PASS |
| ADR-007 | Specialist, Skill, and Capability IDs are separate concerns | PASS |
| ADR-008 | self-correction has no top-level task creation surface | PASS |
| ADR-009 | Specialist receives no graph and can emit only a pending request | PASS |
| ADR-010 | only `ResearchLeadReplanDecider` can approve/reject in agentic code | PASS |
| ADR-011 | no scheduling, state engine, checkpoint, or event emission is implemented here | PASS |
| ADR-013 | contexts expose accepted evidence IDs, not raw provider payloads | PASS |
| ADR-015/016 | no calculation/output-value model or financial number generation exists here | PASS |
| ADR-017/018 | agentic output cannot bypass review/proof/release controls | PASS |
| ADR-021/022 | Skills refer to capability IDs, not forced MCP backends | PASS |
| ADR-024 | Code Builder is excluded from the initial graph | PASS |
| ADR-032 | verified under Python 3.11.16 | PASS |
| ADR-033 | no FinRobot or `third_party` imports | PASS |

Automated boundary scan found no imports of `third_party`, FinRobot, runtime, or adapters and no
use of `CalculationRecord`/`output_value` in owned implementation or tests.

## Verification results

Commands were run from the isolated Workstream B checkout.

```text
$ <repository-root>/.venv/bin/python --version
Python 3.11.16

$ PYTHONPATH=. <repository-root>/.venv/bin/python -m pytest -q tests/unit/agentic
..................                                                       [100%]
18 passed in 0.07s

$ PYTHONPATH=. <repository-root>/.venv/bin/python -m pytest -q
........................                                                 [100%]
24 passed in 0.08s

$ PYTHONPATH=. <repository-root>/.venv/bin/python -m ruff check .
All checks passed!

$ git diff --check
(no output; passed)
```

## Integration notes

- Runtime should dispatch a Specialist using `AgentRegistry`, then resolve its declared Skill via
  `SkillRegistry`; capability execution remains outside this workstream.
- Runtime may persist `SpecialistResult.decision` immediately. If `replan_request` is present, it
  must route it to `ResearchLeadReplanDecider`; it must not apply the request directly.
- Graph Engine may apply only an approved `LeadReplanDecision.request`. It owns actual graph
  versioning, mutation history, task creation, and runtime events.
- Generated schemes with custom Skill requirements require an explicit planner mapping before
  planning; current behavior intentionally fails closed.
- Scheme confirmation timestamps and immutable snapshot persistence belong to application/runtime
  integration, not the generator.

## Deferred by design

- No LLM-backed scheme generator.
- No Specialist business implementation.
- No financial calculation, FinRobot import, FMP processing, or report rendering.
- No runtime scheduling, graph mutation, SSE emission, database persistence, review, proof, or
  release logic.

These exclusions preserve Workstream B ownership and the Foundation boundary.
