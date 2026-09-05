# V17 Frontend Contract Preparation

Status: `PROVISIONAL_READY_BLOCKED_BY_BACKEND_CONTRACT`

```text
NAMED_FRONTEND_CONTRACTS_PREPARED = 13/13
UNRESOLVED_FRONTEND_CONTRACT_CONFLICTS = 9
FINAL_BACKEND_PHASE4_CONTRACT_FREEZE = NOT_AVAILABLE
FRONTEND_V17_IMPLEMENTATION_AUTHORIZED = NO
```

## Scope and source coordinates

This is a proposed frontend normalization contract, not TypeScript implementation. It reconciles:

- `FRONTEND_BASELINE_V8.1@d854c97789c98cca14fee3f4b3d7f00e0d5d137a`;
- the V17 target/scaffold package, treated as non-authoritative reference input;
- Backend Phase 3 `codex/phase3-contracts@11fe8173a25ff7ac08bae42340ba7c6fae591be5`;
- the provisional Phase 4 API, event, identity/error/availability, mapping, and blocker drafts.

Every shape below remains subject to the approved Backend Phase 4 contract freeze. Pages must never
consume raw backend JSON.

## Mandatory boundary

```text
response.json(): unknown
→ versioned runtime decoder
→ private snake_case Backend DTO
→ HttpFrontendDataSource / RuntimeTransport normalization
→ immutable camelCase Frontend projection
→ runtimeEventReducer / store
→ Page / Component
```

Rules:

1. Backend DTOs stay private to adapters/transports. A cast such as `json() as Promise<T>` is invalid.
2. Pages do not import wire DTOs or accept unbounded `Record<string, unknown>` business records.
3. Backend owns identity, Run/Task/graph lifecycle, financial values and semantics, Review, Proof,
   release state, artifact integrity, and A/B/C relations.
4. `runtimeEventReducer` is the only live business-state mutation point. Connection and presentation
   state cannot mutate canonical Run truth.
5. Unknown major schemas, enum values, event types/payloads, or failed identity closure fail closed,
   retain at most the visibly stale last-valid projection, and request authoritative recovery.
6. Prompts, raw completions, scratch state, hidden reasoning/Chain-of-Thought, provider raw bodies,
   secrets, filesystem paths, and internal artifact refs never enter normalized projections.

## Shared normalized vocabulary

```ts
type RunStatus =
  | "PREPARING" | "AWAITING_CONFIRMATION" | "PLANNING"
  | "RESEARCHING" | "REVIEWING" | "PROVING"
  | "COMPLETED" | "FAILED" | "CANCELLED";

type RunStage =
  | "PREPARE" | "CONFIRM" | "PLANNING" | "RESEARCH"
  | "REVIEW" | "PROVING" | "COMPLETE" | "FAILED" | "CANCELLED";

type ReviewVerdict = "PASS" | "PASS_WITH_UNCERTAINTY" | "REVIEW" | "BLOCK";
type ReviewExceptionState = "NONE" | "OPEN" | "RESOLVED";
type ProofStatus =
  | "NOT_REQUIRED" | "REQUIRED_PENDING" | "PROVING" | "VALID"
  | "INVALID" | "ERROR" | "UNSUPPORTED" | "UNKNOWN";
type PathChangeType = "SELF_CORRECTION" | "ADD_TASK" | "CHANGE_DEPENDENCY";
```

Backend Run normalization is total: `DRAFT/SCHEME_GENERATING → PREPARING`,
`AWAITING_CONFIRMATION → AWAITING_CONFIRMATION`, `PLANNING → PLANNING`, `RUNNING → RESEARCHING`,
`REVIEW → REVIEWING`, `PROVING → PROVING`, `RELEASED → COMPLETED` only after release closure,
and `FAILED/CANCELLED → FAILED/CANCELLED`. Preserve the source `backendStatus`; never cast.

