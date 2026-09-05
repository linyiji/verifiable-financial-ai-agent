# Phase 4 Wave 1 — Codex C Internal Ownership

Status: `LOCKED`

This file applies only to the Codex C Run Snapshot / SSE / Research Path worktree.
The parent-authorized Git ref-prefix recovery maps the planned branch
`phase4/run-sse` to the actual branch `p4-run-sse`; the worktree remains
`/Users/mac/Verifiable_Financial_Agent_System_phase4/run-sse`.

## Preconditions recorded

- Parent coordinator ready: `YES`
- Wave 1 ready: `YES`
- Wave 1 worktrees ready: `YES`
- Wave 1 ownership locked: `YES`
- Shared hot files identified: `YES`
- Base SHA: `4b6721b6db433aae300f94750e1a405b6b450501`
- Base tree: `35c47508ed65220c26620f5ec4bdd14cb798480d`
- Initial worktree status: `CLEAN`

## Single-writer map

### Codex C coordinator

- this ownership record and the final C handoff/event support matrix;
- approved-baseline materialization commits;
- `apps/web/src/state/runtimeEventReducer.ts` (shared C semantic join point);
- integration-only resolution when more than one C specialist needs the same C-owned file;
- Parent-only semantic patch proposals.

### C1 — SSE Runtime

- `contracts/events/runtime_event.schema.json`
- `src/domain/runtime_event.py`
- `apps/web/src/runtime/RuntimeTransport.ts`
- `apps/web/src/runtime/SSERuntimeTransport.ts`
- `tests/unit/test_phase4_event_contract.py` (new, if required)

### C2 — Recovery / Reconciliation

- `src/application/events.py`
- `src/runtime/events.py`
- `src/runtime/sse.py`
- `src/runtime/checkpoint.py`
- `src/infrastructure/database/postgresql_events.py`
- `src/infrastructure/database/checkpoints.py`
- `tests/unit/test_phase4_sse_recovery.py` (new, if required)

### C3 — Research Path

- `src/runtime/state.py`
- `src/runtime/graph.py`
- `src/runtime/lifecycle.py`
- `src/runtime/scheduler.py`
- `apps/web/src/components/research-path/ResearchPath.tsx`
- `apps/web/src/components/tasks/TaskDetailDrawer.tsx`
- `tests/unit/test_phase4_research_path.py` (new, if required)

### C4 — Dynamic Path / Acceptance

- `apps/web/scripts/runtime-reducer.test.mjs`
- `tests/unit/test_phase4_dynamic_path_acceptance.py` (new, if required)
- read-only review of all C1–C3/coordinator implementation;
- negative-matrix and acceptance findings returned to the owning writer rather than
  editing another owner's files.

## Serialization rules

1. No specialist edits a path assigned to another specialist.
2. The coordinator is the only writer of `runtimeEventReducer.ts` because SSE,
   recovery, graph projection, and acceptance all converge there.
3. Baseline frontend files are materialized byte-for-byte from
   `d854c97789c98cca14fee3f4b3d7f00e0d5d137a` in a baseline-only commit before
   semantic edits.
4. `PARENT_ONLY` paths, including API routes, frontend root composition, shared
   contract types, package/lock/config files, and `ResearchRunPage.tsx`, are not
   edited. Required integration is returned as a semantic patch proposal.
5. Production code has no demo/fixture fallback and never fabricates Tasks from
   sparse events or Scheme content.

