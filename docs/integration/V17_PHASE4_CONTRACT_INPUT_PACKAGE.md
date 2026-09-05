# V17 Phase 4 Contract Input Package

Status: `READY_FOR_OWNER_APPROVAL`

```text
V17_CONTRACT_INPUT_PACKAGE_READY = YES
V17_CONTRACT_INPUT_PACKAGE_SHA256 = 36cf733d07b4df1ad4cb1065bdd17eceb6bbc98cf6f77fe0dfb1963185757e08
NORMALIZED_CONTRACTS = 13/13
BD_RECORDS = 12/12
REFERENCE_MANIFEST = 44be67d6854a284055c19919bcaf979097c710b33d3e5f57c5f7a35fe376f394
FRONTEND_IMPLEMENTATION_AUTHORIZED = NO
FRONTEND_CANDIDATE_CREATED = NO
CONTRACT_INPUT_APPROVAL_READY = YES
OWNER_APPROVAL_REQUIRED = YES
OWNER_APPROVAL_STATUS = PENDING
```

## 1. Purpose and authority boundary

This documentation/governance package is the single Frontend V17 consumer-contract input prepared
for Phase 4 Backend Final Contract Freeze. It freezes the requested frontend-facing field names,
types, nullability, enum mappings, unknown behavior, identity keys, availability semantics, backend
dependency IDs, adapter ownership, interaction reservations, test-gate delta, Scene dispositions,
and Node 24 compatibility evidence.

It is not a Frontend V17 implementation Candidate, source baseline, build, integration PASS, Delta
Audit, implementation evidence, or implementation authorization. It creates no Candidate SHA and
does not alter application or backend source.

The immutable parent remains:

```text
FRONTEND_BASELINE_V8.1
d854c97789c98cca14fee3f4b3d7f00e0d5d137a
```

The machine-readable semantic authority for this package is
`V17_PHASE4_CONTRACT_INPUT_PACKAGE.json`. This Markdown document is its human-readable companion.

## 2. Canonical package hash

```text
canonicalization_profile = LEXICOGRAPHIC_COMPACT_JSON_V1
canonical_payload = V17_PHASE4_CONTRACT_INPUT_PACKAGE.json
canonical_package_sha256 = 36cf733d07b4df1ad4cb1065bdd17eceb6bbc98cf6f77fe0dfb1963185757e08
```

`LEXICOGRAPHIC_COMPACT_JSON_V1` recursively sorts every JSON object key by bytewise lexical order,
retains array order, serializes compact UTF-8 JSON with JSON string escaping, and adds no terminal
newline. This package uses only strings, integers, booleans, null, arrays, and objects, avoiding
cross-runtime floating-point canonicalization differences. Reproduction command:

```sh
jq -cS . docs/integration/V17_PHASE4_CONTRACT_INPUT_PACKAGE.json \
  | tr -d '\n' \
  | shasum -a 256
```

The manifest binds the exact on-disk JSON and Markdown digests separately. It omits its own digest
from its body to avoid a recursive self-hash.

## 3. Bound governance inputs

| Input | Exact bound revision |
|---|---|
| Corrected V17 reference manifest | `V17_REFERENCE_MANIFEST_V1.json` SHA-256 `44be67d6854a284055c19919bcaf979097c710b33d3e5f57c5f7a35fe376f394`; `65/65`; reference input only |
| Contract preparation | SHA-256 `09d473ec009fd6658569c4054b3943f26679f74aa671772b6a0bc8887381067d`; 13/13 normalized contracts |
| Backend dependency matrix | SHA-256 `9f6981cd7e5782b5467f4a1fc8770b46d0e1460e9b18bc20aa8918b82034eb24`; `BD-001..012` |
| Interaction impact | SHA-256 `39fbe34aafd98e5916f0d714dac1d217752e68fe813dc4bd85fc8b746f280d1a`; reservations `071..076` |
| Test preparation | SHA-256 `5955d37ec6e3fce2e623f2b85e9c03108608cd385782a7d253c84e78dc0067c4`; proposed `P4-E2E-107..112` delta |
| Browser Scene matrix | SHA-256 `9da7425b1bab5fab8371a2ee8e5ea733f7871e4ec3b4c581793564cd94de2052` |
| E2E activation matrix | SHA-256 `b3b2aa62e8a389403f3d5b537de5a316bacaab88d2286cb7bb43f556ca25a96e` |
| Node 24 evidence | SHA-256 `889a975aa39f6401cf06c5ba59e6d9256d8159c489a4861ed85db9562e3feca7` |
| Governance-cycle rule | SHA-256 `6a3d64d12f6742f14c5fa0d66dc60bdc0fc45c8eab640677022332676b8d3d63` |

