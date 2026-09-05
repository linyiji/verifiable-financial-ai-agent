# Phase 4 Backend UAC Closure Register

Status: `AUTHORITATIVE_FOCUSED_CLOSURE_PREPARATION — NOT_FINAL`  
Contract family: `phase4-core/v1`  
Normative decision text: `PHASE4_BACKEND_FINAL_FREEZE_DECISION_DRAFT.md`  
Machine-readable authority: `PHASE4_BACKEND_UAC_CLOSURE_REGISTER.json`  
UAC-006 owner decision: `PHASE4_ACCESS_MODE_DECISION_V1.md` / `.json`  
Governance boundary: `PHASE4_CONTRACT_FREEZE_ACCEPTANCE_BOUNDARY.md`

This is the single working closure register for `UAC-001..018`. It does not create another conflict namespace, approve a Phase 3 parent, close a UAC, authorize implementation, or record executed acceptance. Each closure row contains every literal field required by the coordinator request.

## Preparation result

```text
PHASE4_BACKEND_UAC_CLOSURE_PREP_READY=YES
PHASE4_ACCESS_MODE_DECISION_READY=YES
ACCESS_MODE_ID=phase4-local-single-user-trusted/v1
UAC_006=RESOLVED_PROVISIONALLY
UAC_TOTAL=18
UAC_DISPOSITIONED=18/18
UAC_PROVISIONAL_DECISIONS_COMPLETE=18/18
UAC_RESOLVED_PROVISIONALLY=11
UAC_WAITING_FOR_APPROVED_PHASE3_PARENT=1
UAC_WAITING_FOR_FINAL_V17_CONTRACT=1
UAC_WAITING_FOR_IMPLEMENTATION_EVIDENCE=5
UAC_SEMANTIC_DECISION_REQUIRED=0
UAC_FINAL_CLOSED=0
CONTRACT_SEMANTICS_PENDING=0
IMPLEMENTATION_EVIDENCE_PENDING=16
CURRENT_STATE_WAITING_FOR_IMPLEMENTATION_EVIDENCE=5
WAITING_FOR_APPROVED_PHASE3_PARENT=YES
WAITING_FOR_V17_CONTRACT_INPUT=YES
BD_TOTAL=12
BD_DISPOSITIONED=12/12
FRONTEND_CONTRACTS_MAPPED=13/13
FRONTEND_CONFLICT_CLUSTERS_MAPPED=9/9
BACKEND_BLOCKERS_MAPPED=8/8
PHASE5_LEAKAGE=0
PHASE4_BACKEND_CONTRACT_FREEZE_READY=NO
PHASE4_PRODUCTION_IMPLEMENTATION_AUTHORIZED=NO
CONTRACT_FREEZE_IMPLEMENTATION_EVIDENCE_DEADLOCK=RESOLVED
```

## Authority and drift notice

- Declared inspected candidate: `11fe8173a25ff7ac08bae42340ba7c6fae591be5`, tree `b5f7bf960853c43344516031058f043ba45aaac5`.
- Later clean coordination-worktree observation: `8c4a77ccb70bceb1e8bf496ea528682df95a3405`, tree `3a9329f1a5f9c30f3ec1190457e09067c0c102d3`.
- The later 11-file delta changes financial arithmetic/lineage instrumentation but does not become the approved parent by observation. UAC-001 remains open and requires the final delta to bind and re-audit the independently accepted parent.
- UAC-006 follows the project-owner record `PHASE4_ACCESS_MODE_DECISION_V1`: trusted local single-user, no account authentication, mandatory exact identity closure, and no invented principal/tenant/workspace/user entities. A future protected profile is a separate governed change.

## State model

Only these five current states are valid: `RESOLVED_PROVISIONALLY`, `WAITING_FOR_APPROVED_PHASE3_PARENT`, `WAITING_FOR_FINAL_V17_CONTRACT`, `WAITING_FOR_IMPLEMENTATION_EVIDENCE`, and `SEMANTIC_DECISION_REQUIRED`. No row is final-closed.

The compatibility `current_state` and the orthogonal semantic/evidence fields answer different
questions. All 18 rows are `contract_semantics_state=READY_FOR_FINAL_FREEZE`. UAC-001/002 await
authority inputs and have implementation evidence `NOT_APPLICABLE_TO_THIS_ROW`; UAC-003..018 have
`implementation_evidence_state=PENDING`. Thus 16 rows have later executable evidence pending,
while five rows retain the historical `WAITING_FOR_IMPLEMENTATION_EVIDENCE` current state.

| State | UAC IDs | Count |
|---|---|---:|
| `RESOLVED_PROVISIONALLY` | `003`, `004`, `005`, `006`, `008`, `010`, `012`, `013`, `014`, `017`, `018` | 11 |
| `WAITING_FOR_APPROVED_PHASE3_PARENT` | `001` | 1 |
| `WAITING_FOR_FINAL_V17_CONTRACT` | `002` | 1 |
| `WAITING_FOR_IMPLEMENTATION_EVIDENCE` | `007`, `009`, `011`, `015`, `016` | 5 |
| `SEMANTIC_DECISION_REQUIRED` | none | 0 |
| final `CLOSED` | none | 0 |

## Canonical closure rows

### UAC-001 — Authoritative Phase 3 Backend parent identity and evidence binding

- `uac_id`: UAC-001
- `title`: Authoritative Phase 3 Backend parent identity and evidence binding
- `current_state`: WAITING_FOR_APPROVED_PHASE3_PARENT
- `decision_owner`: Phase 3 release authority and Backend/Financial Semantics independent auditors
- `mapped_backend_blockers`: `P4-BLOCKER-01..08`
- `mapped_bd_dependencies`: `BD-001..012`
- `mapped_frontend_contracts`: `ALL_13_V17_NORMALIZED_CONTRACTS`
- `mapped_frontend_conflict_cluster`: `1 Prepare Scheme vs Plan/Tasks`, `2 Confirm/start state and route`, `3 Durable idempotency`, `4 Progress/enums`, `5 Runtime event semantics`, `6 Browser SSE protocol`, `7 Financial Review projection`, `8 Artifact semantics`, `9 Financial/Object projection`
- `mapped_p4_be`: `P4-BE-001..030`
- `mapped_p4_e2e`: `P4-E2E-001..014`, `P4-E2E-016..061 Core variants`, `P4-E2E-063..096`, `P4-E2E-098`, `P4-E2E-101..102`, `P4-E2E-105..106`
- `mapped_p4_sse`: `P4-SSE-001..020`
- `mapped_p4_id`: `P4-ID-001..020`, `P4-ID-023..028`
- `actual_phase3_backend_fact`: The declared inspected candidate is 11fe8173a25ff7ac08bae42340ba7c6fae591be5 (tree b5f7bf960853c43344516031058f043ba45aaac5), still not an approved parent and with no authoritative Run. The clean coordination worktree was later observed at 8c4a77ccb70bceb1e8bf496ea528682df95a3405 (tree 3a9329f1a5f9c30f3ec1190457e09067c0c102d3); its 11-file delta changes financial arithmetic/lineage instrumentation, so the final reconciliation must bind and re-audit whichever parent is independently accepted.
- `product_semantic_constraint`: An inspected clean candidate is not an approved immutable parent.
- `provisional_contract_decision`: Keep the current SHA as INSPECTED_PHASE3_SOURCE_CANDIDATE only and recompute all EXISTING_BACKEND classifications if the approved parent differs.
- `wire_schema_requirement`: Bind approved source SHA/tree, authoritative Run ID, migration/database/API/event/route/build hashes, clean-tree receipt and both independent PASS audits as specified by decision draft section 1. None now; all existing-field classifications remain conditional.
- `persistence_requirement`: Later evidence must identify the exact accepted database and migration state.
- `route_requirement`: Bind the final hash-listed route inventory to the independently approved Phase 3 parent; no route is authorized by this preparation row.
- `event_requirement`: Bind the final raw event inventory and hashes to the approved parent.
- `frontend_normalization_requirement`: All 13 V17 normalized contracts bind the same parent.
- `acceptance_oracle`: Verify every hash/receipt names one immutable candidate and Run, then diff it against every Backend-fact statement; any mismatch remains open.
- `implementation_evidence_required`: Approved-parent identity, authoritative same-Run receipt, clean-tree receipt, migration/API/event hashes, and both independent audit PASS receipts.
- `blocking_dependency`: Approved Phase 3 parent and Backend/Financial Semantics independent PASS receipts.
- `final_close_condition`: The later delta binds and verifies the immutable approved parent with no unexplained drift.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: NOT_APPLICABLE_TO_THIS_ROW
- `requires_approved_phase3_parent`: `true`
- `requires_implementation_evidence`: `false`
- `affected_scenes`: `SCENE-01..04`

