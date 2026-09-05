# Phase 4 Backend / Frontend Field Ownership Matrix

Status: `FIELD_OWNERSHIP_RECONCILED — NOT_FINAL`  
Contract family: `phase4-core/v1`  
Coverage: 13/13 normalized contracts, nine conflict clusters, eight Backend blockers.

Each row has exactly one classification. Field groups are used only when every named field has the same source and classification. Snake-case public DTO names become the listed camelCase adapter names by mechanical rename; a rename never transfers business authority to the Frontend.

## Classification rules

| Classification | Meaning |
|---|---|
| `EXISTING_BACKEND` | Exact durable source fact exists in the inspected Backend; re-audit against UAC-001's accepted parent. |
| `BACKEND_FIELD_REQUIRED` | A new durable Backend fact or consistency protocol is required. |
| `PROJECTION_ONLY` | Backend constructs a read-only fact from exact durable relations or frozen maps. |
| `ADDITIVE_ROUTE_REQUIRED` | Public route/route behavior is absent and must be added after authorization. |
| `FRONTEND_ADAPTER_DERIVED_NONBUSINESS` | Mechanical rename or transport/presentation-only derivation; never financial, identity, lifecycle, relation, release or artifact truth. |
| `DISPLAY_ONLY` | Component-local label/layout/focus/rounding that is not sent back as authority. |
| `PHASE5_DEFERRED` | Absent from Phase 4 Core and must not be fabricated. |

## Shared Availability and Error contracts

| Contract / source record | Backend DTO field(s) | Adapter normalized field(s) | Frontend field(s) | Consumer | Classification | P4-BE | P4-E2E | P4-SSE / P4-ID |
|---|---|---|---|---|---|---|---|---|
| Frozen availability map over exact component records | `availability.status` | `availability.status` | `status` | all unavailable/partial panels and actions | `PROJECTION_ONLY` | `007`, `020..030` | `032`, `043`, `057`, `070`, `092..098` | ID `011..020`, `025..028` |
| Frozen reason/retry table | `availability.reason_code`, `availability.retryable` | `reasonCode`, `retryable` | recovery banner/action enablement | all normalized consumers | `PROJECTION_ONLY` | `007`, `018`, `020..030` | `032`, `043`, `057`, `070..073`, `096`, `098` | SSE `016..018`; ID `025..028` |
| Version/error mapper | `schema_version`, `error.code`, `error.message`, `error.retryable`, `error.recovery` | `schemaVersion`, `error.code`, `message`, `retryable`, `recovery` | normalized request failure | shell, every route boundary, SSE setup | `PROJECTION_ONLY` | `001..030` negative paths | `012`, `023`, `032`, `057`, `070..073`, `077`, `079..080`, `084`, `086`, `088`, `092`, `096`, `098`, `105` | SSE `003`, `006..014`, `016..020`; ID `001..020`, `023..028` |
| Request/resource context | `error.request_id`, `error.resource.type`, `error.resource.id`, allowlisted `error.details` | camel-case exact copy | diagnostic context | error surfaces | `PROJECTION_ONLY` | `001..030` negative paths | same ErrorEnvelope set | SSE `003`, `018`; ID `025..028` |
| Public error route behavior | one `ErrorEnvelopeV1` on every JSON/pre-header SSE failure | one parser path | one failure model | route and transport adapters | `ADDITIVE_ROUTE_REQUIRED` | `003..006`, `011..018`, `025..030` | negative suite above | SSE `003`, `018`; ID `025..028` |

## Global Run collection