### Exact FCR revision

```text
change_id = FRONTEND_V17_PHASE4_CORE_INTEGRATION
record_revision = DRAFT-01
status = DRAFT_CHANGE
file_sha256 = b20f2a0527638d057b1de62a6b154cdc8d50724d4aa75ee3491122fad3280df1
git_blob_sha1 = 52a3ebdbc107f42b87094e60cbc39ad730089510
candidate_sha = PENDING
implementation_authorized = false
```

This package does not edit or promote the FCR. Its historical disclosure of the embedded V17
manifest defect is read together with correction record `V17-RMCR-001`, whose separately versioned
companion manifest closes only that reference-manifest defect.

## 4. Shared consumer boundary

```text
response.json(): unknown
→ versioned runtime decoder
→ private snake_case Backend DTO
→ HttpFrontendDataSource / RuntimeTransport normalization
→ immutable camelCase Frontend projection
→ runtimeEventReducer / store
→ Page / Component
```

Pages never consume raw backend JSON. Backend owns identity, Run/Task/graph lifecycle, financial
values and semantics, Review, Proof, release state, artifact integrity, and A/B/C relations.
`runtimeEventReducer` is the only live business-state mutation point. Connection and presentation
state never mutate canonical Run truth.

Unknown major schemas, enum values, event types/payloads, or failed identity closure fail closed,
retain at most a visibly stale last-valid projection, and request authoritative recovery. Prompts,
raw completions, scratch state, hidden reasoning/Chain-of-Thought, provider bodies, secrets,
filesystem paths, and internal artifact refs never enter normalized projections.

Run normalization is total:

| Backend value | Consumer status | Consumer stage |
|---|---|---|
| `DRAFT`, `SCHEME_GENERATING` | `PREPARING` | `PREPARE` |
| `AWAITING_CONFIRMATION` | `AWAITING_CONFIRMATION` | `CONFIRM` |
| `PLANNING` | `PLANNING` | `PLANNING` |
| `RUNNING` | `RESEARCHING` | `RESEARCH` |
| `REVIEW` | `REVIEWING` | `REVIEW` |
| `PROVING` | `PROVING` | `PROVING` |
| `RELEASED` | `COMPLETED`, only after release closure | `COMPLETE`, only after release closure |
| `FAILED` | `FAILED` | `FAILED` |
| `CANCELLED` | `CANCELLED` | `CANCELLED` |

The exact Phase 4 path-change allowlist is `SELF_CORRECTION`, `ADD_TASK`, and
`CHANGE_DEPENDENCY`. `RETURN_TO_STEP`, `WAIT_FOR_USER`, `RESUME`, and all unknown values fail
closed.

## 5. Frozen normalized Frontend contracts

The JSON companion is normative for every field declaration below, including required presence and
nullability.

### 5.1 `GlobalRunCollectionProjection`

Schema: `schemaVersion`, `items`, `nextCursor`. Each `RunCollectionItem` contains `runId`, `object`
(`objectId`, `symbol`, `companyName`), `backendStatus`, `status`, `stage`, `progress` (`fraction`,
`percent`, `method=ACTUAL_TASK_MEAN_V1`), nullable `activity` (`eventId`, `type`, `sequence`,
`timestamp`, nullable `taskId`, `messageCode`), `graphVersion`, `projectionRevision`,
`projectionSequence`, `asOf`, `createdAt`, `updatedAt`, nullable `startedAt`, nullable
`completedAt`, `terminal`, and `resultAvailability`.