`PASS_WITH_UNCERTAINTY` requires explicit backend authority. `RESOLVED` is exception history, not a
Review verdict. `RETURN_TO_STEP`, `WAIT_FOR_USER`, and `RESUME` are deferred names; any such or other
unknown mutation fails closed during Phase 4.

## Proposed normalized contracts

### 1. `Availability`

```ts
interface Availability {
  status: "PENDING" | "AVAILABLE" | "NOT_GENERATED" |
          "NOT_RELEASED" | "UNAVAILABLE" | "FAILED";
  reasonCode: string | null;
  retryable: boolean;
}
```

| Dimension | Preparation decision |
|---|---|
| Backend source | Proposed `AvailabilityV1`; Phase 3 has only partial presence/lifecycle signals |
| Rename/normalization | `reason_code → reasonCode`; absence is never synthesized into success |
| Nullability | `reasonCode` is null only for `AVAILABLE`; non-empty otherwise; `PENDING` only for nonterminal Run |
| Identity/owner | Backend projection owns state for the exact resource and Run/Object tuple |
| Unknown/recovery | Unknown/invalid invariant becomes `SCHEMA_INCOMPATIBLE`; withhold resource and reload snapshot |
| Dependency | `BACKEND_PROJECTION_REQUIRED`, `WAITING_FOR_BACKEND_FREEZE` |

### 2. `ErrorEnvelope`

```ts
interface ErrorEnvelope {
  schemaVersion: "phase4-error/v1";
  error: {
    code: "NOT_FOUND" | "FORBIDDEN" | "UNAVAILABLE" | "NOT_GENERATED" |
          "NOT_RELEASED" | "CONFLICT" | "INVALID_CURSOR" | "CURSOR_AHEAD" |
          "SCHEMA_INCOMPATIBLE" | "IDENTITY_MISMATCH" | "INTEGRITY_FAILURE" |
          "UNSUPPORTED_EVENT" | "TERMINAL" | "TRANSIENT_BACKEND_ERROR";
    message: string;
    retryable: boolean;
    recovery: "NONE" | "RETRY" | "SNAPSHOT_RELOAD" | "REAUTHENTICATE";
    requestId: string | null;
    resource: { type: string; id: string } | null;
    details: Readonly<Record<string, SafeJsonValue>>;
  };
}
```

| Dimension | Preparation decision |
|---|---|
| Backend source | Current `ErrorResponse/ErrorDetail` plus proposed Phase 4 wrapper |
| Rename/enum | `request_id → requestId`; `RESOURCE_NOT_FOUND → NOT_FOUND`; freeze total HTTP/SSE map |
| Nullability | `requestId`/`resource` may be null only when backend lacks safe context; `details` is redacted/allowlisted |
| Identity/owner | Backend supplies safe error; adapter retains requested tuple and never substitutes another entity |
| Unknown/recovery | Non-envelope body becomes local transport failure; never expose raw body; recovery follows directive |
| Dependency | `WAITING_FOR_BACKEND_FREEZE` |

### 3. `GlobalRunCollectionProjection`

```ts
interface GlobalRunCollectionProjection {
  schemaVersion: "phase4-run-collection/v1";
  items: readonly RunCollectionItem[];
  nextCursor: string | null;
}
interface RunCollectionItem {
  runId: string;
  object: { objectId: string; symbol: string; companyName: string };
  backendStatus: string;
  status: RunStatus;
  stage: RunStage;
  progress: { fraction: number; percent: number; method: "ACTUAL_TASK_MEAN_V1" };
  activity: { eventId: string; type: string; sequence: number; timestamp: string;
              taskId: string | null; messageCode: string } | null;
  graphVersion: number;
  projectionRevision: number;
  projectionSequence: number;
  asOf: string;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  terminal: boolean;
  resultAvailability: Availability;
}
```

