# Phase 5B — explicit re-execution contract

[简体中文](PHASE5B_REEXECUTION_CONTRACT.zh-CN.md)

Start: branch `phase4`, clean worktree, commit
`3cc8d9d7d7713762031564300993efadcbcbad20`, tree
`d6595a8020718ce3b2dcb81785ec1f38ae78f1a7`.

## Three independent identities

- `base_run_id` / `base_research_view_version`: released knowledge baseline R1/v1.
- `scheme_id` / confirmed Scheme fingerprint: unchanged reviewed research intent.
- `reexecution_of_run_id`: immediate failed execution predecessor, never the base.

The optional Run field is persisted in the existing aggregate JSON, read by the
existing reconstruction path, and exposed on the existing Run detail projection
together with both base identifiers. No historical backfill is performed. The
first failed R2 correctly has no execution predecessor. No timestamp-derived
ordinal, duplicate alias, attempt counter, or separate attempt-group system exists.

## Explicit authorization, not another draft

Two operations extend the existing Run API family:

1. `POST /api/research-runs/{run_id}/reexecution-authorizations`
   accepts only `research_object_id` and `authorize_reexecution: true`, plus the
   existing contract and idempotency headers. This records explicit local-owner
   authorization and resolves the confirmed Scheme entirely on the backend.
2. `POST /api/research-runs/{run_id}/reexecute`
   accepts only `research_object_id` and `authorization_id`, plus idempotency.
   It does not accept a Goal, Scheme, base override, or executable graph from the caller.

Authorization records bind the exact predecessor/Object/Scheme hash/Goal hash/base
Run/base view, local-single-user authority, creation time, and expiry. Expiry uses
the existing 30-minute authorization window; there is no renewal endpoint or
implicit refresh. Authorization replay returns the same record, including its
original expiry. The original consumed Draft is only read as hash-checked evidence
of confirmation; it is never renewed, unconsumed, rewritten, or confirmed again.

The full confirmed Scheme and Goal are hashed using existing canonical JSON
SHA-256, and compared again at admission. Stored Scheme/Goal snapshots must agree
with the failed aggregate and the original immutable draft. Immediate predecessor
chains must reach the original consumed Run without cycles, cross-Object or
cross-Scheme links. The source must be FAILED; the exact released base and current
Memory pointer/view must still agree. An already RELEASED execution of the same
intent prevents another authorization/admission through this path.

## Atomic admission and planner boundary

Admission uses the existing PostgreSQL unit of work, global admission fence,
authoritative row locks, and pending scheduler outbox. It creates a new Run and
new Graph; the old invalid Graph is not reused. The existing incremental planner
must be configured with one logical validation attempt, fail-closed behavior, and
the actual runtime Agent registry. Each admission operation invokes that planner
at most once, with no Scheme generation or automatic validation retry.

After generation, exact Scheme/Goal, new Run/Graph identity, canonical Agent IDs,
profile/skill/dependency validity and incremental binding are checked. Expiry is
checked both before planning and before admission. A graph failure leaves no Run,
task/event rows, scheduler admission, or authorization consumption. The unconsumed
authorization remains durable until its original expiry. This is not an automatic
retry policy or permission for another live model operation.

The new aggregate, graph records, tasks, events, distinct `REEXECUTION` idempotency
outcome, pending scheduler record, and authorization consumption commit together.
No synthetic Draft admission is created. Exact admission replay returns the same
new Run; a different key cannot reuse consumed authorization. Concurrent identical
requests serialize to one admission. The frontend stops after a failed POST and
does not automatically retry or prepare a Scheme.

Initial Scheme-generation events use the existing explicitly retrospective event
representation; no Scheme generation occurs for this execution. Future scheduler
processing uses existing Run reconstruction and persistence. Re-execution runtime
saves cannot rewrite the shared confirmed Scheme. Memory writeback still requires
the new Run to be RELEASED and uses that new Run as v2 source, never failed R2.