### UAC-002 — Governed V17 normalized-contract authority for Backend freeze

- `uac_id`: UAC-002
- `title`: Governed V17 normalized-contract authority for Backend freeze
- `current_state`: WAITING_FOR_FINAL_V17_CONTRACT
- `decision_owner`: Frontend V17 governance owner and Phase 4 Backend Contract Coordinator
- `mapped_backend_blockers`: `P4-BLOCKER-01..08`
- `mapped_bd_dependencies`: `BD-001..012`
- `mapped_frontend_contracts`: `ALL_13_V17_NORMALIZED_CONTRACTS`
- `mapped_frontend_conflict_cluster`: `1 Prepare Scheme vs Plan/Tasks`, `2 Confirm/start state and route`, `3 Durable idempotency`, `4 Progress/enums`, `5 Runtime event semantics`, `6 Browser SSE protocol`, `7 Financial Review projection`, `8 Artifact semantics`, `9 Financial/Object projection`
- `mapped_p4_be`: `P4-BE-001..030 integration mappings`
- `mapped_p4_e2e`: `P4-E2E-001..014`, `P4-E2E-016..061 Core variants`, `P4-E2E-063..096`, `P4-E2E-098`, `P4-E2E-101..102`, `P4-E2E-105..106`
- `mapped_p4_sse`: `P4-SSE-001..020`
- `mapped_p4_id`: `P4-ID-001..020`, `P4-ID-023..028`
- `actual_phase3_backend_fact`: V17 is PREPARATION_COMPLETE_BLOCKED/DRAFT_CHANGE; 13 contracts and BD-001..012 exist without approved hash-bound input.
- `product_semantic_constraint`: Backend cannot guess V17 representation semantics and V17 implementation cannot be a circular freeze prerequisite.
- `provisional_contract_decision`: Require an approved hash-bound V17 contract-input package, not an implemented V17 Candidate SHA.
- `wire_schema_requirement`: Bind approved FCR revision, corrected manifest, 13 schemas, rename/nullability/unknown rules, Scene/interaction dispositions and BD-001..012 per decision draft section 3. None directly; constrains every public wire projection.
- `persistence_requirement`: None directly.
- `route_requirement`: Bind all 13 normalized contracts to exact public routes or an explicit unavailable boundary in the approved V17 contract-input package.
- `event_requirement`: Bind RuntimeEventNormalizedV1, ConnectionState and the complete raw-event map to the approved V17 package.
- `frontend_normalization_requirement`: Establishes the sole governed V17 consumer input to final reconciliation.
- `acceptance_oracle`: Verify approval, hashes, completeness, absence of a governance cycle and field-level parity with the final Backend contract.
- `implementation_evidence_required`: Approved and hash-bound V17 contract-input package; V17 implementation evidence remains a later promotion input.
- `blocking_dependency`: Approved hash-bound V17 contract-input package and readiness decision.
- `final_close_condition`: The later delta cites the package hash and has no Backend/V17 mismatch.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: NOT_APPLICABLE_TO_THIS_ROW
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `false`
- `affected_scenes`: `SCENE-01..04`

### UAC-003 — API, event and route version negotiation

- `uac_id`: UAC-003
- `title`: API, event and route version negotiation
- `current_state`: RESOLVED_PROVISIONALLY
- `decision_owner`: Phase 4 Backend API/Event Contract owner
- `mapped_backend_blockers`: `P4-BLOCKER-01..08`
- `mapped_bd_dependencies`: `BD-001..012`
- `mapped_frontend_contracts`: `ALL_13_V17_NORMALIZED_CONTRACTS`
- `mapped_frontend_conflict_cluster`: `1 Prepare Scheme vs Plan/Tasks`, `2 Confirm/start state and route`, `3 Durable idempotency`, `4 Progress/enums`, `5 Runtime event semantics`, `6 Browser SSE protocol`, `7 Financial Review projection`, `8 Artifact semantics`, `9 Financial/Object projection`
- `mapped_p4_be`: `P4-BE-001..030 versioned routes`
- `mapped_p4_e2e`: `P4-E2E-001..014`, `P4-E2E-016..061 Core variants`, `P4-E2E-063..096`, `P4-E2E-098`, `P4-E2E-101..102`, `P4-E2E-105..106`
- `mapped_p4_sse`: `P4-SSE-001..020`
- `mapped_p4_id`: `P4-ID-001..020`, `P4-ID-023..028`
- `actual_phase3_backend_fact`: Stable /api routes expose unversioned public DTOs/events and implement no request negotiation.
- `product_semantic_constraint`: One deterministic V1 protocol fails closed without downgrade or duplicate /v1 routes.
- `provisional_contract_decision`: Adopt VersionProtocolV1 in decision draft section 4.
- `wire_schema_requirement`: Absent or exact X-Phase4-Contract-Version=phase4-core/v1 selects V1; all other forms return pre-mutation 409 SCHEMA_INCOMPATIBLE; success echoes schema/event tokens and SSE rejects before headers. Version fields are projections; negotiation validation is required transport behavior.
- `persistence_requirement`: Persist payload versions only where deterministic replay requires them.
- `route_requirement`: Apply VersionProtocolV1 to every /api JSON route and the SSE route; do not create a duplicate /v1 path family.
- `event_requirement`: Every normalized event carries event_contract_version and payload_schema_version; request negotiation failures occur before streaming.
- `frontend_normalization_requirement`: All V17 contracts send/validate exact tokens and fail closed.
- `acceptance_oracle`: Exercise absent, exact, empty, malformed, repeated, comma-list and unsupported tokens on JSON/SSE and assert exact success headers or zero-mutation/zero-frame 409.
- `implementation_evidence_required`: Required for final closure: Exercise absent, exact, empty, malformed, repeated, comma-list and unsupported tokens on JSON/SSE and assert exact success headers or zero-mutation/zero-frame 409.
- `blocking_dependency`: Final publication with UAC-002 and implementation evidence.
- `final_close_condition`: Backend/V17 adopt section 4 and every negotiation test passes.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01..04`

### UAC-004 — SSE cursor-family, cursor-ahead and terminal-cursor behavior

- `uac_id`: UAC-004
- `title`: SSE cursor-family, cursor-ahead and terminal-cursor behavior
- `current_state`: RESOLVED_PROVISIONALLY
- `decision_owner`: Phase 4 Backend Event/SSE Contract owner
- `mapped_backend_blockers`: `P4-BLOCKER-02`, `P4-BLOCKER-03`
- `mapped_bd_dependencies`: `BD-003`
- `mapped_frontend_contracts`: `ConnectionState`, `NormalizedRuntimeEventV1`, `RunProjection`, `ErrorEnvelope`
- `mapped_frontend_conflict_cluster`: `6 Browser SSE protocol`
- `mapped_p4_be`: `P4-BE-011..017`
- `mapped_p4_e2e`: `P4-E2E-073`, `P4-E2E-079..081`, `P4-E2E-084..088`, `P4-E2E-098`
- `mapped_p4_sse`: `P4-SSE-007..009`, `P4-SSE-017..018`
- `mapped_p4_id`: `P4-ID-006`, `P4-ID-009`, `P4-ID-023`, `P4-ID-026..027`
- `actual_phase3_backend_fact`: Current int parsing is permissive, has no tail check and occurs after stream construction; ahead/terminal-equal can heartbeat forever.
- `product_semantic_constraint`: Invalid input never replays from zero, switches Run, discloses a foreign event or heartbeats forever.
- `provisional_contract_decision`: Adopt CursorProtocolV1 in decision draft section 10.
- `wire_schema_requirement`: Preflight before SSE headers; canonical numeric and bounded Run-local opaque cursors only; invalid=400, ahead=409, terminal-equal=200 SSE with terminal headers, zero frames and immediate close. Required preflight/terminal headers; no new cursor entity.
- `persistence_requirement`: Read durable same-Run tail/terminal without mutation; restart-stable replay.
- `route_requirement`: GET /api/research-runs/{run_id}/events performs cursor and terminal preflight before committing SSE headers.
- `event_requirement`: Cursor resolution, replay, heartbeat and terminal-at-cursor behavior consume no fabricated business event.
- `frontend_normalization_requirement`: ConnectionState uses fetch-stream, one snapshot recovery path and terminal close.
- `acceptance_oracle`: Cover all numeric/opaque malformed/foreign/ahead/terminal classes before/after restart and assert suffix/status/headers/frames/zero mutation.
- `implementation_evidence_required`: Required for final closure: Cover all numeric/opaque malformed/foreign/ahead/terminal classes before/after restart and assert suffix/status/headers/frames/zero mutation.
- `blocking_dependency`: Final event/error publication and executable cursor/restart evidence.
- `final_close_condition`: Final contract adopts section 10 and the cursor matrix passes.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01..04`

