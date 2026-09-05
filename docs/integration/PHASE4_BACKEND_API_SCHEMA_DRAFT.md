# Phase 4A Core Backend API Schema Draft

Status: `PROVISIONAL_CONTRACT_DRAFT`  
Contract family: `phase4-core/v1`  
Freeze state: `NOT_FINAL`  
Inspected backend: `codex/phase3-contracts@11fe8173a25ff7ac08bae42340ba7c6fae591be5`

This document fixes the proposed public wire semantics only. It does not add routes, models,
migrations, or runtime behavior. Snake case is authoritative on the wire. A frontend adapter may
rename fields to camel case without changing values or identity.

## 1. Classification vocabulary

Every field below is classified as exactly one of:

- `EXISTING_BACKEND`: already carried by the inspected Phase 3 model/record;
- `PROJECTION_ONLY`: derived by a server-side projection from verified existing records;
- `BACKEND_FIELD_REQUIRED`: new durable fact or relation required before the projection is honest;
- `ADDITIVE_ROUTE_REQUIRED`: route/transport surface is absent, while its fields have identified
  sources;
- `SEMANTIC_CONFLICT`: current behavior has a meaning incompatible with this contract;
- `PHASE5_DEFERRED`: explicitly absent from Phase 4A Core.

No field in this draft is `TBD`.

## 2. Shared wire types

### 2.1 `AvailabilityV1`

```json
{
  "status": "PENDING | AVAILABLE | NOT_GENERATED | NOT_RELEASED | UNAVAILABLE | FAILED",
  "reason_code": "string | null",
  "retryable": false
}
```

`AVAILABLE` requires the referenced body/identifier. Every other state requires a stable,
non-empty `reason_code`. `PENDING` is valid only for a nonterminal Run. `NOT_RELEASED` means the
release boundary has not passed. `NOT_GENERATED` means no attempt/record exists. `UNAVAILABLE`
means the fact or retained detail cannot be supplied. `FAILED` means an attempted production step
failed. Empty arrays, nulls, zeroes, or HTTP 200 are not substitutes for this object.

### 2.2 Versions and watermarks

| Field | Type and invariant | Classification |
|---|---|---|
| `schema_version` / `projection_schema_version` | exact reviewed token named by each DTO; incompatible major versions fail closed | `PROJECTION_ONLY` |
| `projection_revision` | integer `>= 1`, monotonic per Run, incremented once per committed projection-affecting transaction | `BACKEND_FIELD_REQUIRED` |
| `projection_sequence` | integer `>= 0`, greatest durable RuntimeEvent sequence included in the same snapshot | `PROJECTION_ONLY` over an atomically readable durable event watermark; current persistence protocol needs strengthening |
| `generated_at` | RFC 3339 UTC time at which the projection was assembled; never used as ordering authority | `PROJECTION_ONLY` |

All detail responses that participate in a live Run carry the same three projection fields. A
released immutable record may retain its release-time watermark. Timestamps never replace a
revision or sequence.

### 2.3 Status, stage, terminal, and progress

The public `status` field preserves the exact backend enum. `stage` is a projection, not another
source of truth.

| Raw `RunStatus` | Public stage | Terminal | Results allowed |
|---|---|---:|---:|
| `DRAFT` | `PREPARE` | no | no |
| `SCHEME_GENERATING` | `PREPARE` | no | no |
| `AWAITING_CONFIRMATION` | `CONFIRM` | no | no |
| `PLANNING` | `PLANNING` | no | no |
| `RUNNING` | `RESEARCH` | no | no |
| `REVIEW` | `REVIEW` | no | no |
| `PROVING` | `PROVING` | no | no |
| `RELEASED` | `COMPLETE` | yes, success | only when release closure is valid |
| `FAILED` | `FAILED` | yes, failure | no |
| `CANCELLED` | `CANCELLED` | yes, cancelled | no |

Unknown Run status is `SCHEMA_INCOMPATIBLE`, requires snapshot/schema recovery, and is never cast
to a known value. Task, Review, Proof, availability, and event maps are frozen in the event and
identity companion documents.

Task `progress` remains a ratio in the inclusive range `0..1`. Collection and Run projection
progress carries Backend-authored `fraction` plus exact method `ACTUAL_TASK_MEAN_V1`. The shared
frontend adapter may derive the nonbusiness value `percent = fraction * 100`; percent is not a
second canonical Backend field. Page-local code only formats the value and progress may not advance
from elapsed time.

## 3. Route surface

The smallest Phase 4A Core public surface is:

