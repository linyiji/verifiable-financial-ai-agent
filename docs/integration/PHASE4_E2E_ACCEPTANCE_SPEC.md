# Phase 4 Frontend × Backend E2E Acceptance Specification

Status: **AUTHORITATIVE DESIGN — FROZEN — NOT YET EXECUTED**  
Scope: browser acceptance design only; no Playwright, frontend, backend, route, schema, or deployment implementation is authorized by this document.  
Specification date: 2026-09-04 (Asia/Shanghai)

## 1. Decision and authority

This is the activation-aware, release-blocking browser contract. A passing Frontend Demo does not
satisfy an integrated gate. A passing backend test does not satisfy a browser gate. An activated
integrated gate passes only when the browser consumes the authoritative backend state through real
HTTP and SSE and the rendered result agrees with the captured backend records.

Source precedence is:

1. Backend domain, runtime, release, review, and persistence semantics.
2. Backend SSE envelope and resume semantics.
3. The typed financial release, `ReportArtifact`, Claim Trace, Research Object, and deployment-mode
   contracts.
4. The six formal frontend Scenes.
5. The 64 handler-equivalent frontend interaction contracts.

When frontend Demo vocabulary differs from backend vocabulary, the Phase 4 adapter may translate
names and shapes but may not invent events, state, IDs, financial values, reviews, artifacts, or
terminal outcomes. The backend value remains authoritative.

The frontend source baseline for this design is the remediated pre-integration contract at
`a850bce3cf0b8a72bc28c7ce16a67e9f83be0c84`. The committed Backend Phase 3 integration baseline is
`5e846326edb70ac3eb7d94910cd6d3008737da22`. Phase 3 financial-semantic corrections observed after
that commit are candidate input, not accepted release evidence. Before implementation, the Phase 4
owner must replace the backend coordinate with one clean, independently accepted Phase 3 commit.

`PHASE4_E2E_SPEC_READY` describes the completeness of this design, not implementation readiness or
product acceptance.

The gate, Scene, SSE, identity, and activation namespaces are frozen by
`PHASE4_E2E_GATE_ACTIVATION_MATRIX.md`. The only expected future design delta is append-only:
after approval of a new Frontend Baseline, newly added interaction contracts receive monotonic
`P4-E2E` IDs above 100. Existing IDs and semantics are not renumbered or repurposed.

The earlier `PHASE4_CONTRACT_PREAUDIT.md` and related mapping/blocker documents are provisional
inputs. This specification preserves the complete future acceptance design, while
`PHASE4_E2E_GATE_ACTIVATION_MATRIX.md` is authoritative for when each gate or real Scene becomes
release-blocking. Definition does not imply activation: Phase 5 and deployment contracts are
`DEFINED_NOT_ACTIVATED` before their activation conditions and do not fail or block Phase 4A Core.

## 2. Required suites and evidence classes

| Suite tag | Data/runtime source | What it may prove | What it may not prove |
|---|---|---|---|
| `@demo-contract` | `DemoFrontendDataSource` + `DemoRuntimeTransport` | The six Scene scripts, all 64 control contracts, reducer behavior, responsive/a11y interactions | HTTP, SSE, persistence, provider truth, backend calculations, backend identity, deployment readiness |
| `@integrated-contract` | Real backend over HTTP/SSE; controlled backend acceptance records allowed | Adapter correctness, identity joins, reconnect, persistence, financial/report/trace projections | Public-provider `LIVE` truth unless run in public mode |
| `@public-real` | `PUBLIC_NETWORK_MODE`, real backend, current permitted providers | Production HTTP/SSE path, `LIVE` source truth, full browser journey | Offline or limited-mode behavior |
| `@limited-real` | `LIMITED_NETWORK_MODE`, real backend, frozen capability policy | Correct `LIVE_ALLOWED`/`CACHE_ONLY`/`DISABLED` behavior | Public or fixture claims |
| `@offline-integrated` | `OFFLINE_DEMO_MODE`, real backend, manifested fixture, PostgreSQL | Integrated offline behavior, persistence, local SSE, truthful Demo/FIXTURE labels | Public live-data claims |
| `@chaos-sse` | Real backend plus a byte-preserving disconnect/reorder proxy | Consumer recovery from disconnect, replay, duplicate and delayed frames | Altered or fabricated business payloads |

Rules:

- `@public-real`, `@limited-real`, and `@offline-integrated` must not use request fulfilment, HAR
  replay, service workers, frontend fixture injection, or Demo stores. Request observation and
  connection aborts are allowed; synthesized HTTP/SSE responses are not.
