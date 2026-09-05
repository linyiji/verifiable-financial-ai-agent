# Phase 4 Backend Acceptance Gate Catalog

Status: `PROVISIONAL_ACCEPTANCE_DESIGN — NOT EXECUTED`  
Namespace owner: Phase 4 Acceptance Coordinator  
Defined namespace: `P4-BE-001..030`  
Activation scope: `PHASE4_CORE_REQUIRED` for every gate in this catalog

This catalog defines the release-blocking backend-contract acceptance boundary. It does not add or
authorize routes, schemas, migrations, runtime behavior, or executable tests. The gate IDs are
stable: they may be clarified by an approved contract-freeze delta, but they must not be
renumbered, reused, or weakened.

## 1. Authority, candidate, and result rules

The design was reconciled against:

- the approved immutable frontend baseline `FRONTEND_BASELINE_V8.1` at
  `d854c97789c98cca14fee3f4b3d7f00e0d5d137a` and governance carrier
  `e2aef1edc22631dc988c862c18972f0fd7630625`;
- the authoritative append-only V8.1 deltas defining `P4-E2E-101..106` and retiring
  `P4-E2E-015` as a tombstone;
- the Phase 4 Backend freeze draft and its API schema, runtime-event,
  identity/error/availability, blocker-closure, and acceptance-mapping companions, all currently
  provisional / `NOT_FINAL` and inspected against
  `codex/phase3-contracts@11fe8173a25ff7ac08bae42340ba7c6fae591be5`;
- `V17_FRONTEND_CONTRACT_PREPARATION.md`, currently
  `PROVISIONAL_READY_BLOCKED_BY_BACKEND_CONTRACT`, with 13/13 named normalized frontend contracts
  prepared and nine unresolved frontend conflict clusters;
- `V17_FRONTEND_BACKEND_DEPENDENCY_MATRIX.md`, currently
  `PREPARATION_COMPLETE_BLOCKED`, with twelve open `BD-001..012` dependencies and no complete
  Phase 4 frontend contract classified as `BACKEND_CONTRACT_AVAILABLE`;
- the Phase 4 pre-audit, blocker register, frontend/backend mapping, E2E, SSE, identity, browser,
  and financial-semantics documents;
- the actual Phase 3 FastAPI, application service, PostgreSQL event store, record repositories,
  artifact publisher/store, integration tests, PostgreSQL tests, and acceptance runners.

An executable result must bind one clean Backend Phase 4 candidate SHA, its independently accepted
Phase 3 parent, database revision, route/event/schema versions, build/runtime environment, and the
same frontend candidate used by integrated browser evidence. The current dirty/moving repository
and draft schema are design evidence only.

For an activated gate the only final outcomes are `PASS` and `FAIL`. `NOT_IMPLEMENTED` may describe
current preparation status but is not a release outcome. `DEFINED_NOT_ACTIVATED` applies only to a
future activation scope and does not apply to these thirty Core gates. A Demo or frontend-fixture
result cannot satisfy a `P4-BE` gate. Deterministic contract/integration executions use
`INTEGRATED` or `OFFLINE_INTEGRATED`; real-network repetitions retain `PUBLIC_REAL` or
`LIMITED_REAL`; stream fault cases retain `CHAOS_SSE`.

Unless a gate narrows it, the current Phase 3 error oracle is a non-2xx response shaped as
`{"error":{"code":<stable code>,"message":<safe text>,"details":{},"request_id":<id|null>}}`.
V17 preparation proposes a versioned `phase4-error/v1` envelope adding retryability, recovery, and
safe resource context. That proposal is an integration requirement, not a frozen backend contract;
the final envelope and total HTTP/SSE mapping remain `UAC-018`.
No error may disclose another tenant's existence, an internal path, raw provider content, a secret,
or hidden reasoning. Authorization-before-disclosure, exact Object/Run ownership, and absence of
fallback-to-latest/first/title/symbol/metric-name are universal.

## 2. Gate index and blocker closure

| Gate | Contract under acceptance | Current implementation status | Primary blockers |
|---|---|---|---|
| `P4-BE-001` | Global Run collection | `NOT_IMPLEMENTED` | `P4-CB-009`, `P4-CB-010` |
| `P4-BE-002` | Prepare draft identity | `NOT_IMPLEMENTED` as frozen V1 | `P4-CB-007` |
| `P4-BE-003` | Prepare Scheme semantics | `NOT_IMPLEMENTED` as frozen V1 | `P4-CB-007` |
| `P4-BE-004` | Durable confirm idempotency | `NOT_IMPLEMENTED` | `P4-CB-008` |
| `P4-BE-005` | Exactly-one Run creation | `NOT_IMPLEMENTED` | `P4-CB-008` |
| `P4-BE-006` | Runtime auto-start | `NOT_IMPLEMENTED` durably | `P4-CB-003`, `P4-CB-008` |
| `P4-BE-007` | Atomic RunProjection | `NOT_IMPLEMENTED` | `P4-CB-001` |
| `P4-BE-008` | Projection sequence | `NOT_IMPLEMENTED` atomically | `P4-CB-001`, `P4-CB-003` |
| `P4-BE-009` | Projection revision | `NOT_IMPLEMENTED` | `P4-CB-001` |
| `P4-BE-010` | Run list/detail consistency | `NOT_IMPLEMENTED` as V1 projections | `P4-CB-009`, `P4-CB-010` |
| `P4-BE-011` | Numeric cursor replay | Partially present; acceptance not executed | `P4-CB-003` |
| `P4-BE-012` | Opaque cursor replay | Partially present; acceptance not executed | `P4-CB-003` |
| `P4-BE-013` | Invalid cursor rejection | Partially present; HTTP behavior not frozen | `P4-CB-003` |
| `P4-BE-014` | Cursor-ahead rejection | `NOT_IMPLEMENTED` | `P4-CB-003` |
| `P4-BE-015` | Terminal success | Partially present; closure proof missing | `P4-CB-003` |
| `P4-BE-016` | Terminal failure | Partially present; all-path proof missing | `P4-CB-003` |
| `P4-BE-017` | PostgreSQL restart replay | Primitive exists; Phase 4 contract not accepted | `P4-CB-003`, `P4-CB-008` |
| `P4-BE-018` | Event normalization | `NOT_IMPLEMENTED` as versioned public map | `P4-CB-002`, `P4-CB-010` |
| `P4-BE-019` | Sparse graph-event recovery | `NOT_IMPLEMENTED` | `P4-CB-001`, `P4-CB-012` |
| `P4-BE-020` | Lossless financial metric | Domain primitive exists; projection absent | `P4-CB-005` |
| `P4-BE-021` | Ratio/percentage semantics | Domain primitive exists; E2E projection absent | `P4-CB-005` |
| `P4-BE-022` | Claim detail | `NOT_IMPLEMENTED` | `P4-CB-005`, `P4-CB-006` |
| `P4-BE-023` | Review/check projection | `NOT_IMPLEMENTED` as required V1 | `P4-CB-010`, `P4-CB-011` |
| `P4-BE-024` | Claim Trace closure | `NOT_IMPLEMENTED` | `P4-CB-006` |
| `P4-BE-025` | Artifact metadata | `NOT_IMPLEMENTED` as public group | `P4-CB-004` |
| `P4-BE-026` | Artifact authorized content | `NOT_IMPLEMENTED` | `P4-CB-004` |
| `P4-BE-027` | Artifact integrity | Internal checks exist; public delivery absent | `P4-CB-004` |
| `P4-BE-028` | Released Object Core | `NOT_IMPLEMENTED` | `P4-CB-005`, `P4-CB-006`, `P4-CB-009` |
| `P4-BE-029` | `latest_released_run_id` | `NOT_IMPLEMENTED` | `P4-CB-009` |
| `P4-BE-030` | Cross-object rejection | Partial repository guards; route closure absent | `P4-CB-004`, `P4-CB-006` |

All twelve `P4-CB-001..012` blockers therefore have one or more acceptance owners. A passing
domain-model test alone closes none of them.

The later V17 preparation expresses the same unresolved surface as twelve frontend dependency
records. The following crosswalk prevents the alternate IDs from creating duplicate acceptance
gates:

| V17 dependency | Existing backend acceptance owner(s) |
|---|---|
| `BD-001` coherent Run projection/watermark | `P4-BE-007..009`, `017`, `019`, `028` |
| `BD-002` raw-event normalization | `P4-BE-018` |
| `BD-003` browser SSE protocol | `P4-BE-008`, `011..017` |
| `BD-004` artifact group/delivery | `P4-BE-024..027`, `030` |
| `BD-005` lossless metric/Claim | `P4-BE-020..022`, `028` |
| `BD-006` Claim Trace/anchors | `P4-BE-022`, `024`, `030` |
| `BD-007` prepare boundary | `P4-BE-002..003` |
| `BD-008` confirm/auto-start | `P4-BE-004..006`, `017` |
| `BD-009` global Run collection | `P4-BE-001`, `010`, `028..029` |
| `BD-010` total enum maps | `P4-BE-001`, `007`, `010`, `018`, `023` |
| `BD-011` Financial Review projection | `P4-BE-023..024` |
| `BD-012` graph mutation semantics | `P4-BE-018..019` |

