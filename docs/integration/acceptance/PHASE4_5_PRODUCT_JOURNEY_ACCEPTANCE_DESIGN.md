# Phase 4/5 Product Journey Acceptance Design

Status: `DESIGN_READY - NOT_IMPLEMENTED - NOT_EXECUTED`  
Authority date: `2026-09-05`  
Phase 4 contracts: `phase4-core/v1`, `phase4-runtime-event/v1`  
Contract-set SHA-256: `0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741`  
Frontend parent: `FRONTEND_BASELINE_V8.1@d854c97789c98cca14fee3f4b3d7f00e0d5d137a`  
Approved V17 R2 input: `fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19`

This document asks a product question, not an API-test question: can a real user reach the intended research outcome against the real Backend, understand what happened, and recover without receiving fabricated success? Unit, component, Backend, browser, Presenter, and competition-script evidence cannot substitute for this layer.

## Result model and activation

| Result | Meaning |
|---|---|
| `PASS` | Every required user, Backend, identity, availability, recovery, evidence, and release oracle passed on one manifested Candidate pair. |
| `FAIL` | An activated mandatory assertion failed, authority was inferred, identity crossed, or false success was shown. |
| `BLOCKED` | An activated attempt could not reach a required oracle. It never counts as PASS and becomes required-evidence failure at a release decision. |
| `NOT_ACTIVATED` | The journey is designed but its execution gate is inactive. Formal gate records use `activation_state=DEFINED_NOT_ACTIVATED` and `result=null`. |

| Journey | Scene | Activation | Release membership |
|---|---|---|---|
| `PJ-01` Full Financial Research | `SCENE-01` | Phase 4 after IG-01 | `PHASE4_CORE_REQUIRED` |
| `PJ-02` Dynamic Research Path | `SCENE-02` | Phase 4 after IG-03 | `PHASE4_CORE_REQUIRED` |
| `PJ-03` Self-Correction and Review | `SCENE-03` | Phase 4 after IG-03 | `PHASE4_CORE_REQUIRED` |
| `PJ-04` Verifiable Claim Trace | `SCENE-04` | Phase 4 after IG-04/05 | `PHASE4_CORE_REQUIRED` |
| `PJ-05` Object Accumulation | `SCENE-05` | `DEFINED_NOT_ACTIVATED` | `PHASE5_ONLY` |
| `PJ-06` Incremental Return | `SCENE-06` | `DEFINED_NOT_ACTIVATED` | `PHASE5_ONLY` |

## Universal authority and oracles

- Provider data must pass validation, normalization, conflict resolution, and acceptance before reasoning.
- Code/deterministic capabilities are the only financial-number authority. The Frontend displays Backend-provided canonical/display values and never calculates, rounds, infers units, or repairs financial truth.
- Planned graph is immutable; actual graph and every path change are Backend-authoritative. Phase 4 accepts only `SELF_CORRECTION`, `ADD_TASK`, and `CHANGE_DEPENDENCY`.
- Self-Correction remains the same Task and graph-semantic scope. Replan is Specialist -> ReplanRequest -> Research Lead -> GraphMutationService.
- A/B/C share one Canonical Execution Record and exact Object/Run/released-result identities. No title, text, position, first, or latest match is an identity join.
- Langfuse is fail-open observability, never a business oracle; evidence contains no secrets, provider bodies, prompts, or hidden Chain-of-Thought.
- ZK proves only the committed deterministic computation, not provider, thesis, market, or external-world truth.
- Backend oracle is HTTP/SSE plus durable PostgreSQL/artifact records; Frontend oracle is user-visible state/navigation; the comparator checks exact IDs, values, availability, sequence, and bytes. DOM-to-DOM comparison is insufficient.

Stable browser observables must expose exact Object, Run, Task, Claim, Review/Check, Calculation/Evidence, Canonical Record, Metric, and Artifact IDs without becoming an authority themselves.

## PJ-01 - Full Financial Research

### Entry and user path

Entry requires IG-01 prerequisites, a real full-stack environment, Object A plus foreign Object B, and an acceptance input capable of valid release. The user follows:

```text
Open -> create/select Object -> define Goal -> generate Scheme -> inspect -> confirm
-> Run Workspace -> observe execution -> Financial Review -> Proof -> Released Result
-> professional report -> HTML/PDF
```