| Contract / source record | Backend DTO field(s) | Adapter normalized field(s) | Frontend field(s) | Consumer | Classification | P4-BE | P4-E2E | P4-SSE / P4-ID |
|---|---|---|---|---|---|---|---|---|
| Collection protocol | `schema_version`, `generated_at`, `next_cursor` | `schemaVersion`, `generatedAt`, `nextCursor` | collection metadata | Shell, Runs page, Object detail history | `PROJECTION_ONLY` | `001`, `010`, `028..029` | `002`, `005..007`, `067`, `076` | ID `006`, `025..027` |
| Object + Run records | `items[].object.{object_id,symbol,company_name}`, `items[].run.{run_id,research_object_id,goal_id,scheme_id,status,as_of,created_at,started_at,completed_at,updated_at}` | exact camel rename | Run list identity/lifecycle fields | Runs table/cards, Object history | `EXISTING_BACKEND` | `001`, `007`, `010`, `028..029` | `002`, `005..007`, `067`, `076` | ID `006`, `025..027` |
| Frozen collection projection | `items[].stage`, `terminal`, `graph_version`, `latest_activity`, `result_availability`, `projection_revision`, `projection_sequence` | exact camel rename | status/stage/activity/result/watermark | Runs page, shell counters, Object history | `PROJECTION_ONLY` | `001`, `007..010`, `017`, `019`, `028..029` | `005..007`, `026..036`, `067`, `076..077`, `087..088` | SSE `012..013`; ID `006..010` |
| Backend progress authority | `progress.{method,completed_tasks,total_tasks,fraction}` | camel rename; exact numbers | progress source | list progress bars | `PROJECTION_ONLY` | `007`, `010`, `028` | `006`, `028..032`, `076` | SSE `002`, `010..013` |
| Adapter presentation | none | `progress.percent = fraction * 100` | percent | progress bar width/ARIA | `FRONTEND_ADAPTER_DERIVED_NONBUSINESS` | `010` | `032` | SSE `010..013` |
| Global collection endpoint | `GET /api/research-runs` with filter-bound opaque cursor and fixed order | data-source method | query/load-more | Runs page | `ADDITIVE_ROUTE_REQUIRED` | `001`, `010`, `028..029` | `002`, `005..007`, `067`, `076` | ID `006`, `025..027` |

## Prepare and Confirm

| Contract / source record | Backend DTO field(s) | Adapter normalized field(s) | Frontend field(s) | Consumer | Classification | P4-BE | P4-E2E | P4-SSE / P4-ID |
|---|---|---|---|---|---|---|---|---|
| Object/Goal/Scheme snapshots | `object`, `goal`, `scheme` | exact camel rename | prepared Object/Goal/Scheme | New Task, Plan Snapshot | `EXISTING_BACKEND` | `002..003` | `017..024`, `074..075`, `102` | ID `002..005`, `007..009` |
| Durable draft facts | `schema_version`, `draft_id`, `version`, `status`, `preview_kind`, `planned_graph_availability`, `prepare_hash`, `draft_hash`, `created_at`, `expires_at` | `schemaVersion`, `draftId`, `version`, `status`, `previewKind`, `plannedGraphAvailability`, `prepareHash`, `draftHash`, `createdAt`, `expiresAt` | `PreparedResearchDraft` | New Task, Plan Snapshot, Confirm control | `BACKEND_FIELD_REQUIRED` | `002..005` | `017..025`, `074..075`, `098`, `102` | SSE `002`, `004`; ID `002..005`, `007..009`, `023`, `026..027` |
| Prepare endpoint | existing `POST /api/research-runs/prepare` | data-source prepare | Prepare action | New Task | `EXISTING_BACKEND` | `002..003` | `017..024`, `074` | ID `002..003`, `026..027` |
| Existing Confirm materialization | `admission.{run_id,object_id,draft_id,draft_version,goal_id,scheme_id,planned_graph_id,status}` | exact camel rename | immutable admission identity | Confirm result, Run landing | `EXISTING_BACKEND` | `004..006` | `024..026`, `075`, `079..081`, `087`, `098` | SSE `002`, `004`, `007..009`, `013`, `015..017`; ID `004..010`, `023`, `026..027` |
| Durable immutable admission | `admission.{schema_version,admission_id,draft_hash,confirmation_request_hash,auto_start.{required,admitted},admitted_at}` | exact camel rename | `RunAdmissionV1` | Confirm result, retry/replay | `BACKEND_FIELD_REQUIRED` | `004..006`, `017` | `025..026`, `075`, `079..081`, `087`, `098` | SSE `002`, `004`, `007..009`, `013`, `015..017`; ID `004..010`, `023`, `026..027` |
| Transport replay metadata | `response_meta.{schema_version,request_id,idempotency_replayed}` | `responseMeta.{schemaVersion,requestId,idempotencyReplayed}` | request/replay diagnostics | Confirm toast/telemetry | `PROJECTION_ONLY` | `004..006` | `023..026`, `075`, `098` | ID `004..005`, `023`, `026..027` |
| Confirm endpoint | existing `POST /api/research-runs`; one consume/admit/start action | data-source confirm | Confirm / Start button | New Task | `EXISTING_BACKEND` | `004..006`, `017` | `024..026`, `075`, `079..081`, `087`, `098` | SSE `015..017`; ID `004..005`, `023`, `026..027` |
| Frontend-only template/mode label | absent from normalized DTO | local route/form state | display mode/template label | New Task | `DISPLAY_ONLY` | — | `017..024` | — |