- A chaos proxy may drop, delay, duplicate, or reorder complete frames from the real SSE response.
  It must not edit event IDs, sequences, types, payloads, or timestamps.
- Every test starts with cleared cookies and browser storage unless its purpose is refresh/reopen.
- Screenshots, traces, request/response ledgers, selected sanitized payloads, console output, and the
  backend run manifest are retained per failed test. Secrets and raw licensed provider bodies are
  excluded.
- Once activated, release disposition is binary: required gate `PASS` or release `FAIL`. `NOT_RUN`,
  `BLOCKED`, `SKIPPED`, flaky retry-only success, and `PASS_WITH_MINOR_ISSUE` do not pass a required
  gate. A future gate may instead be `DEFINED_NOT_ACTIVATED` with no result; that state is valid only
  before its activation condition and is excluded from the earlier aggregate.

The mandatory browser target is the exact Chromium/Playwright revision pinned by the future release
lock and manifest, desktop `1366x900`, `zh-CN`, and the configured Asia/Shanghai user timezone while
wire timestamps remain RFC 3339/UTC. Responsive interaction smoke runs at widths 1024, 1280, 1440
and 1920 with no horizontal page overflow. Firefox/WebKit become required only if the release
manifest advertises them; advertised targets may not be skipped. Console errors, unhandled page
errors, failed identity validation, and unexpected HTTP failures fail the current test.

## 3. Acceptance corpus and captured oracles

Each execution uses two distinct objects, `O_A` and `O_B`, with different symbols and company
names. Each Scene creates or selects its own run. IDs are captured from responses; integrated tests
must not assume Demo IDs or infer IDs from display text.

The per-Scene browser context must contain non-empty aliases by the end of the scenario:

```text
O = objectId
R = runId
T = taskId
C = claimId
V = reviewId
A = artifactId
K = calculationId
E = evidenceId
X = canonicalRecordId / execution record ID
```

The oracle ledger records, in order:

- object create/select response;
- prepare response, including `draft_id`, Goal and unconfirmed Scheme snapshot;
- confirm response and idempotency key;
- run detail, task list, planned/actual graph, and their response timestamps;
- every SSE frame (`id`, `event`, parsed `data`, arrival index, connection number);
- released result, typed metrics and material Claims;
- exact Review record/checks;
- canonical/execution record;
- `ReportArtifact` metadata and downloaded bytes;
- Research Object history/writeback/comparison projection when Phase 5 is activated;
- deployment-mode/bootstrap and safe component outcomes when deployment acceptance is activated.

The browser assertion compares DOM state with this ledger. Values copied from one DOM region to
another are not an oracle.

## 4. Authoritative P4 E2E gate set

The IDs and assertions in this section remain the semantic authority. The exhaustive
`activation_scope` assignment for all 100 gates, including the FULL/INCREMENTAL and current/versioned
variants of mixed gates `P4-E2E-058` and `P4-E2E-059`, is defined in
`PHASE4_E2E_GATE_ACTIVATION_MATRIX.md`. Activation changes release timing only; it does not alter an
assertion.

### 4.1 The 64 interaction gates

`P4-E2E-001` through `P4-E2E-064` are deliberately one-to-one with the frozen 64
handler-equivalent frontend contracts. All run in `@demo-contract`; each also runs against the real
backend wherever the control is present. For a public/limited release, only the real variant can
pass the release gate.

