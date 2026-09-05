# Phase 4 Backend / Frontend Final Parity Matrix

Status: `SEMANTIC_PARITY_RECONCILED — V17_OWNER_APPROVAL_PENDING`  
Backend contract family: `phase4-core/v1`  
Runtime event contract: `phase4-runtime-event/v1`  
Compared frontend input: 13/13 normalized contracts in canonical V17 package
`36cf733d07b4df1ad4cb1065bdd17eceb6bbc98cf6f77fe0dfb1963185757e08`, plus the focused Backend
contract corrections in this final delta.

## Comparison rule

Every row is an exact wire-to-adapter-to-frontend mapping. A row groups fields only when every named
field has the same identity, type/nullability rule, enum handling, availability behavior and owner.
Snake case to camel case is mechanical. The frontend may derive only transport/presentation state,
immutable wrappers, and the nonbusiness `percent = fraction * 100`; it never derives identity,
Run/Task/graph lifecycle, Review, Proof, release, artifact or financial truth.

The prepared V17 document is not itself the frozen input package. The corrected target below removes
its nine provisional conflict clusters. Owner approval/hash binding remains the separate UAC-002
gate and is not counted as a field-semantic mismatch.

Both independent audit `FAIL` receipts are separate UAC-001 parent/evidence gates. Their findings are
Backend implementation/provenance/redaction nonconformities, not wire-to-adapter field conflicts:
the final Backend contract binds signed-prior revenue growth, explicit formula-specific half-even
Decimal profiles, immutable hash-verifiable generated source/test bytes, and omission or
irreversible redaction of sensitive telemetry values such as `LANGFUSE_PUBLIC_KEY`.

## 1. `Availability`

| Backend wire field | Adapter normalization | Frontend field | Exact type / nullability / enum | Availability and unknown handling | Owner |
|---|---|---|---|---|---|
| `status` | identity | `status` | required enum `PENDING\|AVAILABLE\|NOT_GENERATED\|NOT_RELEASED\|UNAVAILABLE\|FAILED` | Unknown/invariant failure rejects the containing projection as `SCHEMA_INCOMPATIBLE`; `PENDING` only while Run nonterminal. | Backend projection |
| `reason_code` | camel rename | `reasonCode` | `string|null`; null iff `status=AVAILABLE`, otherwise stable nonempty code | Never infer a reason or success from absence. | Backend projection |
| `retryable` | identity | `retryable` | required boolean; value follows the frozen availability/error policy | Frontend enables retry only when true. | Backend projection |

## 2. `ErrorEnvelope`

| Backend wire field | Adapter normalization | Frontend field | Exact type / nullability / enum | Availability and unknown handling | Owner |
|---|---|---|---|---|---|
| `schema_version` | camel rename | `schemaVersion` | exact `phase4-error/v1` | Unknown version rejects the whole error as a local safe transport failure; raw body is not exposed. | Backend/version protocol |
| `error.code` | identity | `error.code` | required enum `INVALID_CURSOR\|UNAUTHENTICATED\|FORBIDDEN\|NOT_FOUND\|IDENTITY_MISMATCH\|UNAVAILABLE\|NOT_GENERATED\|NOT_RELEASED\|CONFLICT\|CURSOR_AHEAD\|SCHEMA_INCOMPATIBLE\|UNSUPPORTED_EVENT\|TERMINAL\|REQUEST_VALIDATION_ERROR\|INTEGRITY_FAILURE\|INTERNAL_ERROR\|TRANSIENT_BACKEND_ERROR` | Unknown code fails closed; legacy `RESOURCE_NOT_FOUND` and `RESULT_NOT_RELEASED` are normalized at the Backend boundary, not by pages. | Backend error mapper |
| `error.message` | identity | `error.message` | required safe string | Never contains provider bodies, SQL, stack, secrets, prompts, hidden reasoning or internal paths. | Backend |
| `error.retryable` | identity | `error.retryable` | required boolean fixed by code table | Frontend does not override. | Backend |
| `error.recovery` | identity | `error.recovery` | `NONE\|RETRY\|SNAPSHOT_RELOAD\|REAUTHENTICATE` | Frontend executes only the named recovery. | Backend policy |
| `error.request_id` | camel rename | `error.requestId` | `string|null` | Null only when no safe request identity exists. | Backend |
| `error.resource.{type,id}` | camel rename | `error.resource.{type,id}` | whole object `object|null`; when present both strings are required | Concealed failures may repeat caller IDs but never reveal resolved foreign IDs. | Backend |
| `error.details` | readonly safe JSON | `error.details` | required allowlisted JSON object | Unknown/unsafe members reject or are redacted at Backend; pages never render arbitrary raw values. | Backend |