All `BD-001..012` records are therefore covered without extending the `P4-BE-001..030` namespace.

The Backend draft's `P4-BC-001..018` labels are proposed contract cases, not coordinator-owned
acceptance gates. Their positive and negative variants are absorbed into the thirty stable gates
and the seven-variant matrix in this package. They must not appear as a second result namespace,
change the `P4-BE` denominator, or independently declare release PASS.

## 3. Full gate contracts

### P4-BE-001 — Global Run collection

- **gate_id:** `P4-BE-001`; **title:** Global Run collection.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** `GET /api/research-runs` → `ResearchRunCollectionV1`, backend draft §4;
  `P4-CB-009`; E2E Run-collection contract.
- **preconditions:** Authenticated actor can read Object A; corpus contains multiple A/B Runs with
  equal timestamps, different statuses, and released/nonreleased result states.
- **setup:** Persist at least 26 Runs; record canonical ordering tuples and normalized filters;
  retain one unauthorized Object B.
- **action/request:** Page with `limit=25`, then use `next_cursor`; repeat `object_id`, `status`, and
  `result_availability` filters without changing the cursor-bound filter set.
- **expected response:** JSON schema `phase4-run-collection/v1`; stable order
  `(updated_at DESC, run_id DESC)`; exact Object summary, raw status, mapped stage, progress ratio
  and `ACTUAL_TASK_MEAN_V1` method, activity, graph/revision/sequence, timestamps, availability, and
  opaque `next_cursor`. Whether percent is also carried on the backend wire or derived once in the
  V17 adapter must follow the resolution of `UAC-008`; pages never derive canonical Run progress.
- **expected persistence:** Read-only; Run/event/release rows and cursor state are unchanged. Cursor
  validity is reproducible against the frozen collection protocol.
- **identity assertions:** Every item resolves `run_id → object.object_id`; B items never appear in
  A-scoped results; `P4-ID-001`, `006`, `025..027`.
- **negative variant:** Reuse a valid cursor with changed filters, a malformed cursor, and an
  unauthorized Object filter; no offset fallback or Object-route crawl.
- **error behavior:** `INVALID_CURSOR` for cursor failures; authorization policy returns its frozen
  concealed-not-found or forbidden error; unknown enum/version fails `SCHEMA_INCOMPATIBLE`.
- **restart behavior if applicable:** After backend restart, the same immutable dataset and cursor
  yield the same suffix; no in-memory-only ordering state.
- **evidence retained:** Requests/responses, normalized filters, decoded test-side ordering tuples,
  row identity ledger, database before/after counts, schema hash.
- **mapped P4-E2E IDs:** `002`, `005..007`, `076`, `105`; **mapped P4-SSE IDs:** none;
  **mapped P4-ID IDs:** `001`, `006`, `025..027`.
- **PASS condition:** All positive, pagination, identity, authorization, missing-data, version, and
  restart variants meet the exact oracle with zero mutation.
- **FAIL condition:** Any omission is represented as success data, order/page membership changes,
  filters detach from the cursor, identity leaks, or a fallback/guess is used.

### P4-BE-002 — Prepare draft identity

- **gate_id:** `P4-BE-002`; **title:** Prepare draft identity.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** `POST /api/research-runs/prepare` → `ResearchRunDraftV1`, backend draft §5;
  `P4-CB-007`.
- **preconditions:** Authorized Object A exists; `FULL` mode and a deterministic Scheme generator
  are available; no Run has yet been created.
- **setup:** Capture A plus distinct Object B, exact goal/as-of/preferences, prepare idempotency keys
  K1/K2, and database counts for drafts, Goals, Schemes, graphs, Tasks, and Runs.
- **action/request:** Submit the V1 prepare body for A with K1; retry the identical request with K1;
  then request intentional regeneration with new key K2 and the same body.
- **expected response:** The first K1 request returns a new non-empty `draft_id`, `draft_version=1`,
  `status=AWAITING_CONFIRMATION`, `preview_kind=SCHEME_ONLY`, exact A/FULL/Goal identity, request
  hash, creation and expiry; the K1 retry replays that draft, while K2 returns a distinct draft.
- **expected persistence:** One durable prepare outcome, draft, Goal, and unconfirmed Scheme per
  distinct request-bound key; retry creates no duplicate; zero Run, planned graph, and Task rows.
- **identity assertions:** Goal and Scheme resolve to A and each other; `P4-ID-002..003`.
- **negative variant:** Reuse K1 with a changed request hash; use Object B's identifier in a
  route/body context authenticated only for A; omit the object; and attempt symbol/name fallback.
- **error behavior:** Same-key/different-request returns `CONFLICT`; authorization/not-found and
  validation failures are safe; `INCREMENTAL` fails closed and is never coerced; no partial draft
  remains after failure.
- **restart behavior if applicable:** Restart preserves the K1 outcome, draft identity, version,
  expiry, hash, Goal, and Scheme; identical K1 retry still returns the same draft until the frozen
  expiry/consumption rule applies.
- **evidence retained:** Keys as redaction-safe digests, request/response and replay ledger,
  draft/Goal/Scheme/outcome rows, hashes, before/after cardinalities, auth principal, restart read.
- **mapped P4-E2E IDs:** `017..024`, `074`, `102`; **mapped P4-SSE IDs:** none;
  **mapped P4-ID IDs:** `002..003`.
- **PASS condition:** Exact identity and persistence invariants hold; K1 replay is duplicate-free;
  K2 regeneration creates a distinct immutable draft; and no Run/Task/graph exists.
- **FAIL condition:** Same-key replay creates a draft, new-key regeneration reuses or mutates the old
  draft, ownership is inferred, planned Tasks appear at prepare, or failure leaves partial state.

### P4-BE-003 — Prepare Scheme semantics

- **gate_id:** `P4-BE-003`; **title:** Prepare Scheme semantics.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** `ResearchRunDraftV1.scheme_snapshot`, backend draft §5.2; `P4-CB-007`.
- **preconditions:** Same corpus as `P4-BE-002`; generator output has all required Scheme sections.
- **setup:** Freeze the returned Scheme source facts and the canonical prepare body/hash.
- **action/request:** Prepare FULL research, inspect every Scheme field, then regenerate using a new
  prepare idempotency key.
- **expected response:** `SCHEME_ONLY` preview preserves Scheme/Goal/Object IDs, requirements,
  limitations, generator metadata, and `confirmed_at=null`; it contains no invented Task graph.
- **expected persistence:** Immutable first Scheme; a new draft/Scheme identity for regeneration;
  no confirmation timestamp before confirm.
- **identity assertions:** Scheme Object and Goal IDs equal the draft Goal and A; no latest-Scheme
  lookup; `P4-ID-002..003`.
- **negative variant:** Missing generator output or an object/goal-mismatched Scheme fails the whole
  request and is not replaced with frontend/Demo defaults.
- **error behavior:** Typed failed/unavailable or safe 5xx contract error, as frozen; never 2xx with
  empty requirements masquerading as a generated Scheme.
- **restart behavior if applicable:** Stored Scheme bytes/semantic hash and `confirmed_at=null`
  survive restart unchanged.
- **evidence retained:** Scheme JSON/hash, generator audit reference without hidden reasoning,
  persistence snapshot, regeneration identity comparison.
- **mapped P4-E2E IDs:** `021..024`, `074`, `102`; **mapped P4-SSE IDs:** none;
  **mapped P4-ID IDs:** `002..003`.
- **PASS condition:** Scheme is an honest immutable backend projection with exact ownership and
  explicit missing/failure states.
- **FAIL condition:** It contains fabricated Tasks, mismatched IDs, mutable regeneration, premature
  confirmation, or silent generator fallback.

### P4-BE-004 — Durable confirm idempotency

- **gate_id:** `P4-BE-004`; **title:** Durable confirm idempotency.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** Confirm/admission draft §5.3; `P4-CB-008`.
- **preconditions:** Unconsumed unexpired draft A/v1 and authenticated actor/tenant; PostgreSQL is
  the target store.
- **setup:** Generate key K and canonical request hash H; capture all admission-related counts.
- **action/request:** Confirm with K/H, simulate response loss, retry K/H before and after backend
  restart; also issue K with changed draft/body/actor.
- **expected response:** First HTTP 201 admission for Run R; same K/H retry HTTP 200 for the same R
  and immutable admission fields with replay indicated; changed hash is rejected.
