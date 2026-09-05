# Phase 4 Backend Final Freeze Decision Draft

Status: `FOCUSED_UAC_CLOSURE_PREPARATION_READY — NOT_FINAL`  
Scope: `PHASE4_CORE` contract text only  
Authority register: `PHASE4_BACKEND_UAC_CLOSURE_REGISTER.md` / `.json`  
Inspected source candidate: `11fe8173a25ff7ac08bae42340ba7c6fae591be5`  
Inspected tree: `b5f7bf960853c43344516031058f043ba45aaac5`
Later clean worktree observation: `8c4a77ccb70bceb1e8bf496ea528682df95a3405`, tree
`3a9329f1a5f9c30f3ec1190457e09067c0c102d3` — observed drift, not an approved-parent rebase.

```text
PHASE3_FINAL_CANDIDATE_READY=NO
AUTHORITATIVE_PHASE3_RUN_ID=NONE
PHASE4_BACKEND_CONTRACT_FREEZE_READY=NO
PHASE4_PRODUCTION_IMPLEMENTATION_AUTHORIZED=NO
UAC_FINAL_CLOSED=0
```

This is the focused decision text required to convert `UAC-001..018` into the later
`PHASE4_BACKEND_FINAL_CONTRACT_FREEZE`. It reconciles the provisional Backend package with the
authoritative acceptance catalogue without creating another conflict or acceptance-gate namespace.
It does not approve the inspected Phase 3 source candidate, close a UAC, authorize implementation,
or implement a test.

## 1. Authority and closure rule

The later final freeze applies authority in this order:

1. approved product, domain, financial, release and identity semantics;
2. the immutable independently accepted Phase 3 Backend parent when it exists;
3. the final Phase 4 Backend API, event and route contract;
4. `P4-BE-001..030` and the Phase 4 acceptance package;
5. the approved V17 normalized contract input;
6. implementation structure.

The current clean SHA is only `INSPECTED_PHASE3_SOURCE_CANDIDATE`. A final freeze must bind a
non-empty authoritative Phase 3 Run ID and the independent Backend and Financial Semantics audit
receipts. If the accepted parent differs from the inspected SHA/tree, every `EXISTING_BACKEND`
classification and every focused delta below must be recomputed.

The coordination worktree was later observed clean at `8c4a77c...`, two commits after the declared
candidate. Its 11-file delta strengthens financial arithmetic rejection and runtime
lineage/trace/observation instrumentation, but does not itself approve a parent or supply the
Phase 4 projection, SSE, Claim, artifact, or released-state routes. The later final delta must bind
the independently accepted SHA and specifically re-audit UAC-017 and all source classifications;
this draft is not silently rebased to the observation.

The Backend draft's internal `UNRESOLVED_PHASE4_SEMANTIC_CONFLICTS=0` means its provisional choices
are internally complete. It does not close the acceptance authority's `UAC-001..018` register.

## 2. Current disposition summary

| Current state | UAC IDs | Count |
|---|---|---:|
| `RESOLVED_PROVISIONALLY` | `003`, `004`, `005`, `006`, `008`, `010`, `012`, `013`, `014`, `017`, `018` | 11 |
| `WAITING_FOR_APPROVED_PHASE3_PARENT` | `001` | 1 |
| `WAITING_FOR_FINAL_V17_CONTRACT` | `002` | 1 |
| `WAITING_FOR_IMPLEMENTATION_EVIDENCE` | `007`, `009`, `011`, `015`, `016` | 5 |
| `SEMANTIC_DECISION_REQUIRED` | none | 0 |
| `CLOSED` | none | 0 |

`RESOLVED_PROVISIONALLY` freezes a recommended final-contract decision, not a release result.
Implementation-evidence rows have exact required semantics and are ready for final semantic freeze;
they cannot be acceptance-proven without the new durable facts and fault-injection receipts.
UAC-006 is now decided by project-owner record `phase4-local-single-user-trusted/v1`; it deliberately
adds no principal, workspace, tenant, user or ACL model for the trusted/local Phase 4A profile.

## 3. V17 governance-cycle resolution

The V17 FCR is `DRAFT_CHANGE`, its implementation Candidate is pending, and it currently requires
Backend dependencies to close before `CHANGE_APPROVED`. Requiring an implemented V17 Candidate SHA
as an input to the Backend final freeze would therefore create a cycle.

UAC-002 closes against an approved, hash-bound **V17 contract-input package**, consisting of the
approved FCR contract revision, corrected reference manifest, all 13 normalized contract schemas,
rename/nullability/unknown-value rules, Scene and interaction dispositions, and `BD-001..012`
mapping. The V17 implementation Candidate SHA and independent Delta Audit remain later execution and
promotion inputs unless frontend governance is explicitly amended.

Draft `P4-E2E-107..112` reservations remain outside the current `P4-E2E-001..106` result matrix.

### 3.1 Required V17 contract-input corrections

The approved V17 input must incorporate these focused deltas before UAC-002 can close:

| Normalized contract | Required correction |
|---|---|
| `Availability` | Preserve exact Backend status/reason/retry values; never infer release, Proof or artifact state from absence. |
| `ErrorEnvelope` | Include `UNAUTHENTICATED`, `REQUEST_VALIDATION_ERROR`, `INTERNAL_ERROR` and every UAC-018 code with the one frozen HTTP/retry/recovery tuple. |
| `GlobalRunCollectionProjection` | Bind the additive global route, stable filter-bound cursor/order, backend fraction/counts/method and list/detail watermark rules. |
| `PreparedResearchDraft` | Add `draftHash` and `plannedGraphAvailability`; remove normalized `mode`/`goalTemplateId` business claims; preview remains Scheme-only. |
| `ConfirmAndStartResult` | Replace the flat/mutable result with `{admission: RunAdmissionV1, responseMeta: ResponseMetaV1}`; replay metadata never mutates admission. |
| `RunProjection` | Use `ACTUAL_TASK_MEAN_V1`, Backend `fraction`, adapter-only percent, exact `pathChanges`, nullable graph versions and atomic revision/sequence. |
| `NormalizedRuntimeEventV1` | Add `eventContractVersion`, `payloadSchemaVersion`, nullable `graphVersion`, exact effect/refresh mapping and fail-closed unsupported behavior. |
| `ConnectionState` | Use only `IDLE`, `CONNECTING`, `OPEN`, `RECOVERING`, `BACKOFF`, `TERMINAL`, `FAILED`; it is transport state, not Run lifecycle. |
| `FinancialReviewProjection` | Make Review identity/status/reviewer nullable when absent, add input hash and reviewed Judgment refs, stable Checks and exact exception history. |
| `ClaimTraceProjection` / `TraceBundle` | Add metric/calculation/manifest identities, fixed HTML/PDF representation anchors and plural Review/Task/Execution anchors; primary Task needs explicit durable selection. |
| `ReportArtifactGroup` | Add `requiredForRelease`, policy versions, attempt identity/count, manifest identity/hash and exact slot nullability; policy-skipped PDF has no failure code. |
| `ReleasedFinancialMetric` | Add proof policy object, full method metadata, technical-price basis, corporate-action fields and limitations without Frontend arithmetic. |
| `ReleasedObjectCoreProjection` | Bind exact release eligibility/latest tie rule, lossless metric/Claim/artifact group and Phase 4-only Object/run history; omit all Phase 5 truth. |

