# Phase 4 Browser Scenario Matrix

Status: **AUTHORITATIVE DESIGN — FROZEN — NOT YET IMPLEMENTED**  
Companion gate set: `PHASE4_E2E_ACCEPTANCE_SPEC.md`  
Activation authority: `PHASE4_E2E_GATE_ACTIVATION_MATRIX.md`

## 1. Scenario execution contract

The six frontend Scenes are retained as product stories, but each has two independent executions:

- **D — Frontend-only Demo:** the frozen `DemoScenarioStore` and Demo runtime prove rendering,
  reducer and interaction semantics only. Its result class is `DEMO_UX_ONLY`; it has no real-gate
  `activation_scope`.
- **R — Real backend:** the browser obtains all domain state over actual HTTP/SSE and asserts it
  against backend records. R is authoritative only once the Scene's `activation_scope` is active.

No D result may satisfy an R assertion. Reports must publish D and R results in separate columns.
The Phase 4 Core aggregate uses the activated R variants of `SCENE-01..04` only. Real `SCENE-05`
and `SCENE-06` remain defined but do not enter that aggregate.

Every activated R scenario:

1. captures `objectId`, `runId`, `taskId`, `claimId`, `reviewId`, and `artifactId` from the backend;
2. completes an identity closure check for all six IDs, even when the scene's main visual moment
   occurs before release;
3. includes Object B and at least one wrong-Object/wrong-Run negative lookup;
4. verifies browser refresh and Back/Forward at the scene-specific checkpoint;
5. ends by comparing the visible projection with a fresh backend projection;
6. retains the HTTP/SSE ledger and uses no frontend response fulfilment.

Integrated IDs are opaque. The examples `O`, `R`, `T`, `C`, `V`, and `A` below are test aliases,
not required ID formats.

## 2. Stable browser observability contract

Implementation may locate ordinary controls by accessible role/name. Repeated domain records and
exact trace targets require stable non-authoritative observability attributes:

| Element | Required observable identity |
|---|---|
| Object card/detail | `data-object-id=O` |
| Run row/page | `data-run-id=R`, `data-object-id=O` |
| Task/path node/drawer | `data-task-id=T`, `data-run-id=R` |
| Claim anchor/drawer | `data-claim-id=C`, `data-run-id=R` |
| Review record/check | `data-review-id=V`, `data-claim-id=C` where the check is Claim-specific |
| Calculation/Evidence detail | `data-calculation-id=K` / `data-evidence-id=E` |
| Execution target | `data-canonical-record-id=X`, `data-task-id=T` |
| Artifact action | `data-artifact-id=A`, format and availability |
| Metric accessible region | metric ID plus visible value, unit, period and as-of |

These attributes expose backend IDs for testing and accessibility; they do not create state. If the
product chooses another stable mechanism, it must expose the same exact identities without parsing
human-readable text.

## 3. Summary matrix

The gate column records the stable defined coverage. The activation matrix controls which listed
gate variants enter the current aggregate. Scene scope and gate scope are independent: a core gate
referenced by an inactive future Scene remains core-required through its activated Scene/variant;
a deployment gate associated with a core Scene waits for deployment activation.

