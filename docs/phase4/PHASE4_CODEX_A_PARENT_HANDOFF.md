# Phase 4 Codex A — Parent Handoff

Status: `A_WORK_COMPLETE_PARENT_INTEGRATION_REQUIRED`

This handoff is scoped to the owner-authorized child branch
`p4-backend-product`, the flat-name substitute for the requested
`phase4/backend-product` branch. It does not authorize a merge, migration, or
change to `phase4`/`main`.

## Frozen authority and source identity

- Source parent: `4b6721b6db433aae300f94750e1a405b6b450501`
- Source tree: `35c47508ed65220c26620f5ec4bdd14cb798480d`
- Contract freeze tag: `p4-ig00-contract-freeze`
- Frozen Phase 4 contract-set SHA-256:
  `0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741`
- Owner-approved V17 R2 canonical SHA-256:
  `fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19`
- Access scope: `LOCAL_SINGLE_USER`

## Internal A ownership map

| Owner | Exclusive new files | Scope |
|---|---|---|
| A coordinator | `contracts.py`, `errors.py`, `api.py`, package exports and this handoff | shared wire/error/HTTP boundary and serial integration |
| A1 | `hashing.py`, `admission.py` | canonical hashes, Prepare/Confirm, idempotency and scheduler-admission values |
| A2 | `reconstruction.py`, `durability.py` | strict aggregate reconstruction and PostgreSQL transaction protocols |
| A3 | `safety.py`, `projections.py`, `artifacts.py` | safe projections, status/progress maps, trace/artifact closure |
| A4 | `tests/phase4/backend_product/**` | contract and negative acceptance tests only |

No specialist or coordinator edited a Parent-only file. Existing Phase 3
financial, Generated Capability, Proof/RISC Zero, CER, Review, ReleasedResult,
provider-router, Langfuse, event, checkpoint, scheduler and SSE implementations
remain unchanged.

## Child implementation delivered

Files added on this branch:

- `src/phase4_product/`: 11 isolated modules (`__init__`, admission, API,
  artifacts, contracts, durability protocols, errors, hashing, projections,
  reconstruction and safety).
- `tests/phase4/backend_product/`: 19 focused contract/negative test modules.
- `docs/phase4/PHASE4_CODEX_A_PARENT_HANDOFF.md`: this handoff and the 15
  Parent-only semantic proposals below.

The isolated implementation supplies:

- the exact 17 A-owned Product routes and leaves the C-owned events route
  unregistered;
- strict closed DTOs, version/media negotiation, error envelopes, ETags and
  Prepare/Confirm response semantics;
- immutable draft, scoped idempotency outcomes, exact replay, all-or-nothing
  Confirm write-set validation, pristine initial event inventory,
  Run-admission and fenced scheduler transition values;
- deterministic, filter-bound opaque Run collection cursors with exact
  ordering and lifecycle/event consistency checks;
- exact no-fallback snapshot reconstruction and typed unavailable states;
- safe Run, Task Graph, Released Result, Financial Review, Canonical Execution,
  TraceBundle, released-object and report-artifact projection builders;
- artifact identity/Run/release/byte-size/media/hash verification with zero
  protected bytes on failure; and
- recursive secret, bearer, local-path, provider-payload and hidden-reasoning
  rejection at public projection/error boundaries.

Financial Review projection now requires the complete retained E/K/M/C/J plus
ProofPolicyDecision input set, derives subject authority from those records,
and recomputes `input_snapshot_hash` with the existing Phase 3 algorithm. It
does not redefine that historical hash as an RFC 8785 Phase 4 hash.

## Verification performed

- Recovery/finalization focused A-owned suite: `368 passed`, `0 failed`.
- Full repository regression: `833 passed`, `11 skipped`, `0 failed`.
- The full regression result is the last confirmed pre-interruption result; it
  was not redundantly rerun during recovery because the recovered focused
  surface and all static gates passed unchanged.
- The 11 skips are environmental: three require a configured real PostgreSQL
  URL plus `asyncpg`; eight require the prebuilt RISC Zero proof host.
- Ruff: pass for all `src/phase4_product` and
  `tests/phase4/backend_product` files.
- Ruff format check: pass for the same files.
- Compile check: pass for the same files.
- Changed-surface credential scan: no credential material found. Matches are
  safety filters and explicit negative-test dummy values only.
- No authoritative Phase 3 Research Run was started.

The focused test modules are:

1. `test_admission.py`
2. `test_api_contract.py`
3. `test_api_negotiation_audit.py`
4. `test_artifact_integrity_audit.py`
5. `test_artifacts.py`
6. `test_confirm_commit_integrity.py`
7. `test_contract_strictness_audit.py`
8. `test_contracts_and_errors.py`
9. `test_financial_projection_builders.py`
10. `test_hashing.py`
11. `test_identity_contracts.py`
12. `test_projection_safety.py`
13. `test_projection_status.py`
14. `test_reconstruction.py`
15. `test_release_validation.py`
16. `test_run_collection.py`
17. `test_scheduler_durability.py`
18. `test_top_level_projection_builders.py`
19. `test_trace_builder.py`

## Durability boundary and known blockers

The branch contains PostgreSQL-only repository/unit-of-work protocols, exact
MVCC snapshot reconstruction, atomic write-set validators and deterministic
fence transitions. It deliberately contains no concrete PostgreSQL adapter,
schema migration or production application composition. Therefore it does not
claim restart durability, exactly-one persisted Confirm/Run admission, or
production artifact recovery.

The current Phase 3 snapshot also cannot reconstruct an AVAILABLE Review after
restart because it lacks the complete immutable E/K/M/C/J input preimage and
typed Check subject/correction authority. It likewise cannot recompute the four
persisted ReleaseValidation hashes because it does not retain their immutable
release-time proof, material-output, artifact and closure preimages. For a
RELEASED Run, reconstruction now fails closed with
`REVIEW_INPUT_PREIMAGE_NOT_PERSISTED` or
`RELEASE_VALIDATION_PREIMAGE_NOT_PERSISTED`; mixed BLOCKED/ALLOWED history is
also rejected until a decision-aware historical preimage is persisted. Digest
syntax alone is never treated as release authority. The isolated release gate
does recompute its versioned hashes when all explicit inputs are supplied, and
its Canonical Execution preimage deliberately excludes event-page and cursor
transport state.

Consequently A2, real restart/fault acceptance, application-level A1 admission
and overall Codex A acceptance remain blocked on the Parent-approved migration
and Parent-only composition proposals. The pure/isolated A3 projection surface
and its focused negatives pass. There is no frozen-contract conflict; the only
identity deviation is the explicitly authorized flat child-branch recovery
recorded above.

## Migration review gate

`MIGRATION_REQUIRED = YES`

### Why

Migration head `20260904_0006` persists the Phase 3 aggregate and supporting
records, but it has no normalized durable authority for several facts that the
frozen contract explicitly classifies as `BACKEND_FIELD_REQUIRED`. A JSON
payload, process cache, advisory convention, or repository scan cannot enforce
the required uniqueness, fencing, cardinality, append-only history, or atomic
projection publication across API/worker restart.

### Required schema delta

The Parent must allocate a forward-only revision after `20260904_0006` and
review at least these normalized constraints:

1. Draft lifecycle: version, immutable request/draft hashes, expiry, and an
   all-or-none consumed time/admission/Run identity.
2. Durable idempotency outcomes: effective scope, method, normalized route,
   key digest and request hash, with one immutable response/admission outcome
   and a unique scoped key.
3. Scheduler admissions: one row per Run and idempotency outcome, the frozen
   `PENDING -> LEASED -> ACKNOWLEDGED|FAILED` state, attempt counters, lease
   generation/expiry, unique start-event identity and immutable start commit.
4. Run projection publication: per-Run `projection_revision` and an atomic
   event watermark, incremented once per projection-affecting transaction.
5. Terminal effect/finalizer: one durable terminal outcome and terminal event
   per Run under duplicate delivery and restart.
6. Review decisions: stable Check IDs, typed subjects, exact
   Check-to-Correction relations, exception state, Check-level resolution
   time and the immutable ordered E/K/M/C/J hash preimage.
7. Claim anchors: immutable hash-bound manifest rows, fixed HTML/PDF
   representation anchors, and explicit Claim-to-safe-RuntimeEvent links.
8. Artifact generation: independent representation slots, append-only attempt
   rows, durable safe failure reasons, verified successful byte metadata and
   retention/revocation state.
9. Release validation: exactly one successful validation for an eligible
   release, binding O/R/Review/X/L plus every policy ID/hash and the material
   output/artifact closure, with immutable versioned hash preimages sufficient
   for restart recomputation.

### Contract requirements