### UAC-005 — Immutable confirm outcome and transport replay metadata

- `uac_id`: UAC-005
- `title`: Immutable confirm outcome and transport replay metadata
- `current_state`: RESOLVED_PROVISIONALLY
- `decision_owner`: Phase 4 Backend Prepare/Confirm Contract owner
- `mapped_backend_blockers`: `P4-BLOCKER-04`
- `mapped_bd_dependencies`: `BD-007`, `BD-008`
- `mapped_frontend_contracts`: `PreparedResearchDraft`, `ConfirmAndStartResult`, `ErrorEnvelope`
- `mapped_frontend_conflict_cluster`: `1 Prepare Scheme vs Plan/Tasks`, `2 Confirm/start state and route`, `3 Durable idempotency`
- `mapped_p4_be`: `P4-BE-004..005`
- `mapped_p4_e2e`: `P4-E2E-025..026`, `P4-E2E-075`
- `mapped_p4_sse`: none
- `mapped_p4_id`: `P4-ID-004..005`, `P4-ID-009`
- `actual_phase3_backend_fact`: Confirm uses optional process-local unbound idempotency and schedules BackgroundTasks even on replay.
- `product_semantic_constraint`: One confirmation has one immutable admission; replay metadata is per response attempt.
- `provisional_contract_decision`: Adopt split ConfirmRunResponseV1 in decision draft section 8.
- `wire_schema_requirement`: First=201/replayed false; same scope/method/route/key/hash=200/replayed true with identical admission; changed hash or consumed/version/expired draft has exact 409 reason and creates no Run. Add immutable admission/response-meta and durable request-hash/key/draft facts.
- `persistence_requirement`: Atomically persist outcome and scoped key/hash with draft consumption and Run creation.
- `route_requirement`: Retain and strengthen POST /api/research-runs/prepare and POST /api/research-runs with the exact Prepare and Confirm schemas; there is no second Start route.
- `event_requirement`: Prepare emits no runtime event; successful Confirm produces exactly one run.created and one run.started through durable admission.
- `frontend_normalization_requirement`: ConfirmAndStartResult separates admission from response metadata.
- `acceptance_oracle`: Double-click, response-loss, key/body conflicts and restart prove one draft/Run/admission and immutable admission.
- `implementation_evidence_required`: Required for final closure: Double-click, response-loss, key/body conflicts and restart prove one draft/Run/admission and immutable admission.
- `blocking_dependency`: Bind UAC-006 literal scope key LOCAL_SINGLE_USER, UAC-007 admission, final V17 Confirm contract and implementation evidence.
- `final_close_condition`: Final schema and restart/idempotency evidence prove one immutable admission.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01`

### UAC-006 — Authentication mode, actor/tenant scope and denial disclosure

- `uac_id`: UAC-006
- `title`: Authentication mode, actor/tenant scope and denial disclosure
- `current_state`: RESOLVED_PROVISIONALLY
- `decision_owner`: Project owner; PROJECT_OWNER_DECISION_APPLIED=phase4-local-single-user-trusted/v1; recorded by Phase 4 Backend Contract Coordinator
- `mapped_backend_blockers`: `P4-BLOCKER-01..07`
- `mapped_bd_dependencies`: `BD-001`, `BD-003..009`, `BD-011`
- `mapped_frontend_contracts`: `ALL_PROTECTED_V17_CONTRACTS`
- `mapped_frontend_conflict_cluster`: `1 Prepare Scheme vs Plan/Tasks`, `2 Confirm/start state and route`, `3 Durable idempotency`, `6 Browser SSE protocol`, `7 Financial Review projection`, `8 Artifact semantics`, `9 Financial/Object projection`
- `mapped_p4_be`: `P4-BE-001..030`
- `mapped_p4_e2e`: `P4-E2E-001..014`, `P4-E2E-016..061 Core variants`, `P4-E2E-063..096`, `P4-E2E-098`, `P4-E2E-101..102`, `P4-E2E-105..106`
- `mapped_p4_sse`: `P4-SSE-001..020`
- `mapped_p4_id`: `P4-ID-001..020`, `P4-ID-023..028`
- `actual_phase3_backend_fact`: No auth middleware, principal/workspace/tenant model or tenant columns exist; approved local-MVP semantics do not mandate auth.
- `product_semantic_constraint`: Trusted local single-user removes account authentication only; exact O/R/resource identity remains mandatory, client authority fields and cross-object/run fallback are prohibited.
- `provisional_contract_decision`: Adopt LOCAL_SINGLE_USER_TRUSTED_V1 exactly as recorded by PHASE4_ACCESS_MODE_DECISION_V1: no auth/provider/ownership model, server scope LOCAL_SINGLE_USER and public auth deferred.
- `wire_schema_requirement`: No authority fields in request JSON; cache/idempotency use literal LOCAL_SINGLE_USER plus exact identity; normal local mode emits no 401/403; missing=404 NOT_FOUND and foreign nested identity=safe 404 IDENTITY_MISMATCH. No auth middleware or principal/tenant/user/workspace/ACL table; only server-internal effective-scope context where required.
- `persistence_requirement`: No access-control migration; durable idempotency stores LOCAL_SINGLE_USER and all resources retain exact Object/Run validation.
- `route_requirement`: Current governed profile is LOCAL_SINGLE_USER_TRUSTED_V1: no account-auth route behavior; every route still performs exact O/R/child closure under server scope LOCAL_SINGLE_USER. A future protected profile requires authentication before an authorization-scoped concealed lookup.
- `event_requirement`: Under the current local profile, exact Run isolation precedes streaming; a future protected profile authenticates before cursor/resource resolution. Events never carry authority.
- `frontend_normalization_requirement`: V17 sends no credentials or principal/user/tenant/workspace authority fields and fails closed on identity/schema/availability/integrity.
- `acceptance_oracle`: Submit prohibited authority fields, key/cache collisions, foreign resource/artifact IDs and copied refs; prove fields grant no authority, exact scope/identity keys, no normal 401/403, exact safe errors and no fallback/disclosure/mutation.
- `implementation_evidence_required`: Required for final closure: Submit prohibited authority fields, key/cache collisions, foreign resource/artifact IDs and copied refs; prove fields grant no authority, exact scope/identity keys, no normal 401/403, exact safe errors and no fallback/disclosure/mutation.
- `blocking_dependency`: Final freeze must hash-bind PHASE4_ACCESS_MODE_DECISION_V1; implementation evidence remains pending but does not block semantic freeze.
- `final_close_condition`: Final delta binds the owner decision and later acceptance proves exact identity, scope, artifact and denial behavior without invented access entities.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01..04`

### UAC-007 — Durable admission, lease/redelivery and exactly-one logical Run start

