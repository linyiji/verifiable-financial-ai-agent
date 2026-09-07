# Phase 5B R5 adaptive execution acceptance — 2026-09-08

Phase 5 completion gate: **PASS**. One authorization and one new production Run;
no R6, prepare, new Draft, or Scheme regeneration. No push. No Phase 6 evaluation,
POT, rankings, or learned routing implemented.

## Authority and exact lineage

Started on clean `phase4` at `ec60923809dd37874d623c1e71822bc96c3ab426`,
tree `825ec0daa37bff6a9c4eca69df4a08db0f2cf216`; production migration
`20260908_0012` verified before mutation. The accepted R4 launcher MiMo incremental
graph-planner override was retained; Specialist initial route policy was unchanged.

| Identity | Value |
| --- | --- |
| Object | `OBJ-NVDA` |
| Authorization | `REAUTH-9e26582f-0671-40a1-a1cd-d5c43e56f2f0` |
| R5 | `RUN-ab806291-8cbf-4c9b-8852-b6a54f10768d` |
| Re-execution predecessor R4 | `RUN-2bf2ef98-dc79-4b5f-aeb7-fb0ea151948a` |
| Knowledge baseline R1 | `RUN-57aed683-75d6-4b47-acc6-a73053ea492e` |
| Base view v1 | `RVV-05bec42f-ab9b-55c5-b502-c439b8abe948` |
| Same confirmed Scheme | `SCHEME-b7a81dfc-7863-59e2-afd2-0371e796a1b6` |
| Released result / report | `RESULT-RUN-ab806291-8cbf-4c9b-8852-b6a54f10768d` |
| Canonical execution record | `CER-RUN-ab806291-8cbf-4c9b-8852-b6a54f10768d` |
| Object version v2 | `ROV-13d9d21a-661e-5df6-92cd-779ad1f944b0` |
| Research view v2 | `RVV-0f7f4dfc-3dfa-538c-b59f-a8e22607007b` |

One logical graph-planner call. Schema, canonical Agent IDs, task-profile
compatibility, exact Scheme binding, decisions, and base-lineage gates passed
before atomic admission. Initial graph had 9 tasks. The existing research-semantic
replan later added risk-follow-up (10 tasks); this was not a recovery graph call
or Scheme regeneration. The existing correction path resolved PERIOD_MISMATCH.

## Observed live recovery, not a manufactured demonstration

| Task | Initial attempt | Governed recovery | Final attempt |
| --- | --- | --- | --- |
| Peer | MiMo: READ_TIMEOUT, 60.21s | SWITCH_PROVIDER to verified Sol; Gate ALLOW | Sol PASS, 30.93s |
| Fundamental | Sol: READ_TIMEOUT, 60.41s | CAPABILITY_CHECK Luna ALLOW; check PASS 13.95s; SWITCH_MODEL Luna ALLOW | Luna PASS, 35.65s |
| Research/News | MiMo PASS, 7.60s | None | Same first attempt |

Two recoverable failures, three decisions, 23 durable ledger records. Nine
execution attempts across seven completed Specialist tasks, plus one separate
Luna capability check. Seven successful Agent outputs. Original Task and Run IDs
were retained; downstream research, Review, Proof, Report and Release continued.

Fundamental initial route was `teamorouter-sol / gpt-5.6-sol`; final route was
`teamorouter-luna / gpt-5.6-luna`. This was a model switch, **not** a provider
switch. Fundamental × MiMo remained UNKNOWN; MiMo capability checks = 0.
Main Agent proposed actions; deterministic Policy Gate authorized each. Accepted
budgets were unchanged and independently revalidated against persisted contexts.

## Release, memory, history and product

Review PASS (54 checks); required Proof VERIFIED; canonical execution record and
released result available; terminal SUCCESS. Release-only atomic memory writeback
created v2, sourced exactly from R5. Repeated writeback, browser refresh and reopen
left the same v2 IDs. Stale-write/release/idempotency protections passed focused
regression tests. Production totals changed from 39 to 40 Runs and 2 to 3
authorizations, with no further Run admission.

Real in-app browser acceptance exercised Object current v2, history, R5 lineage,
A/B/C, Base vs Current, both exact R1/R5 Results links, refresh, and tab close/reopen.
C displays actual failure classes, routes/models, attempts, capability check,
decisions, Gate results, latency and record IDs. Refresh/reopen showed no service
error after the request-contract repair. This is real persisted product data.

Availability remains honest: A has `REPORT_SOURCE_MAP_PARTIAL`; C has
`REPORT_CONTRIBUTIONS_PARTIAL`. HTML, released report and recovery evidence work;
missing source/contribution mappings and deferred PDF are not relabeled READY.
These retained presentation limitations do not represent failed Release gates.
Financial limitations (including insufficient valuation inputs and unavailable
peer/news evidence) remain visible; no financial claim was strengthened to pass.

R1 remains RELEASED. R2 `RUN-e1b27d55-a58f-428d-b98b-0dc519577bc0`,
R3 `RUN-bd02e630-69e9-468c-a3c8-6819e8facd30`, and R4 remain FAILED.
Before/after fingerprints for historical Runs, Tasks, events, object/view v1,
Drafts, goals and Scheme snapshots match. R5 itself remained unchanged after
Release. No cross-run fallback, cross-object reuse, unsafe public fields, hidden
CoT, or configured secret values were observed in audited public surfaces.

## Product comprehension — PASS

1. **Yes:** Run lineage and comparison explicitly retain R1/v1 as knowledge base.
2. **Yes:** Object history shows R2/R3/R4 FAILED separately, without overwriting them.
3. **Yes:** R5 identifies the same confirmed S1 and separately links predecessor R4.
4. **Yes:** C groups both recovery sequences under the original R5 Task IDs.
5. **Yes:** persisted attempts/decisions/Gate outcomes are inspectable; budget replay passed.
6. **Yes:** Main Agent proposes; Policy/Budget authorizes and cannot be overridden.
7. **Yes:** Base vs Current opens exact R1 and R5 Results using governed identities.
8. **Yes:** explicit v1/v2 history and released-source pointers accumulate research
   without promoting failed attempts into knowledge authority.

## Narrow source repairs discovered during live acceptance

- Add safe, exact-Run recovery decoding and read-only C timeline; no raw provider
  output/private context is rendered and unavailable data never falls back.
- Negotiate the existing product contract header on the recovery endpoint.
- Supply deterministic Object/source-Run idempotency keys for existing frontend
  memory writeback. No changes to persistence semantics or runtime recovery policy.

The acceptance API wrapper disabled scheduler startup and blocked mutations
except exact already-materialized R5 memory replay. No historic Run was restarted.

## Proportional verification

- Backend: **148 passed**, two dependency deprecation warnings. Scopes: recovery
  policy/runtime, re-execution admission, graph identities, Specialist routes,
  recovery persistence, API negotiation, memory PostgreSQL and comparison.
- Frontend: **150 checks passed**: M3/M7-R1 20, M4 27, M5 37, M6 35,
  recovery projection/rendering 24, memory request idempotency 7.
- Total focused test/check count: **298**. TypeScript typecheck and Vite build PASS.
- Read-only exact API/DB acceptance, historical fingerprints, unchanged released
  R5 hash, bounded recovery replay and browser vertical slice PASS.

Local evidence is retained under ignored `artifacts/phase5b_r5_adaptive/`:
dispatch, authorization, admission, graph, terminal, memory, performance, recovery,
before/after history, acceptance audit, and final receipt. Do not rerun `execute.py`.

Next exact action: `USER_ALPHA_AND_PHASE_6_EVALUATION_PREP` — not executed here.