- Identity: `(objectId, runId)`; every item closes through `ResearchRun.research_object_id`.
- Availability: cursor/activity/lifecycle timestamps alone are nullable as declared; result uses the
  explicit `Availability` contract.
- Unknown: one unknown status or invalid owner invalidates the response; transient failure may retain
  a visibly stale last-valid collection.
- Dependency/owner: `BD-009`; `HttpFrontendDataSource` normalizes, store owns immutable state, pages
  only read. Stable order is `(updated_at DESC, run_id DESC)` with opaque versioned filter-bound
  cursor.

### 5.2 `PreparedResearchDraft`

Schema: `schemaVersion=phase4-run-draft/v1`, `draftId`, `draftVersion`,
`status=AWAITING_CONFIRMATION`, `previewKind=SCHEME_ONLY`, `objectId`, `mode=FULL`, nullable
`goalTemplateId`, `goal`, `schemeSnapshot` with `confirmedAt=null`, `prepareRequestHash`, `createdAt`,
and `expiresAt`.

- Identity: `(draftId, draftVersion, objectId, goalId, schemeId, prepareRequestHash)`.
- Availability: Tasks and graph are absent, not empty placeholders.
- Unknown: Incremental/mismatched/expired/consumed input fails explicitly; regenerate creates a new
  draft ID.
- Dependency/owner: `BD-007`; backend owns Goal/Scheme, version, expiry, consumption, and request
  hash; the adapter normalizes; UI labels it honestly as a Scheme/Plan Preview.

### 5.3 `ConfirmAndStartResult`

Schema: `schemaVersion=phase4-run-admission/v1`, `runId`, `objectId`, `goalId`, `schemeId`,
`plannedGraphId`, `backendStatus=PLANNING`, `status=PLANNING`, `autoStart=true`,
`idempotencyReplayed`, `confirmationRequestHash`, `projectionRef`, and `eventsRef`; all fields are
required and non-null.

- Identity: exact Run/Object/Goal/Scheme/graph/request-hash tuple.
- Unknown: ambiguous outcome retries the exact body and stable `Idempotency-Key`; never issue a new
  key automatically.
- Dependency/owner: `BD-008`; backend atomically freezes the draft and admits exactly one durable
  Run/start. The adapter exposes the result. There is one Start action and no second Start API.

### 5.4 `RunProjection`

Schema: `projectionSchemaVersion=phase4-run-projection/v1`, `projectionRevision`,
`projectionSequence`, `generatedAt`, `object`, `run`, `goal`, `confirmedScheme`, `plannedGraph`,
`actualGraph`, `graphVersion`, `tasks`, `pathChanges`, `activity`, `lifecycle`, `review`, `result`,
`artifacts`, `proof`, `execution`, and `terminal`. Arrays and owned availability refs are required.
Each graph requires exact `graphId`, `runId`, version, typed Task IDs, and typed edges.

- Identity: exact Run is the join root; all nested records close to its Object/Run; revision and
  sequence are coherent watermarks.
- Availability: Review/result/artifact/proof/execution absence is explicit; terminal outcome/event is
  nullable only while nonterminal.
- Unknown: gap/order/unknown pauses mutation and reloads one coherent snapshot; sparse graph events
  force refresh and never fabricate Tasks.
- Dependency/owner: `BD-001`; data adapter validates initial snapshot, reducer solely mutates live
  state, store owns the immutable projection.

### 5.5 `NormalizedRuntimeEventV1`

Schema: `schemaVersion=phase4-runtime-event/v1`, `eventId`, `runId`, nullable Run-level `taskId`,
`type`, `timestamp`, `sequence`, payload discriminated by type, `effect`, and
`projectionRefreshRequired`.

- Effects: `PATCH_PROJECTION`, `REFRESH_PROJECTION`, `OBSERVATION_ONLY`, or `TERMINAL`; the exact
  member lists are frozen in the JSON companion. Raw event names are preserved.
