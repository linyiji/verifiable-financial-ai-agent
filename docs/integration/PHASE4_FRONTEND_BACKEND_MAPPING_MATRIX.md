# Phase 4 Frontend / Backend Mapping Matrix

Classification: `PROVISIONAL_CONTRACT_PREAUDIT`

This matrix compares the frontend remediation candidate at `a850bce3cf0b8a72bc28c7ce16a67e9f83be0c84` with the dirty Backend Phase 3 candidate fingerprint `sha256:f0101a685d10b801466f9dad9bd3b8e74221b8bd5ec0b1e9e1b5e4f176fcc592`.

Classification vocabulary: `MATCH`, `RENAMING_ONLY`, `PROJECTION_REQUIRED`, `BACKEND_FIELD_MISSING`, `FRONTEND_FIELD_MISSING`, `SEMANTIC_CONFLICT`, `DEFERRED`.

“Type” and “enum” compare wire semantics, not merely whether both sides use strings.

## Object and Run

| Frontend concept | Frontend field | Backend concept | Backend field | Type match | Enum match | Identity key | Optionality | Lifecycle | Authority | Current gap | Phase 4 action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Research Object identity | `ResearchObject.id` | `ResearchObject` | `object_id` | Yes | N/A | `object_id` | Required both | Stable | Backend | `RENAMING_ONLY` | Map snake/camel names only. |
| Object name | `name` | `ResearchObject` | `company_name` | Yes | N/A | `object_id` | Required both | Mutable metadata | Backend | `RENAMING_ONLY` | Map without duplicating. |
| Object market identity | `symbol`, `exchange`, `sector?`, `currency?` | `ResearchObject` | same semantic fields | Yes | N/A | `object_id` | Sector optional both; frontend currency optional/backend defaulted | Object lifetime | Backend | `MATCH` | Preserve backend value and nullability. |
| Object enrichment | `industry?`, `country?` | None | None | No | N/A | `object_id` | Optional frontend | Object lifetime | Backend or unavailable | `BACKEND_FIELD_MISSING` | Return absent; do not infer. Add only if later backend-owned. |
| Object UI state | `dataStatus`, `price`, `revenue`, `revenueGrowth`, `forwardPe` | Object + released metric projection | No direct fields | Projection | Partial | `object_id` + released `run_id` | Optional frontend | Changes by released Run | Backend projection | `PROJECTION_REQUIRED` | Project explicit availability and released display metrics; never compute in React. |
| Object Run summary | `runCount`, `latestRunStatus?`, `latestReleasedRunId?` | Run repository | object-scoped Runs | Projection | No | `object_id` | Count required; latest optional | Run collection | Backend projection | `PROJECTION_REQUIRED` | Define ordering and “latest released” rule. |
| Run identity | `ResearchRun.id` | `ResearchRun` | `run_id` | Yes | N/A | `run_id` | Required both | Stable | Backend | `RENAMING_ONLY` | Map only. |
| Run owner | `objectId`, `symbol`, `company` | Run + Object | `research_object_id` + object join | Projection | N/A | `run_id → object_id` | Required frontend | Stable | Backend | `PROJECTION_REQUIRED` | Resolve from the Run’s object only and verify join. |
| Run status | `RunStatus` | `RunStatus` | `status` | String-like | No | `run_id` | Required | Draft → released/terminal | Backend | `SEMANTIC_CONFLICT` | Freeze explicit map; never cast. Backend `RELEASED` maps frontend `COMPLETED`; cancelled requires a UI policy. |
| Run stage | `stage` | Run status + lifecycle | No direct field | No | No | `run_id` | Required frontend | Stage projection | Backend projection | `BACKEND_FIELD_MISSING` | Project from frozen lifecycle/event state, not page heuristics. |
| Research step | `researchStep` | Scheme/task types/runtime | No direct field | No | No | `run_id` | Required frontend | Step projection | Backend projection | `BACKEND_FIELD_MISSING` | Define optional projection or make frontend optional; do not infer financial completion. |
| Run progress | `progress` as `0..100` | Task/Run projection | Task `progress` is `0..1`; Run has none | No | N/A | `run_id` | Required frontend | Monotonic display unless reset defined | Backend projection | `SEMANTIC_CONFLICT` | Normalize once at adapter boundary and define aggregation/rounding. |
| Current activity | `currentActivity?` | Latest safe event/task status | No direct field | Projection | N/A | `run_id` + sequence | Optional | Event-derived | Backend projection | `PROJECTION_REQUIRED` | Return server-approved display summary or null. |
| Run mode/scenario | `mode`, `scenarioId` | Goal preferences / no scenario | No first-class fields | Partial | No | `run_id` | Required frontend | Fixed per Run | Backend for mode; frontend Demo for scenario | `SEMANTIC_CONFLICT` | Keep `scenarioId` Demo-only; freeze authoritative FULL/INCREMENTAL or make optional. |
| Graph identity | `graphVersion` | `ActualRuntimeGraph` | `graph_id`, `version` | Partial | N/A | `run_id + graph_id + version` | Required frontend | Increments on mutation | Backend | `PROJECTION_REQUIRED` | Return actual version in snapshot and normalized graph events. |
| Planned/actual path | `initialTasks`, `tasks`, `pathChanges` | planned graph, actual graph, corrections/replans/mutation history | typed objects | Projection | Partial | `run_id`, task/replan/correction ids | Required lists | Append/change through runtime | Backend | `PROJECTION_REQUIRED` | Compose one Run projection; preserve planned snapshot. |
| Run timestamps | `createdAt`, `updatedAt` | Timestamped Run + start/completion/event | `created_at`, `started_at`, `completed_at`; no true updated-at | Partial | N/A | `run_id` | Frontend required | Updated by events | Backend projection | `BACKEND_FIELD_MISSING` | Define authoritative updated timestamp, likely latest persisted event time. |
| Proof status | `proofStatus` | proof policy + Proof records | per-calculation status | Projection | Partial | `run_id + calculation_id + proof_id` | Frontend required | Policy/prove/verify/terminal | Backend | `PROJECTION_REQUIRED` | Aggregate with an explicit policy; frontend must not infer validity/completion. |
| Run collection | `listResearchRuns()` | Repository/API | only object-scoped list route | No | Depends on projection | `run_id` | Required frontend | Paginated collection | Backend | `BACKEND_FIELD_MISSING` | Freeze global collection item, ordering, filters and pagination. |