## Additive persistence migration

`20260907_0011_reexecution_authorizations` creates the authorization table, original
and consuming Run references, unique authorization/admission key digests, and
all-or-nothing consumption constraints. Triggers prevent authorization retargeting,
consumption rewrites, and existing Run execution-lineage rewrites. For a re-execution
Run, Scheme/Goal/base snapshots are also immutable across subsequent updates.

The migration was exercised in disposable PostgreSQL schemas, including real
trigger rejection tests. **It has NOT been applied to production.** No production
authorization was issued. A future owner-authorized live slice must apply migration
0011 before invoking these endpoints; migration application is not itself live-run
authorization.

## Product behavior

The failed incremental Run offers “重新执行”. Its first action creates an explicit
authorization, then “确认沿用方案并重新执行” submits that authorization. Copy explains
the retained research intent/base and new execution record. The new execution's
detail links to the prior failed attempt. Technical identifiers are not primary
button labels. Wrong response identity blocks navigation; double clicks are
suppressed; errors stop further submission in the mounted component.

## Acceptance evidence

- 243 focused Python tests passed: 241 scoped backend/domain/provider/Memory/
  Draft/Graph tests plus 2 new public-boundary tests. Provider responses and graph
  planning in these tests are local fixtures; no scheduler or live provider starts.
- 125 frontend checks passed: 6 tests executing the actual new component's event
  handlers with deterministic hook/network adapters, plus 119 existing M3/M7-R1/
  M4/M5/M6 checks. No production browser action was clicked.
- New persistence coverage includes new identity, exact Scheme/Goal/base retention,
  failed history and consumed Draft preservation, one-shot and concurrent replay,
  invalid graph rollback, injected commit failure, expiry before planner invocation,
  wrong Object/Scheme/base/view, unknown/nonfailed predecessor, chain continuation,
  released-intent exclusion, and database immutability enforcement.
- TypeScript typecheck, Vite build, scoped Ruff and diff whitespace checks pass.
- Broader diagnostic: **710 passed, 2 failed**. The two unchanged baseline tests
  in `test_top_level_projection_builders.py` fail the existing Calculation-unit
  integrity gate (previous repair receipt records their baseline reproduction).
  Neither production projection integrity nor those fixtures were weakened.
  The route inventory test was updated for the two explicit re-execution routes
  and the already-accepted exact-Draft/lease routes.

## Historical safety and boundary

Read-only `python -m scripts.verify_phase5b_runtime_repair_history` passes before
and after repair. Production inventory remains 37 Runs. Failed R2 remains FAILED;
The new authority resolver also passed against the exact historical R2 using only
SELECTs (including transaction-scoped authority locks), followed by rollback. It
issued no authorization and performed no admission.
its aggregate, exact graph, recorded task/event evidence and consumed Draft binding
are unchanged. Full repair-time hashes match the prior checkpoint:

- R2 aggregate: `5e402fe19eef90df2a853a50619b6aa21772b6dbb2a0e7e718f108db9dd03dc5`
- R2 tasks: `9069f8af0b4b754d181f1122c9048179202f342872f1cdfbca9e7698adb879cd`
- R2 events: `20f9dddc04ca3cc9d8588243e74d382f715108a64a221f3f138cfee5efb29bb7`
- Draft payload: `04df3abd6661341575d7aa47d41ecfe793207e1bae2c791ffc0cb989cfab0dca`

R1/v1 fingerprints remain unchanged. Latest released Run remains
`RUN-57aed683-75d6-4b47-acc6-a73053ea492e`, view version 1. Neither Memory table
contains version 2. Historical providers remain successful, non-causal operations;
this contract repair makes zero provider/model calls and zero production Runs.

`NEW_RUN_AUTHORIZED = NO`.
`NEXT_EXACT_ACTION = PHASE_5B_FAILED_R2_REEXECUTION_AUTHORIZATION`.
No final Phase 5B tag and no push.