## 4. VersionProtocolV1 — UAC-003

The route family stays under the stable `/api` prefix. There is no `/v1` path duplicate and no
media-type version parameter.

```text
request header:
  X-Phase4-Contract-Version

accepted request values:
  absent                  -> select phase4-core/v1
  exactly phase4-core/v1  -> select phase4-core/v1

rejected request values:
  empty, malformed, repeated, comma-list, unknown or unsupported token
  -> HTTP 409 phase4-error/v1 / SCHEMA_INCOMPATIBLE
  -> retryable=false, recovery=NONE, zero mutation
```

Every successful JSON response carries
`X-Phase4-Contract-Version: phase4-core/v1` and the DTO's exact top-level `schema_version`.
Every successful stream additionally carries
`X-Phase4-Event-Contract-Version: phase4-runtime-event/v1`, and every business data object carries:

```json
{
  "event_contract_version": "phase4-runtime-event/v1",
  "payload_schema_version": 1
}
```

An SSE incompatibility is returned as JSON before stream headers. There is no implicit minor
downgrade; a different wire contract requires a different reviewed exact token.

## 5. Local single-user trusted access — UAC-006

Project-owner decision `P4-ACCESS-DECISION-001` freezes
`ACCESS_MODE_ID=phase4-local-single-user-trusted/v1` for `PHASE4A_CORE_INTEGRATION_ONLY`:

```text
ACCESS_MODE_NAME=LOCAL_SINGLE_USER_TRUSTED_V1
AUTHENTICATION_REQUIRED=NO
AUTHENTICATION_PROVIDER=NONE
TENANT_MODEL=NONE
WORKSPACE_OWNERSHIP_MODEL=NONE
USER_OWNERSHIP_MODEL=NONE
CLIENT_ASSERTED_ACTOR=PROHIBITED
CLIENT_ASSERTED_TENANT=PROHIBITED
CLIENT_ASSERTED_WORKSPACE=PROHIBITED
SERVER_EFFECTIVE_SCOPE=LOCAL_SINGLE_USER
RESOURCE_IDENTITY_VALIDATION=MANDATORY
CROSS_OBJECT_FALLBACK=PROHIBITED
CROSS_RUN_FALLBACK=PROHIBITED
ARTIFACT_REF_IS_AUTHORITY=NO
PHASE4B_AUTHENTICATION=DEFERRED_TO_SEPARATE_GOVERNED_CHANGE
```

`LOCAL_SINGLE_USER_TRUSTED_V1` removes only account/principal authentication. Every requested and
nested resource still closes to the exact requested Object and Run. A foreign nested identity is
safe 404 `IDENTITY_MISMATCH`; it never triggers latest, first, ticker, company, title, metric-name
or Claim-text repair.

The server-internal scope and idempotency/cache key component is the literal
`LOCAL_SINGLE_USER`. Request JSON never accepts `user_id`, `actor_id`, `tenant_id`, `workspace_id`
or `principal_id` as authority. Phase 4A adds no auth, tenant, workspace, user, principal or ACL
table solely for this profile.

The complete owner record and security limitations are in `PHASE4_ACCESS_MODE_DECISION_V1.md` and
its JSON mirror. This trusted/local profile is not approval for public unauthenticated, multi-user,
multi-tenant, shared-untrusted-network or production-Internet deployment.

## 6. ErrorEnvelopeV1 — UAC-018

All non-stream JSON errors use:

```json
{
  "schema_version": "phase4-error/v1",
  "error": {
    "code": "ErrorCodeV1",
    "message": "safe user-facing text",
    "retryable": false,
    "recovery": "NONE",
    "request_id": "server-issued opaque value or null",
    "resource": {"type": "allowlisted type", "id": "safe identifier"},
    "details": {}
  }
}
```

`resource` is nullable. A concealed response may repeat caller-supplied identifiers but never a
resolved foreign owner or private nested ID. `details` is code-specific and allowlisted; it never
contains provider bodies, SQL, stack traces, credentials, secrets, prompts, hidden reasoning,
filesystem paths or internal artifact locators.

| Code | HTTP | Retryable | Recovery |
|---|---:|---:|---|
| `INVALID_CURSOR` | 400 | false | `SNAPSHOT_RELOAD` |
| `UNAUTHENTICATED` | 401 | false | `REAUTHENTICATE` |
| `FORBIDDEN` | 403 | false | `NONE` |
| `NOT_FOUND` | 404 | false | `NONE` |
| `IDENTITY_MISMATCH` | 404 | false | `NONE` |
| `UNAVAILABLE` | 409 | false | `NONE` |
| `NOT_GENERATED` | 409 | false | `NONE` |
| `NOT_RELEASED` | 409 | false | `SNAPSHOT_RELOAD` |
| `CONFLICT` | 409 | false | `NONE` |
| `CURSOR_AHEAD` | 409 | false | `SNAPSHOT_RELOAD` |
| `SCHEMA_INCOMPATIBLE` | 409 | false | `NONE` |
| `UNSUPPORTED_EVENT` | 409 | false | `SNAPSHOT_RELOAD` |
| `TERMINAL` | 409 | false | `NONE` |
| `REQUEST_VALIDATION_ERROR` | 422 | false | `NONE` |
| `INTEGRITY_FAILURE` | 500 | false | `SNAPSHOT_RELOAD` |
| `INTERNAL_ERROR` | 500 | false | `NONE` |
| `TRANSIENT_BACKEND_ERROR` | 503 | true | `RETRY` |