- Guards: `task.correction_resolved` is explicit same-Task correction resolution;
  `review.resolved` is not exception resolution; `release.completed` is not terminal;
  `proof.generated` is not validity.
- Identity: `(runId, sequence, eventId)` plus a same-Run `taskId` when present.
- Unknown: exact duplicate is ignored; conflicting duplicate, gap, order error, unknown type/payload,
  schema error, or identity mismatch mutates nothing and forces recovery.
- Dependency/owner: `BD-002`, `BD-012`; transport validates and the reducer alone applies effects.
  SSE heartbeats remain comments, not business events.

### 5.6 `ConnectionState`

Exact variants are `IDLE`, `CONNECTING`, `OPEN`, `RECOVERING`, `BACKOFF`, `TERMINAL`, and `FAILED`.
Every variant retains `runId` and `lastSequence`; `OPEN.lastHeartbeatAt` alone may be null.
Recovery reasons are `SEQUENCE_GAP`, `UNKNOWN_EVENT`, `SCHEMA_INCOMPATIBLE`, `CURSOR_REJECTED`, and
`PROJECTION_MISMATCH`; terminal outcomes are `SUCCESS`, `FAILURE`, and `CANCELLED`.

- Mapping: `LIVE→OPEN`; `RECONNECTING|STALE→BACKOFF`; `RECONCILING→RECOVERING`; request-level
  schema incompatibility→`FAILED`; unsupported in-stream value→`RECOVERING`.
- Unknown: typed cursor error and snapshot recovery; terminal never reconnects indefinitely.
- Dependency/owner: `BD-003`; `RuntimeTransport`/store own one exact-Run fetch-stream connection.
  Transport state never changes Run truth.

### 5.7 `FinancialReviewProjection`

Schema: `schemaVersion=phase4-financial-review/v1`, `projectionRevision`, `projectionSequence`,
`objectId`, `runId`, conditionally nullable `canonicalRecordId` and `releasedResultId`, `reviewId`,
`verdict`, `reviewer`, reviewed Evidence/Calculation/Metric/Claim refs, required-Proof Calculation
refs, `checks`, and `availability`.

- Verdict: `PASS`, `PASS_WITH_UNCERTAINTY`, `REVIEW`, or `BLOCK`. Uncertainty requires explicit
  backend authority. `RESOLVED` is exception history, never a verdict.
- Identity: Object/Run/Review and stable check IDs; a released B view shares canonical/result identity
  with A/C.
- Unknown: withhold unknown verdict/check schema; never infer PASS or synthesize steps from logs.
- Dependency/owner: `BD-010`, `BD-011`; backend authors Review truth and the data adapter normalizes.

### 5.8 `ClaimTraceProjection / TraceBundle`

Schema: `schemaVersion=phase4-trace/v1`, revision/sequence, `objectId`, `runId`, `claimId`, typed
Claim and released metric, availability-bearing Task/Evidence/Calculation/Judgment refs, nullable
backend-selected `primaryTaskId`, Review/Proof refs, `canonicalRecordId`, `releasedResultId`, report
identity/artifact IDs/scoped anchor, and scoped Review/Task/Execution anchors with execution event
refs, plus overall availability.

- Identity: `(objectId, runId, claimId, reportId, canonicalRecordId, releasedResultId)`;
  `reportId=releasedResultId` in Phase 4 v1.
- Unknown: never use title/text/first/latest/symbol/metric matching; return exact unavailable state or
  fail closed.
- Dependency/owner: `BD-006`; backend owns relation truth and opaque scoped anchors; frontend owns
  navigation/focus/scroll/highlight only.
- Required round trip: Report → Claim → Review → Task → Calculation → Evidence → Execution → original
  Report Anchor.

### 5.9 `ReportArtifactGroup`

Schema: `schemaVersion=phase4-report-artifacts/v1`, `objectId`, `runId`, `reportId`,
`canonicalRecordId`, `releasedResultId`, `availability`, and independent HTML/PDF
`representations`. Each representation contains `format`, nullable-by-availability `artifactId`, exact
`contentType`, availability, nullable `safeFailureCode`, `sha256`, `sizeBytes`, renderer identity,
`generatedAt`, and `authorizedRef`.