| Dimension | Preparation decision |
|---|---|
| Backend source | Run repository + exact Object + actual graph + safe latest event + release closure |
| Renames | All snake_case identity/timestamp/watermark fields to camelCase in adapter |
| Normalization | Stable order `(updated_at DESC, run_id DESC)`; opaque versioned filter-bound cursor; server supplies non-financial percent |
| Nullability | Activity/start/completion/cursor may be null according to lifecycle; owner IDs never null |
| Identity/owner | Compound `(objectId, runId)`; every item verifies `ResearchRun.research_object_id` |
| Unknown/recovery | One unknown status/invalid owner invalidates response; transient failure may retain visibly stale last-valid collection |
| Dependency | `BACKEND_PROJECTION_REQUIRED`, `BACKEND_ROUTE_REQUIRED` (`GET /api/research-runs`) |

### 4. `PreparedResearchDraft`

```ts
interface PreparedResearchDraft {
  schemaVersion: "phase4-run-draft/v1";
  draftId: string;
  draftVersion: number;
  status: "AWAITING_CONFIRMATION";
  previewKind: "SCHEME_ONLY";
  objectId: string;
  mode: "FULL";
  goalTemplateId: string | null;
  goal: NormalizedGoal;
  schemeSnapshot: NormalizedScheme & { confirmedAt: null };
  prepareRequestHash: string;
  createdAt: string;
  expiresAt: string;
}
```

| Dimension | Preparation decision |
|---|---|
| Backend source | `ResearchRunDraft`, `ResearchGoal`, `ResearchSchemeSnapshot` |
| Rename/normalization | `draft_id`, `research_object_id`, `goal_text`, `scheme_snapshot` → camelCase; replaces V8 `ResearchPlan`/V17 `PreparedRun` |
| Enum/nullability | Phase 4 mode is `FULL`; `confirmedAt` must be null; template/model fields may be null; Tasks/graph are absent, not empty placeholders |
| Identity/owner | `(draftId,draftVersion,objectId,goalId,schemeId)` plus request hash; backend owns expiry/consumption |
| Unknown/recovery | Incremental or mismatched/expired version fails explicitly; regenerate obtains a new draft ID |
| Dependency | `SEMANTIC_CONFLICT`, `BACKEND_FIELD_REQUIRED`, `WAITING_FOR_BACKEND_FREEZE` |

The UI labels this honestly as Scheme/Plan Preview. It does not invent a Task graph before confirm.

### 5. `ConfirmAndStartResult`

```ts
interface ConfirmAndStartResult {
  schemaVersion: "phase4-run-admission/v1";
  runId: string;
  objectId: string;
  goalId: string;
  schemeId: string;
  plannedGraphId: string;
  backendStatus: "PLANNING";
  status: "PLANNING";
  autoStart: true;
  idempotencyReplayed: boolean;
  confirmationRequestHash: string;
  projectionRef: string;
  eventsRef: string;
}
```

| Dimension | Preparation decision |
|---|---|
| Backend source | Strengthened `POST /api/research-runs`; V17 `/confirm-and-start` route is a suggestion, not authority |
| Normalization | UI method may be `confirmAndStartRun`; response represents durable admission at `PLANNING`, not fabricated `RESEARCHING` |
| Nullability | All identity, hash, and refs required; one stable `Idempotency-Key` header and exact body across retries |
| Identity/owner | Same key+hash returns same Run; same key+different hash is `CONFLICT`; backend atomically freezes draft/Goal/Scheme and admits scheduler |
| Unknown/recovery | Ambiguous network outcome retries same body/key; never creates a fresh key; reload exact resulting Run |
| Dependency | `SEMANTIC_CONFLICT`, durable idempotency/admission fields, `WAITING_FOR_BACKEND_FREEZE` |

The user clicks Start Research once. There is no second Start API or button.

### 6. `RunProjection`

