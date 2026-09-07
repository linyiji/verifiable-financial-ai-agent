# Phase 5B invocation diagnosis — PARTIAL, no R2 authorization

Start HEAD `3fc3324c66ca995823f5020b9829d6f5ee9e27a8`, tree
`aa6ccb1c0bc3137a448dd4312b873129986dee6f`, branch phase4, initially clean.
Neither HEAD nor frozen tags changed. Changes remain uncommitted because live
verification failed; the requested successful-repair commit condition was not met.

## Architecture finding

Normal product prepare/confirm uses ResearchApplicationService's defaults:
DeterministicSchemeGenerator and ResearchLeadPlanner. It does not make a model call
at initial planning. Incremental prepare uses PlannerProviderSchemeGenerator;
confirm would use PlannerProviderResearchLeadPlanner (not reached here).

Both model-backed planning classes call `_complete_before_deadline` then the same
TeamoRouterClient.complete_structured adapter. Runtime specialist/research-lead
synthesis also uses that adapter and the same client instance in production.
Incremental does not bypass an extra accepted HTTP gateway or resilience stack.
It differs in bounded context/schema and rejects deterministic Scheme fallback.

The shared adapter deduplicates primary/fallback routes, limits attempts to two,
applies a one-second backoff, and retries read timeouts on the configured fallback.
Effective production configuration is connect 10s, read 60s, write 30s, pool 10s,
attempt deadline 90s, overall deadline 180s. The policy dataclass's standalone
45-second read default is not the production adapter's effective default: the
adapter explicitly supplies 60 seconds. This is shared behavior, not an Incremental
configuration mismatch. No timeout, route, scheduler, validation or retry was changed.

## Historical evidence limits and narrow change

The first live failure retained READ_TIMEOUT but no attempt record. Its process
had no VFA_PERFORMANCE_PATH configured. Actual historical attempt count, per-attempt
duration, fallback and provider queue/inference times cannot be recovered.

Added seven numeric timeout/budget fields to the existing INTERNAL telemetry
allowlist and annotated the existing logical-call span. No public DTO change or
prompt/provider-body logging. Added parity/exhaustion tests and a one-shot guarded
planning-only verification script. Telemetry remains opt-in; the verification
explicitly enables and flushes the existing Recorder. This improves diagnosis, not
provider reliability, and is not presented as a timeout fix.

## Single live verification

One additional planning operation was performed. The existing adapter executed two
HTTP attempts within that operation. No second logical call or manually repeated
verification occurred. The verification caps Scheme validation attempts at one to
stop on invalid output, while retaining production transport retries/fallback and
the same strict Scheme schema, context builder and validators.

Logical call: `9c1245c4-4218-4d61-9c4c-6ea6099670cc`.
Provider: teamorouter. Requested primary: gpt-5.6-sol.

| Stage | UTC start | UTC end | Observed duration | Outcome |
| --- | --- | --- | --- | --- |
| Primary gpt-5.6-sol | 08:12:59.184 | 08:14:00.152 | 60.968s | READ_TIMEOUT |
| Backoff | 08:14:00.152 | 08:14:01.154 | 1.002s | Completed |
| Fallback gpt-5.6-luna | 08:14:01.154 | 08:15:01.935 | 60.781s | READ_TIMEOUT |

All timestamps are 2026-09-07. Total logical duration 122.754s, below the 180s
deadline. Neither attempt returned a completed HTTP response. Actual served model,
schema acceptance, provider queue/inference latency and upstream cause are unknown.
The strongest classification is READ_TIMEOUT_ON_PRIMARY_AND_FALLBACK, not proven
schema rejection, transient slowness, retry bypass, or an undersized total deadline.
Final safe reason: `INCREMENTAL_MODEL_INVOCATION_READ_TIMEOUT`.

Remote schema acceptance NOT_OBSERVED. Live planning FAIL. Scheme validation and
all actual live decision counts NOT_REACHED. Failure is not a valid empty Scheme.
No further provider calls are permitted under this task's consumed allowance.

## Safety, verification, and stop

The script loads the exact released Object/Run/view from PostgreSQL read-only, never
starts the app, and never invokes admission or graph/runtime creation. Before/after
fingerprints match for all 36 Run IDs and R1/v1 records. Latest remains
RUN-57aed683-75d6-4b47-acc6-a73053ea492e / View 1
(RVV-05bec42f-ab9b-55c5-b502-c439b8abe948). No R2 or v2 created.

392 focused tests/checks passed: 66 invocation/schema/policy/telemetry tests,
139 memory/admission/results/safety tests, 187 frontend regression checks.
Typecheck/build and targeted Ruff checks passed. Provider inference and queue times
remain NOT_OBSERVED; no raw prompts, responses, credentials or hidden reasoning
were retained in telemetry or product data.

Evidence under artifacts/phase5b_invocation_repair: attempts.json, result.json,
verification-attempt.json (permanent no-replay guard), history-guard.json.

Prior external operations remain separately counted: one old diagnostic, one first
live workflow planning operation, and this one additional planning operation.
New provider Research Runs remain zero across all three.

LIVE_R2_AUTHORIZED = NO. No commit, tag, push or further live operation.
NEXT_EXACT_ACTION = PHASE_5B_LIVE_R2_BLOCKER_REPAIR_2. STOP.
