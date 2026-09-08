# Phase 6 Adaptive Runtime Recovery Foundation

[简体中文](PHASE6_RECOVERY_FOUNDATION.zh-CN.md)

Design authority: `<local-design-directory>/PHASE6_ADAPTIVE_EXECUTION_RECOVERY_DESIGN.md` (Owner-supplied design document, not a repository file).
Starting checkpoint: `e6d690364c4abd3e53113ad9f52205d50d8d8e40` (`phase4`).

## Frozen scope

Runtime recovery means **same confirmed work, different bounded invocation attempt**.
Research correction/replan means changing the work and remains under the existing
Dynamic Research Path authority. No scheduler retry expansion, new Run admission,
Scheme/Graph generation, release, or memory publication occurs here.

Previously, `LLMResearchAgent.execute` converted a provider failure to a nonretryable
invocation error; the scheduler failed the Task, blocked dependents, and failed the Run.
Recovery now wraps only the Specialist `complete_structured` call, after exact context
construction. Calculation, evidence collection, Review and Proof are not replayed.
The configured initial route retains its accepted invocation authority; alternatives
require matching capability evidence or a separately gated capability check.

Task identity is not attempt identity. Recovery keeps the Task RUNNING while the
independent policy permits another invocation. Successful output returns through the
unchanged Specialist artifact/output validation and ordinary scheduler completion path.
Scheduler `attempt_count` is not redefined: the new evidence describes invocation
attempts inside that one scheduler execution.

## Domain and authority

- Deterministic classifier consumes owned adapter codes, never exception-string guesses.
  Timeouts, unavailable routes, protocol errors and bounded retryable HTTP/rate failures
  can recover. Adapter 408/5xx conflation is honestly classified PROVIDER_UNAVAILABLE.
  Output contracts, authentication, identity, unsafe output and unknown errors fail closed.
- ProviderDetector follows the Tool registry's finite resolution/availability philosophy;
  it does not overload ToolRegistry or build a generic capability platform.
- Only `teamorouter-sol`, `teamorouter-luna`, and `mimo-direct` exist. Canonical
  provider/model pairs and existing credential authority are independently validated.
- Health is separate from profile/model/schema-specific capability. Healthy does not
  mean VERIFIED. Recent transport evidence affects health, not financial truth.
- RecoveryContext contains at most three candidates, three execution routes and twelve
  evidence references, exact Run/Task/Object/Scheme/actor/profile identities, input and
  output-contract hashes, and remaining limits. No prompts, output bodies or raw logs.
  Dependency/downstream fields describe the current scheduler seam, not a new Graph.
- ResearchLeadRecoverySupervisor is a deterministic Lead policy, following the existing
  replan-decider pattern. It proposes known-capability routes before UNKNOWN checks in
  fixed registered order. It does not call an LLM to recognize transport failures.
- Independent policy checks identity, refs, registered authority, health, capability,
  exhaustion, action type and budgets. Supervisor errors are safe terminal denials.
- Closed actions include retries, model/provider switch, capability check, fail Task/Run,
  wait, and semantic correction/replan. This foundation executes only bounded invocation
  actions and failures. Wait and semantic actions are denied here, not silently executed.

## Hard budgets

Defaults: three Task invocations total, one invocation per route, one model fallback,
one provider switch, one capability check, five decisions, zero runtime replans,
300 seconds including the initial invocation. Configurable values cannot exceed these
ceilings, except same-route count can be explicitly raised to two within the total three.
Single-route clients disable hidden retries/fallbacks: one HTTP attempt, read timeout
60 seconds and route deadline 90 seconds, also capped by remaining recovery time.

Capability checks are separately flagged and counted, not hidden as successful Task
execution: a PASS check requires a new decision before an actual invocation. At most
four provider calls can therefore occur per Task (three executions plus one check).
Failed checks quarantine the profile/route/model/schema and cannot force execution.
Budgets never authorize a fourth execution or a second check.

Actual cost is not observable. `max_total_recovery_cost=None` explicitly means no cost
authority; configuring a numeric limit rejects invocation instead of inventing costs.
Terminal exhaustion is persisted as `RECOVERY_BUDGET_EXHAUSTED`.

## Durable evidence and passive certification