- `uac_id`: UAC-007
- `title`: Durable admission, lease/redelivery and exactly-one logical Run start
- `current_state`: WAITING_FOR_IMPLEMENTATION_EVIDENCE
- `decision_owner`: Phase 4 Backend Prepare/Confirm and Runtime Persistence owners
- `mapped_backend_blockers`: `P4-BLOCKER-03`, `P4-BLOCKER-04`
- `mapped_bd_dependencies`: `BD-001`, `BD-003`, `BD-008`
- `mapped_frontend_contracts`: `ConfirmAndStartResult`, `RunProjection`, `NormalizedRuntimeEventV1`
- `mapped_frontend_conflict_cluster`: `2 Confirm/start state and route`, `3 Durable idempotency`
- `mapped_p4_be`: `P4-BE-004..006`, `P4-BE-017`
- `mapped_p4_e2e`: `P4-E2E-025..026`, `P4-E2E-075`, `P4-E2E-087`, `P4-E2E-098`
- `mapped_p4_sse`: `P4-SSE-001`, `P4-SSE-007..009`, `P4-SSE-017`
- `mapped_p4_id`: `P4-ID-004..005`, `P4-ID-009`, `P4-ID-023`
- `actual_phase3_backend_fact`: Confirm/plan commits are split and FastAPI BackgroundTasks is process-local; no durable admission, lease fence or start-effect record exists.
- `product_semantic_constraint`: A committed confirmation survives restart and yields one logical start under at-least-once delivery.
- `provisional_contract_decision`: Adopt RunSchedulerAdmissionV1 and its fenced lifecycle in decision draft section 9.
- `wire_schema_requirement`: Atomically persist confirmation facts and one PENDING admission; current lease generation alone writes; first start commits RUNNING/time/one event; redelivery reconciles; permanent failure uses UAC-011. Add exact admission fields, uniqueness, worker claim/ack and start-effect identity.
- `persistence_requirement`: One admission transaction plus durable lease/attempt/start/ack/failure facts keyed uniquely by Run.
- `route_requirement`: POST /api/research-runs atomically commits one immutable admission and durable outbox record after validating the draft; no second Start endpoint exists.
- `event_requirement`: Admission yields exactly one logical run.created/run.started sequence; every later failure goes through UAC-011.
- `frontend_normalization_requirement`: Confirm, projection and stream observe one Run and one start.
- `acceptance_oracle`: Cut around confirm/lease/start/ack, redeliver/restart and assert one draft, outcome, Run, plan, admission, created/start event and start time.
- `implementation_evidence_required`: Required for final closure: Cut around confirm/lease/start/ack, redeliver/restart and assert one draft, outcome, Run, plan, admission, created/start event and start time.
- `blocking_dependency`: Durable admission implementation and fault/restart evidence.
- `final_close_condition`: Final contract includes section 9 and tests prove one start at every cut.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01`

### UAC-008 — Projection revision, sequence, progress, graph and path-change ownership

- `uac_id`: UAC-008
- `title`: Projection revision, sequence, progress, graph and path-change ownership
- `current_state`: RESOLVED_PROVISIONALLY
- `decision_owner`: Phase 4 Backend Projection Contract owner
- `mapped_backend_blockers`: `P4-BLOCKER-01`, `P4-BLOCKER-02`, `P4-BLOCKER-08`
- `mapped_bd_dependencies`: `BD-001`, `BD-002`, `BD-009`, `BD-010`, `BD-012`
- `mapped_frontend_contracts`: `GlobalRunCollectionProjection`, `RunProjection`, `NormalizedRuntimeEventV1`
- `mapped_frontend_conflict_cluster`: `4 Progress/enums`, `5 Runtime event semantics`, `9 Financial/Object projection`
- `mapped_p4_be`: `P4-BE-001`, `P4-BE-007..010`, `P4-BE-019`
- `mapped_p4_e2e`: `P4-E2E-002`, `P4-E2E-005..007`, `P4-E2E-026..036`, `P4-E2E-060..061`, `P4-E2E-076..077`, `P4-E2E-079`, `P4-E2E-081`, `P4-E2E-083..084`, `P4-E2E-087..089`, `P4-E2E-098`, `P4-E2E-105`
- `mapped_p4_sse`: `P4-SSE-002`, `P4-SSE-004`, `P4-SSE-007`, `P4-SSE-009`, `P4-SSE-011..014`, `P4-SSE-017`, `P4-SSE-020`
- `mapped_p4_id`: `P4-ID-001`, `P4-ID-004`, `P4-ID-006..020`, `P4-ID-023`, `P4-ID-025..027`
- `actual_phase3_backend_fact`: Task ratio and actual graph version/history exist; durable revision/sequence, aggregate progress and public path changes do not.
- `product_semantic_constraint`: Backend owns projection truth; frontend may rename/render but not derive business state.
- `provisional_contract_decision`: Adopt the ownership table and ACTUAL_TASK_MEAN_V1 algorithm in decision draft section 11.
- `wire_schema_requirement`: Backend wire supplies revision/sequence/Task ratio/Run fraction+method/graph/path changes; adapter derives only percent=fraction*100; source Correction/Replan owns each path ID. Add durable revision and progress/path projections; remove Backend percent duplication.
- `persistence_requirement`: Transactional revision and retained exact Correction/Replan operations.
- `route_requirement`: GET /api/research-runs and GET /api/research-runs/{run_id}/projection expose the frozen collection and atomic projection fields; the light canonical Run read is not the browser bootstrap.
- `event_requirement`: path_changes is Backend-owned projection truth; RuntimeEvents never fabricate a change or Task.
- `frontend_normalization_requirement`: Collection/projection consume fraction/method/path changes; one shared adapter derives percent.
- `acceptance_oracle`: Compare DB/list/detail/adapter across every mutation/no-op/rollback/restart; prove exact mean, path identity and immutable plan.
- `implementation_evidence_required`: Required for final closure: Compare DB/list/detail/adapter across every mutation/no-op/rollback/restart; prove exact mean, path identity and immutable plan.
- `blocking_dependency`: Final schema and revision/projection implementation evidence.
- `final_close_condition`: Final contract carries section 11 and mutation/ownership tests pass.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01..04`

### UAC-009 — Atomic projection/event watermark publication