| Gate | Control contract | Machine-verifiable integrated assertion |
|---|---|---|
| P4-E2E-001 | Primary nav: New | URL/state becomes New Task; one nav item selected; browser history entry exists |
| P4-E2E-002 | Primary nav: Runs | authoritative Run collection loads over HTTP; scroll/history semantics hold |
| P4-E2E-003 | Primary nav: Objects | authoritative Object collection loads over HTTP |
| P4-E2E-004 | Runs: new-run CTA | opens object-first wizard without creating a Run |
| P4-E2E-005 | Runs: live card | opens the exact `runId` and matching `objectId`, status, activity, progress, graph version |
| P4-E2E-006 | Runs: completed card | opens A/B/C for the exact released `runId`; no latest-run substitution |
| P4-E2E-007 | Runs: nonterminal/action card | opens exact Run and backend-required action/status; no fabricated user gate |
| P4-E2E-008 | Create Object trigger | accessible modal opens; no Object POST yet |
| P4-E2E-009 | Existing Object card | selects exact `objectId`; goal draft binds to it |
| P4-E2E-010 | Create modal backdrop | closes only top modal; no object mutation; focus restored |
| P4-E2E-011 | Create modal close | descriptive accessible name; no mutation; focus restored |
| P4-E2E-012 | Company search input | editable; loading/result/empty/error states follow actual HTTP search |
| P4-E2E-013 | Search candidate | selected provider/catalog identity is preserved exactly |
| P4-E2E-014 | Create cancel | closes with zero create requests |
| P4-E2E-015 | Candidate detail transition | selected match details render; no duplicate/obsolete transition action |
| P4-E2E-016 | Create Object confirm | one idempotent Object create; returned `objectId` becomes selected |
| P4-E2E-017 | Goal: comprehensive | exact template goal is sent with selected `objectId` |
| P4-E2E-018 | Goal: valuation | exact template goal is sent with selected `objectId` |
| P4-E2E-019 | Goal: risk | exact template goal is sent with selected `objectId` |
| P4-E2E-020 | Goal: custom | previous template is cleared; only entered goal is submitted |
| P4-E2E-021 | Goal text | edits persist across wizard back/forward and match prepare request |
| P4-E2E-022 | Wizard Back | moves one step, preserves selected object/goal, never creates or confirms |
| P4-E2E-023 | Wizard Next | validates locally safe shape, advances once, exposes backend error without substitution |
| P4-E2E-024 | Regenerate Scheme | new prepare request yields new `draft_id`/Scheme; obsolete draft cannot be confirmed by UI |
| P4-E2E-025 | Confirm / Start | rapid click and response-loss retry create exactly one `runId` for one idempotency key |
| P4-E2E-026 | Run lifecycle stages | selected panel matches backend lifecycle projection; no timer-driven stage advancement |
| P4-E2E-027 | Initial Task node | opens exact planned `taskId`; task belongs to Run; planned graph remains immutable |
| P4-E2E-028 | Five research steps | labels/panel follow authoritative task/runtime projection, not elapsed time |
| P4-E2E-029 | Actual Path tab | actual graph equals backend actual graph at its version |
| P4-E2E-030 | Initial Plan tab | initial graph equals confirmed planned snapshot after all mutations |
| P4-E2E-031 | Compare Changes tab | delta is an exact projection of backend mutation history/graphs |
| P4-E2E-032 | Mutation legend | only observed/mapped mutation types are asserted; unknown values are explicit |
| P4-E2E-033 | Mutation history toggle | collapse/expand changes visibility only, never path state |
| P4-E2E-034 | Actual Task node | opens exact actual-graph `taskId` and status |
| P4-E2E-035 | Dynamic Task node | one backend-added Task is marked ADDED; no duplicate; graph remains acyclic and versioned |
| P4-E2E-036 | Mutation Task reference | trigger/added/affected reference opens the exact Run-owned Task |
| P4-E2E-037 | Task drawer X | closes top drawer and restores exact trigger |
| P4-E2E-038 | Task drawer footer close | returns to unchanged origin route/tab/Claim context |
| P4-E2E-039 | Task drawer Escape | topmost-only close, focus trap/restore, background inertness |
| P4-E2E-040 | Review mode switch | Complete and Exception projections derive from the same backend Review source |
| P4-E2E-041 | Review exception filter | All/Open/Resolved counts equal filtered backend records/history |
| P4-E2E-042 | Review Claim link | opens exact `(runId, claimId)`; Review association is verified |
| P4-E2E-043 | Review Task link | opens exact derived `taskId` and timeline anchor; origin preserved |
| P4-E2E-044 | Results: back to Run | returns to same `runId` and records a browser history transition |
| P4-E2E-045 | HTML artifact action | obtains authorized bytes for exact `artifactId`/Run/Object and enforces click cooldown |
| P4-E2E-046 | PDF artifact action | AVAILABLE corpus downloads verified PDF; unavailable corpus is disabled with backend reason |
| P4-E2E-047 | A/B/C tabs | linked tabpanels, roving arrows, and content from one canonical record |
| P4-E2E-048 | Report Claim anchor | exact report anchor opens exact same-Run Claim; no fallback Claim |
| P4-E2E-049 | Claim: locate Report | focuses/highlights exact report anchor and Claim |
| P4-E2E-050 | Claim: open Task | exact Task overlay opens; closing restores Results/tab/Claim |
| P4-E2E-051 | Claim: Evidence ref | exact Evidence record opens, or durable backend UNAVAILABLE with all IDs retained |
| P4-E2E-052 | Claim: Calculation ref | exact Calculation opens, or durable backend UNAVAILABLE with all IDs retained |
| P4-E2E-053 | Claim: locate Review | focuses exact Review record/check containing `claimId` |
| P4-E2E-054 | Claim: locate Execution | focuses exact execution Task/event row, not merely tab C |
| P4-E2E-055 | Claim close | close/X/Escape restores route, tab, focus, and origin context |
| P4-E2E-056 | Objects: create CTA | enters create flow with return route and no implicit Object |
| P4-E2E-057 | Object card | opens exact `objectId`; no symbol/name fallback lookup |
| P4-E2E-058 | Object: start research | preselects same Object and explicit FULL/INCREMENTAL mode |
| P4-E2E-059 | Object tabs | four linked tabpanels preserve exact Object/version context |
| P4-E2E-060 | Latest research | title/KPIs/View/Claim links and action all use one `latestReleasedRunId` |
| P4-E2E-061 | Historical Run row | opens the row's exact immutable `runId`, never latest |
| P4-E2E-062 | Comparison Claim | uses row `sourceRunId`; no-Claim row is noninteractive; no fallback |
| P4-E2E-063 | Browser back/forward/refresh | route, Object, Run, tab, Claim, Task, focus target and scroll restore from URL + backend |
| P4-E2E-064 | Breadcrumb/back | actionable ancestor navigates; context-only text is not presented as a control |