Legacy public-adapter mappings are `RESOURCE_NOT_FOUND -> NOT_FOUND` and
`RESULT_NOT_RELEASED -> NOT_RELEASED`.

Under the applied Phase 4A local profile, normal requests generate neither 401 `UNAUTHENTICATED`
nor 403 `FORBIDDEN`; both remain reserved vocabulary for a future governed access profile. A
missing resource is 404 `NOT_FOUND`; an existing nested resource outside the requested Object/Run
is safe 404 `IDENTITY_MISMATCH` without disclosing its foreign owner. Pre-header SSE failures use
this envelope. Artifact denial or integrity failure returns zero protected bytes.

## 7. Availability/error boundary

An unavailable retained child is not success. The parent may return HTTP 200 only when it retains
the exact child ID plus `AvailabilityV1(UNAVAILABLE, stable reason_code, retryable=false)`.
A directly requested absent generation or release returns typed 409 `NOT_GENERATED` or
`NOT_RELEASED`. A missing/wrong-owner/corrupt child required for release is 500
`INTEGRITY_FAILURE` and withholds the result and bytes. A temporary assembly outage is 503
`TRANSIENT_BACKEND_ERROR`; it may retain a visibly stale last-valid projection but may not advance
business state.

## 8. ConfirmRunResponseV1 — UAC-005

The immutable business outcome and per-attempt transport metadata are separate objects:

```json
{
  "schema_version": "phase4-confirm-response/v1",
  "admission": {
    "schema_version": "phase4-run-admission/v1",
    "admission_id": "ADMISSION-...",
    "run_id": "RUN-...",
    "object_id": "OBJ-...",
    "draft_id": "DRAFT-...",
    "draft_version": 1,
    "draft_hash": "sha256:<64 lowercase hex>",
    "goal_id": "GOAL-...",
    "scheme_id": "SCHEME-...",
    "planned_graph_id": "GRAPH-...",
    "status": "PLANNING",
    "auto_start": {"required": true, "admitted": true},
    "confirmation_request_hash": "sha256:<64 lowercase hex>",
    "admitted_at": "RFC3339 UTC",
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

The first successful commit returns HTTP 201 and `idempotency_replayed=false`. The same approved
scope, method, normalized route, key and request hash return HTTP 200, the byte/semantic-identical
`admission`, and `idempotency_replayed=true`. The immutable `status` is admission-time PLANNING even
if the live Run later advances. `response_meta` is excluded from the stored admission hash.

`confirmation_request_hash` is SHA-256 over RFC 8785 canonical JSON containing the exact contract
token, approved effective access-scope key from UAC-006, method, normalized route template, and body
`{draft_id,draft_version,draft_hash,research_object_id,confirm_scheme:true}`. It excludes the
idempotency key value, credentials, request ID and incidental headers. The stored idempotency key is
a nonreversible digest scoped by approved access scope, method and route.

Same key with a changed request returns HTTP 409 `CONFLICT` with safe
`details.reason_code=IDEMPOTENCY_REQUEST_MISMATCH`; a different key for the consumed draft uses
`DRAFT_CONSUMED`. `DRAFT_EXPIRED` and `DRAFT_VERSION_MISMATCH` are the other closed conflict reasons.
No conflict response exposes an admission body or creates a second Run.

## 9. RunSchedulerAdmissionV1 — UAC-007

Confirm's single PostgreSQL transaction consumes the exact draft, freezes Goal/Scheme, creates the
Run and immutable plan/Tasks, appends initial events, stores the UAC-005 outcome and inserts exactly
one `PENDING` scheduler admission. Rollback exposes none of them. FastAPI `BackgroundTasks` is not
the Phase 4 authority.

```text
RunSchedulerAdmissionV1
  admission_id                 primary key
  run_id                       unique, not null
  idempotency_outcome_id       unique, not null
  state                        PENDING | LEASED | ACKNOWLEDGED | FAILED
  delivery_attempt_count       integer >= 0
  max_delivery_attempts        integer >= 1
  next_attempt_at              nullable UTC instant
  lease_owner                  nullable opaque worker ID
  lease_generation             integer >= 0
  lease_expires_at             nullable UTC instant
  start_committed_at           nullable UTC instant
  run_started_event_id         nullable unique event ID
  run_started_sequence         nullable positive integer
  acknowledged_at              nullable UTC instant
  failed_at                    nullable UTC instant
  failure_code                 nullable safe code
  policy_version               phase4-run-admission-delivery/v1
  created_at / updated_at      UTC instants