Migration `20260908_0012` adds only `phase6_recovery_evidence`, its indexes and immutable
UPDATE/DELETE trigger. No backfill. Attempt start is committed before invocation and
completion after it; decisions retain bounded context and ALLOW/DENY outcome. Evidence
includes owned failure code, route/model, latency, usage when supplied, and output hash.
It complements existing transport telemetry without copying raw HTTP payloads.

Partial uniqueness on the first invocation's Run/Task prevents concurrent duplicate
execution. A restart/redelivery with existing evidence refuses to reset the budget.
An interrupted process can leave STARTED without COMPLETED; that is honest unfinished
evidence, not fabricated success. Automatic crash resumption is outside this foundation.

Historical certification is read-only: exact Task/actor/Run binding, actual route/model,
SHA-verified original artifact, retained structured output equality, current profile
schema validation and secret check. A persisted new PASS certifies capability only when
its matching STARTED evidence agrees on attempt, scope, route/model and check flag.
Ordinary transport failures do not replace a previous successful capability reference.
Missing or unverifiable evidence remains UNKNOWN. Historical failures without a known
actual model do not manufacture model-specific health facts.

Read-only production audit found Peer and Research/News MiMo VERIFIED, Fundamental MiMo
UNKNOWN. Fundamental Luna likewise has no imported successful profile certification;
it is not granted one from a configured fallback name. Fixed-order UNKNOWN probing may
spend the sole check on Luna before MiMo; this foundation promises bounded governed
recovery, not guaranteed recovery for every live availability pattern. No live probe
was performed and no future R5 success is claimed.

Authoritative additive backend projection:
`GET /research-runs/{run_id}/recovery`. It checks exact Run existence and returns typed
owned records. Historical Runs return an empty list, not reconstructed attempts.
No frontend recovery timeline is added. Existing A/B/C projection contracts are intact.

## Product comprehension

1. A recoverable timeout does not immediately fail the Task/Run when an allowed route remains.
2. The Lead policy decides whether another governed attempt is worthwhile under finite limits.
3. It cannot invent a provider: closed identities and independent registry gate.
4. It cannot exceed budgets: every action is gated and clients contain no hidden retry loop.
5. A healthy provider may have UNKNOWN, UNSUPPORTED or QUARANTINED task capability.
6. UNKNOWN permits only a bounded check; successful check still requires a new decision.
7. Attempts and decisions are append-only, exact-identity, publicly safe evidence.
8. Semantic failures stay outside infrastructure switching; Review/Proof are unchanged.

## Verification and operating boundary

Mocked provider tests exercise Sol failure → verified Luna failure → UNKNOWN MiMo check
PASS → MiMo execution PASS. A real DependencyScheduler test then completes downstream
work on the same Graph and enters REVIEW. This is local deterministic evidence, not a
production completion claim. PostgreSQL tests use isolated temporary schemas, including
immutable evidence, concurrent entry, restart budget protection and exact-run API view.

The broad regression uncovered two pre-existing currency fixture failures, reproduced
on the clean starting commit. Only their calculation fixture was corrected from generic
CURRENCY to USD to match the existing release contract; production projection code was
not changed. Frontend typecheck/build and M3–M6 interaction checks are also required.

No real model/provider calls, reexecution authorization, R5, Memory v2, learned ranking,
POT, tag or push are part of this task. Hash audits cover all historical Runs, Drafts,
Schemes, goals, Tasks, events, calculations, Review/release records and Memory tables.
After accepted foundation, stop. Next task: `PHASE_5B_EXECUTE_R5_WITH_ADAPTIVE_RUNTIME`.

Final verification: 724 Python tests passed (backend product, Agentic, Peer input,
TeamoRouter execution policy and transport observability); 119 frontend M3–M6 checks
passed; TypeScript typecheck, Vite build, changed-file Ruff and Python compilation
passed. The two existing Starlette/httpx deprecation warnings are nonblocking.
The additive production migration was applied with zero evidence rows and no backfill.
Local audit artifacts are `artifacts/phase6_recovery/before.json` and `after.json`.
These contain hashes and public identifiers only; all 16 audited historical tables
retain identical counts and hashes, with 39 Runs, two reexecution authorizations,
one Research View and unchanged R1/v1 memory pointer.