## Atomic Run projection

| Contract / source record | Backend DTO field(s) | Adapter normalized field(s) | Frontend field(s) | Consumer | Classification | P4-BE | P4-E2E | P4-SSE / P4-ID |
|---|---|---|---|---|---|---|---|---|
| Run aggregate | `object`, `run`, `goal`, `confirmed_scheme`, `planned_graph`, `actual_graph`, `graph_version`, `tasks` | exact camel rename | core Run state | Run header, Research Path, Task drawer | `EXISTING_BACKEND` | `007..010`, `019`, `028` | `026..036`, `063`, `077`, `087..091`, `098` | SSE `012..014`, `019..020`; ID `006..010`, `023` |
| Atomic watermark | `projection_schema_version`, `projection_revision`, `projection_sequence`, `generated_at` | exact camel rename | snapshot identity | reducer, transport handshake | `BACKEND_FIELD_REQUIRED` | `007..009`, `017`, `019` | `026..036`, `077`, `087..090`, `098` | SSE `012..013`, `020`; ID `006..010`, `023` |
| Backend projection summaries | `activity`, `lifecycle.{status,stage,progress,terminal,terminal_outcome,safe_failure}`, component `review`, `result`, `artifacts`, `proof`, `execution`, `terminal` | exact camel rename | normalized Run projection | all Run tabs/panels | `PROJECTION_ONLY` | `007..010`, `017`, `019..030` | `026..043`, `057`, `069..098` | SSE `010..020`; ID `006..020`, `023..028` |
| Durable path-change sources | `path_changes[].{path_change_id,source_kind,source_id,change_kind,status,decision,reason_code,task_refs,operations,graph_version_before,graph_version_after,created_at,resolved_at}` | exact camel rename | `pathChanges[]` | Research Path, activity, Task drawer | `PROJECTION_ONLY` | `018..019` | `033..039`, `077`, `084`, `088..091` | SSE `010..014`, `019..020`; ID `007..010` |
| Run projection endpoint | `GET /api/research-runs/{run_id}/projection` | data-source snapshot | authoritative Run load/reload | Run page/reducer | `ADDITIVE_ROUTE_REQUIRED` | `007..009`, `017`, `019`, `028` | `026..036`, `077`, `087..090`, `098` | SSE `012..014`, `020`; ID `006..010`, `023` |

## Runtime event and connection state

| Contract / source record | Backend DTO field(s) | Adapter normalized field(s) | Frontend field(s) | Consumer | Classification | P4-BE | P4-E2E | P4-SSE / P4-ID |
|---|---|---|---|---|---|---|---|---|
| Durable RuntimeEvent | `event_id`, `run_id`, `task_id`, `type`, `timestamp`, `sequence`, `payload` | exact camel rename, raw `type` preserved | normalized event identity/data | SSE transport, reducer, activity | `EXISTING_BACKEND` | `011..019` | `068`, `071..073`, `077..091`, `098` | SSE `001..020`; ID `007..010`, `023`, `026..027` |
| Public event version/projection metadata | `event_contract_version`, `payload_schema_version`, nullable `graph_version` | exact camel rename | event compatibility and graph watermark | parser/reducer | `PROJECTION_ONLY` | `018..019` | `032`, `084`, `088..091` | SSE `002..005`, `010..020`; ID `007..010` |
| Frozen type-to-effect map | no new durable fact | `effect`, `projectionRefreshRequired` from exact contract table | reducer instruction | reducer only | `FRONTEND_ADAPTER_DERIVED_NONBUSINESS` | `018..019` | `032`, `077`, `084`, `088..091` | SSE `010..014`, `019..020` |
| Browser connection state | no business DTO | `IDLE`, `CONNECTING`, `OPEN`, `RECOVERING`, `BACKOFF`, `TERMINAL`, `FAILED` from fetch/cursor state | `ConnectionState` | connection banner/retry UI | `FRONTEND_ADAPTER_DERIVED_NONBUSINESS` | `011..017` | `077..088`, `098` | SSE `004..018`; ID `009`, `023`, `026..027` |
| SSE behavior | preflight cursor, headers, replay suffix, heartbeat, terminal close | fetch-stream implementation | live Run transport | Run page | `ADDITIVE_ROUTE_REQUIRED` | `011..017` | `068`, `077..088`, `098` | SSE `001..020`; ID `009`, `023`, `026..027` |