- `uac_id`: UAC-009
- `title`: Atomic projection/event watermark publication
- `current_state`: WAITING_FOR_IMPLEMENTATION_EVIDENCE
- `decision_owner`: Phase 4 Backend Persistence/Unit-of-Work owner
- `mapped_backend_blockers`: `P4-BLOCKER-02`, `P4-BLOCKER-03`
- `mapped_bd_dependencies`: `BD-001`, `BD-003`, `BD-012`
- `mapped_frontend_contracts`: `RunProjection`, `GlobalRunCollectionProjection`, `NormalizedRuntimeEventV1`, `ConnectionState`
- `mapped_frontend_conflict_cluster`: `4 Progress/enums`, `5 Runtime event semantics`, `6 Browser SSE protocol`
- `mapped_p4_be`: `P4-BE-007..009`, `P4-BE-017`, `P4-BE-019`
- `mapped_p4_e2e`: `P4-E2E-026..036`, `P4-E2E-075..077`, `P4-E2E-079..081`, `P4-E2E-083..084`, `P4-E2E-087..089`, `P4-E2E-098`, `P4-E2E-105`
- `mapped_p4_sse`: `P4-SSE-002`, `P4-SSE-004`, `P4-SSE-007..009`, `P4-SSE-011..014`, `P4-SSE-017`, `P4-SSE-020`
- `mapped_p4_id`: `P4-ID-001`, `P4-ID-004..020`, `P4-ID-023`, `P4-ID-025..027`
- `actual_phase3_backend_fact`: Event and aggregate saves use separate transactions; success events may precede aggregate save and no atomic projection watermark exists.
- `product_semantic_constraint`: A 200 snapshot never mixes commit times or claims/omits facts inconsistently with its watermark.
- `provisional_contract_decision`: Adopt the serialized PostgreSQL/MVCC protocol in decision draft section 12.
- `wire_schema_requirement`: Commit aggregate/children/events/one revision together; read greatest reflected sequence in one MVCC snapshot; exact ETag; admission/terminal atomic; rollback/no-op invisible. Durable revision, atomic route and event writer participating in caller unit-of-work.
- `persistence_requirement`: Per-Run PostgreSQL transaction replaces split commits.
- `route_requirement`: GET /api/research-runs/{run_id}/projection reads one event-consistent MVCC snapshot; collection projection uses the same ordering and watermark semantics.
- `event_requirement`: Aggregate mutation, projection revision and corresponding RuntimeEvent watermark commit atomically or with proven equivalent consistency.
- `frontend_normalization_requirement`: Projection/collection/event/ConnectionState use sole revision-watermark handoff.
- `acceptance_oracle`: Pause/fail at each write/commit cut and concurrently read; assert coherent snapshot, N+1 replay, invisible rollback, one revision and restart equality.
- `implementation_evidence_required`: Required for final closure: Pause/fail at each write/commit cut and concurrently read; assert coherent snapshot, N+1 replay, invisible rollback, one revision and restart equality.
- `blocking_dependency`: PostgreSQL unit-of-work implementation and race/rollback/restart evidence.
- `final_close_condition`: Final contract adopts section 12 and independent evidence proves no torn projection.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01..04`

### UAC-010 — Total status, availability, event and payload-version mapping

- `uac_id`: UAC-010
- `title`: Total status, availability, event and payload-version mapping
- `current_state`: RESOLVED_PROVISIONALLY
- `decision_owner`: Phase 4 Backend Projection/Event Contract owner
- `mapped_backend_blockers`: `P4-BLOCKER-03`, `P4-BLOCKER-08`
- `mapped_bd_dependencies`: `BD-002`, `BD-003`, `BD-010`, `BD-012`
- `mapped_frontend_contracts`: `RunProjection`, `NormalizedRuntimeEventV1`, `ConnectionState`, `FinancialReviewProjection`, `ClaimTraceProjection/TraceBundle`, `Availability`
- `mapped_frontend_conflict_cluster`: `4 Progress/enums`, `5 Runtime event semantics`, `6 Browser SSE protocol`, `7 Financial Review projection`
- `mapped_p4_be`: `P4-BE-001`, `P4-BE-007`, `P4-BE-010`, `P4-BE-018..019`, `P4-BE-023`
- `mapped_p4_e2e`: `P4-E2E-002`, `P4-E2E-005..007`, `P4-E2E-026..036`, `P4-E2E-040..043`, `P4-E2E-053`, `P4-E2E-060..061`, `P4-E2E-072..073`, `P4-E2E-076..077`, `P4-E2E-083..084`, `P4-E2E-087..091`, `P4-E2E-094..095`, `P4-E2E-098`, `P4-E2E-105`
- `mapped_p4_sse`: `P4-SSE-002`, `P4-SSE-004..005`, `P4-SSE-010..017`, `P4-SSE-019..020`
- `mapped_p4_id`: `P4-ID-001`, `P4-ID-004`, `P4-ID-006..020`, `P4-ID-023`, `P4-ID-025..027`
- `actual_phase3_backend_fact`: Phase 3 has rich raw enums, 55 event names and heterogeneous unversioned payloads; eight names lack approved producer schemas.
- `product_semantic_constraint`: Unknown values never cast, fabricate state or advance the reducer.
- `provisional_contract_decision`: Adopt all total maps and dispositions in decision draft section 13.
- `wire_schema_requirement`: Versioned exact event identity/payload; 55 closed dispositions; eight named unsupported outputs fail; five frontend-only labels are never RuntimeEvents; sparse graphs force refresh. Total projections/versioned envelope plus durable missing failure facts where necessary.
- `persistence_requirement`: Retain deterministic replay data and safe quarantine metadata/hash.
- `route_requirement`: Every versioned JSON/SSE route uses the total enum maps; the event route uses RuntimeEventNormalizedV1.
- `event_requirement`: All 55 raw event values have an exact PATCH_PROJECTION, REFRESH_PROJECTION, OBSERVATION_ONLY, TERMINAL, or UNSUPPORTED disposition.
- `frontend_normalization_requirement`: Reducers use total maps and one recovery path without Task fabrication.
- `acceptance_oracle`: Exhaust types/statuses/payloads and inject unknown/version/identity/duplicate/sparse cases; assert exact mapping or zero-mutation recovery.
- `implementation_evidence_required`: Required for final closure: Exhaust types/statuses/payloads and inject unknown/version/identity/duplicate/sparse cases; assert exact mapping or zero-mutation recovery.
- `blocking_dependency`: Final event/status publication and implementation/unknown-value evidence.
- `final_close_condition`: Every raw value has one disposition and mapped suites prove normalization/fail-closed recovery.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01..04`

### UAC-011 — All-path terminal failure and exactly-one durable run.failed

- `uac_id`: UAC-011
- `title`: All-path terminal failure and exactly-one durable run.failed
- `current_state`: WAITING_FOR_IMPLEMENTATION_EVIDENCE
- `decision_owner`: Phase 4 Backend Runtime/Release Persistence owner
- `mapped_backend_blockers`: `P4-BLOCKER-03`, `P4-BLOCKER-05..07`
- `mapped_bd_dependencies`: `BD-001`, `BD-003..005`, `BD-010..011`
- `mapped_frontend_contracts`: `RunProjection`, `NormalizedRuntimeEventV1`, `Availability`, `FinancialReviewProjection`, `ReportArtifactGroup`, `ReleasedObjectCoreProjection`
- `mapped_frontend_conflict_cluster`: `2 Confirm/start state and route`, `3 Durable idempotency`, `5 Runtime event semantics`, `6 Browser SSE protocol`, `7 Financial Review projection`, `8 Artifact semantics`, `9 Financial/Object projection`
- `mapped_p4_be`: `P4-BE-006`, `P4-BE-015..017`
- `mapped_p4_e2e`: `P4-E2E-025..026`, `P4-E2E-075`, `P4-E2E-079..081`, `P4-E2E-085..087`, `P4-E2E-092..096`, `P4-E2E-098`, `P4-E2E-105`
- `mapped_p4_sse`: `P4-SSE-002`, `P4-SSE-004`, `P4-SSE-007..009`, `P4-SSE-013`, `P4-SSE-015..017`
- `mapped_p4_id`: `P4-ID-004..005`, `P4-ID-008..020`, `P4-ID-023`, `P4-ID-025..027`
- `actual_phase3_backend_fact`: Scheduler/service failure paths can omit or duplicate terminal effects and split commits prevent atomic proof.
- `product_semantic_constraint`: Every admitted unsuccessful terminal Run has one safe public terminal truth.
- `provisional_contract_decision`: Adopt TerminalFailureV1 in decision draft section 14.
- `wire_schema_requirement`: FAILED/CANCELLED iff one last run.failed, zero run.completed and matching status; one idempotent finalizer publishes state/failure/availability/event/revision/watermark atomically for every enumerated stage. Safe terminal record/payload and unique finalizer effect; reuse run.failed for cancellation.
- `persistence_requirement`: Unique transactional terminal effect and restart reconciliation.
- `route_requirement`: Confirm/admission, projection, release and SSE paths share one terminal finalizer; no new terminal route or event name is introduced.
- `event_requirement`: Exactly one terminal raw run.failed or run.completed exists; no business event follows it.
- `frontend_normalization_requirement`: Projection/events/result/review/proof/artifact availability converge to one terminal failure and no Results.
- `acceptance_oracle`: Inject every stage plus duplicates/restart; assert one last failure event, zero success, matching state, no PENDING terminal resource or released exposure.
- `implementation_evidence_required`: Required for final closure: Inject every stage plus duplicates/restart; assert one last failure event, zero success, matching state, no PENDING terminal resource or released exposure.
- `blocking_dependency`: Atomic finalizer implementation and all-path fault/restart evidence.
- `final_close_condition`: Section 14 is final and every failure class proves exactly one terminal effect.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01..04 negative variants`

### UAC-012 — Closed Claim detail and typed Judgment availability

- `uac_id`: UAC-012
- `title`: Closed Claim detail and typed Judgment availability
- `current_state`: RESOLVED_PROVISIONALLY
- `decision_owner`: Phase 4 Backend Contract Coordinator and Financial Semantics owner
- `mapped_backend_blockers`: `P4-BLOCKER-05`
- `mapped_bd_dependencies`: `BD-005`, `BD-006`
- `mapped_frontend_contracts`: `ClaimTraceProjection/TraceBundle`, `ReleasedFinancialMetric`, `Availability`
- `mapped_frontend_conflict_cluster`: `7 Financial Review projection`, `9 Financial/Object projection`
- `mapped_p4_be`: `P4-BE-022`, `P4-BE-024`
- `mapped_p4_e2e`: `P4-E2E-042`, `P4-E2E-048..054`, `P4-E2E-072..073`, `P4-E2E-094..095`, `P4-E2E-098`, `P4-E2E-105`
- `mapped_p4_sse`: none
- `mapped_p4_id`: `P4-ID-011..020`, `P4-ID-023`, `P4-ID-025..028`
- `actual_phase3_backend_fact`: Typed released Claim/metric refs exist; no Claim route exists and durable Judgment bodies remain generic JSON.
- `product_semantic_constraint`: Financial values/lineage are Backend truth; Judgment is interpretation; no client joins or hidden reasoning.
- `provisional_contract_decision`: Adopt ClaimDetailV1/JudgmentAvailabilityV1 in decision draft section 15.
- `wire_schema_requirement`: Exact route/schema/cardinality/order/safe details/refs/X/L/anchors; generic Judgment is UNAVAILABLE/JUDGMENT_DETAIL_NOT_TYPED until typed persistence exists. Joins/wrappers are projections; route is additive; typed Judgment detail requires a Backend field.
- `persistence_requirement`: Existing released Claim remains authority; AVAILABLE Judgment requires typed same-Run ID persistence.
- `route_requirement`: ADD GET /api/research-runs/{run_id}/claims/{claim_id}.
- `event_requirement`: No new event; Claim relations come from explicit persisted records and projection joins.
- `frontend_normalization_requirement`: Trace/metric/availability preserve exact IDs and unavailable detail.
- `acceptance_oracle`: Compare exact C/M/K/E/T/V/P/X/L ordering and test multi-Task, unavailable Judgment, restart, substitutions and forbidden fields.
- `implementation_evidence_required`: Required for final closure: Compare exact C/M/K/E/T/V/P/X/L ordering and test multi-Task, unavailable Judgment, restart, substitutions and forbidden fields.
- `blocking_dependency`: UAC-008/009/013/014, approved V17 and route/typed-detail evidence.
- `final_close_condition`: Parent delta confirms facts, schema/hash is adopted and mapped positive/negative/restart tests pass.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01`, `SCENE-03`, `SCENE-04`

