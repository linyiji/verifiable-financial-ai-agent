# Phase 4A Backend Blocker Closure Matrix

Status: `PROVISIONAL_CONTRACT_DRAFT`  
Freeze state: `NOT_FINAL`  
Inspected backend: `codex/phase3-contracts@11fe8173a25ff7ac08bae42340ba7c6fae591be5`

“Contract closure” below means the draft makes one exact decision with an acceptance oracle. It
does not mean the current source implements or passes that decision.

## 1. Eight V17 blockers

| ID | Observed backend reality | Frozen draft decision | Exact delta/classification | Closure oracle | Contract closure | Implementation |
|---|---|---|---|---|---|---|
| `P4-BLOCKER-01` Global Run collection | No global collection or repository query; object route returns raw unordered Runs | Add `GET /api/research-runs`, fixed `(updated_at DESC,run_id DESC)`, filter-bound opaque cursor, limit 50/default and Run item with exact object/status/stage/progress/activity/graph/times/availability/watermark | Route/cursor `ADDITIVE_ROUTE_REQUIRED`; object/stage/progress/activity `PROJECTION_ONLY`; revision/accurate update facts `BACKEND_FIELD_REQUIRED` | `P4-E2E-002`, `005..007`, `067`, `076`; `P4-ID-006`, `025..027`; two-object/multipage/tampered-cursor evidence | `DRAFT_SPECIFIED` | `OPEN` |
| `P4-BLOCKER-02` Atomic Run projection | Run, Tasks, graph, result, review, execution are separate; no shared watermark; aggregate can be stale relative to events | Add `AtomicRunProjectionV1` from one committed snapshot with integer monotonic `projection_revision`, exact `projection_sequence`, immutable planned graph, actual graph/version, Tasks, lifecycle and component availability/IDs | Route `ADDITIVE_ROUTE_REQUIRED`; revision and atomic publication `BACKEND_FIELD_REQUIRED`; derived state `PROJECTION_ONLY` | Snapshot-at-N plus concurrent events; resume after N; deep equality to fresh projection: `P4-E2E-026..036`, `077`, `087..090`; `P4-SSE-012..013`, `020`; `P4-ID-006..010` | `DRAFT_SPECIFIED` | `OPEN` |
| `P4-BLOCKER-03` SSE recovery/terminal | Durable ordered PostgreSQL replay and numeric/opaque lookup exist, but cursor errors are lazy; ahead/terminal cursors heartbeat; post-scheduler/cancel paths can omit terminal; event/projection commits split | Keep raw names; preflight cursor; define invalid/ahead/cross-Run behavior, fetch-stream browser transport, exact duplicate/order/gap recovery, heartbeat, terminal-at-cursor close, PostgreSQL restart, and exactly one all-path terminal event (`run.completed` or `run.failed`) | Existing log/replay `EXISTING_BACKEND`; normalized version fields `PROJECTION_ONLY`; preflight/finalizer/atomic terminal `BACKEND_FIELD_REQUIRED` | Entire `P4-SSE-001..020`; `P4-E2E-068`, `077..088`, `098`; `P4-BRIDGE-015`; DB/event/network ledgers | `DRAFT_SPECIFIED` | `OPEN` |
| `P4-BLOCKER-04` Prepare/Confirm | Prepare produces Goal+Scheme only; plan/Tasks at confirm. Draft lacks version/hash/expiry/consume. Confirm key is optional, process-local, unbound; background admission not durable | Preview is explicitly `SCHEME_ONLY`; no fake Tasks. Require request-bound keys, immutable draft version/hash/expiry, expected Object, atomic consume/Run/plan/initial-events/admission, same-key replay and conflict rules, automatic runtime start | Current request/Goal/Scheme/paths `EXISTING_BACKEND`; draft/idempotency/admission facts `BACKEND_FIELD_REQUIRED`; current cache/background task `SEMANTIC_CONFLICT` | `P4-E2E-017..025`, `074..075`, `098`; `P4-ID-001..005`, `023`; double-click/response-loss/restart and different-body/different-key negatives | `DRAFT_SPECIFIED` | `OPEN` |
| `P4-BLOCKER-05` Claim/Review/Trace | Strong typed Claim/metric/K/E/review/proof/CER/result records exist, but no detail/trace routes; Review view is ref-only/release-gated; no check IDs or anchors; default API uses legacy release path | Add exact same-Run Claim detail and `TraceBundleV1`; upgrade `/review-view` independently of release; K->Task only; reciprocal Review binding; policy-aware proof; O/R/X/L closure; scoped report/review/task/execution anchors; unavailable retained detail, never text/latest/first joins | Existing records `EXISTING_BACKEND`; joins/wrappers `PROJECTION_ONLY`; routes `ADDITIVE_ROUTE_REQUIRED`; check/anchor/retention authority `BACKEND_FIELD_REQUIRED`; release gating/legacy API composition `SEMANTIC_CONFLICT` | `P4-E2E-040..054`, `069..073`, `092..095`, `098`; `P4-ID-011..020`, `023`, `025..028`; cross-Run C/E/K/V/P substitutions | `DRAFT_SPECIFIED` | `OPEN` |
| `P4-BLOCKER-06` Report artifact delivery | Internal records have Run/X/L, hash/size/renderer/time and internal locator; HTML/PDF publisher exists mainly in acceptance composition; no public metadata/content route, object binding, availability, auth or anchors | `ReportArtifactGroupV1`, `report_id := released_result_id`, fixed HTML/PDF slots with nullable byte-derived fields when unavailable, distinct IDs when available, mandatory available HTML for successful release, optional explicitly unavailable PDF, allowlisted renderer mapping, same-origin authorized ref, repeat full binding/hash/size/type checks on content | Internal fields `EXISTING_BACKEND`; grouping/O/report/availability `PROJECTION_ONLY`; failure attempt facts `BACKEND_FIELD_REQUIRED`; metadata/content routes `ADDITIVE_ROUTE_REQUIRED`; exposing internal ref `SEMANTIC_CONFLICT` | `P4-E2E-045..049`, `067`, `072..073`, `095..096`, `098`; `P4-ID-019..020`, `023`, `025..027`; byte rehash and substitution | `DRAFT_SPECIFIED` | `OPEN` |
| `P4-BLOCKER-07` Released Object Core | Stable Object and object Runs exist; no latest released field; `/financials` is lossy and calls summaries versions; `/state` exposes writeback proposals | Add `/objects/{object_id}/released-state`; choose only valid object-owned RELEASED closure ordered `(released_at DESC,run_id DESC)`; source Run equals latest released; newer non-release never supersedes; reuse global item for object history | Existing Object/Runs/results `EXISTING_BACKEND`; latest/closure/counts `PROJECTION_ONLY`; route/cursor `ADDITIVE_ROUTE_REQUIRED`; current state/financials as authority `SEMANTIC_CONFLICT`; all memory/version/comparison/writeback `PHASE5_DEFERRED` | `P4-E2E-003`, `057`, Core `059`, `060..061`, `063`, `070`, `073`, `076`, `092`, `098`; `P4-ID-001`, `006`, `023..027` | `DRAFT_SPECIFIED` | `OPEN` |
| `P4-BLOCKER-08` Event/status normalization | Raw enums are richer than frontend; progress is ratio; correction/review meanings and graph payloads conflict; some event types have no producer | Preserve raw types/status; total Run/Task/Review/Proof/availability maps; `RuntimeEventNormalizedV1` with payload version and graph version; unknowns fail closed; sparse graph events require projection refresh | Raw values `EXISTING_BACKEND`; mapping/version/redaction `PROJECTION_ONLY`; safe missing payload/failure facts `BACKEND_FIELD_REQUIRED`; direct casts/default Task/synthetic events `SEMANTIC_CONFLICT` | `P4-E2E-026..043`, `069`, `077..095`; `P4-SSE-002..005`, `010..020`; `P4-ID-007..020`; unknown enum/payload injection | `DRAFT_SPECIFIED` | `OPEN` |