## 3. `GlobalRunCollectionProjection`

| Backend wire field(s) | Adapter normalization | Frontend field(s) | Exact type / nullability / enum | Availability and unknown handling | Owner |
|---|---|---|---|---|---|
| `schema_version` | camel rename | `schemaVersion` | exact `phase4-run-collection/v1` | Mismatch rejects collection. | Backend |
| `items` | readonly wrapper, order preserved | `items` | required array | One invalid item invalidates response; a prior projection may remain visibly stale. | Backend collection projection |
| `items[].run_id` | camel rename | `runId` | required string | Exact route identity; no fallback. | Backend |
| `items[].object.{object_id,symbol,company_name}` | camel rename | `object.{objectId,symbol,companyName}` | three required strings | Object must own Run; mismatch rejects item/response. | Backend |
| `items[].status` | preserve as `backendStatus`, total map | `backendStatus`, normalized `status` | raw required `RunStatus`; normalized `RunStatus` total map | Unknown raw status fails closed. | Backend raw; adapter mechanical frozen map |
| `items[].stage`, `items[].terminal` | camel rename | `stage`, `terminal` | required `RunStage` and boolean consistent with status | Inconsistency rejects item. | Backend projection |
| `items[].progress.{method,completed_tasks,total_tasks,fraction}` | camel rename; add exact `percent=fraction*100` | `progress.{method,completedTasks,totalTasks,fraction,percent}` | method exact `ACTUAL_TASK_MEAN_V1`; counts integers `>=0`; fraction/percent finite numbers; counts/fraction required | No elapsed-time or frontend business inference. | Backend except adapter-owned percent |
| `items[].activity.{event_id,type,sequence,timestamp,task_id,message_code}` | camel rename | `activity.{eventId,type,sequence,timestamp,taskId,messageCode}` | activity whole object nullable; if present identity/time/message required, `taskId` nullable | Unsafe event detail absent; invalid same-Run identity rejects item. | Backend safe-event projection |
| `items[].graph_version` | camel rename | `graphVersion` | `integer>=1|null`; null only before actual graph exists | Never fabricate zero/current graph. | Backend |
| `items[].projection_revision`, `items[].projection_sequence` | camel rename | `projectionRevision`, `projectionSequence` | required integers `>=1` and `>=0` | Must be mutually consistent with detail snapshot. | Backend/MVCC projection |
| `items[].as_of`, `created_at`, `updated_at`, `started_at`, `completed_at` | camel rename | `asOf`, `createdAt`, `updatedAt`, `startedAt`, `completedAt` | dates/times required except lifecycle-governed nullable start/completion | Timestamps do not replace revision/order identity. | Backend |
| `items[].result_availability` | camel rename | `resultAvailability` | required `Availability` | No inference from missing result. | Backend |
| `next_cursor` | camel rename | `nextCursor` | opaque `string|null` | Filter mismatch/malformed/ahead is typed error; no offset or from-zero fallback. | Backend cursor protocol |

## 4. `PreparedResearchDraft`

