# Phase 6 Evaluation Data Contract V1

Status: **parent-frozen preparation contract**, 2026-09-08. Documentation only;
no new runtime model, table, API, extractor, scores or route policy implemented.
Existing storage/APIs and safe retained telemetry suffice for the R5 vertical slice.
Baseline: `85962ecb9148c5a93bfd855ee6bffe554967db9b`. Companion
[Alpha authority](USER_ALPHA_READINESS.md) and [R5 acceptance](PHASE5B_R5_ADAPTIVE_ACCEPTANCE.md).

## 1. Subject, identities and evidence discipline

`EvaluationObservationV1` is a future read-only projection of an invocation,
keyed by existing `(run_id, task_id, attempt_id)`. The canonical attempt identity
is `RecoveryEvidence.attempt_id` (`ATT-UUID`), not a new evaluation ID.
`record_id` (`REC-UUID`) identifies ledger events. The repository does **not**
currently have a separate type/table named `TaskExecutionAttempt`.

Pair ATTEMPT_STARTED and ATTEMPT_COMPLETED by exact ATT ID and full Scope; retain
both REC IDs. DECISION/TERMINAL events are separately linked evidence, not fake
attempts. Missing completion means incomplete/unknown, not presumed failure.
Conflicting scope, duplicated conflicting completions or ambiguous joins are
quarantined, not silently merged. Do not backfill ATT IDs into old Runs.

Every evidence-bearing field uses this envelope, including optional fields and
derived grouping keys. Projection schema/version labels are metadata, not evidence.

```text
EvidenceValue<T> {
  value: T | null
  evidence_class: OBSERVED | DERIVED | NOT_OBSERVED
  source_refs: [{authority, run_id?, record_id?, field_path, artifact_digest?}]
  derivation: null | {rule_id, definition, input_refs}
  missing_reason: null | closed missingness code
  native_classification: null | source classification, when different
}
```

- OBSERVED = value actually recorded by identified authority. A runtime classifier's
  observed classification is not proof of provider/proxy root cause.
- DERIVED = deterministic result with explicit inputs/rule, not guessed quality.
- NOT_OBSERVED requires `value=null`, never `0`, `false`, empty-success or a guessed
  enum. Missingness codes: `ABSENT_SOURCE_FIELD`, `NO_EXACT_JOIN`,
  `NO_BILLING_AUTHORITY`, `NO_DIRECT_QUALITY_LINK`, `LEGACY_NO_ATTEMPT_LEDGER`,
  `NOT_APPLICABLE`, `NOT_YET_COLLECTED`. State which applies.
- Referenced authority may contain private material internally; exported fields
  are allowlisted IDs/codes/hashes/numbers and scoped safe evidence only. No prompts,
  raw responses, scratchpads, CoT, credentials, connection URLs or sensitive feedback.
- Do not add new providers: use existing RouteId/ModelId registry conventions.

## 2. Minimum field contract and present authority

Paths refer to existing `src/domain/recovery.py` types unless noted.