## Plan, Task and dynamic path

| Frontend concept | Frontend field | Backend concept | Backend field | Type match | Enum match | Identity key | Optionality | Lifecycle | Authority | Current gap | Phase 4 action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Prepare input | `{objectId, goal, template, mode?}` | `PrepareResearchRunRequest` | `{research_object_id, research_goal, as_of, preferences}` | Partial | No | Object + draft | Different required fields | Creates draft | Backend | `SEMANTIC_CONFLICT` | Freeze template/mode/as-of mapping and validation. |
| Prepared plan id | `ResearchPlan.planId` | `ResearchRunDraft` | `draft_id` | Similar identifier | N/A | `draft_id` | Required | Draft until confirm/expiry | Backend | `RENAMING_ONLY` only if semantics are frozen | Either rename in adapter or expose `draft_id`; specify expiry/version. |
| Prepare-visible plan | goal/title/questions/scopes/methods/tasks | Goal + Scheme snapshot; graph planned only on confirm | scheme requirements, no Task graph | Partial | N/A | `draft_id + scheme_id` | Frontend required | Prepared/awaiting confirmation | Backend | `SEMANTIC_CONFLICT` | Decide whether prepare returns a planned graph or frontend previews scheme requirements instead. |
| Confirm input | `{objectId, goal, planId}` | `ConfirmResearchRunRequest` | `{draft_id, confirm_scheme}` + header key | Partial | N/A | draft + idempotency key | Required | Exactly-once Run creation | Backend | `SEMANTIC_CONFLICT` | Bind idempotency key to draft/request hash; reject mismatch; return same Run on retry. |
| Task identity | `ResearchTask.id` | `Task` | `task_id` | Yes | N/A | `(run_id, task_id)` | Required | Stable | Backend | `RENAMING_ONLY` | Always resolve under requested Run. |
| Task owner | inherited `objectId`, `symbol`, `runId` | `Task` + Run + Object | `run_id`; no direct object/symbol | Projection | N/A | `run_id → object_id` | Required frontend | Stable | Backend projection | `PROJECTION_REQUIRED` | Inject verified owner fields in projection. |
| Task definition | `name`, `question`, `agentLabel`, `skillLabel`, `toolLabels?` | `Task` | `task_type`, `goal`, `assigned_agent`, `skill_id`; capability refs elsewhere | Partial | N/A | task | Labels partly optional | Fixed except generated support | Backend facts / frontend labels | `PROJECTION_REQUIRED` | Map facts; presentation labels may remain UI-owned. |
| Task status | frontend 7-value enum | backend 12-value enum | `status` | String-like | No | task | Required | Rich state machine | Backend | `SEMANTIC_CONFLICT` | Freeze total map including created, waiting-for-capability, review, cancelled and capability-build-failed. |
| Task progress | `0..100` number | `Task.progress` | constrained `0..1` float | No | N/A | task | Optional frontend/backend required | Execution | Backend | `SEMANTIC_CONFLICT` | Multiply once in projection; do not let page code decide. |
| Task lineage | `dependsOn`, `evidenceRefs`, `calculationRefs` | Task + calculations | dependencies, input/output evidence ids, calculation rows | Projection | N/A | task + referenced ids | Optional frontend | Accumulates | Backend | `PROJECTION_REQUIRED` | Return stable deduplicated references verified to the same Run. |
| Task detail summaries | duration/analysis/conclusion/correction/replan/error/events | Task + event/correction/replan/output records | distributed | Projection | Partial | task + event sequence | Optional | Append-only/history | Backend projection | `PROJECTION_REQUIRED` | Build safe observable timeline; do not expose hidden reasoning. |
| Dynamic path change | `PathChange` | `ReplanRequest`, CorrectionRecord, graph mutation | different names/shape | Partial | No | replan/correction ids | Lists | Requested → applied/resolved | Backend | `PROJECTION_REQUIRED` | Normalize ids, types and status; no fabricated change ids. |
| Added Task event | reducer creates Task from event payload | `graph.task_added` | event carries task id, replan id, graph version only | No | N/A | task + graph version | Event payload sparse | Graph mutation | Backend graph | `SEMANTIC_CONFLICT` | Refetch/patch from authoritative graph; never create a default Task in production. |
| Capability support | `supportingActivity` | gap/build/generated/validation/sandbox/registration records | typed lifecycle | Projection | No | `(run_id, task_id, gap_id/build_id/capability_id)` | Optional | Supporting lifecycle | Backend | `PROJECTION_REQUIRED` | Aggregate under the original Task; never add a Research Task. |