- Identity: Object/Run/report/canonical/result plus format and available artifact ID.
- Availability: AVAILABLE requires ID/hash/size/renderer/time/ref; NOT_GENERATED requires null ID;
  HTML and PDF remain independent.
- Unknown: bad format/type/hash/size/ref/owner is `INTEGRITY_FAILURE`; never expose internal locators.
- Dependency/owner: `BD-004`; backend owns bytes and integrity, adapter groups without merging
  identities and revalidates exact ownership on retrieval.

### 5.10 `ReleasedFinancialMetric`

Schema: `runId`, `metricId`, `name`, string `canonicalValue`, canonical unit, string `displayValue`,
`displayUnit`, `period`, period basis, actuality, `asOf`, conditionally nullable `currency`,
`formulaId`, `capabilityId`, `calculationId`, Evidence refs, Claim refs, Proof requirement/status/refs,
and limitations.

- Closed units: `RATIO`, `PERCENT`, `CURRENCY`, `COUNT`, `SHARES`, `INDEX`, `MULTIPLE`.
- Closed period basis: `FY`, `QUARTER`, `TTM`, `LTM`, `CURRENT`, `DAILY`.
- Closed actuality: `UNKNOWN`, `ACTUAL`, `ESTIMATE`.
- Identity: `(runId, metricId)` with unique Calculation binding.
- Unknown: withhold unknown semantics or lineage; no frontend recomputation.
- Dependency/owner: `BD-005`; backend is sole financial authority. Mandatory fixture is backend
  `0.6547 RATIO`, display `65.47` + `%`, visible `65.47%`; frontend never multiplies by 100.

### 5.11 `ReleasedObjectCoreProjection`

Schema: `schemaVersion=phase4-released-object-core/v1`, exact Object, nullable
`latestReleasedRunId`, result availability, nullable `sourceRunId`, `releasedResultId`,
`canonicalRecordId`, `releasedAt`, metrics, Claim refs, and nullable artifact group.

- Selection: only valid `RELEASED` Runs ordered `(released_at DESC, run_id DESC)`; failed/running
  Runs never supersede the slice.
- Identity: Object → exact released Run → exact result/canonical/artifact closure.
- Availability: no release means all release IDs/time/artifacts null with `NOT_RELEASED`; AVAILABLE
  requires non-null closure and `sourceRunId=latestReleasedRunId`.
- Unknown: withhold invalid closure; never use the latest arbitrary Run.
- Dependency/owner: `BD-001`, `BD-009`; backend owns selection, adapter normalizes; all Phase 5
  memory/version/comparison/writeback fields stay absent.

### 5.12 `ErrorEnvelope`

Schema: `schemaVersion=phase4-error/v1` and safe `error` containing `code`, `message`, `retryable`,
`recovery`, nullable safe-context `requestId`, nullable safe-context `resource`, and always-present
redacted allowlisted `details`.

- Codes: `NOT_FOUND`, `FORBIDDEN`, `UNAVAILABLE`, `NOT_GENERATED`, `NOT_RELEASED`, `CONFLICT`,
  `INVALID_CURSOR`, `CURSOR_AHEAD`, `SCHEMA_INCOMPATIBLE`, `IDENTITY_MISMATCH`,
  `INTEGRITY_FAILURE`, `UNSUPPORTED_EVENT`, `TERMINAL`, `TRANSIENT_BACKEND_ERROR`.
- Recovery: `NONE`, `RETRY`, `SNAPSHOT_RELOAD`, `REAUTHENTICATE`.
- Mapping: `request_id→requestId`; `RESOURCE_NOT_FOUND→NOT_FOUND`; HTTP/SSE map is total.
- Unknown: non-envelope response becomes local transport failure; raw response body is never shown.
- Dependency/owner: `BD-003`, `BD-004`, `BD-008`; adapters decode/redact and retain the requested
  tuple without entity substitution.

### 5.13 `Availability`