| Method and route | Decision | Response contract |
|---|---|---|
| `GET /api/research-runs` | add | `ResearchRunCollectionV1` |
| `POST /api/research-runs/prepare` | retain and strengthen | `ResearchRunDraftV1` |
| `POST /api/research-runs` | retain and strengthen | `ConfirmRunResponseV1` containing immutable `RunAdmissionV1` plus `ResponseMetaV1` |
| `GET /api/research-runs/{run_id}` | retain as light canonical Run read | `ResearchRunDetailV1` |
| `GET /api/research-runs/{run_id}/projection` | add | `AtomicRunProjectionV1` |
| `GET /api/research-runs/{run_id}/events` | retain and strengthen | fetch-stream SSE defined by the event contract |
| `GET /api/research-runs/{run_id}/result` | retain and version | `ReleasedResultProjectionV1` or typed error |
| `GET /api/research-runs/{run_id}/claims/{claim_id}` | add | `ClaimDetailV1` |
| `GET /api/research-runs/{run_id}/review-view` | retain path; replace thin ref-only body | `FinancialReviewProjectionV1` |
| `GET /api/research-runs/{run_id}/execution-view` | retain and version | `ExecutionProjectionV1` |
| `GET /api/research-runs/{run_id}/trace/{claim_id}` | add | `TraceBundleV1` |
| `GET /api/research-runs/{run_id}/artifacts` | add | `ReportArtifactGroupV1` |
| `GET /api/research-runs/{run_id}/artifacts/{artifact_id}/content` | add | authorized bytes plus integrity headers |
| `POST /api/objects` | retain and strengthen | request-bound idempotent `ResearchObjectDetailV1` creation |
| `GET /api/objects` | retain and version | searchable/paginated `ResearchObjectCollectionV1` |
| `GET /api/objects/{object_id}` | retain and version | `ResearchObjectDetailV1` |
| `GET /api/objects/{object_id}/runs` | retain and version | object-bound `ResearchRunCollectionV1` |
| `GET /api/objects/{object_id}/released-state` | add | `ReleasedObjectCoreV1` |

Existing `/tasks` and `/graph` reads may remain for diagnostics, but they are not an atomic browser
bootstrap protocol. Existing `/objects/{object_id}/state` writeback proposals and
`/objects/{object_id}/financials` summary versions are not Phase 4 released-object authority.

## 4. Global Run collection

### 4.1 Request

```text
GET /api/research-runs
  ?object_id=<exact id>                 optional
  &status=<RunStatus>                   optional, repeatable OR
  &result_availability=<Availability>   optional
  &cursor=<opaque server cursor>        optional
  &limit=<1..100>                       optional, default 50
```

Ordering is fixed as `(updated_at DESC, run_id DESC)`. `updated_at` is the last committed
projection-visible mutation and therefore must be repaired before this order is authoritative. The
cursor is opaque, integrity-protected,
versioned, and bound to the normalized filter set and last ordering tuple. A cursor cannot be used
with different filters. Unknown, malformed, expired, or filter-mismatched cursors return
`INVALID_CURSOR`; there is no offset fallback and no crawl of Object routes.

### 4.2 `ResearchRunCollectionV1`

```json
{
  "schema_version": "phase4-run-collection/v1",
  "items": [{
    "run_id": "RUN-...",
    "object": {"object_id": "OBJ-...", "symbol": "NVDA", "company_name": "NVIDIA"},
    "status": "RUNNING",
    "stage": "RESEARCH",
    "progress": {"method":"ACTUAL_TASK_MEAN_V1","completed_tasks":2,
      "total_tasks":5,"fraction":0.42},
    "activity": {"event_id": "EVT-...", "type": "task.progress", "sequence": 18,
      "timestamp": "2026-09-04T00:00:00Z", "task_id": "TASK-...", "message_code": "..."},
    "graph_version": 2,
    "projection_revision": 14,
    "projection_sequence": 18,
    "as_of": "2026-09-03",
    "created_at": "2026-09-04T00:00:00Z",
    "updated_at": "2026-09-04T00:03:00Z",
    "started_at": "2026-09-04T00:00:02Z",
    "completed_at": null,
    "terminal": false,
    "result_availability": {"status": "PENDING", "reason_code": "RUN_NONTERMINAL",
      "retryable": false}
  }],
  "next_cursor": "opaque-or-null"
}
```

| Fields | Source | Classification |
|---|---|---|
| `run_id`, `status`, `as_of`, `created_at`, `started_at`, `completed_at` | `ResearchRun` | `EXISTING_BACKEND` |
| `object.object_id` | `ResearchRun.research_object_id` verified against `ResearchObject.object_id` | `EXISTING_BACKEND` |
| `object.symbol`, `object.company_name` | exact owning `ResearchObject` | `PROJECTION_ONLY` |
| `stage`, `terminal`, `result_availability` | frozen status/release maps | `PROJECTION_ONLY` |
| `progress` | aggregate of authoritative Task progress/status under the frozen algorithm | `PROJECTION_ONLY` |
| `activity` | latest safe normalized RuntimeEvent for this Run | `PROJECTION_ONLY` |
| `graph_version` | `ActualRuntimeGraph.version` | `EXISTING_BACKEND` |
| `updated_at` | last committed Run projection mutation | `SEMANTIC_CONFLICT`: current SQL writer can reuse create/completion time; a correct durable value is required |
| `projection_revision` | durable Run projection revision | `BACKEND_FIELD_REQUIRED` |
| `projection_sequence` | consistent event watermark | `PROJECTION_ONLY` with atomic persistence delta |
| route, filter-bound cursor, `next_cursor` | collection protocol | `ADDITIVE_ROUTE_REQUIRED` |

