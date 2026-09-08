# Adaptive runtime

[简体中文](ADAPTIVE_RUNTIME.zh-CN.md)

Generated-capability construction shares the Specialist registry, single-route clients, RecoveryBudget, Lead decisions, model execution policy and append-only evidence store. Generation uses an operation identity scoped to the real Task and requirement, preventing duplicate entry or outer-build budget resets while permitting later Specialist execution. Migration 0013 changes only the duplicate-entry index; legacy records default to the Specialist operation and remain immutable.

Spec capability evidence requires request-bound deterministic compilation before PASS, and stores requested/actual models plus candidate hash. UNKNOWN is not prior verification. Docker validation and registration approval remain mandatory independent gates. Classified generation or financial validation rejection is output-local and retains build IDs/stage; authentication, authority, hash/security/runtime integrity and unknown contract defects remain fatal. The generated operation retains the existing 180-second overall construction ceiling.

Source/dependency events use the frozen progress envelope and actual recorded task progress. The bounded public `message_code` grammar is `SOURCE_OUTCOME:<endpoint>:<status>:<accepted_count>`, `FINANCIAL_BRANCH:<calculation_type>:<status>:<available>/<required>:<reason>`, or `BLOCKED_BY_DEPENDENCY:<required_output_ids>`. These are display snapshots, never success or calculation authority. Source coverage exposes only the ten owned endpoints and explicit status/count fields; unknown fields still fail closed. Historical malformed events are not rewritten or accepted by weakening validation.

Provider/model failure → owned error classification → Lead recovery proposal → independent policy gate → bounded same-Run invocation → ordinary structured-output validation.

Recovery preserves Object, Run, Scheme, Task, actor/profile, exact input and output-contract hashes. It does not change financial evidence, regenerate the Scheme, replan the graph or admit another Run.

Registered candidates are teamorouter-sol, teamorouter-luna, teamorouter-terra (gpt-5.6-terra) and mimo-direct. Terra starts UNKNOWN without exact task/profile/schema evidence, not capability-verified. Health and capability are distinct: a reachable provider is not automatically verified for a profile/model/schema. Existing verified outputs may supply scoped capability evidence; otherwise only a separately permitted capability check can establish it. A fresh database must not import fabricated certifications.

Bounded Dynamic Model Routing: a provider may substitute the preferred model only within the pre-authorized model set for that execution. The actual model is authoritative execution identity and must be persisted truthfully. A provider response cannot expand its own authorization. The prospective `bounded-model-execution/v1` policy is resolved before HTTP and retained with each attempt. Explicit Luna→Terra grants cover Fundamental, Valuation and generated free-cash-flow-margin only; UNKNOWN Terra requires a budgeted capability check, otherwise exact scoped capability evidence is required. Other profiles remain exact-route. MiMo Provider / `mimo-v2.5` is authorized through `mimo-direct`, never through a TeamoRouter substitution. Provider changes require independent cross-provider recovery approval. Missing/unknown identities and substitution-disabled responses fail closed. Historical rejections are not reinterpreted.

A successful substituted capability check may supply its already-validated exact Task output without another HTTP call; it is observed success and does not certify Luna or Terra. Recovery switches and provider substitution are recorded separately. The preferred wire request remains in the policy snapshot; legacy `requested_model` on Specialist output retains the first request, while `actual_model` identifies execution. [Shared authority](../../src/domain/model_execution.py) governs Specialist, generated builder and checks. Graph planning and the evaluator gateway retain their separate exact-route contracts; this change does not claim dynamic substitution support there. Release, Review, Proof and source-availability policies are unchanged.

Defaults: at most three task invocations total, one invocation per route, one model fallback, one provider switch, one capability check, five decisions, zero runtime replans and 300 seconds including the initial invocation. A configured same-route ceiling can reach two within the total-three ceiling. Recovery single-route clients disable hidden retries/fallbacks.

Owned timeout/availability/protocol/rate failures can be considered. Authentication, identity, unsafe output, output-contract and unknown failures fail closed. Candidate selection is deterministic governed policy, not a model deciding that its own retry is safe.

The accepted historical Peer example shows MiMo timeout → ALLOW → Sol success within the same Run. It is evidence of one successful bounded recovery, not universal provider reliability.

[Domain](../../src/domain/recovery.py) · [Runtime](../../src/agentic/recovery.py) · [Composition](../../src/agentic/recovery_composition.py) · [Acceptance](../validation/ADAPTIVE_RECOVERY_ACCEPTANCE.md).