### 4.2 Cross-cutting integrated gates

| Gate | Requirement | Pass oracle |
|---|---|---|
| P4-E2E-065 | Demo/real classification | Every result and artifact is tagged with suite/source; Demo evidence cannot be counted as integrated evidence |
| P4-E2E-066 | No Demo data source | Public/limited bundle/runtime contains no reachable `DemoFrontendDataSource`, `DemoRuntimeTransport`, Demo store, `RUN-DEMO`, data-URL artifact, or frontend fixture path |
| P4-E2E-067 | Actual HTTP source | Object/prepare/create/run/review/result/artifact views are backed by observed successful backend HTTP responses; no fulfilled/intercepted response |
| P4-E2E-068 | Actual SSE source | runtime changes arrive from a backend `text/event-stream` response for exact `runId`; no polling or Demo replay masquerades as SSE |
| P4-E2E-069 | No frontend financial authority | bundle/source boundary contains no financial formula implementation; every visible metric text equals backend `display_value + display_unit` and metadata |
| P4-E2E-070 | Object identity closure | all Run/Goal/Scheme/history records resolve to the captured `objectId` |
| P4-E2E-071 | Run/Task identity closure | every Task/graph/event/calculation/evidence record resolves to captured `runId`; event `task_id`, when present, is in actual graph |
| P4-E2E-072 | Claim/Review/Artifact closure | captured Claim, exact Review, execution/canonical record, result, and artifacts resolve to the same Run/Object |
| P4-E2E-073 | Cross-object rejection | substituting `O_B`/`R_B`/`C_B`/`V_B`/`A_B` into A routes fails closed; A UI never shows B content |
| P4-E2E-074 | Prepare Scheme authority | response has new `draft_id`; Goal/Scheme Object IDs match; `confirmed_at` is null; plan is backend-generated |
| P4-E2E-075 | Exactly-once confirmation | one stable, request-bound, durable idempotency key across double click/response-loss/restart retry returns one `runId`; one persisted Run, one `run.created`, and one scheduler admission/`run.started` |
| P4-E2E-076 | Run list/detail consistency | list row and detail agree on Run/Object/status/as-of; after terminal reconciliation both agree on RELEASED/FAILED and timestamps |
| P4-E2E-077 | Snapshot cursor | authoritative composite projection includes the event sequence it represents; browser starts from that sequence without a race |
| P4-E2E-078 | SSE disconnect | connection is cut after a recorded nonterminal sequence; browser shows reconnecting/stale state without resetting progress |
| P4-E2E-079 | Numeric `Last-Event-ID` | reconnect request sends last committed sequence; server replays only events with greater sequence |
| P4-E2E-080 | Opaque `Last-Event-ID` | browser-context stream request using captured `event_id` resolves to the same suffix as its sequence |
| P4-E2E-081 | SSE gap-free resume | merged pre/post-disconnect sequences equal the backend persisted sequence range exactly |
| P4-E2E-082 | Duplicate idempotence | duplicate real frame changes no entity twice, adds no duplicate Task/history/review, and leaves projection equal to snapshot |
| P4-E2E-083 | SSE ordering | producer frames are strictly contiguous by per-Run sequence and unique by `event_id` |
| P4-E2E-084 | Delayed/out-of-order defense | delayed real frames are not applied over newer state; detected gap/order violation triggers authoritative reconciliation |
| P4-E2E-085 | Success terminal | `release.completed` precedes `run.completed`; stream closes after `run.completed`; UI reconciles then stops reconnecting |
| P4-E2E-086 | Failure terminal | `run.failed` closes stream; UI stays FAILED, exposes safe failure, and never enables released Results |
| P4-E2E-087 | Browser refresh during Run | route reload fetches backend snapshot, resumes after snapshot cursor, and converges to uninterrupted-browser state |
| P4-E2E-088 | Projection reconciliation | DOM projection and fresh backend Run/Task/graph/review/result reads are deeply equivalent on IDs, states, graph version and terminal outcome |
| P4-E2E-089 | Dynamic Graph | approved replan mutates only Actual Graph, increments version once per atomic mutation, retains planned graph, added Task and valid edges |
| P4-E2E-090 | Self-Correction | `task.self_correcting` → `task.correction_resolved` occurs on the same `taskId`; no new top-level Task; Correction remains in history/CER |
| P4-E2E-091 | Generated Capability Waiting | gap → same Task waiting → build/validation → approval → registration → same Task resume; graph Task count/version unchanged |
| P4-E2E-092 | Typed financial equality | visible value, unit, period, actuality and as-of equal one backend `ReleasedFinancialMetric` and matching Claim |
| P4-E2E-093 | Ratio/percentage semantics | canonical `0.6547` with unit RATIO and backend display `65.47`/`%` renders **65.47%**, never `0.6547%` or unlabeled `0.6547` |
| P4-E2E-094 | Claim Trace round trip | Report metric → exact Claim → exact Review → exact Task → exact Calculation/Evidence → exact Execution → original Report anchor |
| P4-E2E-095 | Report A/B/C consistency | A result/report, B Review and C Execution share exact `canonicalRecordId`, `runId`, Object and released Claim/calculation refs |
| P4-E2E-096 | Artifact integrity | HTML and PDF have distinct IDs; metadata Object/Run/report/canonical IDs, media type, size and hash match authorized downloaded bytes |
| P4-E2E-097 | Object history | Run completion appends versioned writeback/history; earlier Run snapshot is unchanged; comparison uses explicit base/current Run IDs |
| P4-E2E-098 | Durable reopen | new browser context and backend restart reopen Object/Run/A/B/C/artifacts from persistence with exact IDs and terminal state |
| P4-E2E-099 | Deployment-mode truth | bootstrap mode equals immutable Run mode; mode, source, LLM, trace, sandbox, proof, artifact and frontend alignment states are visible |
| P4-E2E-100 | Public/limited/offline policy | Public uses real HTTP/SSE and permitted LIVE calls; limited follows frozen policy; offline uses backend FIXTURE with Demo watermark and zero public calls |