| Step | Backend authoritative fact | Required user-visible assertion |
|---|---|---|
| Object | Object routes return/create exact O with request-bound idempotency | Company/symbol/O match; no default Demo/NVDA substitution |
| Goal/Scheme | Prepare returns immutable `SCHEME_ONLY` draft with O/G/S/hash/version/expiry and planned graph `NOT_GENERATED` | Scheme is understandable; no Task or graph is fabricated before confirm |
| Confirm | One transaction consumes the draft, creates one admission/R/plan/Tasks/outbox/lease, and replays exact idempotent response | One busy action; double-click, lost response, and retry always open the same R |
| Workspace | Atomic RunProjection returns O/R/GP/GA/Tasks/path changes/lifecycle/revision/sequence/availability | Heading, stage, progress, graphs, Tasks, and availability equal the snapshot |
| Live execution | Real fetch-stream SSE has exact R/T and contiguous sequence | UI mutates only from validated events/snapshot and separates connection state from Run truth |
| Review/Proof | Exact Review/Checks and declared Proof policy close to R/K/C | User sees precise status and limited proof scope; no inferred PASS |
| Release | L/X/material outputs/Review/Proof/required HTML commit before `release.completed`, then one final `run.completed` | Results enable only after final authoritative reconciliation |
| Results/report | Backend supplies metric value/unit/period/as-of and A/B/C identities | `0.6547 RATIO` renders from supplied `65.47 %`; no client multiply |
| Artifacts | Fixed HTML/PDF slots; each byte GET rechecks O/R/A identity and hash/size/type | HTML required. PDF independent and optional; unavailable PDF stays disabled with reason |
| Reopen | Persistence reproduces the terminal tuple and artifact metadata | Refresh, Back/Forward, and clean context return to the same O/R and selection |

Success requires exactly one R, immutable G/S/GP, real HTTP/SSE execution, Backend-authored numbers, Review PASS, required Proof satisfaction, release-before-terminal ordering, A/B/C identity closure, valid HTML bytes, honest PDF availability, and restart-safe reopening.

Mandatory failure variants: expired/consumed/mismatched draft; changed-body idempotency conflict; provider/Task failure; Review `REVIEW` or `BLOCK`; missing/invalid required Proof; broken material lineage; HTML/hash/type failure; PDF policy skip/failure; cross-owned Claim/artifact; unknown schema/status/event; terminal failure before release.

Manual assertions cover Scheme comprehension, single confirmation, credible live progress, planned/actual distinction, Review/Proof comprehension, honest unavailable states, professional report, and stable reopening. Automation covers route/ID ledgers, double-submit and response loss, real named SSE, financial display comparison, A/B/C IDs, artifact hashing, refresh/restart/history, Object B substitutions, console/a11y/focus/responsive checks.

Evidence: Candidate/environment manifest, sanitized HTTP ledger, idempotency/admission rows, SSE apply ledger, projections, financial lineage, Review/Proof/release/terminal records, artifact metadata/bytes, browser trace/DOM/a11y/focus/history, restart evidence, and failed attempts.

## PJ-02 - Dynamic Research Path

Entry requires a real input that naturally causes Replan and captures GP/GA/version, ReplanRequest, Research Lead decision, graph operations, Task refs, and path-change projections.

| User-observed moment | Backend oracle | Frontend oracle |
|---|---|---|
| Before change | Immutable GP and current GA/version | Initial, Actual, Compare bind exact graph IDs |
| Replan requested | Exact R/T/replan ID/reason/source | Pending reason appears; no speculative Task |
| Replan approved | Same replan ID and Lead decision | Approval/source is visible without invented human identity |
| Mutation | Task/edge events followed by one graph-version change | Actual path remains recovering until an atomic projection confirms it |
| After change | GA has exact Backend-created Task, operations, dependencies, history, and one version increment | Added/affected markers and Task drawers bind exact IDs; GP remains unchanged |
| Recovery/release | Snapshot+cursor reconstruct one mutation and same R continues | Disconnect/refresh/restart never duplicates or partially commits the path |

Reject planned-graph mutation, Task-before-approval, missing request/source, frontend Task construction, cross-Run refs, duplicate/cyclic/unknown dependencies, version regression/double increment, silent mutation, deferred/unknown change kinds, Demo-label substitution, or replay duplication.

Manual and automated evidence must let a user answer what changed, why, where execution is now, and how the original plan differs. Retain pre/post graph hashes, Replan/decision records, event ledger, graph diff/DAG report, Task navigation, recovery/restart, and release identity closure.

## PJ-03 - Self-Correction and Review