| Backend wire field(s) | Adapter normalization | Frontend field(s) | Exact type / nullability / enum | Availability and unknown handling | Owner |
|---|---|---|---|---|---|
| `schema_version` | camel rename | `schemaVersion` | exact `phase4-run-draft/v1` | Mismatch rejects draft. | Backend |
| `draft_id`, `draft_version` | camel rename | `draftId`, `draftVersion` | required string and integer `>=1` | Exact consumed/expired version only. | Backend |
| `status`, `preview_kind` | camel rename | `status`, `previewKind` | exact `AWAITING_CONFIRMATION`, `SCHEME_ONLY` | Other value fails closed; Tasks/graph are absent. | Backend |
| `planned_graph_availability` | camel rename | `plannedGraphAvailability` | required Availability, initially `NOT_GENERATED/PLAN_CREATED_ON_CONFIRM/false` | Prevents empty graph from being read as generated. | Backend |
| `object_id` | camel rename | `objectId` | required string | Must equal exact requested Object. | Backend |
| `goal` | recursive camel rename/readonly | `goal` | required normalized Goal; all IDs required; nullable fields preserve source | Unknown fields/version fail decoder; no template business ID. | Backend |
| `scheme_snapshot` | recursive camel rename/readonly | `schemeSnapshot` | required normalized Scheme; `confirmedAt=null` | Scheme is preview authority; no planned Task invention. | Backend |
| `prepare_request_hash`, `draft_hash` | camel rename | `prepareRequestHash`, `draftHash` | required `sha256:<64 lowercase hex>` strings | Mismatch/invalid hash rejects Confirm. | Backend |
| `created_at`, `expires_at` | camel rename | `createdAt`, `expiresAt` | required RFC3339 UTC strings | Expiry is Backend decision. | Backend |
| no wire field | omitted | no `mode`, no `goalTemplateId` business field | absent from normalized contract | UI template/mode labels remain display-only. | Frontend display only |

## 5. `ConfirmAndStartResult`

| Backend wire field(s) | Adapter normalization | Frontend field(s) | Exact type / nullability / enum | Availability and unknown handling | Owner |
|---|---|---|---|---|---|
| `admission.schema_version`, `admission.admission_id` | camel rename | `admission.schemaVersion`, `admission.admissionId` | exact `phase4-run-admission/v1`; required string ID | Invalid admission rejects entire result. | Backend |
| `admission.run_id`, `object_id`, `draft_id`, `draft_version`, `goal_id`, `scheme_id`, `planned_graph_id` | camel rename | corresponding camel fields | all required; IDs strings, version integer `>=1` | Exact immutable identity closure; no latest fallback. | Backend |
| `admission.status` | preserve/map | `admission.backendStatus`, `admission.status` | exact raw/normalized `PLANNING` at admission | Never fabricate immediate `RESEARCHING`. | Backend/raw plus adapter map |
| `admission.draft_hash`, `confirmation_request_hash` | camel rename | `draftHash`, `confirmationRequestHash` | required sha256 strings | Same key+different hash is `CONFLICT`. | Backend |
| `admission.auto_start.{required,admitted}` | camel rename | `autoStart.{required,admitted}` | both required booleans and true for successful V1 admission | Failure is typed error; no second Start call. | Backend scheduler admission |
| `admission.admitted_at` | camel rename | `admittedAt` | required RFC3339 UTC | Immutable admission time. | Backend |
| `response_meta.{schema_version,request_id,idempotency_replayed}` | camel rename | `responseMeta.{schemaVersion,requestId,idempotencyReplayed}` | exact response-meta V1, request ID string/null per protocol, replay boolean | Transport metadata never mutates admission fields. | Backend transport projection |

## 6. `RunProjection`

| Backend wire field(s) | Adapter normalization | Frontend field(s) | Exact type / nullability / enum | Availability and unknown handling | Owner |
|---|---|---|---|---|---|
| `projection_schema_version`, `projection_revision`, `projection_sequence`, `generated_at` | camel rename | corresponding camel fields | exact `phase4-run-projection/v1`; revision `>=1`, sequence `>=0`, UTC time | Torn/inconsistent watermark rejects snapshot. | Backend atomic projection |
| `object`, `run`, `goal`, `confirmed_scheme` | recursive camel rename/readonly | same normalized records | required exact-ID records | Every nested Object/Run/Goal/Scheme relation closes to route Run. | Backend |
| `planned_graph`, `actual_graph` | typed recursive normalization | same fields | planned required immutable; actual nullable only before creation | Unknown graph/task/edge rejects snapshot; no raw JSON passthrough. | Backend |
| `graph_version` | camel rename | `graphVersion` | `integer>=1|null`, equals actual graph version when present | Null before actual graph; mismatch rejects. | Backend |
| `tasks` | typed readonly normalization | `tasks` | required array of exact Run Task projections | Unknown TaskStatus fails closed. | Backend |
| `path_changes` | camel rename | `pathChanges` | required array; `change_kind` only `SELF_CORRECTION\|ADD_TASK\|CHANGE_DEPENDENCY`; graph before/after nullable by source lifecycle | Sparse data causes projection refresh; never invent operations/Tasks. | Backend projection |
| `activity` | safe typed normalization | `activity` | required ordered array | Unsafe payload data is omitted; same-Run only. | Backend |
| `lifecycle.{status,stage,progress,terminal,terminal_outcome,safe_failure}` | camel rename; frozen raw map | same camel fields | total Run map; terminal outcome null iff nonterminal; progress uses Backend fraction/method | Unknown or contradictory lifecycle rejects snapshot. | Backend except adapter display percent |
| `review`, `result`, `artifacts`, `proof`, `execution` | camel rename | same owned availability refs/summaries | required availability-wrapped fields; IDs nullable only when unavailable per contract | No presence inference; every ref exact same Run. | Backend |
| `terminal` | camel rename | `terminal` | required terminal state; event/outcome nullable only nonterminal | Terminal snapshot prevents subscription. | Backend |