## 5. Backend semantic mappings that the browser must preserve

| Concern | Phase 3 backend authority | Frontend adapter requirement |
|---|---|---|
| Run terminal | `RunStatus.RELEASED` plus `release.completed`, then `run.completed`; failure is `run.failed` | Map to user-facing COMPLETED/FAILED only after authoritative projection; do not treat `release.completed` as SSE terminal |
| Run active statuses | `PLANNING`, `RUNNING`, `REVIEW`, `PROVING` | Presentation labels may differ, but raw status and mapping version must be inspectable/testable |
| Progress | Task progress is `0..1` | If UI uses percent, format the backend value; do not infer from elapsed time |
| Self-correction | `task.self_correcting`, `task.correction_resolved` on same Task | Translate the event name if needed; never fabricate `correction.resolved` as a backend event |
| Dynamic graph | approved Replan; `graph.task_added`, edge add/remove events, `graph.version_changed`; Actual Graph only | Demo peer-gap story remains Demo-only. Real scene asserts the actual backend mutation (currently bounded risk follow-up) |
| Capability waiting | `capability.gap_detected` → `task.waiting_for_capability` → build/validation events → `capability.approved` → `capability.registered` → `task.resumed` | Multiple backend validation events may be grouped visually, but exact order/IDs must remain available |
| Review | one exact backend `ReviewRecord` may review many Claims; `reviewed_claim_refs` and checks are authoritative | Do not mint one fake Review ID per Claim. Focus the exact Review/check associated with the Claim |
| Financial metric | `canonical_value`, `canonical_unit`, `display_value`, `display_unit`, `period`, `period_basis`, `actuality`, `as_of`, currency and lineage refs | Render supplied display fields and metadata; never use a React formula to create authoritative output |
| Claim | typed material Claim matches metric value/unit/period/as-of and exact Calculation/Evidence refs | Derive Task only from the referenced Calculation record; no title/symbol guessing |
| A/B/C | Released result/report plus B/C projections from one Canonical Execution Record | Preserve `canonical_record_id` across all three tabs |
| SSE ID | SSE `id:` is numeric per-Run `sequence`; JSON also carries opaque `event_id` | Deduplicate by event identity, enforce sequence, and resume using the committed cursor |
| SSE terminal | stream returns after `run.completed` or `run.failed`; heartbeat is a comment | Heartbeat changes no business state; intentional terminal close does not reconnect |

