# Adaptive runtime

[简体中文](ADAPTIVE_RUNTIME.zh-CN.md)

Generated-capability construction shares the Specialist registry, single-route clients, RecoveryBudget, Lead decisions, policy gate and append-only evidence store. It starts on the governed Sol route; Terra is an explicit candidate, never a Luna alias. A mismatched response is rejected and quarantines that route; a separate permitted decision may select another route within the unchanged limits. Generation uses an operation identity scoped to the real Task and requirement, preventing duplicate entry or outer-build budget resets while permitting later Specialist execution. Migration 0013 changes only the duplicate-entry index; legacy records default to the Specialist operation and remain immutable.

Spec capability evidence requires request-bound deterministic compilation before PASS, and stores requested/actual models plus candidate hash. UNKNOWN is not prior verification. Docker validation and registration approval remain mandatory independent gates. Classified generation or financial validation rejection is output-local and retains build IDs/stage; authentication, authority, hash/security/runtime integrity and unknown contract defects remain fatal. The generated operation retains the existing 180-second overall construction ceiling.

Source/dependency events use the frozen progress envelope and actual recorded task progress. The bounded public `message_code` grammar is `SOURCE_OUTCOME:<endpoint>:<status>:<accepted_count>`, `FINANCIAL_BRANCH:<calculation_type>:<status>:<available>/<required>:<reason>`, or `BLOCKED_BY_DEPENDENCY:<required_output_ids>`. These are display snapshots, never success or calculation authority. Source coverage exposes only the ten owned endpoints and explicit status/count fields; unknown fields still fail closed. Historical malformed events are not rewritten or accepted by weakening validation.

Provider/model failure → owned error classification → Lead recovery proposal → independent policy gate → bounded same-Run invocation → ordinary structured-output validation.

Recovery preserves Object, Run, Scheme, Task, actor/profile, exact input and output-contract hashes. It does not change financial evidence, regenerate the Scheme, replan the graph or admit another Run.

Registered candidates are teamorouter-sol, teamorouter-luna, teamorouter-terra (gpt-5.6-terra) and mimo-direct. Terra starts UNKNOWN without exact task/profile/schema evidence, not capability-verified. Health and capability are distinct: a reachable provider is not automatically verified for a profile/model/schema. Existing verified outputs may supply scoped capability evidence; otherwise only a separately permitted capability check can establish it. A fresh database must not import fabricated certifications.

Luna requests returning Terra remain MODEL_IDENTITY_MISMATCH and are rejected. Only an explicitly authorized Terra request with an exact Terra response can pass. Missing reported identity is also rejected. Registering a fourth candidate does not increase any attempt or recovery budget. This is governed maintenance, not learned routing or capability certification.

Defaults: at most three task invocations total, one invocation per route, one model fallback, one provider switch, one capability check, five decisions, zero runtime replans and 300 seconds including the initial invocation. A configured same-route ceiling can reach two within the total-three ceiling. Recovery single-route clients disable hidden retries/fallbacks.

Owned timeout/availability/protocol/rate failures can be considered. Authentication, identity, unsafe output, output-contract and unknown failures fail closed. Candidate selection is deterministic governed policy, not a model deciding that its own retry is safe.

The accepted historical Peer example shows MiMo timeout → ALLOW → Sol success within the same Run. It is evidence of one successful bounded recovery, not universal provider reliability.

[Domain](../../src/domain/recovery.py) · [Runtime](../../src/agentic/recovery.py) · [Composition](../../src/agentic/recovery_composition.py) · [Acceptance](../validation/ADAPTIVE_RECOVERY_ACCEPTANCE.md).