Run progress fraction is `1` only for a valid `RELEASED` Run, or for a terminal unsuccessful Run
whose tasks are all terminal; it does not imply release. For nonterminal Runs it is the unweighted
mean of exact actual-graph Task ratios under `ACTUAL_TASK_MEAN_V1`. A later weighted algorithm
requires durable weights and a new method token. The shared adapter's exact percent conversion is
presentation plumbing, not financial or lifecycle authority.

## 5. Prepare and confirm

### 5.1 Prepare request

Header `Idempotency-Key` is required and request-bound. Regenerate uses a new key.

```json
{"research_object_id":"OBJ-NVDA","research_goal":"...","as_of":"2026-09-03",
  "preferences":{}}
```

The exact object is resolved before generation. Goal templates are frontend authoring aids: the
expanded `research_goal` text is authoritative and no template ID is persisted in Core. Research
mode is implicitly `FULL`; a supplied `INCREMENTAL` field is rejected by the existing extra-forbid
request model and remains Phase 5. Neither deployment `OperatingMode` nor `preferences` may be
repurposed to imply incremental research.

### 5.2 `ResearchRunDraftV1`

```json
{
  "schema_version": "phase4-run-draft/v1",
  "draft_id": "DRAFT-...",
  "draft_version": 1,
  "status": "AWAITING_CONFIRMATION",
  "preview_kind": "SCHEME_ONLY",
  "planned_graph_availability": {"status":"NOT_GENERATED",
    "reason_code":"PLAN_CREATED_ON_CONFIRM","retryable":false},
  "object_id": "OBJ-NVDA",
  "goal": {"goal_id": "GOAL-...", "research_object_id": "OBJ-NVDA",
    "goal_type": "comprehensive_equity_research", "goal_text": "...",
    "as_of": "2026-09-03", "preferences": {}, "created_at": "..."},
  "scheme_snapshot": {"scheme_id": "SCHEME-...", "research_object_id": "OBJ-NVDA",
    "goal_id": "GOAL-...", "research_scope": [], "data_requirements": [],
    "agent_requirements": [], "skill_requirements": [], "calculation_requirements": [],
    "assurance_requirements": {}, "report_requirements": [], "limitations": [],
    "generated_by": "...", "generated_model": null, "created_at": "...",
    "confirmed_at": null},
  "prepare_request_hash": "sha256:<64 lowercase hex>",
  "draft_hash": "sha256:<64 lowercase hex>",
  "created_at": "2026-09-04T00:00:00Z",
  "expires_at": "2026-09-04T00:30:00Z"
}
```

No planned Task or graph is returned. `planned_graph_availability` is
`NOT_GENERATED/PLAN_CREATED_ON_CONFIRM`. The current backend honestly creates Tasks only during
confirm. Regeneration creates a new `draft_id`; the old draft remains independently identifiable
until expiry/consumption. `draft_hash` is the RFC 8785 canonical JSON SHA-256 of the immutable draft
payload excluding the hash itself; `prepare_request_hash` binds the request and server-internal
effective access scope `LOCAL_SINGLE_USER`.

### 5.3 Confirm request and admission

Header `Idempotency-Key` is required and non-empty.

```json
{"draft_id":"DRAFT-...","draft_version":1,"draft_hash":"sha256:...",
  "research_object_id":"OBJ-NVDA","confirm_scheme":true}
```

Successful first admission is HTTP 201:

```json
{
  "schema_version": "phase4-confirm-response/v1",
  "admission": {
    "schema_version": "phase4-run-admission/v1",
    "admission_id": "ADMISSION-...",
    "run_id": "RUN-...",
    "object_id": "OBJ-NVDA",
    "draft_id": "DRAFT-...",
    "draft_version": 1,
    "draft_hash": "sha256:<64 lowercase hex>",
    "goal_id": "GOAL-...",
    "scheme_id": "SCHEME-...",
    "planned_graph_id": "GRAPH-...",
    "status": "PLANNING",
    "auto_start": {"required":true,"admitted":true},
    "confirmation_request_hash": "sha256:<64 lowercase hex>",
    "admitted_at": "2026-09-04T00:00:00Z",
    "projection_ref": "/api/research-runs/RUN-.../projection",
    "events_ref": "/api/research-runs/RUN-.../events"
  },
  "response_meta": {
    "schema_version": "phase4-response-meta/v1",
    "request_id": "opaque",
    "idempotency_replayed": false
  }
}
```