## 6. Phase 4 integration entry blockers

These are contract gaps, not permission to modify code. The implementation owner must close each
one before a gate in that blocker's activation scope can run. A future-scope blocker is not a Phase
4A Core blocker.

| Blocker | Missing/frozen decision | Gates blocked | `activation_scope` |
|---|---|---|---|
| P4-BRIDGE-001 | Clean, independently accepted Phase 3 commit and authoritative acceptance corpus | all integrated gates | inherited from each target gate |
| P4-BRIDGE-002 | Global authoritative Run collection projection | 002, 005–007, 076 | `PHASE4_CORE_REQUIRED` |
| P4-BRIDGE-003 | Object search/provider-match endpoint or approved adapter contract | 012–016 | `PHASE4_CORE_REQUIRED` |
| P4-BRIDGE-004 | Atomic Run projection containing Run, Tasks, graphs, events cursor and result availability | 026–036, 077–088 | `PHASE4_CORE_REQUIRED` |
| P4-BRIDGE-005 | Claim/detail plus Evidence/Calculation detail or durable unavailable contracts | 042, 048–054, 094 | `PHASE4_CORE_REQUIRED` |
| P4-BRIDGE-006 | Exact Review record/check projection, not refs alone | 040–043, 053, 094–095 | `PHASE4_CORE_REQUIRED` |
| P4-BRIDGE-007 | Phase 4 `ReportArtifact` metadata/delivery contract with Object binding and authorized refs | 045–047, 096 | `PHASE4_CORE_REQUIRED` |
| P4-BRIDGE-008 | Versioned Object Research View and backend comparison projection | Phase 5 variants of 058–059, 062, 097 | `PHASE5_ACTIVATED` |
| P4-BRIDGE-009 | Durable prepare/confirm idempotency, draft expiry/version and consumed-draft behavior | 024–025, 074–075 | `PHASE4_CORE_REQUIRED` |
| P4-BRIDGE-010 | Event/status adapter mapping for Phase 3 names and complete event vocabulary | 026–036, 078–091 | `PHASE4_CORE_REQUIRED` |
| P4-BRIDGE-011 | Snapshot sequence/revision for race-free SSE reconciliation | 077, 087–088 | `PHASE4_CORE_REQUIRED` |
| P4-BRIDGE-012 | Bootstrap/health deployment-mode and component projection | 099–100 | `DEPLOYMENT_ACTIVATED` |
| P4-BRIDGE-013 | Run/Object identity on artifact projection and resolvable ownership for entities carrying only `run_id` | 070–073, 096 | `PHASE4_CORE_REQUIRED` |
| P4-BRIDGE-014 | Incremental-run/memory/freshness/writeback contract | Scene 06, incremental 058, 097 | `PHASE5_ACTIVATED` |
| P4-BRIDGE-015 | Exactly one durable `run.completed` or `run.failed` from every terminal path, including post-scheduler assurance/release failures | 085–086, SSE terminal cases | `PHASE4_CORE_REQUIRED` |

Observed Phase 3 routes are useful inputs but not sufficient by themselves: there is no global Run
collection, Claim API, exact Review-record detail response, report artifact delivery route,
versioned Research View/comparison response, or composite projection cursor in the currently
observed route set.

## 7. Network and frontend-authority assertions

For every `@public-real` execution:

1. Block service workers and fail the test if any route is fulfilled by the test harness.
2. Record every domain request. Object, Run, Review, result, trace and artifact DOM content must map
   to at least one successful backend response bearing a sanitized request ID.
3. Require the runtime response media type `text/event-stream`, exact Run path, and backend origin
   (direct or reviewed same-origin reverse proxy). `blob:`, `data:`, static JSON and timer replay fail.
4. Scan the production module graph/bundle for reachable Demo source, Demo IDs, frontend financial
   fixtures and data-URL report payloads. Any reachable occurrence fails. A dead source file excluded
   from the production graph is not runtime use, but release policy may separately forbid shipping it.