| Scene | Product purpose | D: frontend-only semantics | R: backend-authoritative proof | R `activation_scope` | Defined gates |
|---|---|---|---|---|---|
| SCENE-01 Full Research | End-to-end financial research | Frozen full Demo replay reaches rich A/B/C and READY Demo artifact | create/select Object → prepare unconfirmed Scheme → exactly-once Run → real SSE → typed metrics/Claims/Review/CER → verified HTML/PDF → RELEASED | `PHASE4_CORE_REQUIRED` | 004–028, 040–047, 065–076, 083, 085, 092–096; 099–100 when deployment-activated |
| SCENE-02 Dynamic Path | Runtime is not a fixed workflow | Demo peer gap adds `TASK-B1`, rewires valuation, Graph v2 | actual Phase 3 Replan/Graph events add the backend-selected bounded Task (currently risk follow-up), mutate Actual only, then release | `PHASE4_CORE_REQUIRED` | 029–036, 065–073, 076–089, 092–096 |
| SCENE-03 Self-Correction + Review | Detect, repair and review a financial error | Demo period conflict loops and appears resolved in exception history | real period mismatch emits `task.self_correcting` then `task.correction_resolved` on one Task; recalculation and exact independent Review pass before release | `PHASE4_CORE_REQUIRED` | 034, 040–043, 065–073, 076–090, 092–095 |
| SCENE-04 Claim Trace | Verifiable report navigation | Demo trace preserves origin and uses durable unavailable placeholders | exact backend Report Claim → Review → Task → Calculation/Evidence → Execution → Report round trip | `PHASE4_CORE_REQUIRED` | 042–055, 063, 065–073, 087–088, 092–096 |
| SCENE-05 Object Accumulation | Long-lived versioned research asset | two immutable Demo releases compare changed/unchanged Claims | two persisted real Runs append immutable versions; history/latest/comparison and historical Claim links use explicit Run IDs | `PHASE5_ACTIVATED` | 057–063, 065–073, 076, 087–088, 092, 094–098 |
| SCENE-06 Incremental Return | Reuse memory and refresh what changed | Demo shows REUSE/REFRESH/REVALIDATE/PREVENT from prior Run | backend incremental plan references exact prior Run, performs freshness decision, reports actual delta (including an empty delta), appends new version | `PHASE5_ACTIVATED` | 017–025, 058–063, 065–076, 087–088, 092, 094–098; 099–100 when deployment-activated |

## 4. SCENE-01 — Full Financial Research

### D — Demo scenario

Given `scene-01-full`, replay the frozen Demo events through the production reducer boundary. Assert
the Demo watermark/source, six owned Tasks, capability-supporting activity, four Demo Claims and
reviews, Report READY, Execution RELEASED, Result AVAILABLE, and Run COMPLETED. Demo HTML may be
downloaded; Demo PDF follows the frozen scenario's explicit availability state. None of these
values is backend evidence.

### R — Real backend scenario

`activation_scope = PHASE4_CORE_REQUIRED`

| Step | Browser action | Network/record oracle | Required visible assertion |
|---:|---|---|---|
| 1 | Open Objects and select O, or create O from provider search | Object GET/POST returns O; idempotency ledger contains one create at most | selected company, symbol and O agree |
| 2 | Enter goal and continue | no Run exists yet | goal is retained and bound to O |
| 3 | Prepare Research Scheme | one prepare response contains `draft_id`, Goal and Scheme with O; `confirmed_at=null` | plan/scope/data/method/limitations are the returned Scheme projection |
| 4 | Optionally regenerate once | second prepare returns a different draft/Scheme; old draft becomes UI-ineligible | visible plan changes to the second response |
| 5 | double-click Start; simulate lost first response and retry, including a restart retry variant | one stable request-bound/durable idempotency key; all successful responses identify the same R; exactly one persisted Run, `run.created`, and scheduler admission/`run.started` | busy guard, then route for R |
| 6 | Observe execution | actual SSE response for R; persisted events are contiguous | stage, current activity, Task statuses and progress follow events/snapshot |
| 7 | Open Initial/Actual/Compare and a Task | planned and actual graph reads for R | exact T, dependencies, status and graph version |
| 8 | Wait for release | `review.started`/`review.resolved`; proof policy; `release.completed` then terminal `run.completed` | Review passes; Results enable only after authoritative release/terminal reconciliation |
| 9 | Inspect financial metric | one typed metric M and Claim C from released result | visible value/unit/period/as-of exactly match M; `0.6547 RATIO` corpus displays `65.47%` |
| 10 | Open A/B/C | result/report, exact Review V, and Execution/CER X | same O/R/X and same Claim/calculation refs in all views |
| 11 | Download HTML and PDF | separate AVAILABLE artifacts A-html/A-pdf with verified bytes | correct controls, media types and filenames; no Demo fallback |
| 12 | refresh Results, then Back/Forward | new HTTP reads; no local-state authority | exact O/R/T/C/V/A and selected tab restore |