```ts
interface RunProjection {
  projectionSchemaVersion: "phase4-run-projection/v1";
  projectionRevision: number;
  projectionSequence: number;
  generatedAt: string;
  object: NormalizedObjectIdentity;
  run: NormalizedRunRecord;
  goal: NormalizedGoal;
  confirmedScheme: NormalizedScheme;
  plannedGraph: NormalizedGraph;
  actualGraph: NormalizedGraph;
  graphVersion: number;
  tasks: readonly RunTaskProjection[];
  pathChanges: readonly PathChangeProjection[];
  activity: readonly SafeRuntimeActivity[];
  lifecycle: NormalizedRunLifecycle;
  review: OwnedAvailabilityRef;
  result: OwnedAvailabilityRef;
  artifacts: OwnedAvailabilityRef;
  proof: NormalizedProofSummary;
  execution: OwnedAvailabilityRef;
  terminal: NormalizedTerminalState;
}
```

`NormalizedGraph` requires exact `graphId`, `runId`, version, typed task IDs, and typed edges.

| Dimension | Preparation decision |
|---|---|
| Backend source | Coherent projection over Run, Goal/Scheme, graphs, Tasks, events, review, result, proof, canonical execution, artifacts |
| Normalization | Planned graph immutable; actual graph/version backend-owned; no raw graph JSON; task progress remains authoritative and display conversion occurs once |
| Nullability | Release/review/proof/execution refs nullable only under explicit `Availability`; terminal outcome/event nullable only when nonterminal |
| Identity/owner | Exact Run is join root; every nested record closes to Run and its Object; reducer/store owns normalized projection |
| Unknown/recovery | Sparse graph event marks `projectionRefreshRequired`; unknown/gap pauses mutation and reloads coherent snapshot |
| Dependency | `BACKEND_PROJECTION_REQUIRED`, `BACKEND_ROUTE_REQUIRED`, revision/watermark freeze |

### 7. `NormalizedRuntimeEventV1`

```ts
interface NormalizedRuntimeEventV1<T extends RuntimeEventType> {
  schemaVersion: "phase4-runtime-event/v1";
  eventId: string;
  runId: string;
  taskId: string | null;
  type: T;
  timestamp: string;
  sequence: number;
  payload: RuntimePayloadByType[T];
  effect: "PATCH_PROJECTION" | "REFRESH_PROJECTION" |
          "OBSERVATION_ONLY" | "TERMINAL";
  projectionRefreshRequired: boolean;
}
```

| Dimension | Preparation decision |
|---|---|
| Backend source | Durable backend `RuntimeEvent` envelope and per-Run sequence; payload families require freeze |
| Rename/event map | Preserve canonical backend name; map `task.correction_resolved` explicitly; `review.resolved` is not exception resolution; missing V8/V17 pseudo-events cause refresh, not invention |
| Enum/nullability | `taskId` nullable only for Run-level events; `run.completed/run.failed` are terminal; `release.completed` is not terminal; cancellation rule remains open |
| Identity/owner | Transport validates envelope; reducer is sole live mutation owner; Task IDs must resolve in exact Run |
| Unknown/recovery | Duplicate exact ID/sequence ignored; conflicting duplicate is integrity failure; gap/out-of-order/unknown pauses reduction and reconciles snapshot |
| Dependency | Envelope `BACKEND_CONTRACT_AVAILABLE`; payload/event/terminal map `SEMANTIC_CONFLICT`, `WAITING_FOR_BACKEND_FREEZE` |

Heartbeats remain SSE comments and never mutate state. Proof generation never implies validity.

### 8. `ConnectionState`

```ts
type ConnectionState =
  | { kind: "IDLE"; runId: string; lastSequence: number }
  | { kind: "CONNECTING"; runId: string; lastSequence: number; attempt: number }
  | { kind: "OPEN"; runId: string; lastSequence: number; lastHeartbeatAt: string | null }
  | { kind: "RECOVERING"; runId: string; lastSequence: number;
      reason: "SEQUENCE_GAP" | "UNKNOWN_EVENT" | "SCHEMA_INCOMPATIBLE" |
              "CURSOR_REJECTED" | "PROJECTION_MISMATCH" }
  | { kind: "BACKOFF"; runId: string; lastSequence: number;
      retryAt: string; attempt: number; error: ErrorEnvelope }
  | { kind: "TERMINAL"; runId: string; lastSequence: number;
      outcome: "SUCCESS" | "FAILURE" | "CANCELLED" }
  | { kind: "FAILED"; runId: string; lastSequence: number; error: ErrorEnvelope };
```