```

An expired lease is re-leased with a higher generation; only the current fence may write or
acknowledge. The first valid worker claim atomically changes PLANNING to RUNNING, sets immutable
`started_at`, appends one `run.started`, and records its identity/sequence. Redelivery after that
transaction resumes/reconciles the same Run without resetting time or emitting another start.
`run_id` is the unique logical effect key. Permanent admission failure passes once through the
UAC-011 terminal finalizer. This does not claim exactly-once external Task side effects.

UAC-007 remains `WAITING_FOR_IMPLEMENTATION_EVIDENCE`: fault cuts before/after confirm commit,
lease, start commit and acknowledgment must prove one draft consumption, outcome, Run, plan,
admission, `run.created`, `run.started` and immutable start time across API/worker restart.

## 10. CursorProtocolV1 — UAC-004

Cursor authorization and parsing complete before SSE headers:

| Input | Required result |
|---|---|
| header absent | resolve sequence 0 |
| canonical decimal `0\|[1-9][0-9]*` within signed 64-bit range and `N <= tail(R)` | replay strictly after N |
| whitespace, sign, leading zero, blank, decimal, control character, overflow or malformed value | JSON 400 `INVALID_CURSOR`, zero frames |
| opaque token matching `[A-Za-z0-9._:-]{1,256}` and exact `event_id` in R | replay strictly after its sequence |
| unknown, expired, lexically invalid or other-Run opaque token | JSON 400 `INVALID_CURSOR`, no existence disclosure |
| canonical numeric `N > tail(R)` | JSON 409 `CURSOR_AHEAD`, snapshot recovery, zero frames |
| valid cursor below terminal | replay through terminal, then close |
| valid numeric/opaque cursor equal to terminal | HTTP 200 SSE; `X-Run-Terminal` and `X-Terminal-Sequence`; zero business/heartbeat frames; immediate close |

A terminal snapshot tells the browser not to subscribe. Replay is read-only and identical after
PostgreSQL/API restart. No cursor class may clamp, replay from zero, switch Runs, fabricate recovery
or heartbeat indefinitely.

## 11. Projection ownership — UAC-008

| Field | Required owner | Classification |
|---|---|---|
| `projection_revision` | Backend wire; durable per-Run integer, initial admission is 1 | `BACKEND_FIELD_REQUIRED` |
| `projection_sequence` | Backend wire; greatest included event sequence in same snapshot | `PROJECTION_ONLY` over atomic persistence |
| Task `progress` | Backend wire, stored ratio `0..1` | `EXISTING_BACKEND` |
| Run `progress.fraction` | Backend wire | `PROJECTION_ONLY` |
| `progress.method` | Backend wire, exact `ACTUAL_TASK_MEAN_V1` | `PROJECTION_ONLY` |
| `progress.percent` | shared adapter computes exactly `fraction * 100` | `FRONTEND_ADAPTER_DERIVED_NONBUSINESS` |
| formatted percent label/rounding | component only | `DISPLAY_ONLY` |
| `graph_version` | Backend wire, exact actual-graph version | `EXISTING_BACKEND` |
| `path_changes[]` | Backend wire projection of exact Correction/Replan/mutation records | `PROJECTION_ONLY` |
| snake/camel rename and immutable wrapping | shared adapter only | nonbusiness representation |

The wire progress object is:

```json
{"method":"ACTUAL_TASK_MEAN_V1","completed_tasks":2,"total_tasks":5,"fraction":0.42}
```

For a nonterminal Run with Tasks, fraction is the unweighted mean of exact actual-graph Task ratios;
with zero Tasks it is 0. A valid RELEASED Run is 1. A terminal unsuccessful Run is 1 only when all
Tasks are terminal; otherwise it retains the computed value. Adding a Task may honestly lower the
fraction. This progress display transform is not financial arithmetic.

Each `path_changes[]` row has a source `correction_id` or `replan_id` as `path_change_id`, source
kind, allowlisted `change_kinds` (`SELF_CORRECTION`, `ADD_TASK`, `CHANGE_DEPENDENCY`), status,
reason code, exact Task refs, typed graph operations, nullable before/after graph versions and source
timestamps. One source record creates one path-change identity even when it contains multiple
operation kinds. Planned graph remains immutable.

## 12. Atomic projection publication — UAC-009

Every projection-affecting business unit is serialized per Run and commits aggregate/child
mutations, corresponding RuntimeEvents and one projection-revision increment in one PostgreSQL
transaction. Several events in one transaction consume consecutive sequences but increment revision
once. A visible transaction without an event may advance revision while sequence remains unchanged;
an event append is visible activity and advances revision. Reads, heartbeats, rollback, rejection,
exact replay and no-op redelivery change neither.

`projection_sequence` is read inside the same MVCC snapshot and equals the greatest committed event
whose reflected state is present. `GET /projection` reads all members in that snapshot and returns:

```text
ETag: "p4:<run_id>:<projection_revision>:<projection_sequence>"
```

Initial admission publishes revision 1 and all initial facts atomically. Terminal publication
atomically binds Run state, component availability, safe failure or release closure, terminal event,
revision and watermark. PostgreSQL is required for acceptance; split aggregate/event commits and
in-memory substitutions cannot pass. UAC-009 remains `WAITING_FOR_IMPLEMENTATION_EVIDENCE` until
every commit/rollback/race/restart cut proves no torn 200 projection.

## 13. Total normalization maps — UAC-010

The total Run map is:

```text
DRAFT|SCHEME_GENERATING -> PREPARE, nonterminal
AWAITING_CONFIRMATION    -> CONFIRM, nonterminal
PLANNING                 -> PLANNING, nonterminal
RUNNING                  -> RESEARCH, nonterminal
REVIEW                   -> REVIEW, nonterminal
PROVING                  -> PROVING, nonterminal
RELEASED                 -> COMPLETE, terminal success only with release closure
FAILED                   -> FAILED, terminal failure
CANCELLED                -> CANCELLED, terminal nonsuccess
```

The total Task map is:

```text
CREATED|WAITING          -> QUEUED, nonterminal
READY                    -> READY, nonterminal
RUNNING                  -> ACTIVE, nonterminal
WAITING_FOR_CAPABILITY   -> WAITING_SUPPORT, nonterminal
SELF_CORRECTING          -> CORRECTING, nonterminal
BLOCKED                  -> BLOCKED, nonterminal at Task-map level
REVIEW                   -> REVIEW, nonterminal
COMPLETED                -> COMPLETE, terminal
FAILED|CAPABILITY_BUILD_FAILED -> FAILED, terminal
CANCELLED                -> CANCELLED, terminal
```

Review maps `PASS -> PASS`, `REVIEW -> NEEDS_REVIEW`, and `BLOCK -> BLOCKED`; only PASS releases.
Proof policy is explicit: absence is UNKNOWN/blocking. `VALID` is generated-unverified until a
matching verification closes; VERIFIED requires exact Run/calculation/commitment closure;
invalid/failed/error remain blocking; unsupported/not-implemented releases only under explicit
NOT_REQUIRED policy.

Availability is the closed set `PENDING`, `AVAILABLE`, `NOT_GENERATED`, `NOT_RELEASED`,
`UNAVAILABLE`, `FAILED`. Only AVAILABLE may have a null reason. PENDING is nonterminal only;
NOT_GENERATED means no attempt/record; FAILED means an attempt ended unsuccessfully; UNAVAILABLE
retains a known ref that cannot be supplied. Terminal resources never remain PENDING.

Every business event uses the UAC-003 event version fields, exact raw name, exact Run/Task identity,
positive sequence, validated V1 payload and nullable graph version. The exhaustive raw-event
dispositions and payload schemas are the table in `PHASE4_BACKEND_EVENT_CONTRACT_DRAFT.md` §3,
subject to these focused changes:

- sparse graph events always force snapshot refresh and never construct a Task;
- `release.completed` is nonterminal and forces release-state refresh;
- `run.failed` uses UAC-011;
- `scheme.generation_started`, `replan.rejected`, `evidence.conflict`, `workspace.created`,
  `capability.generation_started`, `capability.tested`, `capability.validated`, and
  `review.required` are unsupported output until their producer/payload contract is approved;
- frontend-only labels such as `correction.resolved`, `capability.validating`,
  `claim.materialized`, `report.started`, and `result.prepared` are never RuntimeEvents.

Unknown names, payloads, versions, enum values, identities or conflicting duplicates cause zero
mutation and zero cursor advance, quarantine only safe metadata/hash, retain the visibly stale last
valid projection and enter one authoritative snapshot recovery path.

## 14. TerminalFailureV1 — UAC-011

For every durably admitted unsuccessful Run:

```text
status in FAILED|CANCELLED
<=> exactly one run.failed
    and zero run.completed
    and run.failed is the last business event
    and payload status equals persisted Run status