These deltas are required by frozen UAC-005, UAC-007, UAC-009, UAC-011,
UAC-013, UAC-014, UAC-016 and UAC-017. They are prerequisites for honest
restart durability, exactly-one logical Run admission/start, atomic projection
ETags, trace anchors, artifact state and released-object selection.

### Alternatives considered

- Reusing the current JSON aggregate: rejected because relational uniqueness,
  fencing/cardinality and append-only history are not enforceable.
- Process-global or inherited in-memory maps: rejected because state and
  idempotency disappear on restart and diverge across workers.
- Scanning existing rows and choosing `first`/`latest`: rejected by exact
  identity and no-fallback rules.
- PostgreSQL advisory locks without durable rows: rejected because they do not
  preserve the frozen outcome, lease/fence or restart evidence.
- Encoding new facts into unrelated payload fields: rejected as hidden schema
  mutation and insufficient database authority.

No migration was created or applied on this branch. Non-migration wire,
admission, reconstruction, safety and test work continued as required.

## Parent semantic patch proposals

### P4A-PROP-001

- Target file: `apps/api/main.py`
- Reason: root application composition is Parent-only.
- Required semantic change: construct the production PostgreSQL Phase 4
  backend, install the frozen Product error handlers, and make it available as
  `app.state.phase4_product_backend`; issue an opaque server request ID into
  `request.state.request_id`; never use SQLite/in-memory Product truth.
- Required imports/types: `Phase4ProductBackend`,
  `install_phase4_error_handlers`, Parent-approved PostgreSQL adapters.
- Expected behavior: lifespan initializes/closes one production composition;
  all Product responses use the frozen error/version boundary, including
  router-level 404/405 failures without changing unrelated Phase 3 routes.
- Required tests: startup/shutdown, PostgreSQL-only preflight, missing backend
  503 envelope, generic exception 500 envelope, Product-route 404/405
  `phase4-error/v1` envelopes with explicit UTF-8 JSON media type, restart
  reconstruction.
- Dependency on A implementation: `src.phase4_product.api` and A2 durability
  protocols; blocked on the approved migration.

### P4A-PROP-002

- Target file: `apps/api/routes.py`
- Reason: A Product routes and C SSE meet in this Parent-only registry.
- Required semantic change: register the 17 A-owned routes from
  `create_phase4_product_router`; replace overlapping legacy handlers instead
  of exposing two implementations; preserve C ownership of the exact events
  route.
- Required imports/types: `create_phase4_product_router`; C's frozen SSE
  router/handler.
- Expected behavior: the frozen 18-route inventory is unique, with no execute
  click, `BackgroundTasks`, legacy result/review/execution body, or route-order
  shadowing; unmatched or method-invalid Product requests are routed to the
  Parent-scoped error boundary instead of Starlette's default body.
- Required tests: exact method/path inventory, no duplicate routes, 201/200
  Confirm replay, A/C version-header parity.
- Dependency on A implementation: `src.phase4_product.api`; dependency on C
  for `/events`.

### P4A-PROP-003

- Target file: `contracts/api/models.py`
- Reason: the central DTO registry is Parent-only and current Confirm/request
  schemas conflict with the freeze.
- Required semantic change: re-export or delegate to the closed Phase 4 DTOs;
  remove legacy permissive response authority from Product routes.
- Required imports/types: the request, admission, projection, trace, artifact
  and error DTOs in `src.phase4_product.contracts`.
- Expected behavior: extra fields fail, Confirm requires version/hash/object
  identity and `confirm_scheme=true`, and public models expose no raw runtime
  dictionaries.
- Required tests: OpenAPI/JSON-schema parity and extra-field rejection.
- Dependency on A implementation: `src.phase4_product.contracts`.

### P4A-PROP-004

- Target file: `contracts/api/__init__.py`
- Reason: shared contract exports are Parent-only.
- Required semantic change: expose only the Parent-approved Phase 4 DTO import
  surface needed by A/B/C integration.
- Required imports/types: exact exports approved from
  `src.phase4_product.contracts`.
- Expected behavior: one canonical DTO class per public contract.
- Required tests: import smoke test and duplicate-class identity check.
- Dependency on A implementation: P4A-PROP-003.

### P4A-PROP-005

- Target file: `src/application/errors.py`
- Reason: legacy application errors currently use a different vocabulary and
  envelope.