- **expected persistence:** One durable `(actor,tenant,method,route,key,H)` outcome bound to one
  consumed draft and one Run; no process-local-only authority.
- **identity assertions:** Outcome retains exact draft/Object/Goal/Scheme/Run; `P4-ID-004`, `005`,
  `023`, `026..027`.
- **negative variant:** Same key/different hash, same draft/different key, expired draft, and wrong
  draft version all create zero additional Runs.
- **error behavior:** `CONFLICT` with safe reason `DRAFT_CONSUMED`, `DRAFT_EXPIRED`, or
  `DRAFT_VERSION_MISMATCH` as applicable; hash mismatch uses the frozen conflict reason.
- **restart behavior if applicable:** Restart retry returns the original outcome and R; retained
  evidence proves no new admission.
- **evidence retained:** Raw request canonicalization, H/K redaction-safe digest, responses,
  admission/draft/Run/outbox counts, transaction and restart ledger.
- **mapped P4-E2E IDs:** `025`, `075`, `098`; **mapped P4-SSE IDs:** none;
  **mapped P4-ID IDs:** `004..005`, `023`, `026..027`.
- **PASS condition:** Every same-request retry converges on one durable outcome and every changed
  request fails without mutation.
- **FAIL condition:** A restart loses the result, key reuse is unbound, response identity changes,
  or any conflict creates/mutates a Run.

### P4-BE-005 — Exactly-one Run creation

- **gate_id:** `P4-BE-005`; **title:** Exactly-one Run creation.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** Confirm transaction and `RunAdmissionV1`, draft §5.3; `P4-CB-008`.
- **preconditions:** Same draft/idempotency fixture as `P4-BE-004`.
- **setup:** Instrument database cardinalities and durable events/admission records.
- **action/request:** Race two identical confirmations, inject a commit-boundary response failure,
  and retry.
- **expected response:** Exactly one R with A/Goal/Scheme/planned graph, `status=PLANNING`,
  `auto_start=true`, stable projection/events refs.
- **expected persistence:** One transaction consumes the draft, freezes Goal/Scheme, creates one
  planned graph and Task set, one Run, one request outcome, initial events, and one scheduler
  admission/outbox. Rollback leaves none of them.
- **identity assertions:** All created rows/events own R/A; `P4-ID-004..005`, `007..009`.
- **negative variant:** Concurrent different keys for the same draft; only one wins and the other
  returns `DRAFT_CONSUMED`.
- **error behavior:** Conflict or safe transactional failure, never a second success identity or a
  partially visible aggregate.
- **restart behavior if applicable:** Counts and identities remain exactly one after restart and
  redelivery.
- **evidence retained:** Serializable transaction trace, row/event cardinalities, response ledger,
  injected-failure point, restart counts.
- **mapped P4-E2E IDs:** `025`, `075`; **mapped P4-SSE IDs:** `002`, `004`;
  **mapped P4-ID IDs:** `004..005`, `007..009`.
- **PASS condition:** Exactly one complete aggregate and admission exist at every observable commit.
- **FAIL condition:** Duplicate Run/start/event, partial aggregate, lost outcome, or changed identity.

### P4-BE-006 — Runtime auto-start

- **gate_id:** `P4-BE-006`; **title:** Runtime auto-start.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** `RunAdmissionV1.auto_start`, draft §5.3; terminal/event contracts;
  `P4-CB-003`, `008`.
- **preconditions:** Successful confirmation and a durable scheduler worker.
- **setup:** Record R, admission/outbox key, initial sequence, scheduler deliveries, and Run state.
- **action/request:** Do not send an execute request; permit delivery, redeliver it, and restart the
  API/worker across the admission boundary.
- **expected response:** Admission says `auto_start=true`; projection/event log advances from
  PLANNING under backend authority without a second user action.
- **expected persistence:** One logical start for R, one state transition and start timestamp, one
  durable `run.started`; delivery may repeat but effects do not.
- **identity assertions:** Scheduler key, Run, graph, Tasks, and events all retain R/A;
  `P4-ID-004`, `008..010`.
- **negative variant:** Wrong-Run admission, already-started redelivery, and unauthorized forged
  execute-like request cause no second start.
- **error behavior:** Invalid admission is quarantined/fails safely; runtime failure emits the
  durable failure terminal required by `P4-BE-016`.
- **restart behavior if applicable:** Pending committed admission starts after restart; completed
  admission is not executed again.
- **evidence retained:** Outbox/admission rows, worker delivery ledger, Run/events before/after,
  start cardinality and restart trace.
- **mapped P4-E2E IDs:** `025..026`, `075`; **mapped P4-SSE IDs:** `002`, `004`, `015..017`;
  **mapped P4-ID IDs:** `004`, `008..010`, `023`.
- **PASS condition:** Confirmation alone causes one durable logical start and restart/redelivery is
  idempotent.
- **FAIL condition:** An execute click is required, a committed admission is lost, or duplicate
  execution/start/event occurs.

### P4-BE-007 — Atomic RunProjection

- **gate_id:** `P4-BE-007`; **title:** Atomic RunProjection.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** `GET /api/research-runs/{run_id}/projection` →
  `AtomicRunProjectionV1`, draft §6; V17 prepared `RunProjection`; `P4-CB-001`.
- **preconditions:** Authorized live and released Runs with graphs, Tasks, events, and optional
  review/result/proof/artifact/execution records.
- **setup:** Pause writes at controlled transaction boundaries and capture the database commit
  truth for R/A.
- **action/request:** Read projection while commits occur; repeat with `If-None-Match` where frozen.
- **expected response:** One transactionally consistent DTO with exact Object/Run/Goal/Scheme,
  immutable planned graph, actual graph, Tasks/activity, lifecycle, typed availability summaries,
  and the exact mutation-history/`pathChanges` representation selected at freeze, plus
  revision/sequence/generated time and ETag
  `"p4:<run_id>:<projection_revision>:<projection_sequence>"`.
- **expected persistence:** Read-only; no event or revision is created by a GET.
- **identity assertions:** Every nested ID validates against R then A; `P4-ID-001`, `004`,
  `007..020`, `025..027`.
- **negative variant:** Seed one cross-Run nested record and one event-consistency tear; serializer
  rejects/quarantines rather than returning a mixed 200 snapshot.
- **error behavior:** Safe identity/integrity/schema error; missing optional domains use
  `AvailabilityV1`, not guessed empty success.
- **restart behavior if applicable:** Reopened projection reconstructs from durable records with
  the same terminal identities and nondecreasing revision/sequence.
- **evidence retained:** HTTP body/ETag, transaction snapshot identifier, database oracle,
  projection diff, auth/identity ledger, restart response.
- **mapped P4-E2E IDs:** `026..036`, `077`, `087..089`, `098`, `105`;
  **mapped P4-SSE IDs:** `012..014`, `017`, `020`; **mapped P4-ID IDs:** `001`, `004`,
  `007..020`, `023`, `025..027`.
- **PASS condition:** Every successful DTO is atomic, complete for its availability states,
  identity-closed, and event-consistent.
- **FAIL condition:** Any torn/mixed snapshot, speculative Task, fallback ID, GET mutation, or
  unversioned response is observed.

### P4-BE-008 — Projection sequence

- **gate_id:** `P4-BE-008`; **title:** Projection sequence watermark.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** shared watermark rules and `AtomicRunProjectionV1`, draft §§2.2/6;
  `P4-CB-001`, `003`.
- **preconditions:** Durable contiguous event log for R and projection-affecting aggregate commits.
- **setup:** Create events immediately before/during/after a snapshot transaction.
- **action/request:** Fetch snapshots and replay `Last-Event-ID: projection_sequence`.
- **expected response:** Integer `projection_sequence>=0` equals the greatest durable event whose
  reflected aggregate mutation is included; replay begins strictly after it.
- **expected persistence:** Watermark and reflected mutation become visible atomically; GET does not
  advance either.
- **identity assertions:** Watermark is scoped to R and cannot be resolved using R-B;
  `P4-ID-009`, `023`, `026`.
- **negative variant:** Force an event row without the reflected aggregate state or supply B's
  sequence; no inconsistent snapshot is returned.
- **error behavior:** Safe integrity/reconciliation failure, never timestamp-based approximation.
- **restart behavior if applicable:** Watermark and replay suffix survive PostgreSQL/API restart.
- **evidence retained:** Commit/event ledger, snapshots, replay frames, sequence equality proof,
  database transaction trace.
- **mapped P4-E2E IDs:** `077`, `079`, `081`, `083`, `087..088`;
  **mapped P4-SSE IDs:** `002`, `004`, `007`, `009`, `012..013`;
  **mapped P4-ID IDs:** `009`, `023`, `026`.
- **PASS condition:** No commit-window event is lost or double-applied and the watermark is exact.
- **FAIL condition:** Sequence is ahead/behind reflected state, cross-Run, timestamp-derived, or
  changed by a read.