```

The terminal payload is:

```json
{
  "status": "FAILED",
  "failure_stage": "PLANNING",
  "failure_code": "stable allowlisted code",
  "safe_message": null
}
```

`status` is `FAILED|CANCELLED`. `failure_stage` is one of `PLANNING`, `DATA_EVIDENCE`,
`TASK_EXECUTION`, `GENERATED_CAPABILITY`, `FINANCIAL_REVIEW`, `PROOF`, `ARTIFACT_GENERATION`,
`RELEASE`, `POST_SCHEDULER`, `PERSISTENCE`, `CANCELLATION`. The minimum stable codes are
`PLANNING_FAILED`, `DATA_EVIDENCE_FAILED`, `TASK_EXECUTION_FAILED`,
`GENERATED_CAPABILITY_FAILED`, `FINANCIAL_REVIEW_BLOCKED`, `FINANCIAL_REVIEW_FAILED`,
`PROOF_INVALID`, `PROOF_FAILED`, `REQUIRED_ARTIFACT_GENERATION_FAILED`,
`RELEASE_GATE_BLOCKED`, `RELEASE_FAILED`, `POST_SCHEDULER_FAILED`,
`PERSISTENCE_FINALIZATION_FAILED`, and `RUN_CANCELLED`.

A single idempotent finalizer owns Run state/completion time, safe failure fact, component
availability, terminal record/event, revision and watermark in one transaction. Scheduler, service,
worker and reconciliation may invoke it, but uniqueness by Run permits one terminal effect. Multiple
internal exceptions remain diagnostic only. Nonterminal capability retries and optional PDF failure
do not terminate; required HTML, Review, Proof, material-output or release failure does. Cancellation
uses raw `run.failed` with `status=CANCELLED`; no `run.cancelled` is invented. No business event may
follow terminal, and repeated finalization returns the existing terminal identity without a new
revision or sequence.

Pre-admission validation rollback emits no terminal. If storage failure prevents the terminal
transaction, the Run is not represented as durably terminal until restart reconciliation commits
one finalizer outcome. UAC-011 stays `WAITING_FOR_IMPLEMENTATION_EVIDENCE` until every named failure
class passes duplicate-delivery and restart fault injection with no released success exposure.

## 15. ClaimDetailV1 and Judgment availability — UAC-012

`GET /api/research-runs/{run_id}/claims/{claim_id}` returns the exact Claim named by the route. The
wire object is closed as follows; arrays use the source-reference order, and no text, name,
position, `first` or `latest` join is allowed.

```yaml
ClaimDetailV1:
  schema_version: phase4-claim-detail/v1
  projection_revision: integer >= 1
  projection_sequence: integer >= 0
  object_id: string
  run_id: string
  claim_id: string
  claim:
    claim_id: string
    run_id: string
    claim_type: string
    statement: string
    metric_id: string
    value: canonical decimal string
    unit: FinancialUnit
    period: string
    period_basis: FinancialPeriodBasis
    actuality: FinancialActuality
    as_of: date
    currency: string | null
    calculation_refs: nonempty unique string[]
    evidence_refs: nonempty unique string[]
    judgment_refs: unique string[]
  released_metric: ReleasedFinancialMetricProjectionV1
  task_refs: TaskAvailabilityRefV1[]
  primary_task_id: string | null
  evidence: EvidenceAvailabilityProjectionV1[]
  calculations: CalculationAvailabilityProjectionV1[]
  judgment_refs: JudgmentAvailabilityV1[]
  review_refs: ReviewAvailabilityRefV1[]
  proof_refs: ProofTraceRefV1[]
  canonical_record_id: string
  released_result_id: string
  anchors: ClaimAnchorSetV1
  availability: AvailabilityV1
```

`calculations` follows `claim.calculation_refs`; `evidence` follows `claim.evidence_refs`;
`judgment_refs` follows `claim.judgment_refs`; and `task_refs` is the first occurrence of each exact
`CalculationRecord.task_id` in Calculation order. `primary_task_id` is non-null only when an
explicit durable Backend relation selects one of those derived Tasks. Singleton cardinality alone
does not establish business primacy; without that relation the field is null.
Safe Evidence omits `raw_artifact_ref`, source locators and provider bodies. Safe Calculation omits
internal source references and preserves exact inputs, parameters, output, unit, formula,
capability, version/hash, assurance refs, status and creation time without recomputation.

```yaml
JudgmentAvailabilityV1:
  judgment_id: string
  run_id: string
  availability: AvailabilityV1
  detail: TechnicalIndicatorJudgmentDetailV1 | null

TechnicalIndicatorJudgmentDetailV1:
  schema_version: phase4-technical-judgment/v1
  judgment_id: string
  run_id: string
  task_id: string
  judgment_type: rsi_state | macd_state | moving_average_state
  value: OVERBOUGHT | OVERSOLD | BULLISH | BEARISH | NEUTRAL
  evidence_refs: string[]
  calculation_refs: string[]
  policy_id: string
  skill_version: string
  confidence: number in [0,1] | null
  limitations: string[]
  requires_review: true