A same-scope/key/hash retry returns HTTP 200 with the byte/semantic-identical immutable `admission`
and only `response_meta.idempotency_replayed=true`; the first response is HTTP 201 with false.
`response_meta` is excluded from the stored admission hash. The confirmation hash is SHA-256 over
RFC 8785 canonical JSON containing the exact contract token, approved effective access-scope key,
method, normalized route template, and complete body. It excludes credentials, request ID,
incidental headers and the idempotency-key value. A same-key/different-hash request returns
`CONFLICT/IDEMPOTENCY_REQUEST_MISMATCH`; another key for the consumed draft returns
`CONFLICT/DRAFT_CONSUMED`; expiry/version mismatch uses `DRAFT_EXPIRED` or
`DRAFT_VERSION_MISMATCH`. No conflict returns an admission or creates another Run.

One database transaction must consume the draft, freeze Goal/Scheme, generate and persist the
planned graph/Tasks, create one Run, append initial events, record the request hash/outcome, and
create one durable scheduler admission/outbox record. The admission lifecycle is
`PENDING -> LEASED -> ACKNOWLEDGED` or `FAILED`; leases expire for redelivery, and `run_id` is a
unique effect key. After commit, runtime starts automatically; there is no execute click. Delivery
is at least once, while the Run start effect and `run.started` emission are idempotent exactly once.

| Fields/semantics | Source | Classification |
|---|---|---|
| current prepare request fields, `draft_id`, Goal, Scheme, `confirmed_at` | API/domain draft | `EXISTING_BACKEND` |
| `draft_version`, draft/request hashes, `expires_at`, consumed state | durable draft/admission contract | `BACKEND_FIELD_REQUIRED` |
| template identity and incremental research mode | UI-only authoring / future memory semantics | `PHASE5_DEFERRED` for backend Core; only expanded Goal text and implicit FULL are accepted |
| `preview_kind`, schema versions, refs, response replay metadata | response composition | `PROJECTION_ONLY` |
| prepare/confirm paths | existing routes | `EXISTING_BACKEND` |
| planned Tasks absent at prepare and created on confirm | actual backend semantics selected as authority | `EXISTING_BACKEND` |
| current process-local `(operation,key)` cache and unbound key reuse | restart-unsafe and request-unbound | `SEMANTIC_CONFLICT` |
| current process-local `BackgroundTasks` auto-start | not a durable exactly-once admission | `SEMANTIC_CONFLICT` |

## 6. `AtomicRunProjectionV1`

```json
{
  "projection_schema_version": "phase4-run-projection/v1",
  "projection_revision": 14,
  "projection_sequence": 18,
  "generated_at": "2026-09-04T00:03:00Z",
  "object": {"object_id":"OBJ-...","symbol":"NVDA","company_name":"NVIDIA",
    "object_type":"public_company","exchange":"NASDAQ","sector":null,"currency":"USD",
    "identity_version":1},
  "run": {"run_id":"RUN-...","research_object_id":"OBJ-...","goal_id":"GOAL-...",
    "scheme_id":"SCHEME-...","status":"RUNNING","stage":"RESEARCH","as_of":"2026-09-03",
    "planned_graph_id":"GRAPH-...","actual_graph_id":"GRAPH-...-actual",
    "execution_target":"SERVER_SANDBOX","created_at":"...","started_at":"...",
    "completed_at":null,"updated_at":"..."},
  "goal": {},
  "confirmed_scheme": {},
  "planned_graph": {},
  "actual_graph": {},
  "graph_version": 2,
  "tasks": [],
  "path_changes": [{
    "path_change_id":"REPLAN-...","source_kind":"REPLAN","source_id":"REPLAN-...",
    "change_kind":"ADD_TASK","status":"APPROVED","decision":"APPROVED",
    "reason_code":"CAPABILITY_GAP","task_refs":["TASK-..."],
    "operations":[{"operation":"add_node","task_id":"TASK-..."}],
    "graph_version_before":1,"graph_version_after":2,
    "created_at":"...","resolved_at":"..."
  }],
  "activity": [],
  "lifecycle": {"status":"RUNNING","stage":"RESEARCH",
    "progress":{"method":"ACTUAL_TASK_MEAN_V1","completed_tasks":2,
      "total_tasks":5,"fraction":0.42},
    "terminal":false,"terminal_outcome":null,
    "safe_failure":null},
  "review": {"availability":{},"review_id":null,"status":null},
  "result": {"availability":{},"released_result_id":null,"canonical_record_id":null,
    "released_at":null},
  "artifacts": {"availability":{},"report_id":null,"representation_ids":[]},
  "proof": {"availability":{},"policy":"NOT_REQUIRED | MUST_PROVE | MIXED | UNKNOWN",
    "status":"...","proof_refs":[]},
  "execution": {"availability":{},"canonical_record_id":null},
  "terminal": {"is_terminal":false,"outcome":null,"event_id":null,"sequence":null}
}
```