Entry requires a real same-Task correction input, captured pre-correction K/E/T/graphs, durable Correction records, stable Review/Check identities, a positive Review PASS branch, and a `REVIEW`/`BLOCK` negative branch.

| Step | Required oracle |
|---|---|
| Detect | `task.self_correcting` carries exact R/T and safe problem code; the same T visibly enters correcting. |
| Record | PathChange has `source_kind=CORRECTION`, `change_kind=SELF_CORRECTION`, exact Correction/R/T/reason/timestamps. |
| Resolve | `task.correction_resolved` uses the same R/T/correction ID; no Task is created. |
| Graph | GP, GA Task/edge sets, and graph version are unchanged by correction. |
| Recalculate | Rejected mismatched K is not released; corrected K uses exact accepted period-aligned E. |
| Review | Exact V/Q input hash, typed subjects, reviewed refs, and correction history are shown; filters are presentation only. |
| Consequence | PASS may continue to release; `REVIEW`/`BLOCK` cannot enable result/artifact controls. |

Reject Task/graph creation, differing Task IDs, release of rejected K, unaligned/cross-Run E, client repair/arithmetic, synthetic per-Claim Review, aggregate-event inference, lost history after refresh, or raw failure/hidden reasoning. Evidence includes correction/events, graph hashes, rejected/corrected lineage, Review/Check records, filter counts, positive release, negative block, and restart/browser evidence.

## PJ-04 - Verifiable Claim Trace

The mandatory user traversal is:

```text
Report Claim -> Financial Review Check -> Task -> Calculation -> Evidence
-> Execution -> Proof -> original Report representation anchor
```

The selected corpus Claim must exercise a substantive `MUST_PROVE` calculation. TraceBundle and the hash-bound anchor manifest own all relationships. Review, Task, and Execution anchors are plural collections; no singleton or first-item promotion selects `primaryTaskId`.

Required assertions:

- every transition validates exact O/R/C/M/K/E/T/V/Q/P/Y/X/L identities before navigation;
- all details remain same-Object and same-Run;
- execution exposes typed safe records, never provider bodies/prompts/CoT;
- Proof matches K and declares its limited scope;
- close/back returns focus, scroll, and highlight to the originating representation-scoped anchor;
- HTML-available/PDF-unavailable and HTML+PDF-available corpora both pass; each available format has a distinct artifact/anchor and never borrows the other;
- plural array reordering cannot change the selected business entity;
- hard refresh and Back/Forward restore the exact route/context.

Negative substitutions include other Object, other Run of same Object, wrong Claim/Task/Evidence/Calculation/Review/Proof/artifact/anchor, missing detail, and cross-format anchor. Each fails closed with no foreign body/bytes and no global/latest/search/DOM fallback. Evidence includes TraceBundle and manifest hash, transition/focus/scroll ledger, complete join record, plural-anchor selection, artifact bytes, substitution responses, DOM/a11y/browser trace, restart/history, and failed attempts.

## PJ-05 - Object Accumulation (Phase 5 only)

Activation: `DEFINED_NOT_ACTIVATED`; result: `NOT_ACTIVATED`; excluded from Phase 4. This journey does not freeze Phase 5 routes or schemas.

Future path:

```text
O -> released R1 -> applied append-only Object/View version 1 -> released R2
-> applied version 2 -> explicit current selection -> history -> explicit R1/R2 comparison
-> historical and current Claim/report navigation
```

Future acceptance requires two immutable release tuples, atomic/idempotent writeback, compare-and-swap pointer promotion, exact source-Run IDs, Backend-authored comparison/deltas, reverse-direction recomputation, historical reopening, restart, and Object B rejection. A proposal is never an applied version. Current is selected by an explicit coherent pointer pair, never sort order, title, symbol, or last visit. Failed/running R2 cannot replace valid R1; failed writeback cannot partially advance pointers; older bytes/lineage cannot mutate.

Manual testing asks whether the Object feels cumulative rather than overwritten and whether current, historical, comparison direction, exclusions, and unavailable history are clear. Future automation captures R1/R2 and artifact hashes, writeback/CAS transactions, version manifests, pointer races, forward/reverse and empty comparison, historical traces, cross-object negatives, restart, and clean-context reopening.

## PJ-06 - Incremental Return (Phase 5 only)

Activation: `DEFINED_NOT_ACTIVATED`; result: `NOT_ACTIVATED`; excluded from Phase 4. Provisional names such as Incremental Seed and Reuse/Refresh/Revalidate/Prevent remain design references until Phase 5 contract freeze.