### P4-BE-009 — Projection revision

- **gate_id:** `P4-BE-009`; **title:** Projection revision.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** shared revision rules, draft §2.2; `P4-CB-001`.
- **preconditions:** R exists with controlled projection-affecting and non-affecting transactions.
- **setup:** Record revision at creation and enumerate the frozen mutation set.
- **action/request:** Commit each mutation once, retry it, perform pure reads, and compare revisions.
- **expected response:** Integer `>=1`, monotonic per R, incremented once per committed
  projection-affecting transaction; ETag carries the same revision.
- **expected persistence:** Revision is durable and transactional; rollback/read/retry-without-change
  does not increment it.
- **identity assertions:** Revision is Run-scoped; R-B cannot satisfy R-A; `P4-ID-006`, `023`, `026`.
- **negative variant:** Unknown revision/version, rollback, duplicate delivery, and cross-Run ETag
  never yield a false not-modified or accepted snapshot.
- **error behavior:** Invalid conditional/version request fails closed under the frozen negotiation
  contract.
- **restart behavior if applicable:** Restart preserves the last revision and monotonic next value.
- **evidence retained:** Mutation/revision ledger, transaction outcomes, ETags, restart values.
- **mapped P4-E2E IDs:** `076..077`, `088`, `098`; **mapped P4-SSE IDs:** `012..013`;
  **mapped P4-ID IDs:** `006`, `023`, `026`.
- **PASS condition:** Exact one-increment semantics hold for the reviewed mutation set.
- **FAIL condition:** Revision regresses, skips due to non-atomic writes, changes on GET, or collides
  across Runs.

### P4-BE-010 — Run list/detail consistency

- **gate_id:** `P4-BE-010`; **title:** Run list/detail consistency.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** `ResearchRunCollectionV1`, `ResearchRunDetailV1`, and projection draft
  §§3/4/6; `P4-CB-009`, `010`.
- **preconditions:** A live R and a terminal success/failure R exist.
- **setup:** Capture collection row revision/sequence and exact detail/projection reads.
- **action/request:** Read list then detail at a consistent revision; repeat after terminal commit
  and restart.
- **expected response:** Run/Object/status/as-of/timestamps, lifecycle, graph version,
  revision/sequence and result availability agree; normalized stage/progress are from the same map.
- **expected persistence:** Read-only; terminal update is one durable authoritative state change.
- **identity assertions:** Exact row R opens detail R, never latest; `P4-ID-001`, `004`, `006`,
  `023`, `025..027`.
- **negative variant:** Request R-B from A context and a historical R while a newer R exists.
- **error behavior:** Reject mixed ownership; missing row/detail is unavailable/not-found without
  substituting latest.
- **restart behavior if applicable:** Same terminal identity/status and availability appear after
  restart.
- **evidence retained:** Timestamped list/detail/projection bodies, revision alignment, identity and
  restart diffs.
- **mapped P4-E2E IDs:** `002`, `005..007`, `060..061`, `076`, `098`, `105`;
  **mapped P4-SSE IDs:** `013`, `017`; **mapped P4-ID IDs:** `001`, `004`, `006`, `023`,
  `025..027`.
- **PASS condition:** Comparable reads agree exactly or declare their different revisions and
  reconcile deterministically.
- **FAIL condition:** Same-revision disagreement, stale terminal state, latest substitution, or
  fabricated status/progress occurs.

### P4-BE-011 — Numeric cursor replay

- **gate_id:** `P4-BE-011`; **title:** Numeric cursor replay.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** SSE draft route and frozen SSE acceptance §§1/6.
- **preconditions:** R has durable contiguous events `1..M`; caller is authorized.
- **setup:** Select committed nonterminal N with `0<=N<M`.
- **action/request:** `GET .../events` with `Accept: text/event-stream` and
  `Last-Event-ID: <N>`.
- **expected response:** Actual SSE; first business frame N+1; exact suffix through terminal; wire
  `id==data.sequence`, `event==data.type`.
- **expected persistence:** Replay is read-only and does not duplicate/resequence rows.
- **identity assertions:** Every frame owns R and valid Task; `P4-ID-009`, `026`.
- **negative variant:** Use R-B cursor/event sequence against R-A and wrong media type.
- **error behavior:** Authorization/media/schema errors occur before business frames; no replay from
  zero on invalid input.
- **restart behavior if applicable:** Same suffix and hashes after PostgreSQL/API restart.
- **evidence retained:** Request headers, raw/parsed frames, database event range/hash, row counts.
- **mapped P4-E2E IDs:** `068`, `078..079`, `081`, `083`, `098`;
  **mapped P4-SSE IDs:** `001..004`, `006..009`, `017`;
  **mapped P4-ID IDs:** `009`, `023`, `026`.
- **PASS condition:** Returned suffix is exactly persisted events with sequence `>N`.
- **FAIL condition:** Missing/extra/resequenced frames, wrong Run, wrong media, or mutation occurs.

### P4-BE-012 — Opaque cursor replay

- **gate_id:** `P4-BE-012`; **title:** Opaque event-id cursor replay.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** frozen SSE acceptance §§1/6.
- **preconditions:** R has a captured opaque `event_id` E at sequence N.
- **setup:** Retain numeric-control suffix and E/R binding.
- **action/request:** Stream R with `Last-Event-ID: E`.
- **expected response:** Byte/semantic suffix equals numeric N replay, beginning N+1; E is never
  parsed as a global cursor.
- **expected persistence:** Read-only exact lookup within R.
- **identity assertions:** E resolves only within its owning R; `P4-ID-009`, `026..027`.
- **negative variant:** Use E from R-B or unknown E against R-A.
- **error behavior:** Safe invalid-cursor error; no global scan, cross-Run resolution, or replay zero.
- **restart behavior if applicable:** Opaque mapping and suffix survive restart.
- **evidence retained:** Both requests, suffix equality diff, E/R database lookup, frame hashes.
- **mapped P4-E2E IDs:** `080..081`, `098`; **mapped P4-SSE IDs:** `008..009`, `017..018`;
  **mapped P4-ID IDs:** `009`, `023`, `026..027`.
- **PASS condition:** Opaque and numeric cursors identify exactly the same Run-local position.
- **FAIL condition:** Mapping changes, crosses Runs, falls back, or returns a different suffix.

### P4-BE-013 — Invalid cursor

- **gate_id:** `P4-BE-013`; **title:** Invalid cursor rejection.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** provisional SSE bad-cursor rule; draft authorization/negotiation §11.
- **preconditions:** Authorized R exists and has events.
- **setup:** Prepare negative integer, malformed numeric, unknown opaque, blank/oversized token, and
  other-Run opaque cursors.
- **action/request:** Request SSE once per invalid cursor.
- **expected response:** Safe non-2xx typed error before SSE business data.
- **expected persistence:** Zero event/Run/projection mutation.
- **identity assertions:** Resolution is R-scoped; `P4-ID-009`, `026..027`.
- **negative variant:** Every invalid family above, including authorization denial.
- **error behavior:** Frozen `INVALID_CURSOR` (or its final reviewed SSE-specific equivalent); never
  replay from zero or heartbeat forever.
- **restart behavior if applicable:** Same error class/disclosure after restart.
- **evidence retained:** Requests, status/error bodies, proof of zero frames and zero database delta.
- **mapped P4-E2E IDs:** `073`, `079..080`; **mapped P4-SSE IDs:** `018`;
  **mapped P4-ID IDs:** `009`, `026..027`.
- **PASS condition:** Every invalid cursor fails closed identically under the frozen policy.
- **FAIL condition:** Any data frame, fallback, cross-Run lookup, hang, or mutation occurs.

### P4-BE-014 — Cursor ahead

- **gate_id:** `P4-BE-014`; **title:** Cursor-ahead rejection.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** coordinator-required cursor-ahead case and the acceptance-package
  `P4-SSE-018` ahead variant; this gate owns its Backend oracle.
- **preconditions:** R's durable maximum sequence is M.
- **setup:** Choose numeric `M+1` and a large valid integer; capture terminal/nonterminal variants.
- **action/request:** Stream with the ahead cursor.
- **expected response:** Provisional oracle is HTTP 409 with code `CURSOR_AHEAD`, returned before
  SSE headers/business frames; execution waits for that status/envelope to be finally frozen.
- **expected persistence:** Zero mutation and no cursor registration.
- **identity assertions:** Maximum is computed for exact R; `P4-ID-009`, `026..027`.
- **negative variant:** Apply R-B's higher valid numeric cursor to R-A.
- **error behavior:** Never wait in heartbeat loop and never treat the cursor as an empty valid
  suffix. The provisional event draft proposes `409 CURSOR_AHEAD`; its final status/envelope and
  implementation remain freeze conflict `UAC-004`.