## 7. `NormalizedRuntimeEventV1`

| Backend wire field | Adapter normalization | Frontend field | Exact type / nullability / enum | Availability and unknown handling | Owner |
|---|---|---|---|---|---|
| `event_contract_version` | camel rename | `eventContractVersion` | exact `phase4-runtime-event/v1` | Unknown version: zero mutation/cursor advance, quarantine safe metadata, snapshot recovery. | Backend public event projection |
| `payload_schema_version` | camel rename | `payloadSchemaVersion` | exact integer `1` | Unsupported version is `UNSUPPORTED_EVENT`. | Backend |
| `event_id`, `run_id` | camel rename | `eventId`, `runId` | required strings | Must match exact subscription Run; conflicting duplicate is integrity failure. | Backend |
| `task_id` | camel rename | `taskId` | `string|null`; nullable only for Run-level event family | Unknown/foreign Task causes zero mutation and recovery. | Backend |
| `type` | identity raw name | `type` | one of the 55 candidate raw types; only 47 have V1 normalized payloads, 8 are explicit unsupported | Unknown/unsupported causes `UNSUPPORTED_EVENT`; no invented frontend event. | Backend raw enum |
| `timestamp`, `sequence` | identity/camel | same | required UTC string, integer `>=1` contiguous per Run | Duplicate exact identity ignored; gap/out-of-order recovers snapshot. | Backend |
| `payload` | decoder selected by exact raw type | typed `payload` | required V1 discriminated safe payload | Invalid/sparse payload follows frozen refresh/unsupported rule; no financial display value authority. | Backend schema |
| `graph_version` | camel rename | `graphVersion` | always present `integer>=1|null`; non-null for graph-semantic events and `run.started` | Mismatch triggers refresh. | Backend projection |
| `effect`, `projection_refresh_required` | identity or mechanical frozen lookup | `effect`, `projectionRefreshRequired` | effect `PATCH_PROJECTION\|REFRESH_PROJECTION\|OBSERVATION_ONLY\|TERMINAL`; boolean true exactly for refresh/terminal | Lookup is contract plumbing, not business inference. | Frozen shared contract / adapter |

## 8. `ConnectionState`

| Backend/transport input | Adapter normalization | Frontend field(s) | Exact type / nullability / enum | Availability and unknown handling | Owner |
|---|---|---|---|---|---|
| snapshot Run/cursor + stream state | discriminated transport state | `kind` | exact `IDLE\|CONNECTING\|OPEN\|RECOVERING\|BACKOFF\|TERMINAL\|FAILED` | Never mapped to Run lifecycle. | Frontend transport |
| exact subscribed Run | identity | every variant `runId` | required string | One active subscription per exact Run. | Backend identity retained by transport |
| last committed cursor | identity | every variant `lastSequence` | integer `>=0` | Never advances on invalid/unknown event. | Frontend transport from Backend sequence |
| connection attempts/timers | transport derivation | `attempt`, `retryAt`, `lastHeartbeatAt` | attempt required only connecting/backoff; retry time only backoff; heartbeat nullable only open | Heartbeat is liveness comment, not business event. | Frontend transport |
| recovery/error/terminal signals | frozen protocol | `reason`, `error`, `outcome` | recovery reason exact `SEQUENCE_GAP\|UNKNOWN_EVENT\|SCHEMA_INCOMPATIBLE\|CURSOR_REJECTED\|PROJECTION_MISMATCH`; terminal outcome exact `SUCCESS\|FAILURE\|CANCELLED` | Bad/ahead cursor reloads snapshot; terminal does not reconnect indefinitely. | Shared protocol / transport |