Final identity assertion: O/R/T/C/V/A are all non-empty and close through the backend ownership
graph. Querying A's Claim using Object B/Run B fails closed.

## 5. SCENE-02 — Dynamic Research Path

### D — Demo scenario

Given `scene-02-dynamic`, assert seven initial Tasks, a peer evidence gap, one `ADD_TASK` for
`TASK-B1`, one dependency change, eight actual Tasks, Graph v2, retained downstream Tasks, and an
ADDED marker. This is the frozen Demo story only.

### R — Real backend scenario

`activation_scope = PHASE4_CORE_REQUIRED`

The real scenario follows the backend's actual decision. It must not force the Demo peer narrative
onto the backend. With the observed Phase 3 runtime, the bounded risk follow-up is the expected
mutation.

| Checkpoint | Backend oracle | Browser assertion |
|---|---|---|
| Planned snapshot | immutable graph P at version 1 | Initial Plan renders exactly P before and after mutation |
| Replan request | `replan.requested` has R, requesting T and `replan_id` | path history shows pending reason without adding a Task yet |
| Approval | later `replan.approved` carries same `replan_id` and authorized decider | mutation is marked approved; no human action is fabricated |
| Atomic mutation | `graph.task_added`, required edge remove/add events, then one `graph.version_changed` | Actual Path adds exact T-added once, marks ADDED and shows exact rewiring |
| Graph validity | fresh graph G has R, version P+1, unique Task IDs, known dependencies, no cycle | Actual and Compare match G; Initial remains P |
| Task navigation | mutation references contain exact trigger/added/affected IDs | every reference opens that exact Task drawer |
| Refresh/replay | refresh after `graph.task_added` but before terminal | snapshot + SSE cursor converges to one T-added and one mutation history entry |
| Completion | continue the same R through review/release | capture C/V/A and complete O/R/T/C/V/A identity closure |

The real assertion fails if the frontend labels a backend risk-follow-up as Demo “Additional Peer
Evidence,” loses an existing downstream Task, increments graph version twice, mutates the planned
graph, or constructs an added Task from a local template rather than the backend graph.

## 6. SCENE-03 — Self-Correction and Financial Review

### D — Demo scenario

Given `scene-03-correction`, assert the Demo period-conflict loop, resolved exception history, Full
Review/Exception filters, four Demo Claim reviews and coherent A/B/C. The reducer's Demo event name
`correction.resolved` is not evidence that the backend emitted that type.

### R — Real backend scenario

`activation_scope = PHASE4_CORE_REQUIRED`

| Step | Exact assertion |
|---:|---|
| 1 | Capture the financial Task T and the two mismatched Evidence candidates from backend records |
| 2 | Observe `task.self_correcting` for R/T with `problem_code=PERIOD_MISMATCH` |
| 3 | Observe later `task.correction_resolved` for the same R/T and capture correction ID |
| 4 | Assert actual graph Task count/version do not change because self-correction is internal to T |
| 5 | Assert the rejected mismatched calculation is not released; the corrected Calculation K uses the period-aligned Evidence cohort |
| 6 | Open Task T and focus exact correction timeline events; refresh and assert they remain visible |
| 7 | Open Financial Review V. V is the real backend Review record; its reviewed Claim/calculation refs and checks include C/K, and status is PASS before release |
| 8 | Exception view derives resolved history from the Correction/Review projection; All/Open/Resolved counts equal source records; it does not create a second truth |
| 9 | Continue to terminal, capture artifact A, and assert O/R/T/C/V/A closure plus A/B/C canonical identity |

If Review is BLOCK/REVIEW, the run must not release. The negative variant deliberately introduces a
semantic mismatch and asserts Review/release fail closed rather than expecting a PASS repair.

## 7. SCENE-04 — Claim Trace / Verifiable Research

### D — Demo scenario

Given `scene-04-trace`, assert Demo origin-aware Report/Review/Task/Execution focus, Task-to-Claim
return, and ID-bearing Evidence/Calculation unavailable panels. These placeholders do not prove
backend artifacts exist.