5. Capture typed metric JSON before inspecting the UI. The UI must use backend display fields. A
   source-boundary check additionally rejects frontend formula IDs and calculation implementations.
6. Assert the Run's evidence outcome is `LIVE` only when a current provider call for that same Run
   succeeded. Credential presence or a health probe is insufficient.
7. Clear storage, reload, and reopen in another browser context. If business state survives only in
   local/session storage or IndexedDB, fail.

The network ledger recognizes these observed Phase 3 operations. A reviewed same-origin alias or
aggregation endpoint is allowed, but the ledger must retain the downstream backend request(s) and
the response-to-projection mapping.

| Browser need | Observed Phase 3 operation | Acceptance note |
|---|---|---|
| Object collection/create/detail | `GET/POST /api/objects`, `GET /api/objects/{object_id}` | create uses `Idempotency-Key`; search/provider-match remains a bridge gap |
| Object state/financials/history | `GET /api/objects/{object_id}/state`, `/financials`, `/runs` | versioned Research View/comparison remains a bridge gap |
| Scheme prepare | `POST /api/research-runs/prepare` | returns draft Goal/Scheme; it is not yet an immutable planned-graph preview |
| confirm/create Run | `POST /api/research-runs` | uses `Idempotency-Key`; durable request binding/exact scheduler admission remain acceptance requirements |
| Run/Tasks/graphs | `GET /api/research-runs/{run_id}`, `/tasks`, `/graph` | separate reads lack one atomic projection cursor |
| release/report JSON | `GET /api/research-runs/{run_id}/result` | observed response contains released result/report, not the Phase 4 artifact delivery projection |
| B/C projections | `GET .../review-view`, `GET .../execution-view` | Review view currently exposes refs, so exact Review detail remains required |
| runtime | `GET /api/research-runs/{run_id}/events` | fetch-stream SSE with explicit `Last-Event-ID` |
| Claim/Evidence/Calculation/Artifact detail | no sufficient observed route | must use reviewed Phase 4 routes/projections; frontend synthesis is forbidden |

## 8. Financial and artifact oracle

For each displayed material metric, build this exact comparison tuple:

```text
(metricId, canonicalValue, canonicalUnit, displayValue, displayUnit,
 period, periodBasis, actuality, asOf, currency,
 calculationId, evidenceIds, claimId, runId)
```

The DOM must expose the same value, unit, period and as-of together in the metric's accessible
region. Hidden developer metadata alone does not satisfy visible financial semantics. Currency is
required for CURRENCY metrics. Method, observation count, lookback dates, price basis, corporate
action status and limitations are required where supplied for technical metrics.

The mandatory ratio fixture is backend-authored:

```json
{
  "canonical_value": "0.6547",
  "canonical_unit": "RATIO",
  "display_value": "65.47",
  "display_unit": "%"
}
```

Expected visible text is `65.47%`. The frontend is tested as a formatter/renderer, not as the
financial authority.

For each AVAILABLE artifact, the test obtains bytes through its authorized reference and verifies
content type, byte count and SHA-256 against metadata. HTML and PDF are separate artifacts. A local
filesystem path, public permanent URL, secret query string, unverified bytes, or cross-Run artifact
is a failure. An unavailable representation must be disabled and show the backend allowlisted
reason; it must not fall back to a Demo artifact.

## 9. Claim Trace acceptance path

The mandatory order is:

```text
Report metric C
  -> Claim C
  -> Review V whose reviewed_claim_refs/check subject_refs include C
  -> Task T == Calculation.task_id
  -> Calculation K referenced by C
  -> Evidence E referenced by C and K
  -> Execution X containing T, K, E, C and V
  -> return to the original report anchor for C
```

Every transition asserts the exact IDs before clicking onward. Closing a nested detail restores the
previous overlay and focus. Browser Back/Forward must replay the same logical route without
substituting the latest Run or Claim. If an Evidence/Calculation body is intentionally unavailable,
the durable unavailable view must retain O/R/T/C/V/K/E/A context and provide a direct return.

## 10. Deployment-mode future acceptance

`P4-E2E-099` and `P4-E2E-100` are defined now and run for every mode advertised by the future
release candidate. Their `activation_scope` is `DEPLOYMENT_ACTIVATED`: they become release-blocking
only for Phase 4B, RP2+, or Competition Release, not for Phase 4A Core. They do not authorize
deployment implementation.