## 9. `FinancialReviewProjection`

| Backend wire field(s) | Adapter normalization | Frontend field(s) | Exact type / nullability / enum | Availability and unknown handling | Owner |
|---|---|---|---|---|---|
| `schema_version`, `projection_revision`, `projection_sequence` | camel rename | corresponding camel fields | exact `phase4-financial-review/v1`; integers `>=1`,`>=0` | Incompatible/torn projection rejected. | Backend |
| `object_id`, `run_id` | camel rename | `objectId`, `runId` | required strings | Exact route closure. | Backend |
| `canonical_record_id`, `released_result_id` | camel rename | corresponding camel fields | both `string|null`; both null live/pre-release or both non-null released | Half-null pair is integrity failure. | Backend |
| `review_id`, `status`, `reviewer`, `input_snapshot_hash` | camel rename; optional `status→verdict` frozen rename | `reviewId`, `verdict`, `reviewer`, `inputSnapshotHash` | all nullable only when Review absent; status exact `PASS\|REVIEW\|BLOCK`, never `RESOLVED`/invented uncertainty | Absence has explicit Availability and never implies PASS. | Backend |
| `reviewed_evidence_refs`, `reviewed_calculation_refs`, `reviewed_metric_refs`, `reviewed_claim_refs`, `reviewed_judgment_refs`, `required_proof_calculation_refs` | camel rename/readonly | corresponding camel arrays | required ordered unique string arrays; empty only where contract permits | Same-Run exact refs; no log reconstruction. | Backend |
| `checks[].check_id`, `check_code`, `status` | camel rename | corresponding fields | required stable IDs/codes; status `PASS\|REVIEW\|BLOCK` | Unknown check schema withholds Review. | Backend |
| `checks[].subjects`, `expected`, `actual`, `detail` | typed readonly normalization | same | typed subject enum/IDs; expected/actual safe JSON; detail `string|null` | Frontend does not calculate expected/actual. | Backend |
| `checks[].exception_state`, `correction_refs`, `created_at`, `resolved_at` | camel rename | corresponding fields | state `NONE\|OPEN\|RESOLVED`; resolvedAt null for NONE/OPEN and required for RESOLVED; exact linked corrections | Aggregate `review.resolved` cannot manufacture Check resolution. | Backend |
| `availability` | identity/camel | `availability` | required Availability | Release-independent Review may be pending/not-generated/available. | Backend |

## 10. `ClaimTraceProjection` / `TraceBundle`

| Backend wire field(s) | Adapter normalization | Frontend field(s) | Exact type / nullability / enum | Availability and unknown handling | Owner |
|---|---|---|---|---|---|
| `schema_version`, watermarks, `anchor_manifest_id`, `anchor_manifest_sha256` | camel rename | corresponding camel fields | exact `phase4-trace/v1`; required IDs/hash; revision `>=1`, sequence `>=0` | Hash/version failure withholds trace. | Backend |
| `object_id`, `run_id`, `claim_id`, `metric_id`, `calculation_id` | camel rename | corresponding camel fields | all required strings | Exact join root; no text/name/latest fallback. | Backend |
| `claim`, `released_metric` | typed camel normalization | same | required typed records | Metric/Calculation/Evidence semantics must agree exactly. | Backend |
| `task_refs`, `evidence_refs`, `calculation_refs`, `judgment_refs`, `review_refs`, `proof_refs` | camel rename/order preserved | corresponding arrays | required arrays of availability-wrapped exact refs; primary source order retained | Missing detail remains an unavailable ref, never substitutes another ID. | Backend |
| `primary_task_id` | camel rename | `primaryTaskId` | `string|null`; non-null only from explicit durable primary relation | Singleton cardinality does not infer primacy. | Backend |
| `canonical_record_id`, `released_result_id` | camel rename | corresponding fields | required strings for released trace | Must close same Run and Object. | Backend |
| `report.{report_id,representations}` | camel rename | same | report ID required and equals released result ID; exactly HTML/PDF representation entries | Unavailable representation cannot borrow another format's artifact/anchor. | Backend |
| representation `format`, `artifact_id`, `availability`, `claim_anchor` | camel rename | same | format `HTML\|PDF`; artifact/anchor IDs nullable only when unavailable | Exact representation scope. | Backend |
| `review_anchors`, `task_anchors`, `execution_anchors` | camel rename/order preserved | plural arrays | required arrays; each anchor has exact target IDs and Availability; execution `event_refs` ordered | No DOM/document search fallback; observability trace refs are not execution anchors. | Backend |
| `availability` | identity/camel | `availability` | required Availability | Invalid closure withholds entire trace. | Backend |