Future path:

```text
return to O -> inspect exact prior released R0/View0 -> freshness evaluation
-> Backend decisions for reuse/refresh/revalidate/prevent -> incremental Scheme
-> confirm new R1 -> observe current execution -> Backend R0/R1 comparison
-> new Review/Proof/release -> append-only Object/View writeback
```

The source identity is frozen before confirm; R1 differs from R0; both own O. Reused records retain original source Run, current/revalidated records close through R1, prior Review/Proof is never copied to changed values, empty delta is a valid available outcome, provider failure never splices fixtures, failed R1 does not advance current pointers, and R0 remains immutable.

Manual testing asks whether the user understands the exact source, what is reused versus redone and why, prior versus current evidence, and empty delta. Future automation covers no-source disabling, source race, exact prepare/confirm binding, classification-to-record comparison, freshness/revalidation/prevent provenance, no approval transfer, R0 immutability, known/empty deltas, identity of prior/current A/B/C, provider failure, pointer/writeback/restart.

## Cross-cutting failure and recovery

These variants are mandatory for activated PJ-01..04 and become applicable to PJ-05/06 only after Phase 5 activation.

| Variant | Pass oracle |
|---|---|
| Browser reload | Exact route/entity survives; old stream aborts; snapshot installs; one exact-Run stream resumes after N. |
| SSE disconnect | Last valid state is visibly stale/reconnecting; no fabricated progress or reset. |
| Gap/out-of-order | Event is quarantined; zero mutation/cursor advance; one snapshot recovery converges. |
| Cursor rejected | Invalid/foreign -> pre-header `INVALID_CURSOR`; ahead -> `CURSOR_AHEAD`; zero frames. |
| Provider failure | Provider/model selected before Run remains locked; no mid-Run switch or live-to-fixture substitution. |
| Task failure | Exact failure/dependents shown; unrecoverable Core path ends in one `run.failed`; no Results. |
| Review BLOCK | Review remains inspectable; no release/result/artifact. |
| Proof failure | `MUST_PROVE` failure blocks release; no prior receipt substitution. |
| Required artifact | HTML failure blocks professional release; unavailable/tampered content returns zero bytes. |
| Optional PDF | HTML/release may pass; PDF is disabled with exact reason and no fabricated ID. |
| Terminal | Success ends `release.completed` then one `run.completed`; failure/cancel ends one `run.failed`; reopen is stable. |

## Aggregate and evidence rules

```text
PHASE4_PRODUCT_JOURNEY_ACCEPTANCE =
  PJ-01 PASS AND PJ-02 PASS AND PJ-03 PASS AND PJ-04 PASS
  AND all applicable cross-cutting variants PASS

PJ-05/PJ-06/SCENE-05/SCENE-06 in Phase 4 denominator = 0
```

The product aggregate supplements, never replaces, the technical gates. Every run records the Candidate pair, environment, data class, contract hashes, activation, steps, identity closure, availability assertions, failures, supporting gates, evidence refs, and decision owner. Screenshots support evidence but do not prove Backend truth.

## Current contradictions resolved

- The owner receipt and current brief supersede stale R2 text that says UAC-002 is pending.
- Contract-closed BD/UAC semantics do not mean implementation or acceptance is complete.
- The newer PJ-04 order places Execution before Proof; existing Scene text with the reverse UI order remains compatible only if the same exact trace relations are proven. This document governs the requested user traversal without changing the wire contract.
- HTML is required and PDF optional; older prose suggesting universal PDF availability is not release authority.
- The current 13 contracts do not clearly expose provider/model lock to the Frontend. Until a reviewed surface exists, the Backend acceptance oracle must prove the lock; the UI must not infer it from Langfuse.

```text
PRODUCT_JOURNEYS_DEFINED=6/6
PHASE4_CORE_JOURNEYS=4/4
PHASE5_ONLY_JOURNEYS=2/2
PHASE5_JOURNEYS_IN_PHASE4_DENOMINATOR=0
CROSS_CUTTING_FAILURE_CLASSES=11/11
PHASE5_WIRE_SCHEMAS_FROZEN_BY_THIS_DOCUMENT=0
FRONTEND_FINANCIAL_AUTHORITY=0
CROSS_OBJECT_FALLBACK=0
CROSS_RUN_FALLBACK=0
DEMO_AS_REAL_EVIDENCE=0
SOURCE_MODIFIED=NO
```
