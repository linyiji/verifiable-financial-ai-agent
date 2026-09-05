# Frontend V17 Phase 4 Contract Input Package — R2

Status: `READY_FOR_OWNER_APPROVAL`  
Classification: `DOCUMENTATION / GOVERNANCE ONLY`  
Package revision: `2.0.0`  
Canonical package SHA-256: `fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19`

## Result and boundary

This R2 package is the single governed Frontend V17 consumer-contract input prepared for Phase 4
Backend Final Contract Freeze. It supersedes R1 before owner approval and reconciles the focused
corrections already frozen by the Backend Final Contract Delta and Final Parity Matrix.

It is not a Frontend implementation Candidate, source baseline, build, integration PASS, Delta
Audit, Phase 4 start, or implementation authorization. No Frontend or Backend production source was
modified. The owner has not approved this package.

```text
R1_PACKAGE_SHA256=36cf733d07b4df1ad4cb1065bdd17eceb6bbc98cf6f77fe0dfb1963185757e08
R1_STATUS=SUPERSEDED_BEFORE_OWNER_APPROVAL
R1_OWNER_APPROVAL=NO

PHASE4_BACKEND_FINAL_CONTRACT_SET_SHA256=0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741
V17_REFERENCE_MANIFEST_SHA256=44be67d6854a284055c19919bcaf979097c710b33d3e5f57c5f7a35fe376f394
R2_PACKAGE_SHA256=fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19
```

The canonical SHA is over the recursively bytewise-key-sorted, compact UTF-8 JSON serialization of
`V17_PHASE4_CONTRACT_INPUT_PACKAGE_R2.json`, with array order preserved and no terminal newline.
The JSON is the normative machine-readable semantic payload. This Markdown file is its
human-readable companion.

## Governance cycle

```text
owner approval of this exact R2 hash
→ Backend Final Contract Freeze consumes the approved R2 contract input
→ Frontend V17 implementation later consumes the frozen Backend contract
```

No V17 Candidate SHA is required for Backend Final Contract Freeze. R2 approval readiness does not
waive UAC-001, approve the FCR, authorize implementation, or assert implementation evidence.

## Authority order

| Precedence | Authority | Bound digest/state |
|---:|---|---|
| 1 | Approved `FRONTEND_BASELINE_V8.1` parent | source SHA `d854c97789c98cca14fee3f4b3d7f00e0d5d137a` |
| 2 | Phase 4 Backend Final Contract Delta | SHA-256 `191d7ffb2f2636ed772839fd3888850adeb64b6e4680fd09803ab45aadd91fe3` |
| 3 | Phase 4 Backend/Frontend Final Parity Matrix | SHA-256 `ac3a3c6e1735519a960df7643bf8353646e2d5ab63874965d7beac3e6da48028` |
| 4 | Final UAC disposition | SHA-256 `226a586e696f92fe6249f7c043ea005291858e7c1bcf46d5a825d1ecf595146c` |
| 5 | Final BD disposition | SHA-256 `99ffdc460d2e2c9d49984af4882f076ca21f094f380487d4ab0a283cb8acbd28` |
| 6 | Access Mode Decision V1 | JSON SHA-256 `c32ac85f7930ab151fbb769350bed270549bdb132489c5c769ec7ef1e042415d` |
| 7 | Acceptance V17 interaction design/delta | exact three-artifact hashes in the JSON payload |
| 8 | Previous R1 package | canonical SHA-256 `36cf733d…`; loses all conflicts with 2–7 |

The Backend final manifest is bound at byte SHA-256
`1886ef831ebff461afcabd936deaadbb10afcaf0d3bd3a037e0f3a7de995657d`. Its embedded aggregate
contract-set SHA-256 is
`0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741`.

## Independently validated component hashes

Every digest below was recomputed from exact artifact bytes or, where stated, from the manifest's
recursively key-sorted compact canonical payload. All comparisons matched.