| Dimension | Preparation decision |
|---|---|
| Backend source | SSE replay/heartbeat/terminal primitives plus frozen snapshot/cursor protocol |
| Normalization | Transport/store owns connection state; it never changes Run status; fetch-stream is preferred if explicit initial cursor/header is required |
| Nullability | Only heartbeat timestamp may be null while open; all variants retain exact Run and cursor |
| Identity/owner | One active subscription per exact Run; stale last-valid projection is visibly marked during reconnect |
| Unknown/recovery | Bad/ahead cursor uses typed error and snapshot recovery; terminal state never reconnects indefinitely |
| Dependency | `WAITING_FOR_BACKEND_FREEZE`; native V17 `EventSource.onmessage` is insufficient for named events/cursor seeding |

### 9. `FinancialReviewProjection`

```ts
interface FinancialReviewProjection {
  schemaVersion: "phase4-financial-review/v1";
  projectionRevision: number;
  projectionSequence: number;
  objectId: string;
  runId: string;
  canonicalRecordId: string | null;
  releasedResultId: string | null;
  reviewId: string;
  verdict: ReviewVerdict;
  reviewer: string;
  reviewedEvidenceRefs: readonly string[];
  reviewedCalculationRefs: readonly string[];
  reviewedMetricRefs: readonly string[];
  reviewedClaimRefs: readonly string[];
  requiredProofCalculationRefs: readonly string[];
  checks: readonly FinancialReviewCheckProjection[];
  availability: Availability;
}
```

| Dimension | Preparation decision |
|---|---|
| Backend source | Exact `ReviewRecord`/`ReviewCheck`, Claims, Calculations, corrections, canonical execution/result |
| Renames/normalization | Snake_case refs to camelCase; expected/actual become typed backend-authored data; V17 input→process→output steps are not synthesized from logs |
| Enum/nullability | Verdict excludes `RESOLVED`; canonical/result IDs nullable only for explicit live nonreleased review; stable check IDs/resolution time required |
| Identity/owner | Backend authors verdict/check relations; released B must share Object/Run/canonical ID with A/C |
| Unknown/recovery | Unknown verdict/check schema withholds review and requests compatible projection; no frontend PASS inference |
| Dependency | `SEMANTIC_CONFLICT`, `BACKEND_PROJECTION_REQUIRED`, field additions/freeze pending |

### 10. `ClaimTraceProjection` / `TraceBundle`

```ts
interface ClaimTraceProjection {
  schemaVersion: "phase4-trace/v1";
  projectionRevision: number;
  projectionSequence: number;
  objectId: string;
  runId: string;
  claimId: string;
  claim: TypedReleasedClaim;
  releasedMetric: ReleasedFinancialMetric;
  taskRefs: readonly AvailabilityRef<"taskId">[];
  primaryTaskId: string | null;
  evidenceRefs: readonly AvailabilityRef<"evidenceId">[];
  calculationRefs: readonly AvailabilityRef<"calculationId">[];
  judgmentRefs: readonly AvailabilityRef<"judgmentId">[];
  reviewRefs: readonly ReviewTraceRef[];
  proofRefs: readonly ProofTraceRef[];
  canonicalRecordId: string;
  releasedResultId: string;
  report: { reportId: string; artifactIds: readonly string[]; anchor: ScopedAnchor };
  reviewAnchor: ScopedAnchor;
  taskAnchor: ScopedAnchor;
  executionAnchor: ScopedAnchor & { eventRefs: readonly string[] };
  availability: Availability;
}
```