- **restart behavior if applicable:** Same rejection after restart.
- **evidence retained:** Max-sequence query, headers, timing-bounded response, zero-frame proof.
- **mapped P4-E2E IDs:** `079`, `081`, `084`; **mapped P4-SSE IDs:** `018` ahead variant;
  **mapped P4-ID IDs:** `009`, `026..027`.
- **PASS condition:** Final frozen ahead-cursor contract rejects promptly and consistently.
- **FAIL condition:** HTTP 200 heartbeat wait, replay-zero, cross-Run use, or ambiguous timeout.

### P4-BE-015 — Terminal success

- **gate_id:** `P4-BE-015`; **title:** Successful terminal contract.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** status map draft §2.3, release rules, frozen SSE terminal acceptance.
- **preconditions:** R can satisfy canonical/review/proof/material-output/artifact release closure.
- **setup:** Capture all preterminal records and SSE frames.
- **action/request:** Execute through release and reopen projection/result/stream.
- **expected response:** Exactly one `release.completed` precedes exactly one `run.completed`;
  stream closes after terminal; final projection is `RELEASED/COMPLETE`, terminal success, and only
  then result availability is AVAILABLE.
- **expected persistence:** Run, terminal event, released result, canonical, valid Review, required
  Proof, and artifact states commit durably with exact refs.
- **identity assertions:** All terminal/release refs own R/A/X; `P4-ID-009`, `013..020`, `023`.
- **negative variant:** Remove/block one release prerequisite; success terminal and released result
  must not appear.
- **error behavior:** Failed release follows `P4-BE-016`; no structurally present but semantically
  unavailable report passes.
- **restart behavior if applicable:** Terminal reopen returns history/cursor/result and closes or
  completes without reconnect loop.
- **evidence retained:** Ordered frame ledger, release-gate inputs, rows/hashes, final projection,
  stream-close and restart trace.
- **mapped P4-E2E IDs:** `085`, `092..096`, `098`; **mapped P4-SSE IDs:** `015`, `017`;
  **mapped P4-ID IDs:** `009`, `013..020`, `023`.
- **PASS condition:** One durable, correctly ordered, semantically valid success closure is proven.
- **FAIL condition:** Premature/duplicate/missing terminal, release without prerequisites, or reopen
  divergence.

### P4-BE-016 — Terminal failure

- **gate_id:** `P4-BE-016`; **title:** Failure terminal contract.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** status map draft §2.3 and frozen SSE failure-terminal acceptance;
  `P4-CB-003`.
- **preconditions:** Controlled failure can be injected at planning, execution, assurance, proving,
  artifact, and post-scheduler release boundaries without fabricating business frames.
- **setup:** One fresh R per terminal path; capture database and SSE.
- **action/request:** Trigger each real failure path and read final stream/projection/result.
- **expected response:** Exactly one final `run.failed`, stream closes, projection is terminal FAILED
  with safe reason, and released Results/A/B/C/downloads are unavailable.
- **expected persistence:** Failure state/event/reason are durable; no released-result row or
  invalid partial release is exposed.
- **identity assertions:** Failure and any retained audit records own exact R/A; `P4-ID-009`, `023`,
  `025..027`.
- **negative variant:** Simulate failure after scheduler return and duplicate failure delivery.
- **error behavior:** Result/detail uses typed unavailable/error; no Demo success tail or leaked
  exception/secret.
- **restart behavior if applicable:** Reopen remains FAILED, returns the same terminal cursor, and
  does not resume or reconnect forever.
- **evidence retained:** Failure injection point, sanitized logs, row/frame cardinality, final
  responses, restart trace.
- **mapped P4-E2E IDs:** `086`, `098`, `105`; **mapped P4-SSE IDs:** `016..017`;
  **mapped P4-ID IDs:** `009`, `023`, `025..027`.
- **PASS condition:** Every reviewed terminal failure path emits/persists one failure terminal and
  exposes no released success.
- **FAIL condition:** Missing/duplicate terminal, released data after failure, unsafe reason, or
  restart changes outcome.

### P4-BE-017 — PostgreSQL restart replay

- **gate_id:** `P4-BE-017`; **title:** PostgreSQL restart replay.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** persistence/restart mandate; Postgres event store and frozen SSE recovery.
- **preconditions:** Target PostgreSQL composition, nonterminal and terminal R, and durable events.
- **setup:** Record event bytes/hashes, cursor positions, projection, aggregate, review/result,
  artifacts, and A/B/C identities.
- **action/request:** Stop/recreate API, worker, repositories, and browser context without deleting
  database/artifact storage; replay numeric/opaque cursors and reopen records.
- **expected response:** Exact event suffix/history and identical durable entities; no Demo or
  in-memory reconstruction.
- **expected persistence:** All recorded rows and artifact identities/bytes survive; next sequence
  remains contiguous.
- **identity assertions:** Entire O/R/T/C/V/A/K/E/X tuple remains exact; `P4-ID-005`, `009`,
  `011..020`, `023`, `025..027`.
- **negative variant:** Restart between confirm commit/start delivery and during live execution; no
  duplicate admission/event/Run.
- **error behavior:** Missing/corrupt state fails closed and cannot be filled from fixture/latest.
- **restart behavior if applicable:** This is the behavior under test; repeat twice to exclude
  process cache.
- **evidence retained:** Pre/post manifests, database revision, process boundaries, row/frame/hash
  diffs, artifact byte hashes.
- **mapped P4-E2E IDs:** `075`, `079..081`, `087`, `098`; **mapped P4-SSE IDs:** `007..009`,
  `013`, `017`; **mapped P4-ID IDs:** `005`, `009`, `011..020`, `023`, `025..027`.
- **PASS condition:** Pre/post durable truth and replay are identical and execution effects remain
  exactly once.
- **FAIL condition:** Any identity/data/event is lost, duplicated, resequenced, or rebuilt from
  nonauthoritative memory.

### P4-BE-018 — Event normalization

- **gate_id:** `P4-BE-018`; **title:** Versioned event normalization.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** event mapping and SSE acceptance §4; `P4-CB-002`, `010`.
- **preconditions:** Corpus contains every frozen backend runtime event type and payload version.
- **setup:** Capture real durable events, raw enums, progress ratios, graph/correction/review/
  capability/terminal cases, and expected public normalized DTOs.
- **action/request:** Project each event through the backend public normalization contract and
  replay the stream.
- **expected response:** Total versioned mapping preserves raw identity/sequence/type and exact
  semantics; task progress stays ratio; correction, run-level review, sparse graph, capability,
  and terminal meanings are not conflated or fabricated.
- **expected persistence:** Normalization is read-only; raw durable events remain immutable.
- **identity assertions:** Every event and Task/capability/replan/correction reference owns R;
  `P4-ID-008..010`, `025..027`.
- **negative variant:** Unknown event/payload version, `review.resolved` ambiguity, unsupported
  mutation name, and malformed Task ref fail closed or trigger reviewed refresh policy.
- **error behavior:** `SCHEMA_INCOMPATIBLE`/typed normalization error; never coerce to a known event
  or invent defaults.
- **restart behavior if applicable:** Same raw event maps identically after restart and mapper
  version is evidenced.
- **evidence retained:** Raw and normalized JSON, schema/map hashes, exhaustive enum coverage,
  before/after event-store hash.
- **mapped P4-E2E IDs:** `026..036`, `040..043`, `083`, `089..091`;
  **mapped P4-SSE IDs:** `002`, `004..005`, `010..011`, `015..016`, `019..020`;
  **mapped P4-ID IDs:** `008..010`, `025..027`.
- **PASS condition:** Every supported event has one exact mapping and every unknown/ambiguous event
  fails or refreshes under the frozen rule.
- **FAIL condition:** Any guessed enum/default, scale error, semantic conflation, fabricated event,
  or identity leak occurs.

### P4-BE-019 — Sparse graph event recovery

- **gate_id:** `P4-BE-019`; **title:** Sparse graph-event recovery.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** `AtomicRunProjectionV1` sparse-event rule; `P4-CB-012`.
- **preconditions:** Approved real replan emits sparse `graph.task_added`/edge/version events.
- **setup:** Capture immutable planned graph and authoritative actual graph before/after mutation.
- **action/request:** Consume sparse events, disconnect between frames, and request projection
  refresh.
- **expected response:** Sparse event sets `projection_refresh_required=true`; refreshed actual
  graph provides full Task/dependencies and one incremented version; planned graph is unchanged.
- **expected persistence:** One atomic graph mutation/version and durable history; no client-created
  Task row.
- **identity assertions:** Added/affected Tasks and edges own R and form a valid acyclic graph;
  `P4-ID-007..010`, `023`, `026..027`.
- **negative variant:** Sparse event from R-B, missing Task definition, gap/out-of-order delivery,
  and unsupported mutation type.