| Mode | Required browser/network facts | Forbidden behavior |
|---|---|---|
| `PUBLIC_NETWORK_MODE` | backend bootstrap and immutable Run both say PUBLIC; frontend alignment is ALIGNED; domain reads use real HTTP/SSE; current successful provider records alone are LIVE; mode/source/LLM/trace/sandbox/proof/artifact outcomes are visible | Demo source/store, fixture substitution, silent cache, mode switch after provider failure, healthy trace claim for no-op adapter |
| `LIMITED_NETWORK_MODE` | bootstrap/Run say LIMITED; UI shows frozen per-component `LIVE_ALLOWED`/`CACHE_ONLY`/`DISABLED` policy and actual outcomes; HTTP/SSE remain integrated | frontend fixture, unverified cache, hidden fallback, mode inferred from missing credential |
| `OFFLINE_DEMO_MODE` | bootstrap/Run say OFFLINE; browser still uses real local backend HTTP/SSE/PostgreSQL; persistent Demo and FIXTURE/as-of labels; zero public-provider/LLM/trace calls; local artifact/proof states are exact | `DemoFrontendDataSource`, public network request, fixture labelled LIVE, in-memory-only persistence, removal of Demo watermark |

Across modes, a mode change requires a new process composition and a new Run ID. Refresh, browser
reopen, backend restart and artifact download must retain the original Run mode. Unknown mode or
frontend/backend mismatch blocks the integrated UI.

## 11. Activation-aware result model

Acceptance reports publish three independent results:

| Result | Required contents | Pre-activation handling |
|---|---|---|
| `PHASE4_CORE_E2E_RESULT` | real-backend `SCENE-01..04` plus every `PHASE4_CORE_REQUIRED` gate/variant | required for Phase 4A |
| `PHASE5_EXTENSION_E2E_RESULT` | real-backend `SCENE-05..06`, every `PHASE5_ACTIVATED` gate/variant, and applicable core regression | `DEFINED_NOT_ACTIVATED` until `PHASE5_OBJECT_MEMORY_IMPLEMENTED` |
| `DEPLOYMENT_E2E_RESULT` | `P4-E2E-099..100` for each declared mode plus applicable core regression | `DEFINED_NOT_ACTIVATED` until Phase 4B/RP2+/Competition activation |

Each result row carries `activation_scope`, `activation_state`, and `result`. Before activation,
`activation_state=DEFINED_NOT_ACTIVATED` and `result=null`. After activation,
`activation_state=REQUIRED` and the final result may only be `PASS` or `FAIL`.

## 12. Release rules

`PHASE4_CORE_E2E_RESULT` is `PASS` only when, in one manifested candidate:

- all real-backend `SCENE-01..04` scenarios pass;
- all core HTTP, SSE, identity, prepare/confirm, Run projection, Dynamic Graph, Self-Correction,
  Generated Capability Waiting, Review, financial metric, proof, A/B/C, artifact, Claim Trace, and
  refresh/persistence gates pass;
- the core Object slice proves Object collection, object-scoped Run history, exact historical Run
  opening, `latest_released_run_id`, same-Run Claim/artifact links, and `source_run_id` preservation;
- every required identity assertion and the two-object negative corpus pass;
- the build hash, backend commit, database revision, request/event ledger, and artifact hashes are
  retained, and no unresolved P0/P1 core integration finding remains.

This yields `PHASE4_CORE_PRODUCT_ACCEPTED` without requiring real Scene 05/06,
`ResearchObjectVersion`, `ResearchViewVersion`, `ComparisonDataset`, `IncrementalResearchSeed`,
backend-driven reuse/refresh/revalidate/prevent, or deployment gates 099–100.

Once a later scope is activated, its own required gates may only pass or fail and its roll-up follows
`PHASE4_E2E_GATE_ACTIVATION_MATRIX.md`. Demo results remain separate and never roll up into a real
result. Retries retain the failed attempt; a retry cannot erase a deterministic failure.

## 13. Design completion

The five Phase 4 design documents are complete. No Playwright files or application files are added
by this work.

```text
PHASE4_E2E_SPEC_READY = YES
PHASE4_CORE_GATE_SET_DEFINED = YES
PHASE5_EXTENSION_GATES_DEFINED = YES
DEPLOYMENT_EXTENSION_GATES_DEFINED = YES
PHASE4_E2E_DESIGN = FROZEN
WAITING_FOR_APPROVED_BACKEND_AND_FRONTEND_CANDIDATES = TRUE
PHASE4_E2E_IMPLEMENTED = NO
PHASE4_E2E_EXECUTED = NO
PHASE4_PRODUCT_ACCEPTED = NO
```