| Dimension | Preparation decision |
|---|---|
| Backend source | Claim→Metric→Calculation→Task/Evidence; Review checks; Proof/verification; canonical/result/report artifacts |
| Renames/normalization | Private `TraceBundleV1` DTO maps to camelCase; anchors remain opaque and scope-bound |
| Nullability | `primaryTaskId` may be null unless backend selects one; each missing detail/anchor carries explicit availability; canonical/result IDs required for released trace |
| Identity/owner | Backend relations only; `(objectId,runId,claimId,reportId/canonicalRecordId)` scope; `reportId = releasedResultId` in Phase 4 v1 |
| Unknown/recovery | Missing/unknown never uses title/text/first/latest matching; exact unavailable state or fail closed |
| Dependency | `BACKEND_PROJECTION_REQUIRED`, `BACKEND_ROUTE_REQUIRED`, anchor/check ID freeze |

The exact path is Report → Claim → Review → Task → Calculation → Evidence → Execution → original
Report Anchor. Back/Forward, focus, scroll, and highlight are frontend presentation responsibilities;
relation truth remains backend-owned.

### 11. `ReportArtifactGroup`

```ts
interface ReportArtifactGroup {
  schemaVersion: "phase4-report-artifacts/v1";
  objectId: string;
  runId: string;
  reportId: string;
  canonicalRecordId: string;
  releasedResultId: string;
  availability: Availability;
  representations: readonly ReportRepresentation[];
}
interface ReportRepresentation {
  format: "HTML" | "PDF";
  artifactId: string | null;
  contentType: "text/html; charset=utf-8" | "application/pdf";
  availability: Availability;
  safeFailureCode: string | null;
  sha256: string | null;
  sizeBytes: number | null;
  renderer: { rendererId: string; rendererVersion: string } | null;
  generatedAt: string | null;
  authorizedRef: string | null;
}
```

| Dimension | Preparation decision |
|---|---|
| Backend source | Per-representation `ReportArtifactRecord` plus exact Run/canonical/result closure |
| Renames/normalization | `artifact_type → format/contentType`, `content_hash → sha256`, `created_at → generatedAt`; group HTML/PDF without merging identity |
| Nullability | Available representation requires ID/hash/size/renderer/time/ref; `NOT_GENERATED` has null artifact ID; each representation independent |
| Identity/owner | Backend owns bytes/integrity; opaque same-origin authorized ref; retrieval repeats Object/Run/report/canonical checks |
| Unknown/recovery | Bad type/hash/size/owner is integrity failure; never expose `artifact://`/filesystem ref; refresh/re-authorize exact representation |
| Dependency | `SEMANTIC_CONFLICT`, `BACKEND_PROJECTION_REQUIRED`, `BACKEND_ROUTE_REQUIRED` |

### 12. `ReleasedFinancialMetric`

```ts
interface ReleasedFinancialMetric {
  runId: string;
  metricId: string;
  name: string;
  canonicalValue: string;
  canonicalUnit: "RATIO" | "PERCENT" | "CURRENCY" | "COUNT" |
                 "SHARES" | "INDEX" | "MULTIPLE";
  displayValue: string;
  displayUnit: string;
  period: string;
  periodBasis: "FY" | "QUARTER" | "TTM" | "LTM" | "CURRENT" | "DAILY";
  actuality: "UNKNOWN" | "ACTUAL" | "ESTIMATE";
  asOf: string;
  currency: string | null;
  formulaId: string;
  capabilityId: string;
  calculationId: string;
  evidenceRefs: readonly string[];
  claimRefs: readonly string[];
  proof: { requirement: "NOT_REQUIRED" | "MUST_PROVE";
           status: ProofStatus; proofRefs: readonly string[] };
  limitations: readonly string[];
}
```