Schema: `status`, nullable `reasonCode`, and `retryable`. Status is exactly `PENDING`, `AVAILABLE`,
`NOT_GENERATED`, `NOT_RELEASED`, `UNAVAILABLE`, or `FAILED`.

- Nullability: `AVAILABLE` requires `reasonCode=null`; every non-AVAILABLE state requires a non-empty
  stable reason code. `PENDING` is valid only for a nonterminal Run.
- Identity: exact resource and owning Run/Object tuple where applicable.
- Unknown: invalid state becomes `SCHEMA_INCOMPATIBLE`, withholds the resource, and reloads the
  authoritative snapshot. Absence never becomes success.
- Dependency/owner: `BD-004`, `BD-005`, `BD-010`; backend projection owns resource state and adapter
  normalizes; UI never infers retryability or availability.

## 6. Backend dependency records

All 12 records are bound as required final-freeze inputs, not claimed as implemented evidence.

| ID | Priority | Frozen input obligation |
|---|---:|---|
| `BD-001` | P0 | Coherent Run projection and event watermark; same-Run ownership and snapshot/replay race oracle |
| `BD-002` | P0 | Total versioned raw-event/payload/effect normalization; unknown fails closed |
| `BD-003` | P0 | Browser fetch-stream cursor/recovery/terminal protocol and typed error behavior |
| `BD-004` | P0 | Frontend-safe artifact group, scoped anchors, authorization, and independent HTML/PDF integrity |
| `BD-005` | P0 | Lossless released metric/Claim projection and exact `0.6547 RATIO → 65.47%` fixture |
| `BD-006` | P0 | Exact Claim Trace relation/anchor bundle and negative substitutions |
| `BD-007` | P1 | Scheme-only prepare boundary, immutable version/expiry/hash, no invented Tasks |
| `BD-008` | P1 | Durable request-bound confirm/auto-start replay with exactly one Run/admission/start |
| `BD-009` | P1 | Global Run collection route, stable ordering, cursor/filter binding, list/detail consistency |
| `BD-010` | P1 | Total Run/Task/Review/Proof maps including unknown and history semantics |
| `BD-011` | P1 | Per-Claim/check Financial Review projection with stable refs and backend decisions |
| `BD-012` | P1 | Complete graph mutation payload or mandatory atomic refresh; no fabricated graph content |

Backend Final Freeze must assign exact frozen dispositions for `BD-001..012`; this input package does
not claim implementation or acceptance closure for them.

## 7. Interaction reservations and proposed E2E delta

Existing interactions `001..070` and gates `P4-E2E-001..106` retain identity; `015` remains a
non-executable tombstone. The following append-only delta is ready for owner approval and becomes
final only if that approval and Backend Final Freeze adopt this package:

| Interaction | Gate | Contract | Activation/result |
|---|---|---|---|
| `071` | `P4-E2E-107` | Execution actor filter over `ALL|AGENT|LLM|DATA|TOOL|CODE|RUNTIME|REVIEW|PROOF`; exact Run/canonical identity; complete-safe-collection or backend cursor-bound query required | `PHASE4_CORE_REQUIRED`; integrated real result |
| `072` | `P4-E2E-108` | Execution search over frozen safe fields/IDs only; intersects filter; stale-response quarantine; private canary never matches | `PHASE4_CORE_REQUIRED`; integrated real result |
| `073` | `P4-E2E-109` | Presenter Scene selector | `DEPLOYMENT_ACTIVATED` only with `VITE_ENABLE_PRESENTER=true`; `DEMO_UX_ONLY`; no real aggregate |
| `074` | `P4-E2E-110` | Presenter reset | same Demo-only activation/result |
| `075` | `P4-E2E-111` | Presenter previous with first-step disabled/no-op | same Demo-only activation/result |
| `076` | `P4-E2E-112` | Presenter next with final-step disabled/no-op | same Demo-only activation/result |

If finalized: 112 defined E2E IDs; 101 Phase 4 Core unique IDs; four Phase 5-only IDs; two
deployment-only IDs; four Demo-only Presenter IDs; one tombstone. Projected classified inventories
remain production `71/71`, Presenter-enabled Demo `75/75`, and historical union `76/76`.