## 11. `ReportArtifactGroup`

| Backend wire field(s) | Adapter normalization | Frontend field(s) | Exact type / nullability / enum | Availability and unknown handling | Owner |
|---|---|---|---|---|---|
| `schema_version` | camel rename | `schemaVersion` | exact `phase4-report-artifacts/v1` | Mismatch rejects group. | Backend |
| `object_id`, `run_id`, `report_id`, `canonical_record_id`, `released_result_id` | camel rename | corresponding camel fields | all required strings; report ID equals released result ID | Exact Object/Run/canonical/result closure. | Backend |
| `release_policy_version`, `artifact_policy_version` | camel rename | corresponding camel fields | required exact policy tokens; artifact policy `phase4-html-required-pdf-optional/v1` | Unknown policy fails closed. | Backend |
| `availability`, `anchor_manifest_id`, `anchor_manifest_sha256` | camel rename | corresponding fields | Availability required; manifest ID/hash required when group available | Invalid manifest/hash withholds group/content. | Backend |
| `representations` | readonly fixed order | `representations` | exactly `[HTML,PDF]` | Slots independent; no format substitution. | Backend |
| slot `format`, `required_for_release`, `content_type` | camel rename | corresponding fields | HTML/true/`text/html; charset=utf-8`; PDF/false/`application/pdf` | Unknown format/type rejects slot/group. | Backend policy |
| slot `availability`, `artifact_id`, `safe_failure_code` | camel rename | corresponding fields | exact state/nullability table; policy-skipped PDF has Availability reason and null failure code | No absence inference. | Backend |
| slot `generation_attempt_id`, `generation_attempt_count` | camel rename | corresponding fields | ID nullable by state; count integer `>=0`; attempts append-only | Retry creates a new preterminal attempt. | Backend persistence |
| slot `sha256`, `size_bytes`, `renderer`, `generated_at` | camel rename | corresponding fields | all present only for AVAILABLE or retained UNAVAILABLE-after-success per state table; size `>0` | Integrity mismatch returns `INTEGRITY_FAILURE`, no bytes. | Backend |
| slot `authorized_ref` | camel rename | `authorizedRef` | relative same-origin `string|null`; only authorized AVAILABLE metadata | Non-bearer; every GET rechecks identity/availability/integrity; no `artifact://` or filesystem path. | Backend access projection |

## 12. `ReleasedFinancialMetric`