### R — Real backend scenario

`activation_scope = PHASE4_CORE_REQUIRED`

Use one released material metric and capture M/C/K/T/E/V/X/A from the backend before navigation.
Execute this exact browser path:

| Order | Action | Required exact target |
|---:|---|---|
| 1 | click metric in Report A | Claim drawer C; O/R and report anchor match |
| 2 | locate Review | Review V and the exact check/record that covers C |
| 3 | open Task | T equals the `task_id` of K referenced by C |
| 4 | open Calculation | K equals C's calculation ref; canonical value/unit and inputs match M |
| 5 | open each Evidence | each E is in both C support and K inputs, and belongs to R/O |
| 6 | locate Execution | X contains refs for T, K, E, C and V; exact row is highlighted |
| 7 | browser Back/Forward through two transitions | each route restores the same IDs, focus and tab |
| 8 | return/close | original Report anchor for C is focused/highlighted |
| 9 | refresh with Claim drawer open | new backend reads restore C and do not use a fallback Claim |

Repeat one lookup with C from Object B under R. The API/UI must return not-found/forbidden or a
durable unavailable state. Showing C from B, the latest Claim, or a Claim chosen by title is a fail.

Final identity assertion includes artifact A from the Report view, even though the trace's primary
focus is C.

## 8. SCENE-05 — Research Object Accumulation

### D — Demo scenario

Given `scene-05-object-history`, assert the two immutable Demo snapshots, one
`latestReleasedRunId`, fixed base/current comparison, changed/unchanged Claim categories and
source-Run Claim links.

### R — Real backend scenario

`activation_scope = PHASE5_ACTIVATED`  
Before `PHASE5_OBJECT_MEMORY_IMPLEMENTED`, this real scenario is
`DEFINED_NOT_ACTIVATED`; its full semantics below remain preserved and are not a Phase 4 Core gate.

1. Use one Object O and complete Run R1. Capture T1/C1/V1/A1 and the released Object writeback/version.
2. Complete a later Run R2 for O. Capture T2/C2/V2/A2.
3. Open Object Overview. The latest title, KPIs, Research View, Claim links and “latest research”
   action must all use R2, not a mixture of R1/R2.
4. Open Financials/History/Research View. Every version row carries its source Run ID. R1 data and
   artifact hash remain byte/record-identical to their pre-R2 snapshots.
5. Compare explicit `previousRunId=R1` and `currentRunId=R2`. Each comparison row equals the backend
   projection and is categorized changed/unchanged/new without frontend financial recomputation.
6. Click a C1 comparison row and verify the entire trace remains on R1, including V1/T1/A1. Return
   and click C2, verifying R2/V2/T2/A2.
7. Refresh, use Back/Forward, then reopen in a fresh browser context. History order, fixed comparison
   pair and exact IDs persist.
8. Use Object B's Run/Claim/artifact IDs against O. The UI/API fail closed without fallback.

This Scene has two complete identity tuples. It passes only if both
`O/R1/T1/C1/V1/A1` and `O/R2/T2/C2/V2/A2` close.

## 9. SCENE-06 — Incremental Returning User

### D — Demo scenario

Given `scene-06-incremental`, assert the prior Demo Run memory, freshness step,
REUSE/REFRESH/REVALIDATE/PREVENT groups, current Demo Claims, resolved-issue count change and Demo
writeback. The Demo's claimed work savings are not backend evidence.

### R — Real backend scenario

`activation_scope = PHASE5_ACTIVATED`  
Before `PHASE5_OBJECT_MEMORY_IMPLEMENTED`, this real scenario is
`DEFINED_NOT_ACTIVATED`; its full semantics below remain preserved and are not a Phase 4 Core gate.