| Dimension | Preparation decision |
|---|---|
| Backend source | Released metric plus same-Run Claim/Calculation/Evidence/Proof lineage |
| Renames/normalization | Decimal values remain strings; `evidence_ids → evidenceRefs`; Claims match exact `metric_id`; Proofs match exact `calculation_id` |
| Enum/nullability | Currency nullable only when semantically not applicable/unknown as explicitly carried; no unit/actuality/period/proof inference |
| Identity/owner | `(runId,metricId)` plus unique calculation binding; backend is sole financial authority |
| Unknown/recovery | Unknown unit/actuality/lineage withholds metric; no fallback or frontend recomputation |
| Dependency | Core record largely `BACKEND_CONTRACT_AVAILABLE`; Claim/Proof enrichment `BACKEND_PROJECTION_REQUIRED`; final freeze pending |

Mandatory fixture:

```text
canonicalValue = "0.6547"; canonicalUnit = "RATIO"
displayValue = "65.47"; displayUnit = "%"
visible = "65.47%"
```

The frontend only joins/formats backend display fields. It never multiplies by 100.

### 13. `ReleasedObjectCoreProjection`

```ts
interface ReleasedObjectCoreProjection {
  schemaVersion: "phase4-released-object-core/v1";
  object: NormalizedObjectIdentity;
  latestReleasedRunId: string | null;
  currentReleasedResultAvailability: Availability;
  sourceRunId: string | null;
  releasedResultId: string | null;
  canonicalRecordId: string | null;
  releasedAt: string | null;
  metrics: readonly ReleasedFinancialMetric[];
  claimRefs: readonly string[];
  reportArtifacts: ReportArtifactGroup | null;
}
```

| Dimension | Preparation decision |
|---|---|
| Backend source | Object identity + validated released Runs/results/canonical record/metrics/artifacts |
| Renames/normalization | Latest selection only among valid `RELEASED` Runs ordered `(released_at DESC, run_id DESC)` |
| Nullability | No released Run means all release IDs/time null and explicit `NOT_RELEASED`; available means all are non-null and source=latest |
| Identity/owner | Object→exact released Run→exact result/canonical closure; failed/running Runs never overwrite slice |
| Unknown/recovery | Invalid release closure withholds slice; never fall back to latest arbitrary Run |
| Dependency | `BACKEND_PROJECTION_REQUIRED`, `BACKEND_ROUTE_REQUIRED`; all memory/version/comparison/writeback fields `PHASE5_DEFERRED` |

## Run state and A/B/C invariants

```text
A.objectId = B.objectId = C.objectId
A.runId = B.runId = C.runId
A.canonicalRecordId = B.canonicalRecordId = C.canonicalRecordId
```

A/B/C links come only from backend IDs and the trace bundle. C may expose timestamp, sequence, actor,
event, typed input/output facts, observable operations, status, duration, provider/model, usage,
implementation hash, and proof metadata. `observableProcess` is an operation log, never hidden
reasoning. No field or rendering may require Chain-of-Thought.

## Nine unresolved conflict clusters

1. Prepare Plan/Tasks versus actual Scheme-only draft and graph creation on confirm.
2. V17 `/confirm-and-start` + immediate `RESEARCHING` versus backend admission route/state.
3. Process-local idempotency/background start versus durable request-bound exactly-once admission.
4. Progress scale and total Run/Task/Review/Proof enum mappings.
5. Runtime event names/payload completeness, graph refresh, terminal/cancellation/failure semantics.
6. Browser SSE cursor seeding, named-event handling, replay, gap, duplicate and recovery protocol.
7. V17 step-based Financial Review versus current check-based backend record and missing A/B/C IDs.
8. Combined V8/V17 artifact semantics versus per-representation records, authorization, availability,
   byte integrity, and Claim anchor manifest.
9. Lossy frontend financial/Object state versus lossless released metric and released Object core
   projection; Phase 5 memory/comparison/writeback must stay absent.

The backend dependency matrix splits these clusters into twelve closure records. Any change to these
semantics requires review before the frontend Change Request can advance to `CHANGE_APPROVED`.