```

The inspected parent's generic Judgment JSON is not typed durable detail. It is returned as the
exact retained Judgment ID with `UNAVAILABLE/JUDGMENT_DETAIL_NOT_TYPED`, `retryable=false`, and
`detail=null`. `AVAILABLE` is allowed only after exact typed, same-Run, ID-bearing detail is
persisted and validated. No prompt, scratchpad, chain-of-thought or raw provider content is public.

## 16. FinancialReviewProjectionV1 — UAC-013

The Review contract is decision-complete even though several fields require new persistence:

```yaml
FinancialReviewProjectionV1:
  schema_version: phase4-financial-review/v1
  projection_revision: integer >= 1
  projection_sequence: integer >= 0
  object_id: string
  run_id: string
  canonical_record_id: string | null
  released_result_id: string | null
  review_id: string | null
  status: PASS | REVIEW | BLOCK | null
  reviewer: string | null
  input_snapshot_hash: sha256 string | null
  reviewed_evidence_refs: string[]
  reviewed_calculation_refs: string[]
  reviewed_metric_refs: string[]
  reviewed_claim_refs: string[]
  reviewed_judgment_refs: string[]
  required_proof_calculation_refs: string[]
  checks:
    - check_id: string
      check_code: string
      status: PASS | REVIEW | BLOCK
      subjects:
        - subject_type: RUN | TASK | EVIDENCE | CALCULATION | METRIC | CLAIM |
                        JUDGMENT | PROOF | CANONICAL_RECORD | RELEASED_RESULT
          subject_id: string
          run_id: string
      expected: safe JSON object
      actual: safe JSON object
      detail: string | null
      exception_state: NONE | OPEN | RESOLVED
      correction_refs:
        - correction_id: string
          run_id: string
          task_id: string
          relation: ADDRESSES_CHECK
          status: RESOLVED | FAILED | ESCALATED
          resolved_at: RFC3339 UTC | null
      created_at: RFC3339 UTC
      resolved_at: RFC3339 UTC | null
  availability: AvailabilityV1
```

`check_id`, typed subjects, Check-to-Correction links, exception state and Check-level
`resolved_at` are `BACKEND_FIELD_REQUIRED`. `NONE` has no correction and no resolution time;
`OPEN` has null `resolved_at`; `RESOLVED` has at least one exact linked Correction and non-null
`resolved_at`. Neither aggregate `review.resolved`, array position, check text/code nor a Correction
timestamp may manufacture Check resolution.

The original Check `status` never changes. `NONE` is permitted only for a PASS Check with no linked
Correction. REVIEW/BLOCK begins `OPEN`; it becomes `RESOLVED` only after at least one exact linked
Correction and a persisted Check-level verification decision. Aggregate Review is `BLOCK` while
any OPEN BLOCK remains, else `REVIEW` while any OPEN REVIEW remains, else `PASS`. Checks order by
`created_at ASC, check_id ASC`; linked Corrections use the same timestamp/ID tie rule.

A live pre-release Review has both canonical/result IDs null. A released Review has both non-null,
the Canonical record contains its Review ID, and the Released result points to that Canonical
record. If no Review exists, Review fields are null, arrays are empty, and availability is explicit;
the projection never invents PASS. Before Review it is `PENDING`; after an earlier terminal Run it
is `NOT_GENERATED`. A half-null canonical/result pair is an integrity failure. V17 may rename
`status` to `verdict`, but it must preserve the UAC-010 map and may not synthesize
`PASS_WITH_UNCERTAINTY`.

## 17. TraceBundleV1 and anchor manifest — UAC-014

`GET /api/research-runs/{run_id}/trace/{claim_id}` returns:

```yaml
TraceBundleV1:
  schema_version: phase4-trace/v1
  projection_revision: integer >= 1
  projection_sequence: integer >= 0
  anchor_manifest_id: string
  anchor_manifest_sha256: sha256 string
  object_id: string
  run_id: string
  claim_id: string
  metric_id: string
  calculation_id: string
  claim: TypedReleasedClaimV1
  released_metric: ReleasedFinancialMetricProjectionV1
  task_refs: TaskAvailabilityRefV1[]
  primary_task_id: string | null
  evidence_refs: EvidenceAvailabilityRefV1[]
  calculation_refs: CalculationAvailabilityRefV1[]
  judgment_refs: JudgmentAvailabilityV1[]
  review_refs: ReviewAvailabilityRefV1[]
  proof_refs: ProofTraceRefV1[]
  canonical_record_id: string
  released_result_id: string
  report:
    report_id: string
    representations:
      - format: HTML | PDF
        artifact_id: string | null
        availability: AvailabilityV1
        claim_anchor: RepresentationClaimAnchorV1
  review_anchors: ReviewCheckAnchorV1[]
  task_anchors: TaskAnchorV1[]
  execution_anchors: ExecutionEventAnchorV1[]
  availability: AvailabilityV1
```

Each anchor carries `anchor_id` (nullable only when unavailable), `anchor_kind`, `object_id`,
`run_id`, `claim_id`, its exact target IDs, and `availability`. A representation Claim anchor also
carries `report_id`, `released_result_id`, `canonical_record_id`, `artifact_id` and `format`; a
Review anchor carries `review_id/check_id`; a Task anchor carries `task_id`; an execution anchor
carries `canonical_record_id`, `task_id` and exact `event_refs[]`.

```yaml
ClaimAnchorManifestV1:
  schema_version: phase4-claim-anchor-manifest/v1
  anchor_manifest_id: opaque stable string
  anchor_manifest_sha256: sha256 string
  object_id: string
  run_id: string
  claim_id: string
  metric_id: string
  canonical_record_id: string
  released_result_id: string
  report_id: string
  representations: exactly [HTML RepresentationClaimAnchorV1, PDF RepresentationClaimAnchorV1]
  review_anchors: ReviewCheckAnchorV1[]
  task_anchors: TaskAnchorV1[]
  execution_anchors: ExecutionEventAnchorV1[]
  created_at: RFC3339 UTC
