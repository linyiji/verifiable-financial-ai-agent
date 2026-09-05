# Phase 4 Contract Blockers

Classification: `PROVISIONAL_CONTRACT_PREAUDIT`

Overall preaudit result: `READY_WITH_GAPS`.

The items below block the start of Phase 4 implementation until the contract decision is frozen. They are not instructions to modify either active candidate now. None requires reopening Demo fixtures or requiring Phase 5 Object Memory.

## 1. Must-freeze blockers

| ID | Priority | Contract blocker | Evidence | Required decision / closure proof | FBG |
|---|---|---|---|---|---|
| P4-CB-001 | P0 | No coherent Run projection + event watermark | Frontend requires `RuntimeProjection`; backend exposes Run, Tasks/graph, result, review and execution through separate reads and has an internal checkpoint only | Freeze one projection schema containing owner identity, planned/actual graph, lifecycle, claims/review/report/execution/release state, `last_sequence`, `graph_version`, and schema version. Contract test must demonstrate event-consistent snapshot + replay. | FBG-002 |
| P4-CB-002 | P0 | Raw backend events are not safe inputs to the current reducer | Progress scale differs; correction event name differs; `review.resolved` has conflicting meaning; graph payloads differ; backend terminal events are absent from frontend union | Freeze a versioned normalization table and payload schemas. Contract tests must replay real backend events through the production reducer without invented defaults or state rollback. | FBG-002, 003, 005 |
| P4-CB-003 | P0 | SSE cursor/recovery/terminal semantics are incomplete end to end | Backend supports `Last-Event-ID`, replay and heartbeat; frontend transport cannot pass initial watermark; stale/gapped events are applied; reconnect after a terminal cursor can remain open; post-scheduler failures may not emit `run.failed` | Freeze browser-compatible initial cursor, duplicate/gap/out-of-order behavior, unknown/ahead cursor response, terminal snapshot behavior and exactly-one terminal event for every terminal path. Verify restart replay with target PostgreSQL composition. | FBG-002 |
| P4-CB-004 | P0 | Report artifact delivery cannot safely expose the actual record | Backend record has internal `artifact://` reference and no direct object/availability/authorization/failure/anchor fields; normal API has no HTML/PDF artifact delivery route | Freeze the grouped frontend-safe artifact DTO and authorization/binding checks. Tests must reject cross-object/run substitution and validate media type, hash, size and independently available HTML/PDF bytes. | FBG-004 |
| P4-CB-005 | P0 | Released financial values would be lossy in the frontend type | Backend has canonical/display units, period basis, actuality, as-of, currency and lineage; frontend retains only period/value/estimate | Freeze a lossless metric/Claim projection including calculation/evidence/Claim/Proof refs. Tests must show no ratio→percent, period, release, or proof inference in React. | FBG-004, 005, 006 |
| P4-CB-006 | P0 | Claim Trace cannot close to exact report/review/task/proof/execution anchors | Claim has no object/task/review/proof/report anchor fields; Task is indirect; Judgment is untyped JSON; rendered reports have no per-Claim anchor manifest | Freeze the run-scoped Trace projection, primary/multiple Task rule, typed Judgment subset or unavailable state, and representation-scoped anchor manifest. Cross-Run/object negative tests are mandatory. | FBG-006 |
| P4-CB-007 | P1 | Prepare/Confirm models describe different user-visible boundaries | Frontend prepare returns `ResearchPlan` with Tasks and confirms `planId`; backend prepare returns Goal + Scheme draft and creates graph only on confirm | Choose one user-visible boundary. Freeze request fields, draft/plan binding, immutable preview, expiry/version, confirm response and retry behavior. | FBG-008 |
| P4-CB-008 | P1 | Confirm idempotency is not durable or request-bound | Service cache is process-local `(operation, key)` and does not validate the same draft/body; no expiry/reuse conflict is specified | Freeze durable key scope and request hash/draft binding. Same key+same request returns same Run; same key+different request fails; restart retains outcome. | FBG-008 |
| P4-CB-009 | P1 | Global Research Run collection is absent | Backend only exposes object-scoped Runs; frontend shell calls `listResearchRuns()` | Freeze collection item, stable ordering, pagination/filter cursor, object summary, status/stage/progress/activity/graph version and result availability. | FBG-001 |
| P4-CB-010 | P1 | Run/Task/Review/proof enums have no total mapping | Backend and frontend vocabularies materially differ | Freeze total backend→frontend projection maps, including cancelled, waiting-for-capability, review, capability-build-failed, unsupported/not-implemented proof, uncertainty and resolved exception history. Unknown values recover/fail closed. | FBG-001, 003, 005 |
| P4-CB-011 | P1 | Financial Review endpoint is a ref summary, not the UI contract | Backend `FinancialReviewView` exposes ref arrays and one runtime outcome; frontend needs per-Claim and exception records | Freeze per-Claim/check expansion, blocking/user-action semantics, uncertainty rule, correction path and resolved timestamp/history. | FBG-005 |
| P4-CB-012 | P1 | Dynamic graph events cannot authoritatively construct frontend Tasks | `graph.task_added` lacks Task definition; graph version field name differs; reducer fabricates labels/dependencies | Freeze “complete event payload” versus “refresh projection” behavior. Production must source Tasks/dependencies from the actual graph. | FBG-002, 003 |