## Claims, financial metrics, Review, Trace and output

| Frontend concept | Frontend field | Backend concept | Backend field | Type match | Enum match | Identity key | Optionality | Lifecycle | Authority | Current gap | Phase 4 action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Claim identity | `ResearchClaim.claimId` | `MaterialFinancialClaim` | `claim_id` | Yes | N/A | `(run_id, claim_id)` | Required | Materialized at release today | Backend | `MATCH` | Preserve opaque id and Run scope. |
| Claim owner | `objectId`, `symbol`, `runId` | Claim + Run + Object | claim `run_id` only | Projection | N/A | claim → run → object | Required frontend | Stable | Backend projection | `PROJECTION_REQUIRED` | Inject verified ownership; fail on cross-object/run refs. |
| Claim content/type | `title`, `summary`, two-value type | Claim | `statement`, open string `claim_type` | Partial | No | claim | Required | Released | Backend | `SEMANTIC_CONFLICT` | Freeze claim kind vocabulary; derive title only as presentation. |
| Claim metric semantics | frontend omits value/unit/period/as-of | `MaterialFinancialClaim` | typed value/unit/period/basis/actuality/as-of/currency | No | No | claim + metric | Backend required | Released immutable | Backend | `FRONTEND_FIELD_MISSING` | Extend frontend projection; never flatten to summary only. |
| Claim support | `taskId`, evidence/calculation refs | Claim + Calculation | evidence/calculation refs; task indirect through calculation | Partial | N/A | claim + calc + task | Frontend task required | Released | Backend | `PROJECTION_REQUIRED` | Resolve all supporting tasks; define one explicit primary task or allow a list. |
| Claim judgment support | no ids displayed except claim kind | released judgments | `judgment_refs` to untyped JSON | Partial | N/A | judgment id convention | Optional | Released | Backend | `PROJECTION_REQUIRED` | Type the Phase 4 subset or mark unavailable; do not parse arbitrary JSON heuristically. |
| Released metric | `FinancialMetric.values[{period,value,estimate}]` | `ReleasedFinancialMetric` | canonical/display values, units, period basis, actuality, as-of, currency, calc/evidence ids | No; frontend is lossy | No | `metric_id + run_id` | Frontend shape omits mandatory semantics | Released immutable | Backend | `FRONTEND_FIELD_MISSING` | Adopt a lossless projection including Claim and Proof refs. |
| Review aggregate | `ReviewRecord[]` | one `ReviewRecord` per Run in current flow | reviewed refs/checks/status | No | No | `(run_id, review_id)` | Frontend list | Review/release | Backend | `PROJECTION_REQUIRED` | Expand checks/associations into per-Claim and exception records without changing truth. |
| Review status | PASS/uncertainty/REVIEW/BLOCK/RESOLVED | PASS/REVIEW/BLOCK | `status` | String-like | No | review/check | Required | Aggregate/check state | Backend | `SEMANTIC_CONFLICT` | Define uncertainty and resolved-history derivation explicitly; backend `review.resolved` event is not exception RESOLVED. |
| Review correction history | `correctionPath?`, `resolvedAt?`, `kind` | Correction records + review checks/events | distributed | Projection | No | review + correction + task | Optional | Append-only | Backend | `PROJECTION_REQUIRED` | Return durable exception projection with open/resolved semantics. |
| Proof display | Claim `proofStatus` | policy/Proof/Verification | requirement + statuses | Projection | Partial | claim → calc → proof | Frontend required | Required/proving/verified/error | Backend | `PROJECTION_REQUIRED` | Calculate status server-side from exact calculation binding. |
| Trace anchors | report/review/execution/task anchors | Report renderer + projections | no per-Claim anchor manifest | No | N/A | claim + representation/canonical ids | Optional frontend but required for full trace | Stable per released report | Backend/API | `BACKEND_FIELD_MISSING` | Create immutable anchor manifest; frontend may map it to DOM ids but must not choose another Run. |
| Execution view identity | `canonicalRecordId`, owner identity | `ExecutionDetails` | canonical id + run id; object indirect | Partial | N/A | canonical + run + object | Required | Released | Backend | `PROJECTION_REQUIRED` | Inject object/symbol and preserve canonical binding. |
| Execution content | status/counts/events/coverage/release gate/entries | canonical record + graphs/events/review | distributed | Projection | No | run + canonical | Required frontend | Live → released | Backend | `PROJECTION_REQUIRED` | Define live and released projection separately or a stable lifecycle union. |
| Released result | `ReleasedResult.status/releasedAt` | `ReleasedResearchResult` presence + Run status | result id/run/released_at | Projection | No | run + result | Required frontend | Unavailable → released | Backend | `PROJECTION_REQUIRED` | Project availability; frontend must not infer from report presence. |
| Report preview | structured `preview` with Claim ids | `CanonicalReportDTO` / generated HTML | canonical data but different structure | No | N/A | run + report + claim | Frontend required today | Pending → ready | Backend report projection | `PROJECTION_REQUIRED` | Return reviewed preview DTO or safely render backend HTML; no React recomputation. |
| Artifact identity | `artifactId`, owner identity | `ReportArtifactRecord` | artifact id + run; object indirect | Partial | N/A | artifact + run + object | Required | Immutable when present | Backend | `PROJECTION_REQUIRED` | Verify object through Run/canonical and include it in delivery DTO. |
| Artifact representation | one object has HTML/PDF URLs | one record per representation | artifact type/ref/hash/size | No | N/A | artifact id per representation | URLs optional | Availability lifecycle absent | Backend/API | `SEMANTIC_CONFLICT` | Use a group with independent HTML/PDF records and opaque authorized refs. |
| Artifact metadata | renderer/generated time | renderer version + `created_at` | combined version/time | Partial | N/A | artifact | Generated records only | Immutable | Backend | `PROJECTION_REQUIRED` | Split renderer name/version by explicit mapping; map created time. |
| Artifact lifecycle | `PENDING/READY/ERROR/NOT_GENERATED` | record exists only when generated | no availability/failure fields | No | No | run/report/representation | Required frontend | Requested → available/failed | Backend/API | `BACKEND_FIELD_MISSING` | Add delivery projection status and safe failure code; do not alter immutable record. |
| Artifact authorization | download URLs | internal `artifact://` ref | internal path-like token | No | N/A | artifact + caller authorization | Optional | Refresh/revocation | API authorization layer | `SEMANTIC_CONFLICT` | Never expose raw ref; mint/resolve an opaque same-origin authorized reference. |