```

The manifest hash is SHA-256 over RFC 8785 canonical manifest bytes with
`anchor_manifest_sha256` omitted. The ID is stable and immutable; regeneration never mutates bytes
under the same ID. Review anchors follow `review_refs` then Check order; Task anchors exactly follow
`task_refs`; execution anchors follow Task order and each event list by sequence ascending. An
execution anchor requires an explicit persisted Claim-to-safe-RuntimeEvent relation; Canonical
`trace_refs` cannot substitute.

Closure is exact: Claim metric equals the top-level/released metric; the selected Calculation is
the metric's Calculation; Evidence sets are identical; Tasks derive only through Claim Calculation
refs; Review/Check and Proof links are explicit; Canonical X owns O/R and every released ref;
Released L owns R/X; and `report_id == released_result_id`. Every available representation owns
R/X/L and uses only its own artifact/anchor. An unavailable representation has null artifact and
anchor IDs and cannot borrow the other format. Observability `trace_refs` are not execution
anchors. The immutable hash-bound `ClaimAnchorManifestV1` and exact claim-to-event anchors are
`BACKEND_FIELD_REQUIRED`; there is no document search or DOM-ID fallback.

## 18. Artifact authorization and storage isolation — UAC-015

`authorized_ref` is the canonical relative same-origin path
`/api/research-runs/{run_id}/artifacts/{artifact_id}/content`. It contains no signature, bearer
token, credential, query secret or storage locator and is present only for an `AVAILABLE`
representation in an authorized metadata response. Its path has no credential lifetime of its own:
credential expiry, access revocation, artifact revocation and retention expiry are re-evaluated on
every GET. Copying the path grants no authority.

The current local profile first establishes server scope `LOCAL_SINGLE_USER`, then performs one
scope-concealed lookup and validates R/O/A/X/L/report/representation-anchor closure, current
availability, trusted internal storage resolution, complete staged read, type/size/SHA-256, and
only then success headers/bytes. If a future governed profile requires authentication,
authentication occurs before any existence-revealing lookup; one authorization-scoped concealed
lookup follows it. V1 rejects Range requests and storage redirects. The success headers are:

```text
Content-Type: text/html; charset=utf-8 | application/pdf
Content-Length: exact verified byte count
Digest: sha-256=<base64 raw SHA-256 digest>
ETag: "sha256-<64 lowercase hex>"
Content-Disposition: inline; filename="report.html" | attachment; filename="report.pdf"
Cache-Control: private, no-store
X-Content-Type-Options: nosniff
```

The Phase 4A profile has no credential-denial branch. Missing resources use 404 `NOT_FOUND` and a
foreign O/R/artifact tuple uses safe 404 `IDENTITY_MISMATCH`; retained unavailable, revoked or retention-expired bytes use 409
`UNAVAILABLE` with an allowlisted reason; corrupt metadata/bytes use 500 `INTEGRITY_FAILURE`.
Every failure sends zero protected bytes. `artifact_ref` stays inside the storage adapter and is
excluded recursively from DTOs, redirects, logs and errors.

UAC-015 stays `WAITING_FOR_IMPLEMENTATION_EVIDENCE` until route, exact-identity, cache, storage,
tamper, revocation, retention and restart tests prove these rules under the frozen local profile.

## 19. Independent artifact availability — UAC-016

The policy token is `phase4-html-required-pdf-optional/v1`. Every report group has exactly one HTML
slot with `required_for_release=true` and one PDF slot with `required_for_release=false`. Both use
the same immutable CanonicalReportDTO/semantic hash but have independent attempts and identities.

`ReportArtifactGroupV1` carries `schema_version`, `object_id`, `run_id`, `report_id`,
`canonical_record_id`, `released_result_id`, `release_policy_version`,
`artifact_policy_version`, group `availability`, `anchor_manifest_id`,
`anchor_manifest_sha256`, and the fixed `[HTML, PDF]` representations. Every AVAILABLE
representation is covered by its own representation-scoped Claim anchor in that manifest.

```yaml
ReportArtifactRepresentationStateV1:
  format: HTML | PDF
  required_for_release: boolean
  content_type: exact reviewed MIME type
  availability: AvailabilityV1
  artifact_id: string | null
  safe_failure_code: string | null
  generation_attempt_id: string | null
  generation_attempt_count: integer >= 0
  sha256: sha256 string | null
  size_bytes: integer > 0 | null
  renderer: RendererIdentityV1 | null
  generated_at: RFC3339 UTC | null
  authorized_ref: relative path | null

ReportArtifactGenerationAttemptV1:
  attempt_id: string
  object_id: string
  run_id: string
  report_id: string
  canonical_record_id: string
  released_result_id: string
  format: HTML | PDF
  renderer: RendererIdentityV1
  semantic_input_sha256: sha256 string
  outcome: PENDING | AVAILABLE | FAILED
  safe_failure_code: string | null
  started_at: RFC3339 UTC
  completed_at: RFC3339 UTC | null
```

The generation lifecycle is `NOT_GENERATED -> PENDING -> AVAILABLE|FAILED`; a retry is a new
append-only preterminal attempt and may move the slot `FAILED -> PENDING`. `AVAILABLE ->
UNAVAILABLE` is allowed only for later revocation, retention loss or integrity quarantine and
retains immutable successful ID/hash/size. Terminal Runs contain no PENDING slot, and no
post-terminal regeneration mutates a released report.

| Availability | Attempt fields | Successful artifact fields | Renderer / time | Failure / reason | `authorized_ref` |
|---|---|---|---|---|---|
| `NOT_GENERATED` | ID null, count `0` | ID/hash/size null | both null | `safe_failure_code=null`; policy reason in Availability | null |
| `PENDING` | current ID, count `>=1` | ID/hash/size null | renderer non-null, generated time null | `safe_failure_code=null` | null |
| `FAILED` before success | completed attempt ID, count `>=1` | ID/hash/size null | renderer non-null, generated time null | allowlisted `safe_failure_code` non-null | null |
| `AVAILABLE` | successful attempt ID/count | ID/hash non-null, size `>0` | both non-null | `safe_failure_code=null` | non-null in authorized metadata |
| `UNAVAILABLE` after success | retain successful attempt/count | retain ID/hash/size | retain both | `safe_failure_code=null`; revocation/retention/quarantine is Availability reason | null |
| `NOT_RELEASED` | group boundary only | no public prerelease artifact facts | — | `NOT_RELEASED` Availability | null |

HTML must be integrity-valid and `AVAILABLE` before release. PDF may be `AVAILABLE`,
`NOT_GENERATED/PDF_NOT_GENERATED_BY_POLICY`, or `FAILED` with a durable safe code; the
policy-skipped code is an `availability.reason_code`, never a `safe_failure_code`. PDF failure alone
does not fail the Run. Required HTML failure uses the UAC-011 terminal finalizer. UAC-016 stays
`WAITING_FOR_IMPLEMENTATION_EVIDENCE` until fault injection proves every render/store/verify and
commit boundary, append-only retry history, terminal coupling and restart persistence.

## 20. ReleaseValidationRecordV1 and lossless metrics — UAC-017

The umbrella policy is `phase4-release-eligibility/v1`, with Review policy
`phase4-independent-financial-review/v1`, material-output policy
`phase4-full-material-output/v1`, artifact policy `phase4-html-required-pdf-optional/v1`, and the
approved parent's exact durable Proof policy ID/hash. The inspected candidate's provisional Proof
policy is `phase3-revenue-growth-must-prove-v1`; the final parent must confirm or explicitly replace
it.

```text
ReleaseValidationRecordV1
  validation_id
  run_id
  object_id
  decision = ALLOWED | BLOCKED
  reason_codes[]
  review_id
  canonical_record_id
  released_result_id
  release_policy_version
  review_policy_version
  proof_policy_id
  proof_policy_hash
  material_output_policy_version
  material_output_manifest_hash
  artifact_policy_version
  artifact_manifest_hash
  review_input_snapshot_hash
  closure_hash
  evaluated_at
  released_at  # non-null only for ALLOWED