## 2. Required contract decisions

These are the smallest decisions needed to clear the blockers. They specify boundaries, not route implementation.

### A. Identity and projection version

Freeze:

```text
projection_schema_version
object_id
run_id
last_sequence
graph_version
terminal
```

Every nested record must be validated against `run_id`; object identity is resolved once through the Run. Do not require every backend storage model to duplicate `object_id`.

### B. Status and progress maps

Freeze explicit, total maps for Run, Task, Review and Proof. Backend Task `progress` remains `0..1`; the Phase 4 projection or client adapter converts to frontend percent exactly once. No page performs conversion.

### C. Prepare/Confirm

Freeze one of two acceptable models:

1. prepare returns a draft with a previewable planned graph; confirm creates exactly one Run from that immutable draft; or
2. frontend previews the Scheme and labels it accurately, while the planned graph appears only after confirm.

In either model, object, goal, as-of, template/mode/preferences, draft/plan version, expiry and idempotency behavior are explicit.

### D. Snapshot/SSE handshake

Freeze the handshake in `PHASE4_SSE_EVENT_MAPPING.md`. Native `EventSource` cannot set an arbitrary initial `Last-Event-ID` header, so query cursor, cookie/server session, or a fetch-stream transport must be selected explicitly.

### E. Metric/Claim/Review/Trace

Freeze the lossless metric and `TraceContext` projections in the mapping documents. The frontend may format values but may not reinterpret units, periods, actuality, release status or proof validity.

### F. Report artifacts

Keep `ReportArtifactRecord` as the internal immutable representation record. Freeze a separate delivery projection matching the deployment design: exact object/run/report binding, independent HTML/PDF records, availability, safe failure code, renderer metadata and opaque authorized reference. Raw internal artifact refs never cross the API boundary.

## 3. Adaptations that do not block contract freeze

These may be implemented after the decisions above without reopening domain design:

- snake_case to camelCase conversion;
- route aliases and composition hidden in `apps/web/src/api/client.ts`;
- mapping `company_name → name` and `draft_id → planId` if the chosen semantics match;
- converting RFC 3339 strings to localized display;
- UI labels for backend agent/skill/task types;
- pagination controls once cursor/order semantics are fixed;
- separate backend route calls behind a server-side composition layer, provided the client receives one event-consistent projection;
- keeping HTML/PDF semantic hashes internal until an optional public extension is reviewed.

## 4. Explicitly deferred, not blockers

### `PHASE5+`

- applied/versioned Object Memory;
- Research View history DTOs;
- previous/current comparison records and Claim revision categories;
- durable incremental reuse/refresh/revalidate strategy;
- production parity for Demo Scene 5/6;
- POT or any unrelated persistence/object technology.

### `DEPLOYMENT_RP2+`

- `deployment_mode` and frontend-mode alignment;
- data/LLM/trace/sandbox component status;
- process health/readiness projections;
- release manifest identity;
- operational artifact-store status.

These fields must remain absent/unavailable until authoritative. Phase 4 must not derive them from provider names, fixture use or environment assumptions.

## 5. FBG disposition summary

| FBG | State | Clears when |
|---|---|---|
| FBG-001 | `STILL_OPEN` | P4-CB-009 and status collection fields are frozen and later implemented. |
| FBG-002 | `PARTIALLY_RESOLVED` | P4-CB-001/002/003/012 are frozen; real replay/recovery contract tests pass. |
| FBG-003 | `CONTRACT_CHANGED` | Frontend consumes the actual supporting-activity lifecycle and same-Task invariant. |
| FBG-004 | `PARTIALLY_RESOLVED` | P4-CB-004/005 delivery and integrity contracts pass. |
| FBG-005 | `PARTIALLY_RESOLVED` | P4-CB-002/010/011 provide correct per-Claim and exception semantics. |
| FBG-006 | `PARTIALLY_RESOLVED` | P4-CB-005/006 close exact trace and anchors. |
| FBG-007 | `PARTIALLY_RESOLVED` | Phase 4 uses exact Run history safely; true version comparison remains Phase 5. |
| FBG-008 | `CONTRACT_CHANGED` | P4-CB-007/008 freeze the chosen workflow and durable idempotency. |

No FBG may be marked `CLOSED` from a model class or route name alone; the frontend and backend contract tests must exercise the same wire shape.

## 6. Phase 4 entry gate

Phase 4 implementation may begin only after all P0/P1 rows above have an approved contract decision and candidate SHAs are final enough for a focused delta reconciliation. Implementation completion is a later gate.

Required entry evidence:

- final backend branch, HEAD, clean/dirty fingerprint;
- final frontend branch, HEAD, clean/dirty fingerprint;
- approved projection schemas and enum/event maps;
- approved prepare/confirm and SSE recovery semantics;
- approved artifact/trace authorization and identity rules;
- focused delta showing no unreviewed `SEMANTIC_CONFLICT` or `BLOCKER` against these documents.

Current state:

```text
PREAUDIT = READY_WITH_GAPS
CONTRACT_FREEZE = NOT_READY
PHASE4_IMPLEMENTATION = NOT_AUTHORIZED_BY_THIS_AUDIT
```