| Component | Hash scope | SHA-256 |
|---|---|---|
| API schema contract | exact Markdown bytes | `2a1265753c1b7b6e0756ea9c40886dcbcbdf4773e81e467b7df8fddd92763048` |
| Runtime Event contract | exact Markdown bytes | `f6bbca7123051c90d3321781b3e47d4028a457f2ee8a0f51a37acf836b38cf2e` |
| Error/Availability base artifact | exact Markdown bytes | `1cfcafe17c94e1d87bdcd8230ecaeef11913a2cdb7174ace52a2fa01d8ab00b9` |
| Error/Availability final addendum | canonical manifest payload | `5cd8dd06203707b3b9597bc4dbfdc343d7c84884bf2c73982a22cff2f9ffd79a` |
| `VersionProtocolV1` | canonical manifest payload | `ebac4e85f21f9cc145043c9b39d3ca8d04030f8c332b951bb326ab0f4de958fb` |
| `CursorProtocolV1` | canonical manifest payload | `5578976fb01c7ebacaac039a93f21c57cbb2ff51868f7a64513e61660aa42b01` |
| Artifact policy | canonical manifest payload | `1c912c1864aa2c5940182148706757d3f6c92e7c620d275f9c60503e0f30959a` |
| Release policy | canonical manifest payload | `0a823de3f31ec730d32164eec15a0090bd7841ece715603ba57633dd19a9ac63` |
| Financial projection contract | canonical manifest payload | `1c165059432174062625f2a0a969454e831eb2db7a89d9eb52119c6e2f6bfdcf` |

## Shared consumer rules

The boundary is `unknown response → versioned decoder → private snake_case DTO → shared camelCase
adapter → immutable consumer projection → reducer/store → page/component`.

The Backend owns identity; Run/Task/graph lifecycle; Review; Proof; release; artifact state and
integrity; financial values and methodology; and A/B/C/Trace relations. The adapter may only rename,
wrap readonly values, apply a total frozen enum/effect map, maintain transport-only connection state,
and derive nonbusiness `percent=fraction*100`. Pages may format labels/layout/focus only.

Unknown schema, enum, identity, event, payload version/payload, cursor, or conflicting duplicate
causes zero business mutation and zero committed cursor advance. The consumer may retain only a
visibly stale last-valid projection while it performs the frozen authoritative recovery. There is no
cross-Object, cross-Run, first/latest, text/DOM, format-borrowing, or Demo fallback.

The access profile is exactly `phase4-local-single-user-trusted/v1`, with server scope
`LOCAL_SINGLE_USER`, no authentication provider, no client-asserted authority, and no invented
`userId`, `tenantId`, `workspaceId`, or `principalId`. Reserved auth errors remain in the frozen error
vocabulary for future profiles; normal Phase 4A operation does not manufacture account authority.

## Frozen normalized contracts — 13/13

### 1. `GlobalRunCollectionProjection`

- Schema: `phase4-run-collection/v1`; ordered `items`; opaque nullable `nextCursor`.
- Each item carries exact Run/Object identity, raw and normalized status, stage, terminal flag,
  timestamps, activity, revision/sequence, result Availability, and nullable pre-actual
  `graphVersion`.
- Progress is exactly `{method:ACTUAL_TASK_MEAN_V1, completedTasks, totalTasks, fraction, percent}`.
  Backend owns all except adapter-owned presentation `percent=fraction*100`.
- Identity: Object ID, Run ID, projection revision and sequence. Invalid item invalidates the
  response; no crawl/offset/latest fallback. Backend dependency: `BD-009`.

### 2. `PreparedResearchDraft`

- Schema: `phase4-run-draft/v1`; exact draft ID/version/hash, Object/Goal/Scheme, request hash,
  timestamps, `AWAITING_CONFIRMATION`, and `SCHEME_ONLY`.
- `plannedGraphAvailability` is required and initially
  `NOT_GENERATED/PLAN_CREATED_ON_CONFIRM/false`. Tasks and planned graph are absent.
- `mode` and `goalTemplateId` are absent from the normalized Backend business DTO. UI templates and
  FULL labels remain display/form state only. Backend dependency: `BD-007`.

### 3. `ConfirmRunResponseV1`