## Financial Review

| Contract / source record | Backend DTO field(s) | Adapter normalized field(s) | Frontend field(s) | Consumer | Classification | P4-BE | P4-E2E | P4-SSE / P4-ID |
|---|---|---|---|---|---|---|---|---|
| ReviewRecord | `review_id`, nullable `status`, nullable `reviewer`, `input_snapshot_hash`, `reviewed_evidence_refs`, `reviewed_calculation_refs`, `reviewed_metric_refs`, `reviewed_claim_refs`, `reviewed_judgment_refs`, `required_proof_calculation_refs` | exact camel rename; `status` may be exposed as `verdict` only by frozen rename | Review identity/input/verdict | Financial Review, Results, Trace | `EXISTING_BACKEND` | `023..024` | `040..043`, `048..054`, `069`, `072..073`, `094..095`, `098`, `105` | ID `011..020`, `023`, `025..028` |
| Durable check authority | `checks[].{check_id,check_code,status,subjects,expected,actual,detail,exception_state,correction_refs,created_at,resolved_at}` | exact camel rename | checks/exceptions/history | Financial Review | `BACKEND_FIELD_REQUIRED` | `023..024` | `040..043`, `048..054`, `094..095`, `098`, `105` | ID `011..020`, `023`, `025..028` |
| Review scope/release joins | `schema_version`, watermarks, `object_id`, `run_id`, nullable `canonical_record_id`, nullable `released_result_id`, `availability` | exact camel rename | Review envelope | Financial Review, Trace | `PROJECTION_ONLY` | `023..024` | same Review suite | ID `011..020`, `023`, `025..028` |
| Review projection endpoint | expanded release-independent `GET .../review-view` | data-source review load | Review panel | Financial Review | `ADDITIVE_ROUTE_REQUIRED` | `023..024` | `040..043`, `094..095`, `098`, `105` | ID `011..020`, `023`, `025..028` |

## Claim and Trace

| Contract / source record | Backend DTO field(s) | Adapter normalized field(s) | Frontend field(s) | Consumer | Classification | P4-BE | P4-E2E | P4-SSE / P4-ID |
|---|---|---|---|---|---|---|---|---|
| MaterialFinancialClaim + released metric | `claim`, `released_metric`, `claim_id`, `metric_id` | exact camel rename | Claim/metric detail | Results, Claim drawer, Trace | `EXISTING_BACKEND` | `020..022`, `024` | `042`, `048..054`, `072..073`, `094..095`, `098`, `105` | ID `011..020`, `023`, `025..028` |
| Exact C/M/K/E/V/P relations | `task_refs`, `evidence_refs`, `calculation_refs`, `judgment_refs`, `review_refs`, `proof_refs`, `canonical_record_id`, `released_result_id` | exact camel rename; order preserved | Claim lineage | Claim drawer, Trace | `PROJECTION_ONLY` | `022`, `024` | same Claim/Trace suite | ID `011..020`, `023`, `025..028` |
| Explicit primary relation | nullable `primary_task_id`; null unless a durable explicit relation selects one | `primaryTaskId` | optional primary Task action | Claim drawer | `BACKEND_FIELD_REQUIRED` | `022`, `024` | multi-Task and singleton-negative fixtures | ID `011..020`, `025..028` |
| Typed Judgment detail | `judgment_refs[].availability` plus typed retained detail | exact camel rename | Judgment detail/disabled state | Claim/Trace drawer | `BACKEND_FIELD_REQUIRED` | `022`, `024` | unavailable/untyped/cross-Run fixtures | ID `011..020`, `025..028` |
| Claim route | `GET /api/research-runs/{run_id}/claims/{claim_id}` | data-source Claim load | Claim detail | Results/Claim drawer | `ADDITIVE_ROUTE_REQUIRED` | `022`, `024` | Claim/Trace suite | ID `011..020`, `023`, `025..028` |
| Anchor manifest | `anchor_manifest_id`, `anchor_manifest_sha256`, fixed `report.representations[HTML,PDF].claim_anchor`, plural `review_anchors`, `task_anchors`, `execution_anchors` | exact camel rename; disabled when unavailable | trace navigation | Report, Review, Execution, Trace | `BACKEND_FIELD_REQUIRED` | `024..027` | `045..054`, `072..073`, `094..096`, `098`, `105` | ID `011..020`, `023`, `025..028` |
| Trace envelope joins | schema/watermarks, `object_id`, `run_id`, `claim_id`, `metric_id`, `calculation_id`, `report_id`, `availability` | exact camel rename | TraceBundle | Trace page/drawers | `PROJECTION_ONLY` | `024` | Trace suite | ID `011..020`, `023`, `025..028` |
| Trace route | `GET /api/research-runs/{run_id}/trace/{claim_id}` | data-source trace load | trace navigation request | Trace/Report/Review/Execution | `ADDITIVE_ROUTE_REQUIRED` | `024` | Trace suite | ID `011..020`, `023`, `025..028` |