- **error behavior:** Quarantine/reconcile; never fabricate labels, dependencies, change IDs, or a
  Task.
- **restart behavior if applicable:** Projection after restart yields the same actual graph/version
  and mutation history.
- **evidence retained:** Raw frames, frame hashes, before/after graphs, revision/sequence/version,
  cycle/dependency diff, restart snapshot.
- **mapped P4-E2E IDs:** `029..036`, `077`, `084`, `088..089`;
  **mapped P4-SSE IDs:** `011..012`, `020`; **mapped P4-ID IDs:** `007..010`, `023`,
  `026..027`.
- **PASS condition:** Consumer converges only through authoritative projection to one valid actual
  graph mutation.
- **FAIL condition:** Event payload invents a Task, planned graph mutates, version/cardinality is
  wrong, or cross-Run state applies.

### P4-BE-020 — Lossless financial metric

- **gate_id:** `P4-BE-020`; **title:** Lossless released financial metric.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** `ReleasedFinancialMetricProjectionV1`, draft §7; `P4-CB-005`.
- **preconditions:** Released R has reviewed metric M, Claim C, Calculation K, Evidence E, proof
  policy, and canonical/result X.
- **setup:** Use mandatory semantic fixture plus cases with currency/null, limitations, method,
  technical-price, and corporate-action metadata.
- **action/request:** Read released result/metric and exact Claim detail.
- **expected response:** Every required identity, canonical/display value+unit, period/basis,
  actuality, as-of, currency, formula/capability/calculation, Evidence/Claim/Proof refs and
  limitations is preserved without lossy frontend-summary shape.
- **expected persistence:** Read-only immutable released record and lineage.
- **identity assertions:** M→K/E/C/Proof and enclosing R/X are exact; `P4-ID-011..014`, `017..020`.
- **negative variant:** Remove/mismatch any material semantic/lineage field or substitute same-name
  metric from R-B.
- **error behavior:** Release is unavailable/fails; never 200 `AVAILABLE` with null/empty sentinel
  replacing a required fact.
- **restart behavior if applicable:** Exact strings/enums/refs survive restart.
- **evidence retained:** Domain rows, wire JSON, semantic equality diff, release-gate record, schema
  hash.
- **mapped P4-E2E IDs:** `069`, `092`, `094..095`, `098`; **mapped P4-SSE IDs:** none;
  **mapped P4-ID IDs:** `011..014`, `017..020`.
- **PASS condition:** Wire projection is semantically and textually lossless and lineage-closed.
- **FAIL condition:** Recalculation, coercion, omitted authority field, fallback, or invalid release.

### P4-BE-021 — Ratio/percentage semantics

- **gate_id:** `P4-BE-021`; **title:** Ratio/percentage semantics.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** mandatory fixture in draft §7 and coordinator brief.
- **preconditions:** M is reviewed/released with canonical ratio.
- **setup:** Freeze `canonical_value="0.6547"`, `canonical_unit="RATIO"`,
  `display_value="65.47"`, `display_unit="%"` and matching C/K/E.
- **action/request:** Read metric through all backend projections used by list/result/Claim/trace.
- **expected response:** Exact four strings/enums everywhere; backend-provided display fields are
  `65.47` and `%`.
- **expected persistence:** Canonical and display fields are immutable release data, not recomputed
  on GET.
- **identity assertions:** Every copy resolves to the same M/K/C/R/X; `P4-ID-013..014`, `017..020`.
- **negative variant:** Seed `0.6547%`, unlabeled `0.6547`, 65.47 RATIO, float-rounding drift, and a
  same-name metric from B; each is rejected.
- **error behavior:** Integrity/semantic release failure; no server/client repair at read time.
- **restart behavior if applicable:** Exact decimal strings and units remain byte-equivalent.
- **evidence retained:** Stored/wire values, schema validation, equality hashes, release failure
  evidence for negative cases.
- **mapped P4-E2E IDs:** `069`, `092..093`; **mapped P4-SSE IDs:** none;
  **mapped P4-ID IDs:** `013..014`, `017..020`.
- **PASS condition:** All backend consumers receive the exact canonical/display pair.
- **FAIL condition:** Any scaling, rounding, missing label, duplicate conversion, or name fallback.

### P4-BE-022 — Claim detail

- **gate_id:** `P4-BE-022`; **title:** Claim detail.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** `GET .../{run_id}/claims/{claim_id}` → `ClaimDetailV1`, draft §8.1;
  `P4-CB-005`, `006`.
- **preconditions:** Released R/A has exact C/M/K/E, Review V, proof policy/results, X/result and
  scoped anchors.
- **setup:** Include multiple supporting Tasks via Calculation refs and missing retained Evidence
  body while preserving identity.
- **action/request:** Fetch C under R and traverse returned refs.
- **expected response:** Watermarks, O/R, typed C and M, all `task_refs`, safe Evidence,
  deterministic Calculations, proof, Review/check refs, X/result IDs and typed anchors;
  `primary_task_id=null` unless durably selected. No raw artifact/provider body.
- **expected persistence:** Read-only; unavailable detail retains stable IDs/reason.
- **identity assertions:** Task only derives through C→K→T; exact E/M/V/X closure;
  `P4-ID-011..020`, `025..027`.
- **negative variant:** `(R-A,C-B)`, E-B or K-B inside C-A, and missing C; no latest/title/metric
  fallback.
- **error behavior:** Safe not-found/identity mismatch or durable `UNAVAILABLE`; never a different
  Claim/detail.
- **restart behavior if applicable:** Same C and refs/unavailable state survive restart.
- **evidence retained:** Response, join-query ledger, source rows, forbidden-field scan, negative
  request ledger.
- **mapped P4-E2E IDs:** `042`, `048..054`, `072..073`, `094`, `098`, `105`;
  **mapped P4-SSE IDs:** none; **mapped P4-ID IDs:** `011..020`, `023`, `025..027`.
- **PASS condition:** Claim detail is complete, safe, exactly joined, and fail-closed.
- **FAIL condition:** Any heuristic Task/Claim selection, mixed lineage, raw body/path, or missing
  required state represented as success.

### P4-BE-023 — Review/check projection

- **gate_id:** `P4-BE-023`; **title:** Financial Review/check projection.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** `GET .../{run_id}/review-view` → `FinancialReviewProjectionV1`, draft §8.2;
  V17 prepared `FinancialReviewProjection`; `P4-CB-010`, `011`.
- **preconditions:** R has one typed Review V with multiple Checks, reviewed refs, open/resolved
  correction cases, and snapshot hash.
- **setup:** Capture source Review/Correction/Task records and stable check identities.
- **action/request:** Read complete and exception views/filters from the same endpoint projection.
- **expected response:** Version/watermarks/O/R/V/status/reviewer/hash, exact reviewed/proof refs,
  stable `check_id`, code/status/subjects/expected/actual/detail, explicit exception state,
  correction refs and resolution timestamps, plus availability. For a released Review, its
  `canonical_record_id` and `released_result_id` must be carried or resolved by the exact frozen
  projection so A/B/C closure is machine-verifiable; their direct-field nullability is `UAC-013`.
- **expected persistence:** Read-only; resolved history is durable/append-preserving and never
  inferred from array position or `review.resolved` event text.
- **identity assertions:** V owns R and exact C/K/T subjects; `P4-ID-015..020`, `025..027`.
- **negative variant:** V-B under R-A, C/K/T-B subjects, duplicate/missing check ID, unknown status,
  and absent Review.
- **error behavior:** Identity/schema failure or typed availability; no synthetic per-Claim Review.
- **restart behavior if applicable:** Review/check/correction identities and history survive.
- **evidence retained:** Source records, response/filter counts, mapping/schema version, negative
  join evidence, restart diff.
- **mapped P4-E2E IDs:** `040..043`, `053`, `072..073`, `094..095`, `098`;
  **mapped P4-SSE IDs:** none; **mapped P4-ID IDs:** `015..020`, `023`, `025..027`.
- **PASS condition:** One exact backend Review truth supports all views with stable check history.
- **FAIL condition:** UI-shaped fake Reviews, semantic conflation, missing stable identity, mixed
  refs, or unavailable-as-PASS.

### P4-BE-024 — Claim Trace closure

- **gate_id:** `P4-BE-024`; **title:** Claim Trace closure.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** `GET .../{run_id}/trace/{claim_id}` → `TraceBundleV1`, draft §8.3 and
  identity mapping; `P4-CB-006`.
- **preconditions:** Released R/A contains report metric M, C, V/check, K, E, optional Proof, T,
  canonical X/execution and report representation anchor.
- **setup:** Capture exact chain and a second complete B chain with colliding names/metric labels.
- **action/request:** Request trace for C and follow every typed ref to the original report anchor.
- **expected response:** One versioned bundle preserving O/R/T/C/V/A/K/E/X, proof where policy
  requires it, execution event/task anchor, and representation-scoped report anchor; missing bodies
  use typed availability while IDs remain.