| Field/group | Current source | V1 class / semantics |
| --- | --- | --- |
| run_id, task_id, object_id, scheme_id, task_profile, agent_id | RecoveryEvidence.scope | OBSERVED exact identities, not display names |
| context_hash, contract_hash | Scope | OBSERVED stored integrity hashes; contract_hash is response-model JSON schema hash |
| base_run_id, base_research_view_version, reexecution_of_run_id | Exact ResearchRun | OBSERVED lineage via exact-run join; keep knowledge and execution lineage separate |
| attempt_id, attempt_number | RecoveryEvidence | OBSERVED; number is purpose-specific, not global transport count |
| invocation_purpose | capability_check | DERIVED boolean mapping to PRODUCTION or CAPABILITY_CHECK |
| provider_route, provider, model | route/provider/model | OBSERVED ledger route identity; on failure model is attempted identity, not a successful provider response |
| start/completion timestamps, source_record_ids | Paired ledger events | OBSERVED UTC strings/REC IDs; preserve native ordering |
| attempt_outcome | Completed.outcome | OBSERVED PASS/FAIL/CANCELLED; STARTED alone is not success/failure |
| failure_class | Completed.failure_class | OBSERVED owned FailureClass when present; success absence is NOT_APPLICABLE |
| failure_stage, recoverable | Matching DECISION.recovery_context.failure | OBSERVED classifier values only with exact same-scope failure link |
| attempt_latency_ms | Completed.latency_ms | DERIVED monotonic elapsed measurement, rule LATENCY_MONOTONIC_MS_V1; retain source number |
| input_tokens, output_tokens | Completed usage | OBSERVED provider-reported successful usage; absent failure usage remains null |
| output_hash | Completed.output_hash | OBSERVED digest; capability output hash is not a production AgentOutput |
| recovery_action, policy_decision | DECISION.action/outcome | OBSERVED closed Action and ALLOW/DENY; keep REC refs |
| candidates, capability status/evidence | RecoveryContext.candidates | OBSERVED historical snapshot and capability_evidence_refs, not current status substituted backward |
| remaining budget and decision reason | RecoveryContext + RecoveryDecision | OBSERVED snapshot; no budget enlargement or policy mutation |
| terminal_reason | TERMINAL.reason_code | OBSERVED if present; do not synthesize exhaustion from missing history |
| logical_latency_ms | ResearchAgentOutputRecord.duration_ms | OBSERVED recorded whole-Agent duration; scope AGENT_INVOCATION, not a last-attempt duration |
| transport latency/retry/backoff/stage | Safe performance spans, only if unambiguously linked | OBSERVED native fields; cross-source association DERIVED or NO_EXACT_JOIN |
| cost | No billing authority | NOT_OBSERVED / NO_BILLING_AUTHORITY |
| universal quality score, route preference | No authority/scoring in scope | NOT_OBSERVED / NOT_YET_COLLECTED; never inferred from output text |
| semantic task-contract version, normalized complexity class | No general authority | NOT_OBSERVED; no invented default |
| human feedback | Future sanitized Alpha session evidence | NOT_OBSERVED until collected; separate human source and scope |

Latency convention: the recovery runtime records `(monotonic_end-start)*1000`.
V1 labels that calculation DERIVED and names its method; a telemetry source's
native `classification=OBSERVED` is retained separately, not overwritten.
Do not add logical duration to its included attempt durations (double counting).
Failed-call token nulls are not zero; successful reported zeros are observed only
when the source actually supplies them. CER `token_usage=0`, `cost=0.0` and
`latency_ms=0` defaults are **not** measurement/billing authorities.

RecoveryContext does not provide an explicit failure ATT foreign key. Link a
decision's failure to the unique preceding failed completion with identical Scope
and current route, consistent bounded attempt history and event order. Mark this
association DERIVED; retain the observed classifier field from the linked record.
If ambiguous, failure_stage stays null with NO_EXACT_JOIN. Never join by fuzzy text.

## 3. Reliability and recovery derivations (definitions, not scores)

Preserve raw events. Derived facts require complete, consistent relevant evidence;
otherwise unknown. Distinguish transport fallback from Main-Agent recovery.

| Fact | Definition / authority |
| --- | --- |
| production_attempt_count | Count unique completed/started PRODUCTION ATT IDs, reporting started and completed separately |
| capability_check_count | Separate CAPABILITY_CHECK ATT denominator; never count as completed research |
| initial_route_success | First production attempt PASS with no prior production failure |
| timeout/provider_unavailable/protocol_failure | Exact owned recorded failure class; no guessed provider blame |
| native_fallback_used / recovered | Only exact linked transport attempt evidence; configuration alone is not an observed fallback |
| main_agent_recovery_used | Same-scope observed recovery DECISION with allowed action and linked following attempt |
| provider_switch / model_switch | Distinct observed action, validated route/provider/model transition |
| capability_check_recovery | Separate check decision + check result before subsequent permitted execution |
| recovery_success | Failed production attempt → permitted linked recovery → later same Task/Run production PASS |
| recovery_failure | Observed terminal failure or exhaustion, not mere missing completion |
| budget_exhausted | Actual terminal reason/Gate evidence; absent evidence stays unknown |
| end_to_end_task_attempt_window_ms | Last successful production completion UTC minus first production start; wall-clock-derived, may include checks/decisions |
| time_to_recovery_ms | Successful production completion UTC minus causal failed completion UTC; wall-clock-derived, distinct from preceding window |
| retry_backoff_ms | Recorded linked wait measurement only; never copy configured delay as measured time |

Keep initial outcome and final outcome separately. Recovery success never changes
the original timeout to PASS. Registered health is not capability; a later VERIFIED
status cannot be claimed as authority at an earlier attempt. No universal cost,
quality, reliability aggregate or production preference is produced here.