```

For Object O, eligible set E contains only Runs R where R owns O, R is RELEASED, exactly one
successful validation binds R/O/Review/X/L and all policy IDs/hashes, Review is PASS over the exact
input, every required material Calculation has one REPORTABLE metric/Claim/Evidence closure, each
MUST_PROVE decision has exact VERIFIED Proof closure, X is terminal-success and owns O/R, L owns
R/X, HTML is integrity-valid/AVAILABLE, and PDF has a terminal policy-permitted state.
`latest_released_run_id` is the maximum E member by `(L.released_at DESC, R.run_id DESC)`, comparing
the opaque Run ID bytewise for a timestamp tie. Empty E returns null with
`NOT_RELEASED/NO_RELEASED_RUN`. Repository order, `completed_at`, ticker, global latest,
`/financials` and `/state` never participate.

The `phase4-full-material-output/v1` manifest is the accepted parent's reviewed hash-bound FULL
set. For the inspected candidate it is provisionally the exact ten `MATERIAL_FORMULAS`: revenue
growth, EBITDA margin, FCF margin, SMA50, SMA200, RSI14, MACD line/signal/histogram, and volume ratio
20. An empty or runtime-selected subset is invalid; each member must be REPORTABLE with one exact
metric and material Claim.

The lossless metric boundary carries, without omission or client arithmetic:

```text
run_id, metric_id, name, canonical_value, canonical_unit, display_value, display_unit,
period, period_basis, actuality, as_of, currency, formula_id, capability_id,
calculation_id, evidence_refs, claim_refs,
proof {policy_id, requirement, status, proof_refs},
method_metadata {method, ordered parameters, observation_count, warmup_required,
                 warmup_satisfied, first_as_of, last_as_of, is_wilder, ema_adjust},
technical_price_basis, corporate_action_status, corporate_action_guard_refs, limitations
```

Decimal values are strings; display values are Backend-authored. V17 may only rename snake case to
camel case and wrap immutably. It must not multiply, round, select, drop applicability fields or
reinterpret `VALID` as verified; `VALID` maps to `GENERATED_UNVERIFIED`, and required proof releases
only at `VERIFIED`.

## 21. Contract-freeze / acceptance-evidence boundary

The governance lifecycle is orthogonal:

```text
A. SEMANTIC CONTRACT DECISION
   exact semantics/schema/oracle are sufficient for implementation

B. CONTRACT FREEZE
   authoritative API/event/persistence contract is immutable and implementation may target it

C. IMPLEMENTATION / ACCEPTANCE CLOSURE
   executable evidence proves the implementation conforms to the frozen contract
```

Implementation evidence for newly required Phase 4 behavior is not a prerequisite for freezing its
semantics. It blocks `PHASE4_IMPLEMENTATION_ACCEPTED` and `PHASE4_CORE_ACCEPTANCE` after
implementation. Accordingly UAC-007, UAC-009, UAC-011, UAC-015 and UAC-016 retain their historical
compatibility state while carrying:

```text
contract_semantics_state=READY_FOR_FINAL_FREEZE
implementation_evidence_state=PENDING
```

UAC-006 is `RESOLVED_PROVISIONALLY` with the same orthogonal pair. `CONTRACT_CLOSED` means the final
delta removed semantic uncertainty against bound authority; `ACCEPTANCE_PROVEN` means later
executable evidence passed. Neither term is implied by bare `CLOSED`, and no current row is closed.
The full rule is in `PHASE4_CONTRACT_FREEZE_ACCEPTANCE_BOUNDARY.md`.

The machine-readable register applies these orthogonal fields across all rows: UAC-001/002 are
authority-input rows with evidence not applicable, while UAC-003..018 have implementation evidence
PENDING. The complete pending-evidence count is therefore 16; the historical
`WAITING_FOR_IMPLEMENTATION_EVIDENCE` current-state count remains five.

The future semantic freeze may become ready when the approved Phase 3 parent and both audit PASS
receipts, approved hash-bound V17 contract input, all 18 ambiguity-free UAC decisions, exact
`BD-001..012` dispositions, reconciled field ownership, and hash-bound schema/event/error/access/
version contracts are present. The five pending implementation-evidence rows do not add a circular
pre-freeze prerequisite.

## 22. Final reconciliation and stop

The later `PHASE4_BACKEND_FINAL_CONTRACT_DELTA_RECONCILIATION` must:

1. bind the exact approved Phase 3 parent and audit evidence;
2. bind the approved V17 contract-input package without creating the FCR dependency cycle;
3. bind owner decision `phase4-local-single-user-trusted/v1` for UAC-006;
4. compare the approved parent against every current Backend-fact statement;
5. incorporate the remaining focused schemas and invariants in this document;
6. convert each `UAC-001..018` to only `CLOSED` or `STILL_OPEN`;
7. report freeze-ready only when all 18 are `CLOSED`.

Until then, stop at contract documentation. Do not implement Backend, acceptance tests or Frontend
V17 integration.

```text
PHASE4_BACKEND_UAC_CLOSURE_PREP_READY=YES
UAC_TOTAL=18
UAC_DISPOSITIONED=18/18
UAC_RESOLVED_PROVISIONALLY=11
UAC_WAITING_FOR_APPROVED_PHASE3_PARENT=1
UAC_WAITING_FOR_FINAL_V17_CONTRACT=1
UAC_WAITING_FOR_IMPLEMENTATION_EVIDENCE=5
UAC_SEMANTIC_DECISION_REQUIRED=0
UAC_FINAL_CLOSED=0
BD_TOTAL=12
BD_DISPOSITIONED=12/12
FRONTEND_CONTRACTS_MAPPED=13/13
FRONTEND_CONFLICT_CLUSTERS_MAPPED=9/9
BACKEND_BLOCKERS_MAPPED=8/8
PHASE5_LEAKAGE=0
PHASE4_BACKEND_CONTRACT_FREEZE_READY=NO
PHASE4_PRODUCTION_IMPLEMENTATION_AUTHORIZED=NO
```