## Released metric

| Contract / source record | Backend DTO field(s) | Adapter normalized field(s) | Frontend field(s) | Consumer | Classification | P4-BE | P4-E2E | P4-SSE / P4-ID |
|---|---|---|---|---|---|---|---|---|
| ReleasedFinancialMetric | `metric_id`, `name`, `canonical_value`, `canonical_unit`, `display_value`, `display_unit`, `period`, `period_basis`, `actuality`, `as_of`, `currency`, `formula_id`, `capability_id`, `calculation_id`, `method_metadata`, `technical_price_basis`, `corporate_action_status`, `corporate_action_guard_refs`, `limitations` | exact camel rename; decimal strings remain strings | released metric display/source | Results, Financial Review, Object Core | `EXISTING_BACKEND` | `020..022`, `028..029` | `003`, `057`, Core `059`, `060..061`, `069..072`, `085`, `092..095`, `098` | ID `001`, `006`, `011..020`, `023`, `025..027` |
| Release relation projection | `run_id`, `evidence_refs`, `claim_refs`, `proof.{policy_id,requirement,status,proof_refs}` | exact camel rename | metric lineage/proof | metric card, Trace, Review | `PROJECTION_ONLY` | `020..024`, `028` | same metric/release suite | ID `011..020`, `023`, `025..028` |
| Visible formatting | no new fact; exact `display_value` + `display_unit` | no arithmetic | `65.47%` | metric card | `DISPLAY_ONLY` | `020..022` | mandatory `0.6547 RATIO → 65.47%` fixture | — |

## Report artifacts

| Contract / source record | Backend DTO field(s) | Adapter normalized field(s) | Frontend field(s) | Consumer | Classification | P4-BE | P4-E2E | P4-SSE / P4-ID |
|---|---|---|---|---|---|---|---|---|
| Existing successful artifact record | available slot `artifact_id`, `sha256`, `size_bytes`, `renderer.{renderer_id,renderer_version}`, `generated_at`; group `run_id`, `canonical_record_id`, `released_result_id` | exact camel rename | immutable representation identity | Results, Professional Report/download | `EXISTING_BACKEND` | `024..027`, `030` | `045..047`, `067`, `072..073`, `095..096`, `098` | ID `018..020`, `023`, `025..027` |
| Group/format projection | `schema_version`, `object_id`, `report_id`, `release_policy_version`, `artifact_policy_version`, group/slot `availability`, `format`, `content_type`, `required_for_release` | exact camel rename | `ReportArtifactGroup` and two ordered slots | Results/Report/download | `PROJECTION_ONLY` | `024..027`, `030` | artifact suite | ID `018..020`, `023`, `025..027` |
| Generation/anchor state | `generation_attempt_id`, `attempt_count`, nullable `safe_failure_code`, `anchor_manifest_id`, `anchor_manifest_sha256` and immutable slot transitions | exact camel rename | availability/failure/trace actions | Results/Report/Trace | `BACKEND_FIELD_REQUIRED` | `024..028` | `003`, `045..047`, `057`, `060..061`, `070`, `092`, `094`, `096`, `098` | ID `001`, `006`, `013..020`, `023`, `025..027` |
| Authorized action locator | `authorized_ref` only for AVAILABLE, current authorized metadata; never a bearer or cache authority | `authorizedRef` exact copy | download/open action | report action controls | `PROJECTION_ONLY` | `025..027`, `030` | `045..047`, `072..073`, `096`, `098` | ID `018..020`, `023`, `025..027` |
| Artifact routes | group route plus sole content route, full revalidation and byte integrity before response | data-source metadata/fetch | load/open/download | Results/Report | `ADDITIVE_ROUTE_REQUIRED` | `024..027`, `030` | artifact suite | ID `018..020`, `023`, `025..027` |