- **expected persistence:** Read-only immutable release/anchor manifest; no generated fallback.
- **identity assertions:** Exact chain `M→C→V→T→K→E→Proof→Execution→original Report`;
  `P4-ID-011..020`, `025..028`.
- **negative variant:** C-B under R-A, E/K/V/A-B substitution, historical Claim against latest R,
  and title/symbol/metric-name lookup.
- **error behavior:** Fail closed with safe identity/not-found/unavailable; no “closest match.”
- **restart behavior if applicable:** Entire tuple and anchors reopen unchanged.
- **evidence retained:** Trace body, source-record graph, anchor manifest/hash, negative lookups,
  forbidden-field scan.
- **mapped P4-E2E IDs:** `048..054`, `072..073`, `094..095`, `098`, `105`;
  **mapped P4-SSE IDs:** none; **mapped P4-ID IDs:** `011..020`, `023`, `025..028`.
- **PASS condition:** The round trip returns to the exact originating report representation and all
  joins are explicit.
- **FAIL condition:** Any fallback, mixed chain, missing required identity, hidden reasoning, or
  anchor to another representation/Run.

### P4-BE-025 — Artifact metadata

- **gate_id:** `P4-BE-025`; **title:** Report artifact metadata.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** `GET .../{run_id}/artifacts` → `ReportArtifactGroupV1`, draft §9;
  `P4-CB-004`.
- **preconditions:** Released R has HTML available and both available/unavailable PDF corpora.
- **setup:** Capture internal records and exact A/R/O/X/result IDs while preventing internal locator
  exposure.
- **action/request:** Fetch group under R/A authorization.
- **expected response:** V1 group with O/R, `report_id==released_result_id`, X/result,
  `AvailabilityV1`, separate HTML/PDF slots, distinct available artifact IDs, reviewed
  format/content type, SHA-256, size, renderer, generated time, and same-origin authorized ref only
  when available. Both provisional drafts use `artifact_id=null` for a `NOT_GENERATED` slot; the
  final freeze must preserve that rule or issue an explicit reviewed delta.
- **expected persistence:** Read-only; metadata is immutable; failed generation reason is durable.
- **identity assertions:** Every A owns O/R/X/result/report; `P4-ID-018..020`, `025..027`.
- **negative variant:** A-B metadata under R-A, raw `artifact://`/filesystem locator, HTML reused as
  PDF, missing hash/size for AVAILABLE.
- **error behavior:** Safe identity/integrity/schema error or explicit availability; no raw locator.
- **restart behavior if applicable:** Metadata/availability/IDs/hashes survive restart.
- **evidence retained:** Public/internal comparison with locators redacted, response/schema hash,
  identity join, restart diff.
- **mapped P4-E2E IDs:** `045..047`, `072..073`, `096`, `098`;
  **mapped P4-SSE IDs:** none; **mapped P4-ID IDs:** `018..020`, `023`, `025..027`.
- **PASS condition:** Group is identity-closed, lossless, safe, and accurately represents each
  independent format.
- **FAIL condition:** Locator disclosure, shared HTML/PDF identity, wrong/missing metadata,
  cross-object data, or unavailable represented as ready.

### P4-BE-026 — Artifact authorized content

- **gate_id:** `P4-BE-026`; **title:** Authorized artifact content delivery.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** `GET .../{run_id}/artifacts/{artifact_id}/content`, draft §§9/11;
  `P4-CB-004`.
- **preconditions:** Available A bound to R/O/X/result and authorized actor; distinct denied actor
  and A-B exist.
- **setup:** Capture metadata and storage bytes without exposing locator to the caller.
- **action/request:** Download through `authorized_ref`; repeat expired/revoked/denied and
  cross-Run cases.
- **expected response:** Exact bytes plus reviewed `Content-Type`, `Content-Length`,
  `Digest: sha-256=...`, immutable ETag and safe `Content-Disposition`.
- **expected persistence:** Read-only; authorization is rechecked every request; metadata success
  does not grant ambient byte access.
- **identity assertions:** Route R and A join through O/X/result; `P4-ID-019..020`, `025..027`.
- **negative variant:** A-B under R-A, unauthorized actor, expired ref, unsupported media, and direct
  internal locator request.
- **error behavior:** Concealed not-found/forbidden per final policy, or integrity failure; zero body
  bytes on denial/failure.
- **restart behavior if applicable:** Durable available bytes remain verifiable; old authorization
  state is reevaluated, not blindly trusted.
- **evidence retained:** Request/auth ledger, response headers, byte hash/size, zero-byte negative
  bodies, storage comparison.
- **mapped P4-E2E IDs:** `045..046`, `073`, `096`, `098`; **mapped P4-SSE IDs:** none;
  **mapped P4-ID IDs:** `019..020`, `023`, `025..027`.
- **PASS condition:** Only the authorized exact identity receives the exact reviewed bytes.
- **FAIL condition:** Any byte on denial/mismatch, metadata-only authorization, wrong headers/body,
  or path exposure.

### P4-BE-027 — Artifact integrity

- **gate_id:** `P4-BE-027`; **title:** Artifact integrity enforcement.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** artifact byte-route integrity rule, draft §9; `P4-CB-004`.
- **preconditions:** Available HTML and PDF representations with stored metadata.
- **setup:** Independently hash/size/type valid bytes; prepare tampered byte, hash, size, MIME, and
  swapped-representation cases.
- **action/request:** Download each valid and tampered case through the public route.
- **expected response:** Valid bytes match all metadata/headers; every mismatch returns
  `INTEGRITY_FAILURE` with no bytes.
- **expected persistence:** GET does not repair metadata or content; corruption remains quarantined
  pending separate authorized remediation.
- **identity assertions:** Integrity is checked after exact A/R/O/X/result authorization;
  `P4-ID-019`, `026`.
- **negative variant:** Swap HTML/PDF, same-size altered body, wrong charset/media type, truncation,
  and A-B bytes behind A metadata.
- **error behavior:** Safe `INTEGRITY_FAILURE`; no partial body or raw path.
- **restart behavior if applicable:** Verification repeats after process/storage reopen with the
  same result.
- **evidence retained:** Independent hashes/sizes/signatures, headers, zero-body failures, storage
  and metadata manifests.
- **mapped P4-E2E IDs:** `045..046`, `096`, `098`; **mapped P4-SSE IDs:** none;
  **mapped P4-ID IDs:** `019`, `023`, `026`.
- **PASS condition:** Every valid representation verifies and every corruption/substitution is
  withheld.
- **FAIL condition:** Any corrupt/wrong bytes are delivered, auto-repaired, partially streamed, or
  attributed to the wrong representation.

### P4-BE-028 — Released Object Core

- **gate_id:** `P4-BE-028`; **title:** Released Object Core.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** `GET /api/objects/{object_id}/released-state` →
  `ReleasedObjectCoreV1`, draft §10.
- **preconditions:** O has older valid release R1, newer nonterminal/failed Runs, and optionally a
  newer valid release R2; Object B has colliding metric names.
- **setup:** Capture release closure and ordering keys for all Runs.
- **action/request:** Fetch object list/detail/released-state before/after R2 and reopen historical
  R1.
- **expected response:** V1 Object, exact `latest_released_run_id`, availability, matching
  `source_run_id`, result/X/released time, lossless metrics, Claim refs and artifacts. Newer
  draft/running/failed/cancelled Runs never supersede it.
- **expected persistence:** Read-only projection over immutable released Runs; no Phase 5
  ObjectVersion/Memory/writeback is created.
- **identity assertions:** `source_run_id==latest_released_run_id`; every nested release owns O/R/X;
  `P4-ID-001`, `006`, `013..020`, `023`, `025..027`.
- **negative variant:** Inject B release, invalid Review/Proof/material closure, and missing current
  release; no global latest or lossy `/financials` fallback.
- **error behavior:** Typed non-available state or safe identity/integrity error; unavailable Object
  data never becomes success.
- **restart behavior if applicable:** Same latest valid release and historical immutability survive.
- **evidence retained:** Candidate Runs/order, closure validator inputs, responses, row/hash counts,
  Phase-5-field absence scan.
- **mapped P4-E2E IDs:** `003`, `057`, core `059`, `060..061`, `070`, `072`, `076`, `092`,
  `094`, `096`, `098`; **mapped P4-SSE IDs:** none; **mapped P4-ID IDs:** `001`, `006`,
  `013..020`, `023`, `025..027`.
- **PASS condition:** Projection selects only the newest fully valid same-Object release and
  preserves its exact authority.
- **FAIL condition:** A nonreleased/invalid/B Run supersedes, source/latest diverge, Phase 5 state is
  implied, or financial fields are lossy/recomputed.