### UAC-013 — Durable Review Check identity, subject, correction, exception and A/B/C linkage

- `uac_id`: UAC-013
- `title`: Durable Review Check identity, subject, correction, exception and A/B/C linkage
- `current_state`: RESOLVED_PROVISIONALLY
- `decision_owner`: Phase 4 Backend Contract Coordinator and Financial Review owner
- `mapped_backend_blockers`: `P4-BLOCKER-05`
- `mapped_bd_dependencies`: `BD-006`, `BD-010`, `BD-011`
- `mapped_frontend_contracts`: `FinancialReviewProjection`, `ClaimTraceProjection/TraceBundle`
- `mapped_frontend_conflict_cluster`: `7 Financial Review projection`
- `mapped_p4_be`: `P4-BE-023..024`
- `mapped_p4_e2e`: `P4-E2E-040..043`, `P4-E2E-048..054`, `P4-E2E-072..073`, `P4-E2E-094..095`, `P4-E2E-098`, `P4-E2E-105`
- `mapped_p4_sse`: none
- `mapped_p4_id`: `P4-ID-011..020`, `P4-ID-023`, `P4-ID-025..028`
- `actual_phase3_backend_fact`: Review/Check basics exist; stable Check IDs, typed subjects, correction links, exception state/time and full Review projection do not.
- `product_semantic_constraint`: Review identity/history is Backend-durable and never frontend/event/text inferred; released A/B/C shares O/R/X/L.
- `provisional_contract_decision`: Adopt FinancialReviewProjectionV1 in decision draft section 16.
- `wire_schema_requirement`: Expanded review route with stable Checks, typed relations/transitions and exact live-null versus released-non-null X/L rules; never fabricate PASS. Check identity/relations/resolution are Backend fields; O/X/L/availability are projections.
- `persistence_requirement`: Persist Check facts before publication; aggregate event/Correction timestamps cannot substitute.
- `route_requirement`: Retain GET /api/research-runs/{run_id}/review-view, replace its response with FinancialReviewProjectionV1, and make live Review readable independently of release.
- `event_requirement`: review.started and review.resolved cause projection refresh; run-level review.resolved never resolves an individual check.
- `frontend_normalization_requirement`: FinancialReviewProjection and Trace consume exact status/IDs; verdict is only a rename.
- `acceptance_oracle`: Exercise duplicate codes, typed subjects, NONE/OPEN/RESOLVED, corrections, live/released and restart; reject invalid identities/history/X-L tuples.
- `implementation_evidence_required`: Required for final closure: Exercise duplicate codes, typed subjects, NONE/OPEN/RESOLVED, corrections, live/released and restart; reject invalid identities/history/X-L tuples.
- `blocking_dependency`: UAC-010, final V17 Review, durable Check migration/implementation and evidence.
- `final_close_condition`: Final schema plus restart-stable Check identity/history and mapped oracles pass.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01`, `SCENE-03`, `SCENE-04`

### UAC-014 — Exact same-Run Trace bundle and representation-scoped anchor manifest

- `uac_id`: UAC-014
- `title`: Exact same-Run Trace bundle and representation-scoped anchor manifest
- `current_state`: RESOLVED_PROVISIONALLY
- `decision_owner`: Phase 4 Backend Contract Coordinator and Trace/Report owners
- `mapped_backend_blockers`: `P4-BLOCKER-05`, `P4-BLOCKER-06`
- `mapped_bd_dependencies`: `BD-004`, `BD-006`
- `mapped_frontend_contracts`: `ClaimTraceProjection/TraceBundle`, `ReportArtifactGroup`
- `mapped_frontend_conflict_cluster`: `7 Financial Review projection`, `8 Artifact semantics`
- `mapped_p4_be`: `P4-BE-024..027`
- `mapped_p4_e2e`: `P4-E2E-045..054`, `P4-E2E-072..073`, `P4-E2E-094..096`, `P4-E2E-098`, `P4-E2E-105`
- `mapped_p4_sse`: none
- `mapped_p4_id`: `P4-ID-011..020`, `P4-ID-023`, `P4-ID-025..028`
- `actual_phase3_backend_fact`: Exact entity IDs exist separately; no Trace route, Claim graph, claim-event relation or representation anchor manifest exists.
- `product_semantic_constraint`: Every hop is explicit same-Run/Object/result/representation; no fallback or hidden CoT.
- `provisional_contract_decision`: Adopt TraceBundleV1 and scoped anchors in decision draft section 17.
- `wire_schema_requirement`: Exact route/cardinality/order plus manifest ID/hash/version/retention and per-format report, Review/check, Task and execution anchors; unavailable anchors disable navigation. Route/joins are additive/projection; anchor manifest and claim-event relation are Backend fields.
- `persistence_requirement`: Persist immutable manifest and explicit scoped anchor entries.
- `route_requirement`: ADD GET /api/research-runs/{run_id}/trace/{claim_id}.
- `event_requirement`: No synthetic anchor event; execution anchors cite safe existing event IDs through an explicit persisted Claim relation.
- `frontend_normalization_requirement`: Trace/Artifact consumers use exact IDs/per-format anchors and infer nothing.
- `acceptance_oracle`: Traverse all hops, verify hash/restart, substitute each entity/format/anchor and scan forbidden fields.
- `implementation_evidence_required`: Required for final closure: Traverse all hops, verify hash/restart, substitute each entity/format/anchor and scan forbidden fields.
- `blocking_dependency`: UAC-012/013, final Artifact/V17 contracts and renderer/projection evidence.
- `final_close_condition`: Schemas agree and immutable manifests pass positive/substitution/unavailable/integrity/restart tests.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01`, `SCENE-04`