The snapshot is assembled from one transactionally consistent database view. Every embedded Task,
graph, activity item, review/result/artifact/proof/execution ref is validated against the Run and
owning Object before serialization. `projection_sequence` cannot include an event whose reflected
aggregate mutation is absent. The response ETag is
`"p4:<run_id>:<projection_revision>:<projection_sequence>"`.

`projection_revision` increments exactly once for a committed transaction that changes any public
Run, Task, actual-graph, Review/check, proof/policy, result, artifact, availability, or safe-failure
fact. A transaction containing several such changes still increments once. Heartbeats and reads do
not increment it. Any RuntimeEvent and aggregate mutation representing the same business fact are
committed in the same unit of work; `projection_sequence` is the greatest event sequence included
by that view.

`planned_graph` is the immutable confirmed plan. Runtime, self-correction, and approved replan
change only `actual_graph`; one atomic graph mutation produces one new `graph_version`. Sparse graph
events never create a frontend Task: they set `projection_refresh_required=true` and this route is
re-read.

`PathChangeProjectionV1` is a lossless Backend projection of exactly one durable Correction or
Replan source. `path_change_id` and `source_id` are the exact source identity and
`source_kind` is `CORRECTION|REPLAN`. Allowed `change_kind` values are
`SELF_CORRECTION|ADD_TASK|CHANGE_DEPENDENCY`. The row preserves the source-native status/decision,
safe reason code, exact Task refs, typed operations, timestamps, and nullable before/after actual
graph versions. Replan operations are only `add_node|add_edge|remove_edge`; Correction graph
versions remain null unless an explicit durable graph mutation links them. One source has one
path-change identity even when it carries several operations. Planned graph is never rewritten.

| Fields | Source | Classification |
|---|---|---|
| Object, Run, Goal, Scheme, graphs, Tasks | `RunAggregate` and exact Object | `EXISTING_BACKEND` |
| graph version and Task ratios | `ActualRuntimeGraph`, `Task` | `EXISTING_BACKEND` |
| safe activity, stage/progress/terminal, availability summaries | verified records + frozen maps | `PROJECTION_ONLY` |
| review/result/canonical/proof/artifact IDs | completed artifacts/durable record repositories | `EXISTING_BACKEND` when present, wrapped as `PROJECTION_ONLY` |
| atomic route | absent | `ADDITIVE_ROUTE_REQUIRED` |
| durable `projection_revision` and event-consistent commit protocol | absent | `BACKEND_FIELD_REQUIRED` |

## 7. Released financial metric

`ReleasedFinancialMetricProjectionV1` is the only Phase 4 display-number authority:

```json
{
  "run_id":"RUN-...","metric_id":"METRIC-...","name":"EBITDA Margin",
  "canonical_value":"0.6547","canonical_unit":"RATIO",
  "display_value":"65.47","display_unit":"%",
  "period":"FY2026","period_basis":"FY","actuality":"ACTUAL",
  "as_of":"2026-09-03","currency":"USD",
  "formula_id":"ebitda_margin_v1","capability_id":"ebitda_margin",
  "calculation_id":"CALC-...","evidence_refs":["EVD-..."],
  "claim_refs":["CLAIM-..."],
  "proof":{"policy_id":"phase4-proof-policy/v1","requirement":"MUST_PROVE",
    "status":"VERIFIED","proof_refs":["PROOF-..."]},
  "method_metadata":null,"technical_price_basis":null,
  "corporate_action_status":null,"corporate_action_guard_refs":[],"limitations":[]
}
```

| Fields | Source | Classification |
|---|---|---|
| metric identity, canonical/display values and units, period/basis, actuality, as-of, currency, formula/capability/calculation, method and limitations | `ReleasedFinancialMetric` | `EXISTING_BACKEND` |
| `run_id` | enclosing `ReleasedResearchResult.run_id`, verified through calculation/Claim | `PROJECTION_ONLY` |
| `evidence_refs` | rename of `evidence_ids` | `PROJECTION_ONLY` |
| `claim_refs` | exact `MaterialFinancialClaim.metric_id` join in same result/run | `PROJECTION_ONLY` |
| `proof` | exact proof-policy requirement/status and proof records joined by `calculation_id` and Run | `PROJECTION_ONLY` |

The mandatory fixture renders `65.47%`. Neither the browser nor an LLM performs the ratio-to-percent
conversion. Missing material outputs cannot produce `RELEASED`; they produce a non-available result
and a terminal failure when release is required.