| Step | Backend oracle | Browser assertion |
|---:|---|---|
| 1 | select O with released prior Run R0 | wizard identifies exact R0 as memory source |
| 2 | choose INCREMENTAL and prepare | backend Scheme/plan explicitly records mode and `sourceRunId=R0`; no frontend-only mode flag |
| 3 | inspect strategy | backend classifies tasks/data as reuse, refresh, revalidate or prevent | UI displays the exact classification and limitations |
| 4 | start exactly once | create new R1 with R1 != R0 and same O | route/status identify R1; R0 remains immutable |
| 5 | observe freshness/data acquisition | current provider/fixture records and freshness policy are authoritative | refreshed/reused labels match backend outcomes |
| 6 | inspect delta | backend comparison of R0 and R1 | UI displays the exact changed set; an empty changed set is valid and must not be embellished |
| 7 | inspect generated capability/correction if present | exact events/records only | absent lifecycle is shown as absent; no Demo lifecycle is injected |
| 8 | release and open A/B/C | capture T1/C1/V1/A1 and canonical X1 | all current results belong to R1; prior links stay on R0 |
| 9 | inspect Object writeback | new version appended with R1; R0 retained | Object history/latest/comparison agree |
| 10 | restart backend and reopen URL | PostgreSQL/artifact store restore exact records and SSE terminal cursor | O/R1/T1/C1/V1/A1 and mode/source labels survive |

In public mode, the delta is whatever the real provider returned for the two run snapshots and may
be empty. In offline mode, the manifested fixture versions may deliberately contain a known delta.
Limited mode follows its frozen capability policy. None may silently switch to frontend Demo data.

## 10. Shared negative and browser-navigation variants

Run these variants across every activated R scenario, distributed to avoid unnecessary duplicate
runtime cost while retaining complete coverage. Phase 4 Core distributes them across
`SCENE-01..04`; Phase 5 adds real `SCENE-05..06` without rewriting the variants:

| Variant | Required behavior |
|---|---|
| rapid confirm clicks | one POST admitted by UI; server idempotency still returns one R if two arrive |
| lost confirm response | retry with the same request/key, including after backend restart, returns R; same key with a different draft/body conflicts; new key is not used automatically |
| refresh at nonterminal sequence N | snapshot revision + resume converges without regression or duplicate visible rows |
| disconnect at N | reconnect sends `Last-Event-ID: N`; no event gap |
| stale URL for missing R/C/T/A | explicit unavailable/not-found; no latest-entity fallback |
| browser Back/Forward | logical route and exact entity IDs restore; no duplicate network mutation |
| Object B ID substitution | 404/403/safe unavailable; zero B data in A DOM and vice versa |
| artifact unavailable/tampered | disabled safe reason or integrity failure; never Demo bytes |
| terminal refresh | no infinite SSE reconnect; fresh backend state remains RELEASED/FAILED |
| empty list/panel and HTTP error | explicit empty/error/retry; retry performs real read and preserves route identity |

## 11. Scenario result schema

Each test result must emit a sanitized record equivalent to:

```json
{
  "scene": "SCENE-01",
  "source_class": "DEMO | INTEGRATED | PUBLIC_REAL | LIMITED_REAL | OFFLINE_INTEGRATED",
  "activation_scope": "PHASE4_CORE_REQUIRED | PHASE5_ACTIVATED | DEPLOYMENT_ACTIVATED",
  "activation_state": "DEFINED_NOT_ACTIVATED | REQUIRED",
  "deployment_mode": "...",
  "object_id": "...",
  "run_id": "...",
  "task_id": "...",
  "claim_id": "...",
  "review_id": "...",
  "artifact_id": "...",
  "last_event_sequence": 0,
  "gates": {"P4-E2E-001": "PASS | FAIL | DEFINED_NOT_ACTIVATED"},
  "network_ledger_ref": "content-addressed sanitized artifact",
  "trace_ref": "Playwright trace once implementation is authorized"
}
```

For `DEMO_UX_ONLY`, `activation_scope` and `activation_state` are omitted and the Demo result is
reported separately. For a future real Scene, `activation_state=DEFINED_NOT_ACTIVATED` means its
gate results are not evaluated. Once activated, `activation_state=REQUIRED`; missing any required
identity field makes that R Scene fail and the final result may only be `PASS` or `FAIL`.