| Backend wire field(s) | Adapter normalization | Frontend field(s) | Exact type / nullability / enum | Availability and unknown handling | Owner |
|---|---|---|---|---|---|
| `run_id`, `metric_id`, `calculation_id` | camel rename | `runId`, `metricId`, `calculationId` | required strings, unique exact binding | Same-Run closure mandatory. | Backend |
| `name`, `formula_id`, `capability_id` | camel rename | corresponding fields | required nonblank strings | No label-based relation. | Backend |
| `canonical_value`, `display_value` | camel rename, preserve strings | `canonicalValue`, `displayValue` | required canonical Decimal-compatible strings; canonical value is produced under the formula contract's explicit half-even Decimal profile | Frontend never multiplies/rounds/selects or repairs a nonconforming value. | Backend financial authority |
| `canonical_unit`, `display_unit` | camel rename | `canonicalUnit`, `displayUnit` | canonical enum `RATIO\|PERCENT\|CURRENCY\|COUNT\|SHARES\|INDEX\|MULTIPLE`; display nonblank string | Unknown unit withholds metric. | Backend |
| `period`, `period_basis`, `actuality`, `as_of`, `currency` | camel rename | corresponding fields | period/date required; basis `FY\|QUARTER\|TTM\|LTM\|CURRENT\|DAILY`; actuality `UNKNOWN\|ACTUAL\|ESTIMATE`; currency `string|null` by unit semantics | No inference from names/dates. | Backend |
| `evidence_refs`, `claim_refs` | camel rename/readonly | corresponding arrays | required nonempty exact ref arrays; Claim unique per metric under FULL policy | Foreign/missing relation withholds metric/release. | Backend |
| `proof.{policy_id,requirement,status,proof_refs}` | camel rename | same | policy ID required; requirement `NOT_REQUIRED\|MUST_PROVE`; total Proof status; refs ordered | `VALID` is generated-unverified, never converted to VERIFIED. | Backend proof/release policy |
| `method_metadata.{method,parameters,observation_count,warmup_required,warmup_satisfied,first_as_of,last_as_of,is_wilder,ema_adjust}` | camel rename/order preserved | corresponding object | object nullable only when method not applicable; internal fields preserve exact nullable method semantics | No frontend method reconstruction. | Backend |
| `technical_price_basis`, `corporate_action_status`, `corporate_action_guard_refs` | camel rename | corresponding fields | basis/status nullable when nontechnical; otherwise exact enums and required guard refs per release model | Unresolved corporate action blocks release. | Backend |
| `limitations` | readonly identity | `limitations` | required string array | Never dropped by adapter/page. | Backend |

## 13. `ReleasedObjectCoreProjection`

| Backend wire field(s) | Adapter normalization | Frontend field(s) | Exact type / nullability / enum | Availability and unknown handling | Owner |
|---|---|---|---|---|---|
| `schema_version`, `projection_revision`, `generated_at` | camel rename | corresponding camel fields | exact `phase4-released-object-core/v1`; revision `>=1`; UTC time | Mismatch rejects projection. | Backend |
| `object` | typed camel normalization | `object` | required exact Object identity | Route Object must match. | Backend |
| `latest_released_run_id`, `source_run_id`, `released_result_id`, `canonical_record_id`, `released_at` | camel rename | corresponding fields | all null when no eligible release; all non-null when available; source equals latest | Partial tuple is integrity failure; never select newest arbitrary Run. | Backend release selector |
| `current_released_result_availability` | camel rename | `currentReleasedResultAvailability` | required Availability | Empty eligible set is `NOT_RELEASED/NO_RELEASED_RUN/false`. | Backend |
| `metrics`, `claim_refs` | camel rename/readonly | `metrics`, `claimRefs` | empty only with no release; otherwise exact lossless arrays | Invalid member withholds release slice. | Backend |
| `report_artifacts` | camel rename | `reportArtifacts` | `ReportArtifactGroup|null`; non-null for available released result under policy | No artifact inference/fallback. | Backend |
| `runs`, `run_count` where collection/detail surface includes history | camel rename | `runs`, `runCount` | exact Object-owned Run list/count | Phase 4 history only; no memory/version semantics. | Backend |
| no Phase 4 wire field | omitted | no Object version/memory/comparison/incremental/writeback truth | absent | Scene 05/06 real behavior remains Phase 5. | `PHASE5_DEFERRED` |

## Parity result

The corrected final Backend contract and the required V17 consumer normalization agree on identity,
types, nullability, enums, availability, unknown handling and ownership for every field above. The
unapproved older V17 preparation text must not be consumed without the focused corrections captured
here and in its governed contract-input package.

```text
FRONTEND_NORMALIZED_CONTRACTS_COMPARED=13/13
FRONTEND_FIELD_GROUPS_UNMAPPED=0
FRONTEND_CONTRACT_SEMANTIC_CONFLICTS=0
UNOWNED_BUSINESS_FIELDS=0
FRONTEND_FINANCIAL_AUTHORITY=0
CROSS_OBJECT_FALLBACK=0
RAW_ARTIFACT_PATH_EXPOSURE=0
PHASE5_LEAKAGE=0
V17_CONTRACT_INPUT_OWNER_APPROVAL=PENDING
BACKEND_INDEPENDENT_FINAL_AUDIT=FAIL
FINANCIAL_SEMANTICS_INDEPENDENT_AUDIT=FAIL
```