## 8. Claim, Review, Execution, and Trace

### 8.1 `ClaimDetailV1`

The response carries watermark fields, `object_id`, `run_id`, the exact typed Claim, its exact
released metric, `task_refs`, safe `evidence[]`, deterministic `calculations[]`, proof policy/results,
matching review/check refs, canonical/result ids, and typed scoped anchors. Evidence bodies exclude
`raw_artifact_ref` and raw provider JSON. Calculation bodies never recompute or reinterpret output.

Task derivation is only `Claim.calculation_refs -> CalculationRecord.task_id`. All distinct Tasks
are returned. `primary_task_id` is non-null only when an explicit durable Backend relation selects
one of those Tasks as primary. Singleton cardinality alone does not establish business primacy;
without that relation the field is null for both singleton and multi-Task Claims.

### 8.2 `FinancialReviewProjectionV1`

```json
{
  "schema_version":"phase4-financial-review/v1","projection_revision":14,
  "projection_sequence":18,"object_id":"OBJ-...","run_id":"RUN-...",
  "canonical_record_id":"CER-RUN-...","released_result_id":"RESULT-RUN-...",
  "review_id":"REVIEW-RUN-...","status":"PASS","reviewer":"...",
  "input_snapshot_hash":"sha256:...","reviewed_evidence_refs":[],
  "reviewed_calculation_refs":[],"reviewed_metric_refs":[],"reviewed_claim_refs":[],
  "reviewed_judgment_refs":[],
  "required_proof_calculation_refs":[],
  "checks":[{"check_id":"CHECK-...","check_code":"...","status":"PASS",
    "subjects":[{"subject_type":"CLAIM","subject_id":"CLAIM-...","run_id":"RUN-..."}],
    "expected":{},"actual":{},"detail":null,
    "exception_state":"NONE | OPEN | RESOLVED",
    "correction_refs":[],
    "created_at":"...","resolved_at":null}],
  "availability":{"status":"AVAILABLE","reason_code":null,"retryable":false}
}
```

Actual `ReviewRecord` fields are `EXISTING_BACKEND`. Stable `check_id` and an explicit
typed subject, check-to-correction relation, exception state, and Check-level resolution timestamp
are `BACKEND_FIELD_REQUIRED`; array position, code text, aggregate `review.resolved`, or matching
subject text cannot create them. A live pre-release Review has both X/L IDs null; a released Review
has both non-null and verified. The expanded endpoint is `ADDITIVE_ROUTE_REQUIRED` in behavior
while retaining the existing `/review-view` path. The exact nullability/transition rules are in
`PHASE4_BACKEND_FINAL_FREEZE_DECISION_DRAFT.md` §16.

### 8.3 `ExecutionProjectionV1` and `TraceBundleV1`

Execution preserves `CanonicalExecutionRecord.record_id/run_id/object_snapshot_ref`, exact planned
and actual graph snapshots, all ref arrays, costs/latency/token usage, runtime outcome, and safe
event anchors. Trace is specified fully in the identity companion. Both enforce the same Run before
returning data. There is no chain-of-thought, prompt transcript, hidden reasoning, or model scratch
state field.

The execution event page is ordered by `sequence ASC`, uses an opaque Run-bound cursor after the
last included sequence, and accepts `limit=1..500` (default 100), repeatable exact `type`, optional
exact `task_id`, and optional safe text `query`. Query matches only allowlisted normalized event
summary fields; it never searches provider bodies, prompts, paths, or hidden reasoning. Filters are
cursor-bound. Any selected event still carries its original sequence, so filtering never renumbers
or implies a contiguous filtered sequence.

## 9. Report artifact delivery

`report_id` is frozen in V1 as the exact `ReleasedResearchResult.result_id`; Phase 4 does not invent
a second report-version identity.

```json
{
  "schema_version":"phase4-report-artifacts/v1","object_id":"OBJ-...","run_id":"RUN-...",
  "report_id":"RESULT-RUN-...","canonical_record_id":"CER-RUN-...",
  "released_result_id":"RESULT-RUN-...",
  "release_policy_version":"phase4-release-eligibility/v1",
  "artifact_policy_version":"phase4-html-required-pdf-optional/v1",
  "anchor_manifest_id":"ANCHOR-MANIFEST-...",
  "anchor_manifest_sha256":"sha256:<64 lowercase hex>",
  "availability":{},
  "representations":[{
    "artifact_id":"RPT-HTML-...","format":"HTML","required_for_release":true,
    "content_type":"text/html; charset=utf-8",
    "availability":{"status":"AVAILABLE","reason_code":null,"retryable":false},
    "safe_failure_code":null,"generation_attempt_id":"ATTEMPT-...",
    "generation_attempt_count":1,"sha256":"sha256:<64 lowercase hex>","size_bytes":12345,
    "renderer":{"renderer_id":"finrobot-professional-port","renderer_version":"..."},
    "generated_at":"2026-09-04T00:04:00Z",
    "authorized_ref":"/api/research-runs/RUN-.../artifacts/RPT-HTML-.../content"
  },{
    "artifact_id":null,"format":"PDF","required_for_release":false,
    "content_type":"application/pdf",
    "availability":{"status":"NOT_GENERATED","reason_code":"PDF_NOT_GENERATED_BY_POLICY","retryable":false},
    "safe_failure_code":null,"generation_attempt_id":null,
    "generation_attempt_count":0,"sha256":null,"size_bytes":null,
    "renderer":null,"generated_at":null,"authorized_ref":null
  }]
}
```

