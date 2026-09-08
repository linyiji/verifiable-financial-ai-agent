# Codex Master Parallel Execution Prompt V1

[简体中文](CODEX_MASTER_PARALLEL_EXECUTION_PROMPT_V1.zh-CN.md)

You are the engineering coordinator for Verifiable Financial Agent System.

Read first:

1. `README.md`
2. `docs/00_READ_FIRST.md`
3. `docs/03_ARCHITECTURE_DECISIONS_V1.md`
4. `docs/19_PARALLEL_MODULE_BUILD_AND_INTEGRATION_V1.md`
5. `docs/02_BACKEND_ARCHITECTURE_V1.md`
6. `docs/04_DOMAIN_DATA_MODEL_V1.md`
7. `docs/14_ACCEPTANCE_TEST_PLAN_V1.md`

Target user path:

`<repository-root>`

Do not assume the path exists. Confirm it.

## Objective

Execute backend implementation using:

> Foundation Gate → Parallel Workstreams → Integration → Acceptance

Do not implement the entire project serially in one context if parallel execution/worktrees are available.

## Stage 1 — Foundation

Complete only:

- repo skeleton
- pyproject
- Python 3.11 backend baseline and Node.js 24 Web baseline
- shared enums
- domain contracts
- RuntimeEvent
- API schemas
- DB base
- fixture base
- capability / trace / proof interfaces

Run tests.

Commit:

`foundation: freeze v1 contracts`

Do not build all business logic here.

## Stage 2 — Create parallel workstreams

Create isolated branches/worktrees for:

- data-evidence
- agentic
- runtime
- financial-capabilities
- assurance
- output

Use prompts under:

`codex/workstreams/`

Each workstream must not modify files outside ownership unless it produces a CONTRACT_CHANGE_REQUEST.

## Stage 3 — Module gate

For each branch:

- run tests
- inspect diff
- read WORKSTREAM_REPORT
- reject duplicated domain definitions
- reject cross-layer shortcuts
- reject API-route business logic
- reject fake implementations labeled complete

## Stage 4 — Merge

Merge in dependency-safe order documented in parallel plan.

Resolve only at coordinator level.

## Stage 5 — Integration

Execute:

`codex/workstreams/WS_G_INTEGRATION.md`

Required real chain:

```text
Object
→ Goal
→ AI/fallback Scheme
→ Confirm
→ Run
→ Planned Graph
→ parallel Tasks
→ Evidence
→ Financial Code
→ Self-Correction
→ Replan
→ Review
→ Canonical Execution Record
→ Released Result
```

## Stage 6 — Acceptance

Run full offline acceptance.

Do not stop after first non-critical failure.

Collect all failures.

Output final report:

```text
A Environment
B Workstreams
C Commits
D Merge result
E Test summary
F Acceptance matrix
G Known gaps
H Next task
```

Do not automatically start later phases.
