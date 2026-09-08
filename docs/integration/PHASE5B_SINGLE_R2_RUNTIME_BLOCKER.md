# Phase 5B single live R2 — stopped at runtime failure

[简体中文](PHASE5B_SINGLE_R2_RUNTIME_BLOCKER.zh-CN.md)

Start SHA: c4a80adc1db8c83551ee8e3d97442f3a3568450b. Branch phase4 was clean.
No final commit/tag/push: the full vertical slice did not pass. Implementation
changes made before the live attempt are retained uncommitted for review.

## Exact confirmation

Draft DRAFT-036cd4bd-fb8b-4c05-a9ba-25c654588342, version 1.
Scheme SCHEME-b7a81dfc-7863-59e2-afd2-0371e796a1b6.
Hash sha256:543ea7eda59287104b3cb1c2c1ca2f19da256aaa60359a3b6fa39876ab7ebf21.
Authorization LEASE-0e2bb5a10755b04f754bb905e1b5a8a004676c6fcbd1735ce1e92492f15a9bcf
was valid at confirmation; effective expiry 2026-09-07T10:39:17.555353Z.
The draft was consumed at 2026-09-07T10:30:13.187274Z by admission
ADM-315545cb-c617-45bc-ba04-b316a2c1fcf8.

The actual writable application ran with runtime workers and mimo-direct selected
only for Incremental Scheme/graph composition. Existing TeamoRouter runtime policy
was unchanged. The product browser visited OBJ-NVDA Memory v1, loaded the exact
renewed Draft, and clicked confirmation once. No prepare or Scheme generation.

The graph planner was configured before the live call with one validation attempt
and fail-closed behavior (no deterministic fallback on bad output). Typed graph,
dependency/skill checks and incremental fresh-work constraints passed. However,
the existing validator does NOT enforce executable registered Agent identities:
the resulting graph was not fully runtime-compatible. Do not treat its admission
as proof that the complete executable-graph contract passed.

## Observed provider evidence

Graph logical call a264db61-4d74-4dc6-acf5-bfe994082fd5:
mimo-direct / mimo / mimo-v2.5, one logical call, one HTTP attempt, HTTP 200,
2026-09-07T10:29:53.766790Z–10:30:13.182990Z, 19.416177 seconds,
2846 input tokens / 758 output tokens. No retry or fallback.

One later TeamoRouter logical call on the fundamentals task also succeeded:
gpt-5.6-sol, HTTP 200, one attempt, 10.351366 seconds, 1348 input tokens /
343 output tokens. There is no evidence of a provider timeout in this R2.
Runtime-profile route metadata was not present on that legacy client; do not
manufacture it. It was not silently migrated to MiMo.

## Retained R2 and narrow blocker

R2 = RUN-e1b27d55-a58f-428d-b98b-0dc519577bc0.
Object OBJ-NVDA, Base RUN-57aed683-75d6-4b47-acc6-a73053ea492e,
Base View RVV-05bec42f-ab9b-55c5-b502-c439b8abe948.
New LLM graph contains nine independently identified tasks.
Run started 10:30:13.254184Z and failed 10:31:25.561199Z.
Terminal event sequence 606: TASK_EXECUTION_FAILED / TASK_EXECUTION.
Peers, research-news and fundamentals failed; dependent tasks were blocked.

The persisted planned tasks use human labels (Fundamental Analysis Agent,
Peer Analysis Agent, Research News Analysis Agent, etc.) for assigned_agent.
The actual registered runtime identities are fundamental_analyst, peer_analyst,
research_news_analyst, valuation_analyst, risk_analyst and research_lead.
src/application/execution.py invokes registry.get(task.assigned_agent) and raises
for unknown IDs when the production registry is nonempty. The graph schema only
requires a nonempty string for assigned_agent. This is the concrete dispatch
contract mismatch found by read-only inspection. Durable failure events preserve
only TASK_EXECUTION_FAILED, not a detailed original exception traceback.

No failed-Run repair, graph rewrite, second graph call, renewed lease, replacement
Run, provider switch or retry was performed. The consumed draft must not be
confirmed again for a new Run.

## Truth and artifacts

The immutable draft still equals the original MiMo capability artifact. The
confirmed Scheme equals that original Scheme except for confirmed_at; the Goal
is identical. Decisions and exact sources remain 0 REUSE / 1 REFRESH /
1 REVALIDATE / 1 PREVENT / 0 UNKNOWN.

R2 aggregate retains 536 evidence records, 10 calculations, one correction and
zero Agent outputs. No Review, Proof, canonical record, Report, ReleasedResult,
or Memory v2 exists. All previous Run IDs are unchanged with exactly one new ID;
R1 and Object/View v1 fingerprints remain unchanged. Latest memory remains exact
R1 / View v1. No writeback or Base-vs-Current release comparison was attempted.

Browser displays the exact failed R2 and failed/blocked tasks. Full lifecycle
01–05 and A/B/C acceptance were NOT reached. Some existing terminal-status copy
says research completed despite the explicit FAILED badge; this is a secondary
product-copy issue, not proof of a successful research result.

The browser observer lost access to the POST response body after successful
navigation; its final assertion failed. This was an observation failure, not an
admission failure: the server logged HTTP 201, the page navigated to exact R2,
and durable consumption/admission/Run records confirm success. Never rerun the
guarded confirmation script to obtain a missing response artifact.

Evidence directory: artifacts/phase5b_live_r2_final. The permanent confirmation
guard, pre-confirm review, screenshot and safe metadata-only attempts.json remain.
94 focused Python tests and 58 frontend checks passed, plus the earlier 35-test
planner/incremental run; counts overlap, so focused receipt counts only 152.
Typecheck/build passed. Full end-to-end acceptance did not pass.

Product comprehension: remembered R1, exact sources, decision meanings and REUSE0
were visible. Independent R2 identity and failed runtime were visible. Successful
R2 Results, Base-vs-Current v2 and accumulating released Memory v2 were NOT reached.

NEXT_EXACT_ACTION = PHASE_5B_RUNTIME_BLOCKER_REPAIR. STOP.