## 4. Comparability boundary

Primary route slice: `task_profile × provider_route × model` (actual successful
identity or explicitly attempted identity on failure).

Bounded cohort: `task_profile × response_schema_contract_hash × invocation_purpose
× capability_requirement_when_authoritative`. Route/model are comparison dimensions
**within** a compatible cohort, not proof that unrelated workloads are equivalent.
Capability requirement uses actual task/profile/response-schema authority; it is
not a new arbitrary label and not the route's current capability status.

Same exact Run/Task/Scheme/base/context is the strongest paired recovery slice.
Even here later attempts are selected after failure: this is observational recovery
evidence, not a randomized ranking experiment. Peer versus Fundamental are not
comparable workloads. Capability checks versus production are separate cohorts.
Matching schema hashes alone does not prove equal cross-run workload/semantics.
`context_hash` includes run-bound identity; it is not a normalized complexity class.
Unknown semantic version/complexity blocks claims requiring that comparability.

## 5. Quality authorities and attribution

Attempt PASS establishes typed schema/route identity/safe output/frozen-input
validation through `src/agentic/recovery.py`, not financial correctness.
`typed_output_validation` is DERIVED from that accepted completion path, with
code baseline and completion REC references. Text production alone is not quality.

A successful **production** attempt may link to ResearchAgentOutputRecord only
after exact Run/Task/Agent/provider/actual-model matches and verified structured
output hash. An uncertain link is NOT_OBSERVED, not “latest output.” Capability
checks produce no production AgentOutput and cannot receive task completion credit.

Store separately scoped `run_context`: exact task status, Review ID/verdict/check
subject_refs and input snapshot, calculation Proof/verification/commitment refs,
correction/replan references and Run release status. Review (`src/domain/review.py`)
is not a universal Specialist grade; Proof (`src/domain/proof.py`) is calculation
scoped. Without an exact subject/output relationship, direct attempt Review/Proof
quality remains NOT_OBSERVED / NO_DIRECT_QUALITY_LINK. Eventual Run Review PASS,
Proof VERIFIED and RELEASED are context, **never inherited by failed attempts or
capability checks**. Preserve source-map limitations rather than fabricate joins.

## 6. Existing evidence inventory and R5 mapping — PASS

Durable source: `phase6_recovery_evidence`, typed RecoveryEvidenceStore; exact
`GET /api/research-runs/{run_id}/recovery` with
`X-Phase4-Contract-Version: phase4-core/v1`. Review/projection/results APIs supply
separate Run context. Local accepted export: `artifacts/phase5b_r5_adaptive/`:
`recovery.json`, `performance.json`, `acceptance.json`, `terminal.json`, `memory.json`.
No new extractor is needed. These files are local audit evidence, not public API
payloads to dump wholesale; export only the allowlisted fields in this contract.

Exact R5 `RUN-ab806291-8cbf-4c9b-8852-b6a54f10768d`:

| Profile / purpose | ATT identity | Route / model | Outcome | ms | Input/output tokens |
| --- | --- | --- | --- | --- | --- |
| peer_analysis / production 1 | `ATT-13ea7340-c990-49aa-99b6-d69225bfe4e7` | mimo-direct / mimo-v2.5 | FAIL READ_TIMEOUT | 60211.85 | null/null |
| peer_analysis / production 2 | `ATT-9d0ed2e2-661e-4e92-8749-03afd5d6547e` | teamorouter-sol / gpt-5.6-sol | PASS | 30932.51 | 4174/563 |
| fundamental_analysis / production 1 | `ATT-ecc9771a-883c-4c1a-a23a-30a2618e9df5` | teamorouter-sol / gpt-5.6-sol | FAIL READ_TIMEOUT | 60412.33 | null/null |
| fundamental_analysis / capability check 1 | `ATT-6b43d504-5a03-42d8-a492-e8d0013dd026` | teamorouter-luna / gpt-5.6-luna | PASS | 13953.18 | 7856/617 |
| fundamental_analysis / production 2 | `ATT-75e8de27-e21f-4be4-9d10-64327f29f289` | teamorouter-luna / gpt-5.6-luna | PASS | 35650.23 | 7856/582 |

These table columns follow section 2 evidence classes; rounded ms are DERIVED
presentation values from persisted measurements, not invented timing. Failed
usage is NOT_OBSERVED. Both sequences retain identical Task/Run/Scope hashes.