### P4-BE-029 — `latest_released_run_id`

- **gate_id:** `P4-BE-029`; **title:** Latest released Run selection.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** draft §10 ordering and release closure.
- **preconditions:** Same multi-Run Object corpus as `P4-BE-028`, including equal `released_at`
  tie.
- **setup:** Compute oracle from Runs with `status=RELEASED` and valid canonical/result/Review/
  required-Proof/material-output closure, ordered `(released_at DESC, run_id DESC)`.
- **action/request:** Read list/detail/released-state and exact historical row routes.
- **expected response:** All current-Object surfaces expose the same selected R; historical actions
  preserve their row R and never redirect to latest.
- **expected persistence:** Read-only deterministic projection.
- **identity assertions:** Selected R owns O; `P4-ID-001`, `006`, `023`, `025`, `027`.
- **negative variant:** Globally newer B Run, newer failed A Run, equal-time tie, and no valid
  release.
- **error behavior:** Null/typed unavailable when none; no first/list-order/symbol fallback.
- **restart behavior if applicable:** Selection is identical after restart.
- **evidence retained:** Candidate table, closure decisions, ordering calculation, all response
  fields and restart diff.
- **mapped P4-E2E IDs:** `057`, `060..061`, `076`, `098`; **mapped P4-SSE IDs:** none;
  **mapped P4-ID IDs:** `001`, `006`, `023`, `025`, `027`.
- **PASS condition:** Every surface matches the deterministic same-Object release oracle.
- **FAIL condition:** Wrong/ineligible Run, inconsistent surfaces, unstable tie, or historical
  substitution.

### P4-BE-030 — Cross-object rejection

- **gate_id:** `P4-BE-030`; **title:** Cross-object and cross-Run rejection.
- **activation_scope:** `PHASE4_CORE_REQUIRED`.
- **source contract:** authorization draft §11 and identity negative matrix `XL-01..10`.
- **preconditions:** Two authorized-or-differentially-authorized Objects A/B each have complete,
  distinct O/R/T/C/V/A/K/E/X tuples and colliding labels/sentinel values.
- **setup:** Capture every exact route/ref for both tuples and database ownership joins.
- **action/request:** Substitute Run B under Object A, C/T/V/A B under R-A, E/K B in C-A, B latest
  under A, historical Claim under latest, and cross-context shared state.
- **expected response:** Every mismatched API request fails closed; no B content/bytes appear in A;
  a legitimate explicit navigation to B must replace the entire context, never mix it.
- **expected persistence:** Zero mutation, repair, reparenting, or fallback.
- **identity assertions:** Exact ownership for Object, Run, Task, Evidence, Calculation, Claim,
  Review, Proof, Canonical, Result and Artifact; `P4-ID-001`, `004`, `006..020`, `025..027`.
- **negative variant:** All `XL-01..10`, plus latest/first/symbol/title/metric-name fallback and
  unknown IDs.
- **error behavior:** Frozen authorization/identity code with concealed existence where required;
  never 200 partial data or redirected “closest match.”
- **restart behavior if applicable:** Rejections remain identical after backend restart; caches do
  not leak prior actor/Object state.
- **evidence retained:** Full substitution matrix, statuses/safe errors/zero-byte bodies, before/
  after counts, A/B DOM-network sentinel scan supplied by browser suite.
- **mapped P4-E2E IDs:** `005..007`, `042`, `045..054`, `057`, `060..061`, `070..073`, `094`,
  `096`, `105`; **mapped P4-SSE IDs:** `003`, `018`; **mapped P4-ID IDs:** `001`, `004`,
  `006..020`, `025..027`.
- **PASS condition:** Every mismatch is rejected without disclosure, mutation, or fallback, while
  exact legitimate requests still succeed.
- **FAIL condition:** Any mixed tuple, B data/bytes in A, automatic latest repair, heuristic match,
  inconsistent auth behavior, or shared-cache leak occurs.

## 4. Unresolved acceptance-semantic conflicts

These are not waivers. A gate depending on one cannot execute to PASS until the final contract
freezes the decision and the executable harness binds its schema/hash.

| Conflict | Unresolved decision / observed contradiction | Affected gates |
|---|---|---|
| `UAC-001` | Backend API document is `NOT_FINAL`; no immutable independently accepted Phase 3 parent or clean Phase 4 candidate exists. | all |
| `UAC-002` | Provisional V17 preparation is now available (`13/13` named contracts and `BD-001..012`), but the final V17 Integration Readiness Review, approved V17 contract freeze, and governed V17 Candidate SHA are not available. The preparation remains `BLOCKED_BY_BACKEND_CONTRACT` and cannot serve as accepted-candidate evidence. | all integration mappings |
| `UAC-003` | Schema/event/route version negotiation request mechanism and incompatible-version HTTP status are not frozen. | all versioned routes |
| `UAC-004` | The provisional event draft proposes `409 CURSOR_AHEAD`, but the final contract is not frozen and current stores accept an ahead cursor and can heartbeat indefinitely. | `013..014` |
| `UAC-005` | Confirm says a retry returns the “exact same body” while changing `idempotency_replayed=false` to `true`; immutable outcome versus transport replay metadata must be separated. | `004..005` |
| `UAC-006` | Actor/tenant authentication model, key scope representation, and 403-versus-concealed-404 policy are not frozen. | all protected gates, especially `004`, `026`, `030` |
| `UAC-007` | Durable admission/outbox schema, lease/redelivery states, and the exact one-start accounting oracle are not frozen. | `004..006`, `017` |
| `UAC-008` | `projection_revision` mutation set and atomic update protocol do not exist. The backend draft carries ratio `progress`, requires `progress_method` in prose but omits it from the example, while V17 proposes `{fraction, percent, method}` and also requires `pathChanges` absent from the backend projection example. Exact wire versus adapter ownership is not frozen. | `001`, `007..010`, `019` |
| `UAC-009` | Atomic event/aggregate commit protocol required for `projection_sequence` is absent. | `007..009`, `017`, `019` |
| `UAC-010` | Total Run/Task/Review/Proof/availability maps and versioned event payload schemas remain incomplete despite the draft referring to companion “frozen” maps. | `001`, `007`, `010`, `018..019`, `023` |
| `UAC-011` | Every terminal path, especially post-scheduler assurance/release failure, has not proven exactly one durable `run.failed`. | `006`, `015..017` |
| `UAC-012` | `ClaimDetailV1` is prose rather than a closed field/schema definition; typed Judgment availability remains unresolved. | `022`, `024` |
| `UAC-013` | Stable Review `check_id`, check-to-correction relation, exception-state derivation, and resolution timestamp are new required durable facts with no final schema. V17 also proposes direct/nullable `canonical_record_id` and `released_result_id`, which the backend draft Review example omits. | `023..024` |
| `UAC-014` | `TraceBundleV1` and representation-scoped Claim anchor manifest have no exact frozen wire schema. | `024..027` |
| `UAC-015` | Artifact authorization-reference lifecycle, revocation/expiry semantics, storage resolver, and denial disclosure policy are not frozen. | `025..027`, `030` |
| `UAC-016` | Durable PDF/HTML generation failure facts and the implemented availability transition protocol are absent; publishing is not on the normal API path. The provisional Backend and V17 drafts now agree that `NOT_GENERATED` carries a null artifact ID, but that draft rule still requires final freeze and implementation. | `025..028` |
| `UAC-017` | Latest-release validator details must bind the final Review/Proof/material-output policy version; current `/financials` and `/state` cannot serve as authority. V17's normalized metric groups Proof requirement/status and omits several backend-draft extension fields, so the final lossless backend-to-frontend metric boundary also needs explicit freeze. | `015`, `020..021`, `028..029` |
| `UAC-018` | Error codes/statuses for identity mismatch versus authorization concealment, integrity failure, unavailable detail, and failed projection assembly are not one frozen total table. V17 proposes `phase4-error/v1` with `CURSOR_AHEAD`, retryability, recovery, and resource context; current Phase 3 and the backend draft do not freeze that envelope. | all negative cases |

`UNRESOLVED_BACKEND_ACCEPTANCE_SEMANTIC_CONFLICTS = 18`.

## 5. Design declaration

```text
P4_BE_GATES_DEFINED=30
P4_BE_ACTIVATION_SCOPE=PHASE4_CORE_REQUIRED
P4_BE_EXECUTED=NO
P4_BE_IMPLEMENTATION_AUTHORIZED=NO
P4_BE_CURRENT_IMPLEMENTATION_STATUS=NOT_IMPLEMENTED_OR_PARTIAL_AS_CATALOGUED
P4_E2E_015=RETIRED_TOMBSTONE
REAL_SCENE_05_06=DEFINED_NOT_ACTIVATED
UNRESOLVED_BACKEND_ACCEPTANCE_SEMANTIC_CONFLICTS=18
```