- Replaces the flat R1 `ConfirmAndStartResult` with `{schemaVersion, admission, responseMeta}`.
- Immutable admission includes schema/admission/Run/Object/draft/version/hash/Goal/Scheme/planned
  graph identity; raw/normalized `PLANNING`; `{autoStart:{required:true,admitted:true}}`;
  confirmation hash; admitted time; projection and event refs.
- Response metadata contains its schema version, nullable safe request ID, and replay boolean. Exact
  replay may change only response metadata; admission is byte/semantic-identical. Conflict returns
  no admission. Backend dependency: `BD-008`.

### 4. `RunProjection`

- Schema `phase4-run-projection/v1`; atomic revision/sequence/time watermark; exact Object, Run,
  Goal, confirmed Scheme, immutable planned graph, nullable pre-creation actual graph/version, exact
  Tasks, activity, path changes, lifecycle, terminal, and owned Availability refs.
- Lifecycle owns status, stage, method/counts/fraction progress, terminal, terminal outcome and safe
  failure. Adapter alone derives display percent.
- `PathChangeProjectionV1.changeKind` is exactly
  `SELF_CORRECTION|ADD_TASK|CHANGE_DEPENDENCY`; before/after graph versions are source-lifecycle
  nullable. Sparse events refresh the projection and never fabricate Tasks. Dependencies:
  `BD-001`, `BD-010`, `BD-012`.

### 5. `NormalizedRuntimeEventV1`

- `eventContractVersion=phase4-runtime-event/v1`; `payloadSchemaVersion=1`; exact event/Run/Task
  identity, timestamp and per-Run sequence; typed payload; always-present nullable `graphVersion`;
  frozen effect and refresh flag.
- The normative JSON lists all 55 raw names in exact manifest order. Exactly 47 are supported V1;
  the eight explicit unsupported values are `scheme.generation_started`, `replan.rejected`,
  `evidence.conflict`, `workspace.created`, `capability.generation_started`, `capability.tested`,
  `capability.validated`, and `review.required`.
- Unknown/unsupported/invalid events perform zero state mutation and cursor advance, then recover
  through an authoritative snapshot. Dependencies: `BD-002`, `BD-003`, `BD-012`.

### 6. `ConnectionState`

- Fetch-stream variants are exactly `IDLE`, `CONNECTING`, `OPEN`, `RECOVERING`, `BACKOFF`,
  `TERMINAL`, `FAILED`, each retaining exact Run and last committed sequence.
- Recovery reasons are `SEQUENCE_GAP|UNKNOWN_EVENT|SCHEMA_INCOMPATIBLE|CURSOR_REJECTED|
  PROJECTION_MISMATCH`; terminal outcomes are `SUCCESS|FAILURE|CANCELLED`.
- Snapshot-at-N then strict suffix; malformed/foreign cursor is 400 `INVALID_CURSOR`; ahead cursor
  is 409 `CURSOR_AHEAD`; both reload the snapshot before SSE headers. Connection state never mutates
  canonical Run lifecycle. Backend dependency: `BD-003`.

### 7. `FinancialReviewProjection`

- Schema `phase4-financial-review/v1`; exact watermarks, Object/Run, release pair, Review identity,
  reviewer, `inputSnapshotHash`, reviewed evidence/calculation/metric/claim/judgment refs, required
  proof calculations, Checks, and explicit Availability.
- Verdict is exactly `PASS|REVIEW|BLOCK|null`; `PASS_WITH_UNCERTAINTY` is absent. Review fields are
  null only when Review is absent. Check identity/code/status/subjects/expected/actual/detail and
  exception/correction timestamps are Backend truth. `RESOLVED` is exception history, not a verdict.
  Dependencies: `BD-006`, `BD-010`, `BD-011`.

### 8. `ClaimTraceProjection / TraceBundle`

- Schema `phase4-trace/v1`; watermarks; anchor manifest ID/hash; exact Object/Run/Claim/Metric/
  Calculation/canonical/result identities; typed Claim/metric; availability-wrapped lineage refs.