### UAC-015 — Public artifact authorization-reference lifecycle and storage isolation

- `uac_id`: UAC-015
- `title`: Public artifact authorization-reference lifecycle and storage isolation
- `current_state`: WAITING_FOR_IMPLEMENTATION_EVIDENCE
- `decision_owner`: Phase 4 Backend Contract Coordinator, applied project-owner access decision and Artifact Delivery owner
- `mapped_backend_blockers`: `P4-BLOCKER-06`
- `mapped_bd_dependencies`: `BD-004`
- `mapped_frontend_contracts`: `ReportArtifactGroup`, `ErrorEnvelope`, `Availability`
- `mapped_frontend_conflict_cluster`: `6 Browser SSE protocol`, `8 Artifact semantics`
- `mapped_p4_be`: `P4-BE-025..027`, `P4-BE-030`
- `mapped_p4_e2e`: `P4-E2E-045..047`, `P4-E2E-072..073`, `P4-E2E-096`, `P4-E2E-098`
- `mapped_p4_sse`: none
- `mapped_p4_id`: `P4-ID-018..020`, `P4-ID-023`, `P4-ID-025..027`
- `actual_phase3_backend_fact`: Successful internal artifact facts exist; no public routes/auth/ref/revocation/retention or immutable delivery record exists.
- `product_semantic_constraint`: Locators/secrets stay internal; URL/ID is not authority; each request revalidates exact O/R/X/L/artifact; formats never substitute.
- `provisional_contract_decision`: Adopt non-bearer same-origin authorized_ref and integrity-before-delivery protocol in decision draft section 18.
- `wire_schema_requirement`: Exact metadata/content routes and ordered identity/auth/availability/storage/integrity checks; no Range/redirect; exact headers and safe zero-protected-byte denial. Routes, policy hook, scoped lookup/storage port/buffering/safe errors; omit internal ref recursively.
- `persistence_requirement`: No URL token table; persist policy and revocation/retention/quarantine transitions; successful metadata immutable.
- `route_requirement`: ADD GET /api/research-runs/{run_id}/artifacts and sole bytes route GET /api/research-runs/{run_id}/artifacts/{artifact_id}/content; no redirect or storage locator.
- `event_requirement`: Artifact delivery is read-only and does not emit business events; revocation/quarantine changes projection revision.
- `frontend_normalization_requirement`: authorizedRef is current relative AVAILABLE locator, never constructed/cached as authority or cross-format substituted.
- `acceptance_oracle`: Test expiry/revocation/retention/foreign/substitution/tamper/cache/restart and assert exact bytes or zero-byte safe denial without locator leakage.
- `implementation_evidence_required`: Required for final closure: Test expiry/revocation/retention/foreign/substitution/tamper/cache/restart and assert exact bytes or zero-byte safe denial without locator leakage.
- `blocking_dependency`: Bind the applied UAC-006 local profile, UAC-016/018, final V17 Artifact and route/identity/cache/storage evidence.
- `final_close_condition`: Final access/error/artifact contract and mapped tests prove authorization, isolation, integrity and restart.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01`, `SCENE-04`

### UAC-016 — Independent HTML/PDF generation, durable failure and availability transitions

- `uac_id`: UAC-016
- `title`: Independent HTML/PDF generation, durable failure and availability transitions
- `current_state`: WAITING_FOR_IMPLEMENTATION_EVIDENCE
- `decision_owner`: Phase 4 Backend Contract Coordinator, Artifact Generation and Release owners
- `mapped_backend_blockers`: `P4-BLOCKER-06`, `P4-BLOCKER-07`
- `mapped_bd_dependencies`: `BD-004`, `BD-001`, `BD-009`
- `mapped_frontend_contracts`: `ReportArtifactGroup`, `Availability`, `RunProjection`, `ReleasedObjectCoreProjection`
- `mapped_frontend_conflict_cluster`: `8 Artifact semantics`, `9 Financial/Object projection`
- `mapped_p4_be`: `P4-BE-025..028`
- `mapped_p4_e2e`: `P4-E2E-003`, `P4-E2E-045..047`, `P4-E2E-057`, `P4-E2E-059 Core`, `P4-E2E-060..061`, `P4-E2E-070`, `P4-E2E-072..073`, `P4-E2E-076`, `P4-E2E-092`, `P4-E2E-094`, `P4-E2E-096`, `P4-E2E-098`
- `mapped_p4_sse`: none
- `mapped_p4_id`: `P4-ID-001`, `P4-ID-006`, `P4-ID-013..020`, `P4-ID-023`, `P4-ID-025..027`
- `actual_phase3_backend_fact`: Only successful coupled HTML/PDF facts exist; service releases before acceptance-runner artifact publication and has no attempt/failure state.
- `product_semantic_constraint`: Formats have independent identities/states; HTML required, PDF optional terminal; no attempt is NOT_GENERATED and failed attempt is FAILED.
- `provisional_contract_decision`: Adopt artifact policy, representation/attempt schemas and transitions in decision draft section 19.
- `wire_schema_requirement`: One HTML/PDF slot, append-only independent attempts, exact nullability/transitions, HTML before release, explicit PDF state, HTML failure through UAC-011 and no post-terminal regeneration. Group policy/two slots plus durable representation and attempt schemas.
- `persistence_requirement`: Unique slot, append-only attempts, immutable success and mandatory-artifact/terminal coupling.
- `route_requirement`: Artifact group/content routes expose two independent slots; unavailability and required-HTML failure follow the common error/terminal contracts.
- `event_requirement`: release.completed follows mandatory HTML availability; required HTML terminal failure yields one run.failed; optional PDF failure invents no event.
- `frontend_normalization_requirement`: Display exact independent states; enable only matching AVAILABLE; never infer release/copy formats.
- `acceptance_oracle`: Fault render/store/verify/commits; prove policy release behavior, exact no-attempt versus failure, append-only retries, no terminal PENDING and restart equality.
- `implementation_evidence_required`: Required for final closure: Fault render/store/verify/commits; prove policy release behavior, exact no-attempt versus failure, append-only retries, no terminal PENDING and restart equality.
- `blocking_dependency`: UAC-011/015/017 and durable implementation/fault evidence.
- `final_close_condition`: Hash-bound policy/schema and mapped tests prove every format/state/nullability/terminal/retry/restart rule.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01`, `SCENE-04`

### UAC-017 — Deterministic latest released Run eligibility and lossless financial projection