## Released Object Core

| Contract / source record | Backend DTO field(s) | Adapter normalized field(s) | Frontend field(s) | Consumer | Classification | P4-BE | P4-E2E | P4-SSE / P4-ID |
|---|---|---|---|---|---|---|---|---|
| ResearchObject and owned Runs | `object`, `source_run_id`, `runs[]` exact identities/timestamps | exact camel rename | Object identity/history | Object overview, history | `EXISTING_BACKEND` | `001`, `007`, `010`, `028..029` | `003`, `005..007`, `057`, Core `059`, `060..061`, `063`, `070`, `073`, `076`, `092`, `098` | ID `001`, `006`, `023..027` |
| Release selector and core projection | `schema_version`, `projection_revision`, `generated_at`, `latest_released_run_id`, `current_released_result_availability`, `released_result_id`, `canonical_record_id`, `released_at`, `metrics`, `claim_refs`, `report_artifact_group`, `run_count` | exact camel rename | released Object Core | Object overview/financial/market/history | `PROJECTION_ONLY` | `001`, `007`, `010`, `020..029` | Object/release suite above | ID `001`, `006`, `009`, `011..020`, `023`, `025..027` |
| Released-state endpoint | `GET /api/objects/{object_id}/released-state` plus global/history collection reuse | data-source Object Core | Object page load | Object overview/tabs | `ADDITIVE_ROUTE_REQUIRED` | `001`, `010`, `028..029` | Object/release suite | ID `001`, `006`, `023..027` |

## Explicit Frontend-only and Phase 5 boundaries

| Source | Backend DTO field(s) | Adapter field(s) | Frontend field(s) | Consumer | Classification | Acceptance boundary |
|---|---|---|---|---|---|---|
| UI state only | none | readonly wrapper/order preservation | tab, selected row, expanded drawer, focus/highlight/scroll target, label text, local rounding | all pages | `DISPLAY_ONLY` | Cannot become identity, release, Task, financial, Review, Proof or artifact authority. |
| No Phase 4 source | absent | absent | `ResearchObjectVersion`, `ResearchViewVersion`, Research Memory, comparison/diff, incremental seed, freshness/reuse/refresh/revalidate/prevent, Object writeback | Scene 05/06 placeholders only | `PHASE5_DEFERRED` | `SCENE-05..06` remain `DEFINED_NOT_ACTIVATED`; no production truth claim or writeback. |

## Ownership invariants and coverage

- Backend is the only authority for identity, financial values, Run/Task/graph lifecycle, Review, Proof, release, artifact state, and every A/B/C relationship.
- `primary_task_id` is never inferred from singleton cardinality; it is null without an explicit durable primary relation.
- Adapter derivations are limited to mechanical rename, immutable/read-only wrappers, `fraction * 100` presentation percent, event-effect lookup from the frozen contract, and connection transport state.
- No frontend field is both `BACKEND_FIELD_REQUIRED` and Frontend-derived. No business-semantic field is unowned.
- Cross-Object/Run fallback, text/first/latest joins, hidden Chain-of-Thought, raw filesystem paths and public `artifact://` locators are prohibited.

```text
FRONTEND_CONTRACTS_MAPPED=13/13
FRONTEND_CONFLICT_CLUSTERS_MAPPED=9/9
BACKEND_BLOCKERS_MAPPED=8/8
UNOWNED_BUSINESS_SEMANTIC_FIELDS=0
FRONTEND_FINANCIAL_AUTHORITY=0
CROSS_OBJECT_FALLBACK=0
HIDDEN_COT_DEPENDENCY=0
RAW_ARTIFACT_PATH_EXPOSURE=0
PHASE5_LEAKAGE=0
```