- Report contains exactly HTML and PDF representations, each with its own artifact identity,
  Availability and claim anchor. Review, Task and Execution anchors are plural; Execution anchor
  `eventRefs` retain Backend sequence order.
- No DOM/document-text inference, first/latest fallback, cross-format borrowing, or cross-Run join.
  Explicit durable Backend relation alone may populate `primaryTaskId`. Dependencies: `BD-004`,
  `BD-005`, `BD-006`, `BD-011`.

### 9. `ReportArtifactGroup`

- Schema `phase4-report-artifacts/v1`; exact Object/Run/report/canonical/result closure; release and
  artifact policy versions; anchor manifest ID/hash; group Availability; fixed `[HTML,PDF]` slots.
- HTML is required for release with `text/html; charset=utf-8`; PDF is optional with
  `application/pdf`. Every slot includes required flag, Availability, artifact/failure/attempt
  identity/count, hash, size, renderer, time, and nullable non-bearer same-origin `authorizedRef`.
- Policy-skipped PDF is `NOT_GENERATED/PDF_NOT_GENERATED_BY_POLICY/false` with null safe failure.
  Each byte GET rechecks identity, availability and integrity. Dependencies: `BD-004`, `BD-006`.

### 10. `ReleasedFinancialMetric`

- Required fields are Run/Metric/Calculation identity, name, canonical/display value and unit,
  period/basis/actuality/as-of/currency, formula/capability, evidence/claim refs, policy-bound Proof,
  method metadata, technical price basis, corporate-action status/guard refs, and limitations.
- All Decimal wire values remain strings and display strings are Backend-authored. Frontend numeric
  conversion, rounding, unit inference and method reconstruction are prohibited.
- `revenue_growth_v1=(current_revenue-prior_revenue)/prior_revenue`, preserving nonzero denominator
  sign. Every material formula uses an explicit local `ROUND_HALF_EVEN` context: precision 28 for
  fundamental ratios and MACD line/histogram subtraction, precision 50 for technical averaging and
  EMA recurrence. `capabilityVersion` is absent from the current public contract. Backend dependency:
  `BD-005`, `BD-010`.

### 11. `ReleasedObjectCoreProjection`

- Schema `phase4-released-object-core/v1`; projection revision/time, exact Object, current release
  Availability, release closure tuple, metrics, Claims, artifact group, and Object-owned Run
  history/count.
- No eligible release means the entire release tuple is null, arrays are empty, and Availability is
  `NOT_RELEASED/NO_RELEASED_RUN/false`. Available state requires a complete tuple.
- Only eligible RELEASED Runs may become latest; order is `releasedAt DESC, runId DESC bytewise`.
  Phase 5 memory/version/comparison/incremental/writeback fields are absent. Dependencies:
  `BD-001`, `BD-009`.

### 12. `ErrorEnvelope`

- Schema `phase4-error/v1`; safe message, code-bound retry/recovery, nullable safe request/resource
  context, allowlisted safe details.
- Codes are exactly: `INVALID_CURSOR`, `UNAUTHENTICATED`, `FORBIDDEN`, `NOT_FOUND`,
  `IDENTITY_MISMATCH`, `UNAVAILABLE`, `NOT_GENERATED`, `NOT_RELEASED`, `CONFLICT`, `CURSOR_AHEAD`,
  `SCHEMA_INCOMPATIBLE`, `UNSUPPORTED_EVENT`, `TERMINAL`, `REQUEST_VALIDATION_ERROR`,
  `INTEGRITY_FAILURE`, `INTERNAL_ERROR`, `TRANSIENT_BACKEND_ERROR`.
- The exact HTTP/retry/recovery table is normative in the JSON. Unknown/unsafe envelopes fail
  closed; raw bodies, provider content, prompts, hidden reasoning, secrets, stacks, SQL and internal
  paths are never exposed. Dependencies: `BD-003`, `BD-004`, `BD-008`.

### 13. `Availability`

- Exact fields: `status`, nullable `reasonCode`, `retryable`.
- Status is exactly `PENDING|AVAILABLE|NOT_GENERATED|NOT_RELEASED|UNAVAILABLE|FAILED`;
  `reasonCode` is null iff AVAILABLE. `PENDING` is nonterminal only.