- Required semantic change: map `RESOURCE_NOT_FOUND -> NOT_FOUND` and
  `RESULT_NOT_RELEASED -> NOT_RELEASED` at the Product adapter; route all other
  public failures through the exact policy and safe allowlists.
- Required imports/types: `ProductError`, `ErrorEnvelopeV1`, `ErrorCodeV1`.
- Expected behavior: no arbitrary 500, stack/SQL/path/provider body, or legacy
  error name crosses the Product boundary.
- Required tests: all 17 code/status/retry/recovery tuples and leakage
  negatives.
- Dependency on A implementation: `src.phase4_product.errors`.

### P4A-PROP-006

- Target file: `src/application/repository.py`
- Reason: shared repository interfaces are Parent-only and current production
  behavior inherits process-local identity maps.
- Required semantic change: add exact-ID, Run/Object-scoped repository
  operations and durable idempotency/draft/admission/release-validation/anchor
  access; prohibit latest/first/text fallback.
- Required imports/types: A2 snapshot and unit-of-work protocols plus frozen
  domain record types.
- Expected behavior: every nested read closes to one O/R identity and reports
  missing, foreign and corrupt facts distinctly.
- Required tests: cross-Run/Object/Claim/artifact negatives and restart reads.
- Dependency on A implementation: A2 `reconstruction.py`/`durability.py` and
  the approved migration.

### P4A-PROP-007

- Target file: `src/application/persistence.py`
- Reason: shared persistence is Parent-only and currently commits aggregates,
  children and events in separate transactions.
- Required semantic change: implement the A2 atomic PostgreSQL unit of work
  for Confirm, projection-visible mutations, terminal finalization and exact
  MVCC reads; remove process cache as Product authority.
- Required imports/types: A1 admission records, A2 transaction protocols,
  C event/checkpoint persistence.
- Expected behavior: one Confirm transaction publishes all-or-nothing; one
  business transaction advances revision once with its event watermark.
- Required tests: rollback/fault cuts, duplicate delivery, concurrent readers,
  API/worker restart.
- Dependency on A implementation: A1/A2 and C; blocked on migration approval.

### P4A-PROP-008

- Target file: `src/application/service.py`
- Reason: central composition is Parent-only and current Confirm starts work
  via a process-local path.
- Required semantic change: adapt the frozen Product service to exact
  repositories/builders, commit one durable scheduler admission on Confirm,
  and remove Product use of `BackgroundTasks`.
- Required imports/types: A1 admission functions, A2 unit of work and
  reconstruction, A3 projection/artifact builders.
- Expected behavior: exact replay returns one immutable admission; new-key
  consumed draft conflicts; runtime starts only from durable delivery.
- Required tests: Prepare/Confirm matrix, retry after lost response, restart,
  and one logical Run/start effect.
- Dependency on A implementation: all A specialists and Parent-approved DB
  implementation.

### P4A-PROP-009

- Target file: `src/application/execution.py`
- Reason: the A/C orchestration boundary is Parent-only.
- Required semantic change: make worker start/reconciliation consume the
  durable fenced scheduler admission and commit immutable `started_at` plus one
  `run.started` event through the shared unit of work.
- Required imports/types: A1 `RunSchedulerAdmissionV1`, A2 fence helpers, C
  runtime scheduler/event types.
- Expected behavior: expired leases redeliver the same Run; stale fences write
  nothing; acknowledged redelivery never emits another start.
- Required tests: lease expiry, stale worker, crash before/after start commit
  and acknowledgment.
- Dependency on A implementation: A1/A2, C, and migration approval.

### P4A-PROP-010

- Target file: `src/infrastructure/database/models.py`
- Reason: normalized SQLAlchemy metadata is Parent-only.
- Required semantic change: model the reviewed schema delta with foreign keys,
  unique/check constraints and immutable/append-only relations rather than
  ungoverned JSON payloads.
- Required imports/types: Parent-allocated Phase 4 row models matching A1/A2
  record contracts.
- Expected behavior: PostgreSQL rejects duplicate Run effects, torn
  consumption, invalid leases, duplicate release validation and anchor/attempt
  cardinality violations.
- Required tests: metadata/schema constraint inspection plus transaction-level
  negative inserts.
- Dependency on A implementation: migration proposal P4A-PROP-015.

### P4A-PROP-011

- Target file: `src/infrastructure/database/composition.py`
- Reason: root PostgreSQL adapter composition is Parent-only.
- Required semantic change: compose the reviewed Phase 4 repositories/unit of
  work on the existing shared engine/session factory and expose a capability
  preflight that fails closed when schema features are absent.
