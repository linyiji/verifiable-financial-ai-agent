# Provider Runtime Foundation v0 — MiMo capability PASS

Start HEAD: 3fc3324c66ca995823f5020b9829d6f5ee9e27a8.
This checkpoint adds explicit availability routes, not Phase 6 model selection.
No automatic provider failover, ranking, quality routing, timeout increase or R2.

## Contract and composition

Reuse LLMProvider.complete_structured, LLMMessage, LLMStructuredResponse,
ProviderExecutionPolicyV1 and existing logical/attempt telemetry. ProviderRoute is
a frozen, secret-free descriptor: route/provider/model, endpoint authority reference,
structured-output mode and timeout/resilience policy. No redundant request/result
framework was introduced.

Routes: teamorouter-sol, teamorouter-luna, mimo-direct. Explicit selection is
INCREMENTAL_PROVIDER_ROUTE; default remains teamorouter-sol. Application composition
calls configured_incremental_provider; researchers never branch on adapter classes.
MiMo selection affects Incremental Scheme/graph planning only. Existing runtime
specialists and TeamoRouter's 60s read, 90s attempt, 180s total, two-model route and
one-second backoff remain unchanged. No global automatic provider switching.

Each logical call/attempt records task_profile, route, provider, requested/attempted
model, IDs, start/end, duration, failure and observed usage through the existing
allowlisted internal recorder. Attempt count and fallback are derivable from attempt
records; no failed-call tokens or cost are manufactured. No Evaluation tables.

## Local authority and protocol

The external AtlasAnalyse production-runtime-v1 MiMo authority was read in place.
MIMO_API_KEY and MIMO_BASE_URL were nonempty; exact MIMO_CHAT_MODEL is mimo-v2.5.
The file was not copied into the repository. The loader accepts only the approved
HTTPS api.xiaomimimo.com/v1 authority, disallows URL credentials/query/fragment,
and fails closed for missing authority or unestablished model capability. SecretStr
holds credentials; route descriptors and telemetry contain no credential values.
The production recorder's forbidden-values list includes the selected route key.

Prior AtlasAnalyse adapter source (retained September 4 build) uses OpenAI-compatible
chat completions, Bearer auth, nonstreaming JSON mode and local output validation.
Only those protocol concepts and authority are reused, not its application runtime.

MiMo's official structured-output guide documents json_object for mimo-v2.5,
not native JSON-schema enforcement. Classification:
JSON_MODE_WITH_STRICT_LOCAL_VALIDATION. The adapter supplies the complete existing
schema in the system input, asks for JSON only, disables thinking, bounds completion
tokens at 8192, and parses the complete content with json.loads plus the unchanged
Pydantic validator. No Markdown stripping, partial extraction, dropped fields,
invented sources or acceptance of free-form output. Exact incremental policy and
source validation run after parsing. Native schema enforcement is not claimed.

Documentation: https://mimo.mi.com/docs/en-US/quick-start/usage-guide/text-generation/structured-output

MiMo Direct differs from TeamoRouter in gateway/base URL and credential authority.
Failure-domain independence is PARTIAL overall: it escapes the observed gateway
and credential route but shares the user's machine and network egress. Independent
upstream ownership/account internals beyond configured authority are not audited.

## One live capability operation

2026-09-07 09:21:42.199–09:22:11.483 UTC. One logical call, one HTTP attempt, HTTP200.
Reported model mimo-v2.5; logical latency 29.284s. Usage observed: 2783 input tokens,
710 output tokens. No fallback. No prompt, raw provider response or reasoning
content was persisted in diagnostic evidence.

Real exact base: OBJ-NVDA / RUN-57aed683-75d6-4b47-acc6-a73053ea492e /
RVV-05bec42f-ab9b-55c5-b502-c439b8abe948. The returned Scheme passed all typed,
policy, exact-source, public-projection and immutable draft-hash checks.
Actual decisions: REUSE0, REFRESH1, REVALIDATE1, PREVENT1, UNKNOWN0.
The current work scope covers current financial evidence, growth/profitability,
valuation/risks and recent disclosures, with verified/unverified distinctions.

The capability runner invokes production backend.prepare_run without starting the
app/scheduler or invoking confirm. It persists the real draft transaction. Replaying
the same prepare key returns the identical stored draft without another model call.

## Exact next-task handoff

Draft: DRAFT-036cd4bd-fb8b-4c05-a9ba-25c654588342, version1.
Scheme: SCHEME-b7a81dfc-7863-59e2-afd2-0371e796a1b6.
Draft hash: sha256:543ea7eda59287104b3cb1c2c1ca2f19da256aaa60359a3b6fa39876ab7ebf21.
Prepare replay key: mimo-capability-exact-nvda-v1-20260907.
The existing frozen 30-minute lease expires 2026-09-07 09:51:42.157929 UTC.

Next task must load/review and confirm THIS persisted draft, not generate a new
Scheme. confirm_run reconstructs the Scheme from its hash-checked stored snapshot;
it calls the graph planner, not the Scheme generator. Real isolated PostgreSQL
tests prove prepare replay and confirmation reuse. Graph planning is separate new
work within the next R2 task, not a repeat Scheme call.

If the lease has expired, stop before admission: do not bypass expiry or issue a
paid prepare. The validated Scheme remains retained for an explicit local draft
renewal/review step using unchanged Scheme contents. No lease was silently extended
and no expired draft may be confirmed. R2 permission remains subject to those
existing confirmation/expiry gates and the next task's authorization.

For the next production process explicitly select INCREMENTAL_PROVIDER_ROUTE=mimo-direct.
Do not run either consumed verification script again. Both have exclusive attempt
markers. Do not accidentally run the old browser --start flow, which prepares a
new Scheme; the next flow must begin with the retained draft.

## Verification and checkpoint

269 focused Python tests pass, including real isolated PostgreSQL prepare/confirm
replay, MiMo JSON parsing/failure/redaction, exact base, parity, memory and results.
187 frontend regression checks pass. Typecheck/build and targeted lint pass.
All 36 real Run IDs and R1/v1 fingerprints remain unchanged. No R2, tasks, specialist
outputs, review/proof/report/released result, Memory v2 or pointer advancement.

Retained prior dirty diagnostic annotations, parity tests, guarded verification
support and historical blocker receipt have durable provenance value and are
included coherently. No unrelated changes. One foundation checkpoint, no Phase5B
tag, no push. Evidence: artifacts/mimo_provider_capability/{result,attempts,
history-guard,validated-persisted-draft}.json. The exact validated public draft is
also durable in PostgreSQL, not just a file artifact.

NEXT_EXACT_ACTION = PHASE_5B_EXECUTE_SINGLE_LIVE_R2_FINAL. STOP before confirmation.