- `uac_id`: UAC-017
- `title`: Deterministic latest released Run eligibility and lossless financial projection
- `current_state`: RESOLVED_PROVISIONALLY
- `decision_owner`: Phase 4 Backend Contract Coordinator, Financial Semantics, Release Policy and V17 Contract owners
- `mapped_backend_blockers`: `P4-BLOCKER-05..07`
- `mapped_bd_dependencies`: `BD-001`, `BD-004..006`, `BD-009..011`
- `mapped_frontend_contracts`: `ReleasedFinancialMetric`, `ReleasedObjectCoreProjection`, `FinancialReviewProjection`, `ClaimTraceProjection/TraceBundle`, `ReportArtifactGroup`, `Availability`
- `mapped_frontend_conflict_cluster`: `7 Financial Review projection`, `8 Artifact semantics`, `9 Financial/Object projection`
- `mapped_p4_be`: `P4-BE-015`, `P4-BE-020..021`, `P4-BE-028..029`
- `mapped_p4_e2e`: `P4-E2E-003`, `P4-E2E-057`, `P4-E2E-059 Core`, `P4-E2E-060..061`, `P4-E2E-069..070`, `P4-E2E-072`, `P4-E2E-076`, `P4-E2E-085`, `P4-E2E-092..096`, `P4-E2E-098`
- `mapped_p4_sse`: `P4-SSE-015`, `P4-SSE-017`
- `mapped_p4_id`: `P4-ID-001`, `P4-ID-006`, `P4-ID-009`, `P4-ID-011..020`, `P4-ID-023`, `P4-ID-025..027`
- `actual_phase3_backend_fact`: Typed closure records exist; no umbrella validation/latest selector; empty typed result can bypass strict closure; artifacts are outside service release; financials/state routes are not authority.
- `product_semantic_constraint`: Only fully valid same-Object release can be latest; Backend owns Review/Proof/material/X/L/artifact and financial semantics.
- `provisional_contract_decision`: Adopt policy IDs, ReleaseValidationRecordV1, eligible-set ordering, FULL manifest and lossless metric boundary in decision draft section 20.
- `wire_schema_requirement`: One ALLOWED validation binds O/R/V/X/L/policy hashes/material/proof/artifact; max released_at then bytewise run_id; empty set null/NO_RELEASED_RUN; all metric/proof/method/applicability fields preserved without client arithmetic. Validation/policy manifests, validated released-object query and lossless metric projection.
- `persistence_requirement`: Persist decision/reasons/IDs/hashes/manifests/closure/times; prohibit empty FULL subset; preserve decimal/display values.
- `route_requirement`: Released-result, released-state, Object Core and Object run-history routes use one release-eligibility selector and deterministic latest ordering.
- `event_requirement`: release.completed precedes run.completed and is invalid until every frozen release prerequisite closes.
- `frontend_normalization_requirement`: V17 adds omitted method/technical/corporate/proof fields; rename/wrap only; VALID never becomes VERIFIED.
- `acceptance_oracle`: Compete valid/invalid/nonreleased/other-Object/tied Runs and field-diff DB-to-DOM before/after restart, including exact 0.6547 RATIO to Backend-authored 65.47 percent.
- `implementation_evidence_required`: Required for final closure: Compete valid/invalid/nonreleased/other-Object/tied Runs and field-diff DB-to-DOM before/after restart, including exact 0.6547 RATIO to Backend-authored 65.47 percent.
- `blocking_dependency`: UAC-011/013/016, approved V17, approved parent/Financial audit and acceptance evidence.
- `final_close_condition`: Final policy hashes bind the parent, V17 is lossless and deterministic eligibility/financial gates pass.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01`, `SCENE-03`, `SCENE-04`

### UAC-018 — Total error, retryability, recovery, identity and availability mapping

- `uac_id`: UAC-018
- `title`: Total error, retryability, recovery, identity and availability mapping
- `current_state`: RESOLVED_PROVISIONALLY
- `decision_owner`: Phase 4 Backend API/Identity/Error Contract owner; project-owner UAC-006 local profile is applied
- `mapped_backend_blockers`: `P4-BLOCKER-01..08 negative paths`
- `mapped_bd_dependencies`: `BD-003..005`, `BD-008`, `BD-010`
- `mapped_frontend_contracts`: `ErrorEnvelope`, `Availability`, `ConnectionState`, `ALL_ROUTE_DTO_CONSUMERS`
- `mapped_frontend_conflict_cluster`: `1 Prepare Scheme vs Plan/Tasks`, `2 Confirm/start state and route`, `3 Durable idempotency`, `4 Progress/enums`, `5 Runtime event semantics`, `6 Browser SSE protocol`, `7 Financial Review projection`, `8 Artifact semantics`, `9 Financial/Object projection`
- `mapped_p4_be`: `Negative variants of P4-BE-001..030`
- `mapped_p4_e2e`: `P4-E2E-012`, `P4-E2E-023`, `P4-E2E-032`, `P4-E2E-057`, `P4-E2E-070..073`, `P4-E2E-077`, `P4-E2E-079..080`, `P4-E2E-084`, `P4-E2E-086`, `P4-E2E-088`, `P4-E2E-092`, `P4-E2E-096`, `P4-E2E-098`, `P4-E2E-105`
- `mapped_p4_sse`: `P4-SSE-003`, `P4-SSE-006..014`, `P4-SSE-016..020`
- `mapped_p4_id`: `P4-ID-001..020`, `P4-ID-023..028`
- `actual_phase3_backend_fact`: Endpoint exceptions use a simpler envelope without versions/retry/recovery/resource context; lazy SSE errors may occur after headers.
- `product_semantic_constraint`: Negative outcomes are typed/fail closed and never leak foreign/internal/provider/secret/diagnostic/CoT data; artifact denial sends zero protected bytes.
- `provisional_contract_decision`: Adopt ErrorEnvelopeV1 and the total table/boundary in decision draft sections 6-7.
- `wire_schema_requirement`: Every JSON/preheader error uses phase4-error/v1 with exact tuples/allowlisted details; local Phase 4A normally emits neither 401 nor 403; missing is 404 NOT_FOUND and foreign nested identity is safe 404 IDENTITY_MISMATCH; no unavailable child silently succeeds. Versioned safe error projection and preheader SSE validation.
- `persistence_requirement`: Persist stable failure/availability/reason facts where restart-visible; transport diagnostics are not business state.
- `route_requirement`: Every JSON failure and every pre-header SSE failure uses ErrorEnvelopeV1; no alternate error route or in-stream synthetic error event is added.
- `event_requirement`: Pre-header failures use JSON ErrorEnvelopeV1; accepted-stream incompatibility quarantines and recovers without a fabricated business event.
- `frontend_normalization_requirement`: ErrorEnvelope, Availability, ConnectionState and all consumers use exact recovery without guessing.
- `acceptance_oracle`: Exercise every code/route/SSE condition and assert status/schema/retry/recovery/redaction, zero mutation/frames/protected bytes, concealment and restart determinism.
- `implementation_evidence_required`: Required for final closure: Exercise every code/route/SSE condition and assert status/schema/retry/recovery/redaction, zero mutation/frames/protected bytes, concealment and restart determinism.
- `blocking_dependency`: Bind the applied UAC-006 local profile, final route/event schemas and negative evidence.
- `final_close_condition`: One identical final table and mapped tests prove exact envelope/concealment/recovery/no leakage.
- `contract_semantics_state`: READY_FOR_FINAL_FREEZE
- `implementation_evidence_state`: PENDING
- `requires_approved_phase3_parent`: `false`
- `requires_implementation_evidence`: `true`
- `affected_scenes`: `SCENE-01..04 negative and recovery variants`

## Stop boundary

The next authorized operation is only `PHASE4_BACKEND_FINAL_CONTRACT_DELTA_RECONCILIATION` after the approved Phase 3 parent and authoritative Run, both independent audit PASS receipts, and the approved V17 contract-input package exist. That later operation may convert rows to `FINAL_CLOSED` or `STILL_OPEN`. This preparation does not implement Backend, Frontend, migrations, scheduler, SSE, Playwright, or acceptance harnesses.

```text
PHASE4_BACKEND_UAC_CLOSURE_PREP_READY=YES
PHASE4_ACCESS_MODE_DECISION_READY=YES
ACCESS_MODE_ID=phase4-local-single-user-trusted/v1
UAC_006=RESOLVED_PROVISIONALLY
UAC_TOTAL=18
UAC_DISPOSITIONED=18/18
UAC_PROVISIONAL_DECISIONS_COMPLETE=18/18
UAC_RESOLVED_PROVISIONALLY=11
UAC_WAITING_FOR_APPROVED_PHASE3_PARENT=1
UAC_WAITING_FOR_FINAL_V17_CONTRACT=1
UAC_WAITING_FOR_IMPLEMENTATION_EVIDENCE=5
UAC_SEMANTIC_DECISION_REQUIRED=0
UAC_FINAL_CLOSED=0
CONTRACT_SEMANTICS_PENDING=0
IMPLEMENTATION_EVIDENCE_PENDING=16
CURRENT_STATE_WAITING_FOR_IMPLEMENTATION_EVIDENCE=5
WAITING_FOR_APPROVED_PHASE3_PARENT=YES
WAITING_FOR_V17_CONTRACT_INPUT=YES
PHASE4_BACKEND_CONTRACT_FREEZE_READY=NO
PHASE4_PRODUCTION_IMPLEMENTATION_AUTHORIZED=NO
CONTRACT_FREEZE_IMPLEMENTATION_EVIDENCE_DEADLOCK=RESOLVED
```
