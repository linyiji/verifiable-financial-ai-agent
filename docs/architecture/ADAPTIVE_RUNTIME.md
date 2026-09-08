# Adaptive runtime

[简体中文](ADAPTIVE_RUNTIME.zh-CN.md)

Provider/model failure → owned error classification → Lead recovery proposal → independent policy gate → bounded same-Run invocation → ordinary structured-output validation.

Recovery preserves Object, Run, Scheme, Task, actor/profile, exact input and output-contract hashes. It does not change financial evidence, regenerate the Scheme, replan the graph or admit another Run.

Registered candidates are teamorouter-sol, teamorouter-luna, teamorouter-terra (gpt-5.6-terra) and mimo-direct. Terra starts UNKNOWN without exact task/profile/schema evidence, not capability-verified. Health and capability are distinct: a reachable provider is not automatically verified for a profile/model/schema. Existing verified outputs may supply scoped capability evidence; otherwise only a separately permitted capability check can establish it. A fresh database must not import fabricated certifications.

Luna requests returning Terra remain MODEL_IDENTITY_MISMATCH and are rejected. Only an explicitly authorized Terra request with an exact Terra response can pass. Missing reported identity is also rejected. Registering a fourth candidate does not increase any attempt or recovery budget. This is governed maintenance, not learned routing or capability certification.

Defaults: at most three task invocations total, one invocation per route, one model fallback, one provider switch, one capability check, five decisions, zero runtime replans and 300 seconds including the initial invocation. A configured same-route ceiling can reach two within the total-three ceiling. Recovery single-route clients disable hidden retries/fallbacks.

Owned timeout/availability/protocol/rate failures can be considered. Authentication, identity, unsafe output, output-contract and unknown failures fail closed. Candidate selection is deterministic governed policy, not a model deciding that its own retry is safe.

The accepted historical Peer example shows MiMo timeout → ALLOW → Sol success within the same Run. It is evidence of one successful bounded recovery, not universal provider reliability.

[Domain](../../src/domain/recovery.py) · [Runtime](../../src/agentic/recovery.py) · [Composition](../../src/agentic/recovery_composition.py) · [Acceptance](../validation/ADAPTIVE_RECOVERY_ACCEPTANCE.md).