## Object history and deployment boundary

| Frontend concept | Frontend field | Backend concept | Backend field | Type match | Enum match | Identity key | Optionality | Lifecycle | Authority | Current gap | Phase 4 action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Research View history | `researchViews[]` | per-Run released records/writeback proposals | no applied view snapshot | No | N/A | object + source run | Required only by Demo scenes | Phase 5 | Future backend | `DEFERRED` | Keep Demo-only; do not block Phase 4 shell integration. |
| Object comparison | previous/current ids + typed items | none | none | No | No | object + exact two Run ids | Demo-only now | Phase 5 | Future backend | `DEFERRED` | Require explicit pair; never default Claim links to latest unrelated Run. |
| Incremental memory | `memory`, `incrementalStrategy` | Goal preferences/writeback only | no durable memory contract | No | No | object + source/current Run | Optional | Phase 5 | Future backend | `DEFERRED` | Keep Demo-only pending Object Memory. |
| Deployment mode/status | no frontend type | `OperatingMode` enum only; frozen deployment design | enum only/no projection | No | Partial | process + run | Future | RP2+ | Deployment status service | `DEFERRED` | Add only in Deployment RP2; do not infer from fixture/provider names. |
| Future component fields | absent | frozen design | source/LLM/trace/sandbox/proof/artifact status | No | N/A | process/run | Future | RP2+ | Deployment status service | `DEFERRED` | Preserve as `FUTURE_RP2`; no Phase 4 fake values. |

## Minimum lossless financial metric projection

The frontend’s current `FinancialMetric` must not be the Phase 4 wire contract. The minimum projection should preserve, per released Run:

```text
run_id
metric_id
name
canonical_value
canonical_unit
display_value
display_unit
period
period_basis
actuality
as_of
currency
formula_id
capability_id
calculation_id
evidence_refs[]
claim_refs[]
proof_refs[]
limitations[]
```

`claim_refs` is resolved by matching `MaterialFinancialClaim.metric_id`; `proof_refs` is resolved through the exact `calculation_id`. Empty proof refs are valid only when the backend-projected proof policy/status says so. The frontend must not infer ratio-to-percent conversion, period/basis, completion, or proof validity.