HTML and PDF are always separate representation slots and have distinct IDs when available. SVG or
future formats may appear only in a versioned extension, never as a substitute for HTML/PDF.
Successful artifact identity, hash and size are fixed only after verified bytes commit. Renderer,
generation time and `authorized_ref` come from the corresponding committed generation and current
access/delivery projection; they are not described as byte-derived. An artifact ID is opaque and
its current internal derivation algorithm is not public contract. No ID is fabricated for an
ungenerated artifact.

For Phase 4A successful professional release, the HTML representation is mandatory and
`AVAILABLE`; PDF is optional and may be `NOT_GENERATED` or `FAILED` with its explicit safe reason.
If a release policy later makes PDF mandatory, that policy must be durable and versioned; this V1
does not infer it. An `authorized_ref` is a same-origin resource path, not a bearer token: every GET
re-evaluates UAC-006 scope `LOCAL_SINGLE_USER`, exact identity, artifact-revocation and retention
state. Copying the path grants no authority; the path itself has no token expiry semantics.

Generation state follows the exact UAC-016 protocol in
`PHASE4_BACKEND_FINAL_FREEZE_DECISION_DRAFT.md` §19. Attempts are append-only and independent by
format. `NOT_GENERATED` has no attempt or artifact ID; `FAILED` has a completed failed attempt but
no successful artifact ID; `AVAILABLE` has complete immutable byte metadata; later `UNAVAILABLE`
retains that successful identity/metadata but removes `authorized_ref`. A terminal Run has no
PENDING representation and no post-terminal regeneration mutates a released report.

| Fields | Source | Classification |
|---|---|---|
| artifact/run/canonical/result IDs, MIME type, content hash, size, renderer version, created time | `ReportArtifactRecord` | `EXISTING_BACKEND` |
| object and report IDs | verified Run/canonical/result join; `report_id = result_id` | `PROJECTION_ONLY` |
| format/content type mapping, availability, safe failure, renderer object | reviewed allowlist and generation state | `PROJECTION_ONLY`; durable failed-generation reason is `BACKEND_FIELD_REQUIRED` |
| anchor-manifest ID/hash and representation coverage | immutable Claim-anchor manifest | `BACKEND_FIELD_REQUIRED` |
| `authorized_ref` | access-policy projection over the same-origin route | `PROJECTION_ONLY` |
| grouped metadata and content routes | absent | `ADDITIVE_ROUTE_REQUIRED` |
| current `artifact_ref` (`artifact://` or filesystem path) | internal storage locator | `SEMANTIC_CONFLICT` if exposed; it is omitted publicly |

The byte route first establishes the current UAC-006 local effective scope, then performs one
scope-concealed lookup and validates Run -> Object -> canonical -> result -> artifact ->
representation anchor. If a future governed profile requires authentication, authentication occurs
before any existence-revealing lookup. The trusted stored locator is resolved only after closure.
Success returns exact bytes with `Content-Type`, `Content-Length`, `Digest: sha-256=...`, immutable
ETag, and safe `Content-Disposition`. A hash/size/media mismatch returns `INTEGRITY_FAILURE` and no
protected artifact bytes; a safe JSON ErrorEnvelope body is allowed. Cross-Run substitution returns
fail-closed `IDENTITY_MISMATCH`/404. Metadata success never authorizes bytes by itself.

## 10. Released Object Core

`GET /api/objects/{object_id}/released-state` returns:

```json
{
  "schema_version":"phase4-released-object-core/v1",
  "object":{},
  "latest_released_run_id":"RUN-...",
  "current_released_result_availability":{"status":"AVAILABLE","reason_code":null,
    "retryable":false},
  "source_run_id":"RUN-...",
  "released_result_id":"RESULT-RUN-...",
  "canonical_record_id":"CER-RUN-...",
  "released_at":"...",
  "metrics":[],"claim_refs":[],"report_artifacts":{}
}
```