Result: `BLOCKERS_COVERED = 8/8`. No blocker is waived. All eight require later implementation
and executed acceptance after final Phase 3 delta reconciliation.

## 2. Actual-repository conflicts resolved by this draft

| Conflict with older/frontend assumptions | Repository evidence | Contract authority decision |
|---|---|---|
| Prepare preview was assumed to contain planned Tasks | Planner creates Tasks only after confirmed Scheme | Show Goal+Scheme as `SCHEME_ONLY`; planned graph is explicitly `NOT_GENERATED` until confirm |
| Frontend progress treated event value as percent | `Task.progress` is constrained `0..1` | Preserve Task ratio; projection supplies explicit fraction+percent under one named method |
| Frontend `correction.resolved` | raw event is `task.correction_resolved` | Preserve raw name; UI label is presentation only |
| Frontend `review.resolved` meant one exception repaired | raw event means Run-level Review completion | Preserve backend meaning; per-check resolution requires explicit relation |
| Frontend expected synthetic capability/report/result events | no such raw types | Never fabricate them; consume real lifecycle and refresh projection |
| `graph.task_added` looked sufficient to make a Task | actual payload is only Task ID/replan/version | Quarantine and refresh atomic projection; never default missing Task fields |
| Review was treated as released-result-only | persisted BLOCK/REVIEW can exist while release fails | Review availability is independent of result availability |
| Existing result route appears sufficient for typed finance | default API composition can follow legacy empty typed-Claim path | Phase 4 deployable composition must use accepted typed financial/proof/report path; empty material output cannot be professional release |
| Existing Object `/financials` calls summaries “versions” | no Research Object/View version store exists | Do not call it version authority; expose only current valid released-state and exact Run history |
| `ReportArtifactRecord.artifact_ref` looked deliverable | value is internal `artifact://` or filesystem-backed locator | Never cross public boundary; mint authorized same-origin ref and recheck byte integrity |

## 3. Twelve preaudit blockers folded into eight V17 blockers

| Earlier IDs | V17 owner |
|---|---|
| `P4-CB-009` | `P4-BLOCKER-01` |
| `P4-CB-001` | `P4-BLOCKER-02` |
| `P4-CB-002`, `003` | `P4-BLOCKER-03`, `08` |
| `P4-CB-007`, `008` | `P4-BLOCKER-04` |
| `P4-CB-006`, `011` | `P4-BLOCKER-05` |
| `P4-CB-004` | `P4-BLOCKER-06` |
| `P4-CB-005` | `P4-BLOCKER-05`, `06`, `07` |
| `P4-CB-010`, `012` | `P4-BLOCKER-08` |

## 4. Phase boundary check

The matrix defines no `ResearchObjectVersion`, `ResearchViewVersion`, `ResearchMemory`,
`ComparisonDataset`, `IncrementalResearchSeed`, freshness/reuse/refresh/revalidate/prevent decision,
Object writeback, real Scene 05/06, POT, or capability certification/global registry. Generated
capability lifecycle is visible only as supporting activity in its original Task.

`PHASE5_LEAKAGE = 0`.
