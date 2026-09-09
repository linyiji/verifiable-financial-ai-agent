# Owner policy V1

[简体中文](OWNER_POLICY_V1.zh-CN.md)

Version: `recoverable-owner-policy/v1`. Source: [owner_policy.py](../../src/domain/owner_policy.py).
This prospective descriptor consolidates existing authority, not new global model grants. Runtime candidates, dynamic grants, recovery budgets and adaptive transport defaults use this source. Offline parity tests compare this table in both languages with the descriptor. Historical policy and audit evidence are not rewritten.

<!-- OWNER_POLICY_TABLE_START -->
| TaskProfile | Preferred | Candidates | Dynamic grants | Cross-provider | Execution/check/physical | Check | Outer seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GENERATED_CAPABILITY:gross_margin | teamorouter-sol | teamorouter-sol, teamorouter-luna, teamorouter-terra | NONE | NO | 3/1/4 | SEPARATE_EXECUTION | 180.0 |
| fundamental_analysis | teamorouter-sol | teamorouter-sol, teamorouter-luna, teamorouter-terra, mimo-direct | teamorouter-luna→teamorouter-terra | YES | 3/1/4 | SEPARATE_EXECUTION | N/A |
| valuation_analysis | teamorouter-sol | teamorouter-sol, teamorouter-luna, teamorouter-terra, mimo-direct | teamorouter-luna→teamorouter-terra | YES | 3/1/4 | SEPARATE_EXECUTION | N/A |
| risk_analysis | teamorouter-sol | teamorouter-sol, teamorouter-luna, teamorouter-terra, mimo-direct | teamorouter-luna→teamorouter-terra | YES | 3/1/4 | SEPARATE_EXECUTION | N/A |
| risk_follow_up | teamorouter-sol | teamorouter-sol, teamorouter-luna, teamorouter-terra, mimo-direct | teamorouter-luna→teamorouter-terra | YES | 4/3/4 | CONSUME_ONCE | N/A |
| peer_analysis | mimo-direct | mimo-direct, teamorouter-sol, teamorouter-luna | NONE | YES | 3/1/4 | SEPARATE_EXECUTION | N/A |
| research_news_analysis | mimo-direct | mimo-direct, teamorouter-sol, teamorouter-luna | NONE | YES | 3/1/4 | SEPARATE_EXECUTION | N/A |
| report_synthesis | teamorouter-sol | teamorouter-sol, teamorouter-luna, teamorouter-terra, mimo-direct | NONE | YES | 4/3/4 | CONSUME_ONCE | N/A |
| GENERATED_CAPABILITY:free_cash_flow_margin | teamorouter-sol | teamorouter-sol, teamorouter-luna, teamorouter-terra | teamorouter-luna→teamorouter-terra | NO | 3/1/4 | SEPARATE_EXECUTION | 180.0 |
| evidence_collection | NATIVE_DATA | NONE | NONE | NO | N/A | NOT_APPLICABLE | N/A |
<!-- OWNER_POLICY_TABLE_END -->

Execution/check/physical are distinct ceilings: a failed check consumes physical budget but need not consume a formal execution slot. Ordered risk_follow_up/report_synthesis retains the explicit four-physical-call/three-check/300-second exception. Normal profiles retain three execution slots plus one check. A capability check is never a free call. Cost is unknown (null), not zero; numeric cost caps without reliable metering fail closed.

All model task defaults retain one same-route attempt, one cross-provider switch where an independent candidate exists, five decisions, zero replans and a 300-second task ceiling. Ordinary profiles permit one model switch; ordered exceptions permit two. An explicit RecoveryBudget constructor override retains its prior precedence and must be frozen with its source for V1. Preferred route overrides come from Settings.specialist_provider_routes or GovernedCodeBuilder.initial_route, and remain subject to the candidate gate. Generated operations additionally have the existing 180-second outer ceiling. Restart never creates a fresh deadline for V1.

A directly authorized Terra candidate is not a Luna→Terra substitution grant. The five explicit grants are Fundamental, Valuation, Risk, Risk follow-up and generated free-cash-flow-margin. Synthesis and generated gross margin remain exact-route despite direct Terra eligibility. MiMo is an independently authorized cross-provider candidate, never a TeamoRouter substitution.

A validated exact check is consumed once only in the ordered profiles. Other exact checks establish scoped capability and require a separate, gated execution. A successful authorized substituted check may supply its validated output once. Reuse binds Task/Operation, input, schema, actual provider/model and validation; no toy probe supplies research output. New frozen V1 contracts retain these distinctions.

## Independent entry contracts

Scheme and Graph planning do not inherit Specialist candidate/grant authority. Both use explicitly configured exact-route providers (configured Sol may have its existing Luna fallback), a 90-second per-attempt / 180-second workload policy and zero capability checks. Scheme retains two validation passes. Production Graph retains one validation pass and fail-closed behavior; the standalone constructor override is separately frozen. Each inner HTTP attempt is accounted, not merely each wrapper call. INCREMENTAL_RESEARCH_PLANNING is a telemetry alias, not a third model operation. Initial deterministic Scheme/Graph paths are not fabricated model calls.

Native evidence uses FMP structured financials and Bocha Web discovery, each with its existing 20-second HTTP default. Bocha AI is out of scope. Native data inherits no model budget. V1 admission requires explicit finite total Intent/Run budgets; absence rejects V1 rather than inventing an allowance. FMP transient retries and governed slot rotation each count as physical attempts. quality_review remains declared but not an executable profile.

Adaptive single-route transport defaults: connect 10s, read 60s, write 30s, pool 10s, one attempt, no hidden backoff/fallback and 90s per-call wall-clock. All applicable outer/absolute deadlines dominate.

## FMP scoped health

Endpoint 402/403 or payload entitlement stays ENTITLEMENT_DENIED and does not invalidate authentication or rotate through the pool. A denied transcript does not poison quote or financial-statement access. Ambiguous 403 is never upgraded to global invalid authentication. Authentication failure (401 or structured authentication classification) invalidates that credential across endpoints. Bounded slot exclusion applies to HTTP429 and classified payload200 rate limits; exhausted slots do not automatically reset. Explicit structured account-scoped limits stop all slots without rotation. Provider health is not inferred from one endpoint response. Mixed pool exhaustion preserves its last actual classification instead of inventing an authentication failure. No historical Run cause is inferred from this repair.