The latest released Run is selected only among Runs whose `status == RELEASED` and whose canonical,
released-result, review, required proof, and material-output closure validates. Order is
`released_at DESC, run_id DESC`. A newer draft, running, failed, or cancelled Run never supersedes
this state. `source_run_id == latest_released_run_id` is mandatory.

Eligibility additionally requires exactly one `ALLOWED` `ReleaseValidationRecordV1` under the
hash-bound policy family in `PHASE4_BACKEND_FINAL_FREEZE_DECISION_DRAFT.md` §20, including mandatory
integrity-valid HTML and a terminal policy-permitted PDF state. Ordering uses
`ReleasedResearchResult.released_at`; tied opaque Run IDs compare bytewise. An empty eligible set
returns null with `NOT_RELEASED/NO_RELEASED_RUN`. The lossless metric projection must include the
Proof policy/status object plus every method, technical-price-basis and corporate-action field
listed in §20; the frontend performs no numeric conversion or field-dropping.

Object list/detail add `latest_released_run_id`, released availability, `run_count`, and last
activity as projections over exact object-owned Runs. Object-scoped history reuses the global Run
item and ordering contract with an enforced `object_id`; opening a row always uses its exact
`run_id`.

`GET /api/objects` accepts exact `symbol`, safe normalized `query`, opaque filter-bound `cursor`, and
`limit=1..100` (default 50), ordered by `(symbol ASC, object_id ASC)`. Search matches only
allowlisted Object identity/display fields and returns no provider lookup payload.
`POST /api/objects` retains the current exact request fields (`symbol`, `company_name`, `exchange`,
`sector`, `currency`) but requires an effective-scope/request-bound `Idempotency-Key`. Same key and
same canonical request replays one Object; the same key with a different request is `CONFLICT`.
Symbol normalization is part of the request hash; an existing matching Object may be returned only
after its exact normalized identity is verified, never by company-name or provider fallback. The
idempotency outcome is durable across restart.

| Fields | Source | Classification |
|---|---|---|
| object identity | `ResearchObject` | `EXISTING_BACKEND` |
| object-scoped Runs | repository `list_runs_for_object` | `EXISTING_BACKEND` |
| latest released Run, counts, current released closure, `source_run_id` | validated exact Run/result/canonical selection | `PROJECTION_ONLY` |
| Object create request and route | existing API/domain request | `EXISTING_BACKEND` |
| durable request-bound Object creation replay | current cache is process-local and unbound | `BACKEND_FIELD_REQUIRED`; current behavior is a `SEMANTIC_CONFLICT` |
| released-state route and search/cursor/versioned Object responses | absent | `ADDITIVE_ROUTE_REQUIRED` |
| current `/financials` lossy summaries and `/state` writeback proposals | not released-object authority | `SEMANTIC_CONFLICT` if used for this UI |
| `ResearchObjectVersion`, `ResearchViewVersion`, `ResearchMemory`, comparison, incremental seed, freshness/reuse/refresh/revalidate/prevent/writeback | excluded | `PHASE5_DEFERRED` |

## 11. Authorization and content negotiation

UAC-006 is `RESOLVED_PROVISIONALLY` by project-owner decision
`phase4-local-single-user-trusted/v1`. Phase 4A performs no account authentication and introduces
no actor/tenant/workspace/user ownership model. Every request uses server-internal scope
`LOCAL_SINGLE_USER` and validates the exact Run/Object and each nested resource; request JSON never
asserts authority, and IDs/URLs are not authority. JSON success responses use
`application/json; charset=utf-8`; SSE requires `Accept: text/event-stream`; artifact content uses
its recorded reviewed media type. Unsupported media/schema negotiation returns
`SCHEMA_INCOMPATIBLE`. Identity, availability and integrity are rechecked on every detail and byte
request. A public or multi-user access profile requires a separate governed change.

Phase 4 clients may send `X-Phase4-Contract-Version: phase4-core/v1`; omission selects exactly V1.
An empty, malformed, repeated, comma-list, unknown or unsupported token returns HTTP 409
`SCHEMA_INCOMPATIBLE` with zero mutation. Successful JSON/SSE responses echo the selected contract
header; SSE also carries `X-Phase4-Event-Contract-Version: phase4-runtime-event/v1`. Incompatibility
is JSON before stream headers. There is no silent minor downgrade: a future revision requires a new
exact reviewed token before use.

## 12. Explicit exclusions

These fields/routes are `PHASE5_DEFERRED` and absent from all Phase 4A Core success schemas:
`ResearchObjectVersion`, `ResearchViewVersion`, `ResearchMemory`, `ComparisonDataset`,
`IncrementalResearchSeed`, freshness/reuse/refresh/revalidate/prevent decisions, Object writeback,
real Scene 05/06, POT, and any capability certification/global registry. Generated capability
lifecycle may be projected only as supporting activity within its original Task.