Peer switch: `REC-cb9b362f-f235-45a3-bb02-56ca714c4a7f`, SWITCH_PROVIDER/ALLOW.
Fundamental check: `REC-4d718d30-f970-4799-801a-a1eac9c22007`, CAPABILITY_CHECK/ALLOW;
then `REC-8bde5ee9-d492-4776-b723-bd90c68ae01e`, SWITCH_MODEL/ALLOW. Luna capability
was UNKNOWN then check PASS/VERIFIED. Fundamental MiMo remains UNKNOWN, checks=0.

23 ledger events = 10 starts + 10 completions + 3 decisions. Completions comprise
9 production attempts (7 PASS, 2 FAIL) and 1 successful capability check. Seven
final Specialist outputs succeed. Run context is Review PASS/54 checks, required
Proof VERIFIED, RELEASED, exact Memory v2; not an attempt-level universal quality
label. Attempt-window durations 91.211766s (Peer) and 110.091807s (Fundamental)
include initial attempts; do not mislabel them post-failure recovery time.

The performance artifact has **12 model.attempt spans**, including graph planning
and generated-capability building in addition to the 10 ledger invocations.
Transport UUID attempt IDs and recovery ATT IDs have no direct foreign key.
Do not equate all model spans to Specialist execution attempts, double-count
checks, or silently join telemetry by route/time similarity. Missing exact join
remains explicit. No request/response-header absence proves provider root cause.

## 7. R2/R3/R4 legacy evidence — classification PASS

Legacy Run/task/transport evidence may be retained under existing source identity
as `legacy_context`, with ATT identity NOT_OBSERVED. It is not inserted as an
EvaluationObservation invocation or counted in an attempt denominator without
appropriate attempt authority. Missing new-ledger records do not mean no failure.

| Run | Observed authority | Diagnosis/classification | Evaluation restriction |
| --- | --- | --- | --- |
| R2 | Durable TASK_EXECUTION_FAILED / TASK_EXECUTION | DERIVED accepted diagnosis: graph display labels versus canonical Agent IDs | Deterministic identity defect, not model quality; original traceback not persisted |
| R3 | Peer/News Sol read_timeout then Luna provider_unavailable in retained performance/receipt | Runtime transport/availability; route IDs configuration-derived, profile exact Task join | Not semantic/model-quality failure; missing tokens null |
| R4 | Fundamental Sol and Luna ReadTimeout, request sent, response headers/status unobserved | Runtime transport/availability; precise upstream/proxy cause unproved | Separate successful capability-builder operation does not erase Specialist failure |

Sources: `docs/integration/PHASE5B_SINGLE_R2_RUNTIME_BLOCKER.md`;
`artifacts/phase5b_reexecution_authorization/r3-final-receipt.md` and
`r3-performance.json`; `artifacts/phase5b_specialist_reverify_final/final-receipt.md`.
Configuration-derived routes must be labelled DERIVED, not provider-reported.

## 8. Preparation acceptance and future implementation tests

EVALUATION_DATA_CONTRACT, OBSERVED_DERIVED_NOT_OBSERVED,
TASK_PROFILE_COMPARABILITY, RELIABILITY_EVIDENCE, PERFORMANCE_EVIDENCE,
RECOVERY_EVIDENCE, QUALITY_EVIDENCE_MODEL, R5_EVALUATION_MAPPING,
R2_R3_R4_FAILURE_CLASSIFICATION and COST_NOT_FABRICATED = PASS.
This means the contract faithfully represents available evidence and gaps,
not that all optional fields are observed or a Phase 6 evaluation engine exists.

Future Phase 6A implementation must test exact joins, missing/duplicate completion,
ambiguous telemetry correlation, check/production denominators, unknown tokens,
CER zero defaults, cross-profile/cohort rejection, non-attribution of Run quality,
legacy identity-defect preservation, safe field allowlist and zero mutations.
Use only existing evidence; no live provider call is needed to test these rules.

POT_IMPLEMENTED = NO; MODEL_PROVIDER_SCORING_IMPLEMENTED = NO;
PREFERRED_ROUTE_IMPLEMENTED = NO; LEARNED_ROUTING_IMPLEMENTED = NO.
No RecoveryBudget, registered provider, financial gate or historical state changed.
Next separately authorized implementation option: `PHASE_6A_EVALUATION_PLANE`.