- Backend authors every business-resource Availability. Null/missing/HTTP 200 never implies success.
  Dependencies: `BD-001`, `BD-004`, `BD-010`.

## BD and UAC disposition

| Records | Semantic state | Implementation evidence |
|---|---|---|
| `BD-001..012` | `CONTRACT_CLOSED` 12/12 | `PENDING` 12/12; no BD implementation PASS claimed |
| `UAC-003..018` | `CONTRACT_CLOSED` 16/16 | `PENDING` |
| `UAC-001` | `STILL_OPEN` | remediation and independent Backend + Financial Semantics PASS receipts required |
| `UAC-002` | `STILL_OPEN` | owner approval of this exact R2 hash required |

Missing routes are implementation work, not contract ambiguity. Both bound independent audits remain
`FAIL`; this package does not waive or relabel them.

## Interaction and Scene disposition

The current authoritative namespace remains `P4-E2E-001..106`; `015` remains the retired tombstone
and no existing ID changes. Interactions 071..076 and gates 107..112 remain reservations. If later
approved unchanged, 107/108 are `PHASE4_CORE_REQUIRED`; 109..112 use `source_class=DEMO` and
`result_class=DEMO_UX_ONLY` and never enter the real Phase 4 aggregate.

Real Scenes 01–04 are affected Phase 4 Core scope. Real Scenes 05–06 are excluded,
`PHASE5_ACTIVATED`, and currently `DEFINED_NOT_ACTIVATED`; their current relevance is compatibility
and isolated Demo regression only.

## Node 24 and FCR binding

The exact V8.1-only Node 24 evidence is SHA-256
`889a975aa39f6401cf06c5ba59e6d9256d8159c489a4861ed85db9562e3feca7`: Node `v24.18.0`, PASS.
It does not test or authorize a V17 Candidate; V17 Candidate toolchain acceptance is `NOT_RUN`.

This package binds FCR `FRONTEND_V17_PHASE4_CORE_INTEGRATION`, revision `DRAFT-02`, status
`DRAFT_CHANGE`, candidate SHA `PENDING`, implementation authorized `false`. Exact DRAFT-02 file
SHA-256: `1239b97b461415963d8bdbcc1ce5c2409e4e7b5ff0b47b0f0bfea90a5c9ac958`.
DRAFT-01 remains unchanged at SHA-256
`b20f2a0527638d057b1de62a6b154cdc8d50724d4aa75ee3491122fad3280df1`.

## Validation

```text
NORMALIZED_CONTRACTS=13/13
BD_RECORDS=12/12
UAC_MAPPED=18/18
FRONTEND_CONTRACT_CONFLICTS=0
UNMAPPED_FIELD_GROUPS=0
UNOWNED_BUSINESS_FIELDS=0
FRONTEND_FINANCIAL_AUTHORITY=0
CROSS_OBJECT_FALLBACK=0
CROSS_RUN_FALLBACK=0
RAW_ARTIFACT_PATH_EXPOSURE=0
HIDDEN_COT_EXPOSURE=0
PHASE5_LEAKAGE=0
PRODUCTION_SOURCE_MODIFIED=NO
```

## Approval state

```text
V17_CONTRACT_INPUT_R2_READY=YES
R1_STATUS=SUPERSEDED_BEFORE_OWNER_APPROVAL
R2_PACKAGE_SHA256=fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19
PHASE4_CONTRACT_SET_SHA256=0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741
NORMALIZED_CONTRACTS=13/13
BD_RECORDS=12/12
UAC_MAPPED=18/18
FRONTEND_CONTRACT_CONFLICTS=0
FCR_REVISION=DRAFT-02
FCR_STATUS=DRAFT_CHANGE
CONTRACT_INPUT_APPROVAL_READY=YES
OWNER_APPROVAL_REQUIRED=YES
FRONTEND_IMPLEMENTATION_AUTHORIZED=NO
FRONTEND_CANDIDATE_CREATED=NO
PHASE4_STARTED=NO
```