- Required imports/types: A2 capability report/protocols and Parent-approved
  SQL adapters.
- Expected behavior: production cannot silently fall back to SQLite, memory or
  a partially migrated database.
- Required tests: backend/driver checks, migration-head/capability preflight,
  shared-session atomicity and clean close.
- Dependency on A implementation: A2 and P4A-PROP-010/015.

### P4A-PROP-012

- Target file: `src/infrastructure/database/artifacts.py`
- Reason: durable artifact/run-record repository is Parent-only.
- Required semantic change: load exact report representation/attempt,
  anchor-manifest and release-validation rows; preserve the internal locator
  exclusively inside the storage adapter; return verified bytes only after
  full O/R/X/L/artifact closure.
- Required imports/types: A3 artifact snapshot/verifier types and approved row
  models.
- Expected behavior: separate HTML/PDF state, zero protected bytes on every
  failure, no `artifact_ref` in DTO/error/log/redirect.
- Required tests: tamper, MIME/size/hash, retention/revocation, Range,
  cross-Run substitution and restart.
- Dependency on A implementation: `src.phase4_product.artifacts` and the
  approved schema.

### P4A-PROP-013

- Target file: `src/output/projections.py`
- Reason: shared projection composition is Parent-only.
- Required semantic change: delegate Product status/progress, released metric,
  Review, execution, trace, artifact and released-object assembly to the A3
  fail-closed builders over A2 exact snapshots.
- Required imports/types: `src.phase4_product.projections`,
  `src.phase4_product.artifacts`, frozen DTOs.
- Expected behavior: no client/LLM financial arithmetic, no fallback join, no
  protected field, and one consistent revision/watermark.
- Required tests: all total maps, identity closure, lossless metric fields,
  safe projection and torn snapshot negatives.
- Dependency on A implementation: A2/A3.

### P4A-PROP-014

- Target file: `src/output/__init__.py`
- Reason: output exports are Parent-only.
- Required semantic change: expose the reviewed Product projection adapters
  after serial A/B/C integration.
- Required imports/types: only Parent-approved exports from P4A-PROP-013.
- Expected behavior: a single safe public projection path; Phase 3 output
  semantics remain available unchanged.
- Required tests: export/import smoke and legacy regression suite.
- Dependency on A implementation: P4A-PROP-013.

### P4A-PROP-015

- Target file:
  `alembic/versions/<PARENT_ALLOCATED>_phase4_product_durability.py`
- Reason: new revision IDs and the migration chain require explicit
  Parent/owner allocation.
- Required semantic change: implement the reviewed forward-only schema delta
  above, based on `20260904_0006`, without rewriting any prior revision.
- Required imports/types: SQLAlchemy/PostgreSQL types and constraints mirrored
  by P4A-PROP-010.
- Expected behavior: upgrade is atomic and preflightable; no automatic apply;
  downgrade follows the project's forward-only policy.
- Required tests: clean upgrade from `0006`, schema contract, constraint
  negatives, restart/fault matrix, and no prior-revision byte changes.
- Dependency on A implementation: owner approval and Parent revision ID
  allocation.

Proposal count: `15`.

## Cross-child integration dependencies (not Parent-only edits by A)

- C must bind its event counter, event append, checkpoint, scheduler and
  terminal finalizer to the Parent's shared PostgreSQL unit of work.
- C owns `GET /api/research-runs/{run_id}/events`; its successful stream must
  echo both frozen contract headers and its cursor/replay semantics must use
  the same durable watermark exposed by A.
- B may consume only the frozen Product DTOs; it must not compensate for a
  missing backend fact with frontend arithmetic, fallback identity, inferred
  review status or synthesized trace anchors.

## Integration readiness rule

The branch can be integrated only after the Parent approves/allocates the
migration, applies these proposals serially with C's event/runtime changes,
and runs real PostgreSQL restart/fault acceptance. This child does not claim
VS01.

## Recovery/finalization record

- Recovered in place on `p4-backend-product`; no implementation was reset,
  discarded or recreated.
- Ownership check: the recovered change set contains only the 31 A-owned files
  listed above; no tracked or Parent-only file was modified.
- Focused tests, Ruff lint, Ruff format and bytecode compilation all pass on
  the recovered filesystem.
- No write to `main` or `phase4` was performed, and VS01 remains unclaimed.
