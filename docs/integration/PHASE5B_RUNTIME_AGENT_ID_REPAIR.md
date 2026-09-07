# Phase 5B runtime Agent identity repair

Deterministic repair accepted on 2026-09-07. No live provider/model call and no
new production Run. This checkpoint is not Phase 5B completion or live acceptance.

## Contract and admission boundary

`Task.assigned_agent` means canonical runtime Agent ID. Production registration
now has one composition authority, `build_research_agent_registry`, extracted
unchanged from API startup. The actual registry supplies planner descriptors and
validates assignments; there is no second Agent ID allowlist or alias mapping.
Display metadata falls back to the ID where the Agent has no display name.

The shared binding validator checks exact registered identity, declared task
profile compatibility, existing skill/profile bindings, Run/task identity,
dependency closure and acyclicity, nonempty graph, and Scheme skill coverage.
Native evidence collection remains application-executed, with a registered Agent
as owner; it does not claim that every Specialist can execute collection via LLM.
That native profile authority is shared with the actual evidence handler.

The model planner receives these descriptors and canonical-ID instructions.
Invalid registry bindings are rejected without correction calls or fallback.
The PostgreSQL confirmation boundary independently checks bindings (including
custom planners), unchanged Scheme/Goal, and exact Run identity before any atomic
admission, event/task persistence, or draft consumption. Public failures contain
owned classification codes, not raw provider/Python exception text.

Prior coherent dirty changes are retained: one-call/fail-closed incremental graph
planning, retained-draft confirmation UI, its consumed one-shot browser harness,
focused tests, and the historical blocker receipt. The harness was not rerun.
No provider routing, timeout, Scheme generation, or Memory decision repair occurred.

## Deterministic evidence

- Focused Python acceptance: **206 passed**. Covers actual production registry,
  historical label graph, canonical equivalent, unknown/missing/incompatible IDs,
  exact planner descriptors, and isolated PostgreSQL transaction tests. Invalid
  graph variants leave Run/task/event/admission/idempotency counts unchanged and
  drafts unconsumed. Valid fixtures admit only in disposable test schemas.
  Scheme/Goal mutations, bad skills, cycles, empty graphs/registries are rejected.
- Frontend: TypeScript `tsc --noEmit` and Vite build pass. M3/M7-R1/M4/M5/M6:
  **14 + 6 + 27 + 37 + 35 = 119 checks passed**.
- Broader diagnostic suite: **685 passed, 3 failed** before the last three added
  focused mutation/empty-graph cases. All three failures were reproduced from an
  untouched archive of baseline `c4a80adc1db8c83551ee8e3d97442f3a3568450b`:
  `test_router_preserves_frozen_routes_and_adds_only_phase5a_memory` expects an old
  route list; two `test_top_level_projection_builders` fixtures fail the existing
  Calculation-unit integrity gate. No changes were made to those tests or gates.
  Therefore this is a passing focused repair, not an assertion of a fully green
  repository-wide suite.
- Scoped Phase 4.5 dispatch/A-B-C/same-run, Phase 5A Memory, MiMo foundation,
  incremental Scheme, and provider-policy regressions pass without live calls.

## Historical safety

Run `RUN-e1b27d55-a58f-428d-b98b-0dc519577bc0` remains FAILED. Its original
planned graph is retained verbatim as a typed test fixture; canonical replacements
exist only in memory in tests. Production Run inventory remains 37. No retry,
resurrection, lease renewal, Scheme rewrite, or draft consumption was performed.

Read-only verifier: `python -m scripts.verify_phase5b_runtime_repair_history`.
It compares the prior aggregate fingerprint, original draft payload, consumed
admission binding, exact planned graph, recorded task state, event count/type
distribution and recorded causal fields, and every R1/v1 history fingerprint.
It also checks that neither Memory version table contains v2 and latest Memory
still points to R1 / version 1. Full task/event fingerprints below record the
repair-time snapshot; the earlier diagnosis stored only selected causal events.

| Artifact | SHA-256 |
| --- | --- |
| R2 aggregate | `5e402fe19eef90df2a853a50619b6aa21772b6dbb2a0e7e718f108db9dd03dc5` |
| R2 task payloads | `9069f8af0b4b754d181f1122c9048179202f342872f1cdfbca9e7698adb879cd` |
| R2 event payloads | `20f9dddc04ca3cc9d8588243e74d382f715108a64a221f3f138cfee5efb29bb7` |
| Original draft payload | `04df3abd6661341575d7aa47d41ecfe793207e1bae2c791ffc0cb989cfab0dca` |

Scheme `SCHEME-b7a81dfc-7863-59e2-afd2-0371e796a1b6`, Goal, and decisions remain
unchanged (REUSE 0 / REFRESH 1 / REVALIDATE 1 / PREVENT 1 / UNKNOWN 0).
R1 remains `RUN-57aed683-75d6-4b47-acc6-a73053ea492e`, exact view
`RVV-05bec42f-ab9b-55c5-b502-c439b8abe948`, latest version 1.

Provider causality remains unchanged: MiMo graph planning succeeded in
19.416177208s and TeamoRouter generated capability succeeded in 10.351366s.
Neither caused dispatch failure. The defect was the accepted free-form Agent
label contract followed by exact runtime registry lookup.

## Read-only re-execution audit

`EXISTING_REEXECUTION_CONTRACT = ABSENT`.
`ResearchRun` encodes Scheme/Goal and paired incremental base identities, but no
retry/re-execution/supersession/attempt-group relation. Persistence does not enforce
one Run per Scheme, but absence of that uniqueness is not a re-execution contract.
Draft confirmation rejects consumed drafts; idempotency replay returns the original
admission rather than creating a replacement. Base Run identifies released R1
Memory and must not be overloaded to mean failed execution R2.

Recommended future semantic: a NEW Run with an explicit execution lineage link
to failed R2, bound to the same confirmed Scheme and exact R1 base/view. Preserve
failed R2 and its consumed draft. This relation was not implemented here.

`NEW_RUN_AUTHORIZED = NO`.
`NEXT_EXACT_ACTION = PHASE_5B_REEXECUTION_CONTRACT_REPAIR`.
No final Phase 5B tag and no push.