## 8. Scene dispositions

| Scene | Impact | Real-backend disposition |
|---|---|---|
| `SCENE-01` Full Financial Research | `AFFECTED` | `PHASE4_CORE_REQUIRED`: prepare/start, runtime, released finance, A/B/C, trace, artifacts |
| `SCENE-02` Dynamic Research Path | `AFFECTED` | `PHASE4_CORE_REQUIRED`: immutable plan, actual graph, bounded mutations, replay/recovery |
| `SCENE-03` Self-Correction and Review | `AFFECTED` | `PHASE4_CORE_REQUIRED`: same-Task correction, recalculation/review, release closure |
| `SCENE-04` Claim Trace | `AFFECTED` | `PHASE4_CORE_REQUIRED`: exact relation round trip to original Report anchor |
| `SCENE-05` Object Accumulation | `AFFECTED_COMPATIBILITY_ONLY` | `PHASE5_ACTIVATED`, currently `DEFINED_NOT_ACTIVATED`; shared/Demo regression only in Phase 4 |
| `SCENE-06` Incremental Return | `AFFECTED_COMPATIBILITY_ONLY` | `PHASE5_ACTIVATED`, currently `DEFINED_NOT_ACTIVATED`; disabled/unavailable and Demo regression only in Phase 4 |

Demo results remain separate and never satisfy a real-backend assertion. No Phase 4 evidence may
claim real Scene 05/06 behavior.

## 9. Node 24 compatibility binding

The bound record proves only the approved V8.1 source/lock reproduction under Node `v24.18.0` and
npm `11.6.2`: `npm ci`, typecheck, runtime tests, and build passed; the build manifest exactly matched
`5fc76ef3038cc6826c54d072b99466b18d7f61a4528594fbd040f5b7a5a1a943`; lock SHA-256 remained
`55cc3eb4d61e8ab53a130c338ef22fd929545214a9d34f7466f5edf1bbb2a5e0`.

```text
NODE24_COMPATIBILITY = PASS
EVIDENCE_SCOPE = FRONTEND_BASELINE_V8.1_ONLY
V17_CANDIDATE_TOOLCHAIN_ACCEPTANCE = NOT_RUN
```

It does not prove a future V17 dependency graph and does not authorize implementation.

## 10. Governance cycle and approval

The required order is:

```text
owner approval of this hash-bound contract input
→ Backend Final Contract Freeze consumes the approved input
→ Frontend V17 implementation consumes the frozen Backend contract
```

A V17 implementation Candidate SHA is not a prerequisite for Backend Final Contract Freeze. This
removes the circular dependency without weakening later Candidate freeze, implementation evidence,
or independent Delta Audit requirements.

The package is complete and ready for owner approval, but this preparation does not silently approve
it:

```text
CONTRACT_INPUT_APPROVAL_READY = YES
OWNER_APPROVAL_REQUIRED = YES
OWNER_APPROVAL_STATUS = PENDING
SELF_APPROVED = NO
```

The FCR remains `DRAFT_CHANGE`, `candidate_sha=PENDING`, and
`FRONTEND_V17_IMPLEMENTATION_AUTHORIZED=NO`.

## 11. Final attestation

```text
V17_CONTRACT_INPUT_PACKAGE_READY = YES
V17_CONTRACT_INPUT_PACKAGE_SHA256 = 36cf733d07b4df1ad4cb1065bdd17eceb6bbc98cf6f77fe0dfb1963185757e08
NORMALIZED_CONTRACTS = 13/13
BD_RECORDS = 12/12
REFERENCE_MANIFEST = 44be67d6854a284055c19919bcaf979097c710b33d3e5f57c5f7a35fe376f394
FRONTEND_IMPLEMENTATION_AUTHORIZED = NO
FRONTEND_CANDIDATE_CREATED = NO
CONTRACT_INPUT_APPROVAL_READY = YES
OWNER_APPROVAL_REQUIRED = YES
```
