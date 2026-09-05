# Phase 4 Identity Assertion Matrix

Status: **AUTHORITATIVE DESIGN — FROZEN — NOT YET EXECUTED**

Activation authority: `PHASE4_E2E_GATE_ACTIVATION_MATRIX.md`

## 1. Non-negotiable invariant

For a selected Object O and Run R, every browser projection must close through explicit backend
references:

```text
Object O
  <- Goal.research_object_id
  <- Scheme.research_object_id
  <- Run.research_object_id

Run R
  <- Task.run_id
  <- RuntimeEvent.run_id
  <- Evidence.run_id
  <- Calculation.run_id
  <- Claim.run_id
  <- Review.run_id
  <- CanonicalExecutionRecord.run_id
  <- ReleasedResearchResult.run_id
  <- ReportArtifact.run_id
```

Where a nested entity has only `run_id`, its Object is resolved by the authoritative Run record.
It is never derived from an ID prefix, ticker, company name, title, array position, current route,
or “latest” record.

Frontend camelCase (`objectId`, `runId`, `taskId`, `claimId`, `reviewId`, `artifactId`) is an adapter
shape only. It must retain exact backend values; normalization may rename a field but may not
rewrite an identifier.

## 2. Per-scenario required identity tuple

Every activated real-backend Scene must finish with at least this tuple:

```text
I(scene) = (objectId O, runId R, taskId T, claimId C, reviewId V, artifactId A)
```

The test must also capture a Calculation K, Evidence E and Canonical/Execution record X for Claim
Trace and A/B/C closure. No required field may be skipped because the scene's principal visual
moment is nonterminal; the scenario continues through release or uses an already released
same-scene Run to complete the tuple.

| Scene | Real `activation_scope` | Required tuple(s) | How the IDs are selected | Mandatory negative identity |
|---|---|---|---|---|
| SCENE-01 Full | `PHASE4_CORE_REQUIRED` | `O1/R1/T1/C1/V1/A1` | O from create/select; R from confirm; T from actual graph; C from typed released Claim; V from exact Review covering C; A from AVAILABLE report representation | query/open C1 or A1 under Object/Run B |
| SCENE-02 Dynamic | `PHASE4_CORE_REQUIRED` | `O2/R2/T2-added/C2/V2/A2` | T is the backend-added graph Task; C/V/A captured after same R reaches release | use a planned Task from R-B as mutation target; must reject |
| SCENE-03 Correction | `PHASE4_CORE_REQUIRED` | `O3/R3/T3-corrected/C3/V3/A3` | T owns both correction events; C uses corrected K; V reviews C/K | mismatched Evidence/Claim from R-B cannot appear in review/trace |
| SCENE-04 Trace | `PHASE4_CORE_REQUIRED` | `O4/R4/T4/C4/V4/A4` plus `K4/E4/X4` | C chosen from report metric; all other IDs followed through explicit refs | lookup `(R4, C-B)` and `(O4/R4, A-B)` fails closed |
| SCENE-05 History | `PHASE5_ACTIVATED` | `O5/R5a/T5a/C5a/V5a/A5a` and `O5/R5b/T5b/C5b/V5b/A5b` | one tuple per immutable Object version; comparison row supplies `sourceRunId` | C5a must never resolve to R5b; Object B history absent |
| SCENE-06 Incremental | `PHASE5_ACTIVATED` | `O6/R6-prev/...` and `O6/R6-current/T6/C6/V6/A6` | previous Run is explicit memory source; current tuple comes from new release | prior/current refs cannot be silently exchanged; Object B memory forbidden |

Demo tests use their frozen IDs and run the same logical checks, but their results are labeled
`DEMO` and do not satisfy integrated identity closure.

Before `PHASE5_OBJECT_MEMORY_IMPLEMENTED`, the two Phase 5 real tuples are
`DEFINED_NOT_ACTIVATED`; they are not missing Phase 4 Core identity evidence.

## 3. Field-level ownership matrix

| Entity/view | Direct identity fields | Required join/assertion | Forbidden fallback |
|---|---|---|---|
| Research Object | `object_id` | response/path/DOM O are identical | symbol/name match |
| Research Goal | `goal_id`, `research_object_id` | Goal Object is O; Run goal ref is this exact Goal | current wizard object |
| Research Scheme | `scheme_id`, `research_object_id`, `goal_id` | Scheme Object/Goal are O and captured Goal; Run scheme ref is exact | most recent Scheme |
| Research Run | `run_id`, `research_object_id`, `goal_id`, `scheme_id` | R owns O and exact Goal/Scheme | latest Run for ticker |
| Planned graph | `graph_id`, `run_id`; Tasks | graph Run is R; each planned Task has R | actual graph by page state |
| Actual graph | `graph_id`, `run_id`, `version`; Tasks/mutations | graph Run is R; all dependencies resolve within same graph | planned Task with same label |
| Task | `task_id`, `run_id`, dependencies | T is unique within R; parent/dependencies are Run-owned | task title/type |
| Runtime Event | `event_id`, `run_id`, optional `task_id`, sequence | event Run is R; task exists in actual graph at/after its add event | current selected Task |
| Replan/Correction | own ID, `run_id`, requesting/owning `task_id` | R/T exact; created/affected Task IDs exist in R | mutation label |
| Capability gap/build/registration | own IDs, `run_id`, `task_id` | all stages retain R/T and capability implementation identity | capability name alone |
| Evidence | `evidence_id`, `run_id`, `object_id` | E owns R/O; K/Claim refs contain exact E | provider locator or metric label |
| Calculation | `calculation_id`, `run_id`, `task_id`, Evidence refs | K owns R/T and exact E set; canonical/review/proof refs agree | formula/capability name |
| Released metric | `metric_id`, `calculation_id` within Result R | M binds exact K; enclosing Result supplies R; semantics match Claim | metric name |
| Material Claim | `claim_id`, `run_id`, `metric_id`, Calculation/Evidence refs | C owns R and exact M/K/E; task derives from K only | first Claim with same type |
| Review | `review_id`, `run_id`, reviewed refs and check subject refs | V owns R and covers exact C/K; one V may cover multiple Claims | frontend-generated per-Claim Review ID |
| Canonical Execution Record | `record_id`, `run_id`, `object_snapshot_ref`, lineage refs | X owns R/O and includes T/E/K/C/V/A-upstream refs as applicable | current Execution tab data |
| Released Result | `result_id`, `run_id`, `canonical_record_id` | Result owns R/X; every nested metric/Claim belongs to R | newest released result |
| Report A | R, O and X through Result/Report DTO/artifact | report metric C and semantics come from same Result | HTML content search alone |
| Financial Review B | `run_id`, `canonical_record_id`, Review refs | B owns R/X and exact V/C/K refs | same status text |
| Execution C | `run_id`, `canonical_record_id`, Task/lineage refs | C-view owns R/X and contains exact T/K/E/C/V targets | same Task title |
| ReportArtifact | `artifact_id`, `run_id`, `research_object_id`, `report_id`, `canonical_record_id`, format | A owns R/O/report/X; bytes and metadata agree | filename, current Run, public URL |
| Object history version | `object_id`, `source_run_id` | version is append-only and joins to explicit R/O | list index or date only |
| Comparison item | explicit base/current Run IDs; row `sourceRunId`; optional Claim ID | row Claim belongs to source Run; base/current both own O | latest Claim with same category |
| Browser route | O/R/C/T plus tab/focus | route IDs equal loaded records; missing target stays missing | automatic redirect to latest |

`ReportArtifactRecord` observed in Phase 3 carries Run/canonical/result identity but not direct Object
identity. The Phase 4 artifact projection must add/resolve and verify `research_object_id` before the
artifact is exposed. A frontend-only Object field does not close this gap.

## 4. Assertion catalogue

The scope below is the earliest release-blocking owner. Core assertions are rerun where applicable
for Phase 5 and deployment candidates.

| Assertion | Exact check | Applies | `activation_scope` |
|---|---|---|---|
| P4-ID-001 | selected Object response ID equals route and DOM O | every Scene | `PHASE4_CORE_REQUIRED` |
| P4-ID-002 | prepare Goal `research_object_id == O` | 01, 06 and all create variants | `PHASE4_CORE_REQUIRED` |
| P4-ID-003 | prepare Scheme Object/Goal IDs equal O/Goal; `confirmed_at` null | 01, 06 | `PHASE4_CORE_REQUIRED` |
| P4-ID-004 | confirmed Run R references exact O/Goal/Scheme | every newly created Run | `PHASE4_CORE_REQUIRED` |
| P4-ID-005 | request-bound durable idempotent confirmations return the same R across retry/restart; repository and scheduler contain one R admission | 01, 06, confirm regression | `PHASE4_CORE_REQUIRED` |
| P4-ID-006 | list/history row R/Object/status and any exposed `source_run_id` equal detail R/Object/status at the same revision | every Scene | `PHASE4_CORE_REQUIRED` |
| P4-ID-007 | planned and actual graphs both own R; planned snapshot never changes | 01–03, 06 | `PHASE4_CORE_REQUIRED` |
| P4-ID-008 | every Task owns R; all parent/dependency IDs resolve within R | every Scene | `PHASE4_CORE_REQUIRED` |
| P4-ID-009 | every SSE event owns R; event Task is null or a valid R Task | every Scene | `PHASE4_CORE_REQUIRED` |
| P4-ID-010 | replan/correction/capability records retain exact R/T across lifecycle | 02, 03, generated-capability path | `PHASE4_CORE_REQUIRED` |
| P4-ID-011 | Evidence E owns R/O and is explicitly referenced by K and C | 01, 03, 04, 06 | `PHASE4_CORE_REQUIRED` |
| P4-ID-012 | Calculation K owns R/T and exact Evidence inputs | 01, 03, 04, 06 | `PHASE4_CORE_REQUIRED` |
| P4-ID-013 | Metric M references K; enclosing Result is R/X | 01, 03–06 | `PHASE4_CORE_REQUIRED` |
| P4-ID-014 | Claim C owns R and matches M's value/unit/period/as-of/K/E | 01, 03–06 | `PHASE4_CORE_REQUIRED` |
| P4-ID-015 | Review V owns R and includes C/K in reviewed refs/check subjects | every Scene at release | `PHASE4_CORE_REQUIRED` |
| P4-ID-016 | no synthetic per-Claim review ID is introduced by the adapter | every Scene | `PHASE4_CORE_REQUIRED` |
| P4-ID-017 | Canonical X owns R and `object_snapshot_ref == O`; refs include T/E/K/C/V | every Scene at release | `PHASE4_CORE_REQUIRED` |
| P4-ID-018 | Result R and A/B/C use exact X | every Scene at release | `PHASE4_CORE_REQUIRED` |
| P4-ID-019 | Artifact A metadata owns O/R/X/result/report and format-specific bytes | every Scene at release | `PHASE4_CORE_REQUIRED` |
| P4-ID-020 | Claim Trace retains O/R/T/C/V/A/K/E/X through every route/overlay | Scene 04 and trace regression in all released Scenes | `PHASE4_CORE_REQUIRED` |
| P4-ID-021 | Object version's source Run owns the same O; earlier version immutable | 05, 06 | `PHASE5_ACTIVATED` |
| P4-ID-022 | comparison Claim belongs to row `sourceRunId`, not current/latest Run | 05, 06 | `PHASE5_ACTIVATED` |
| P4-ID-023 | refresh/new browser rebuilds the same tuple from backend persistence | every Scene | `PHASE4_CORE_REQUIRED` |
| P4-ID-024 | Back/Forward restores exact tuple and never triggers a mutation request | every Scene | `PHASE4_CORE_REQUIRED` |
| P4-ID-025 | Object B's C/V/A/T IDs are absent from Object A DOM/network-derived projection | every Scene | `PHASE4_CORE_REQUIRED` |
| P4-ID-026 | cross-Run/ cross-Object API substitutions fail 404/403/safe unavailable | every Scene | `PHASE4_CORE_REQUIRED` |
| P4-ID-027 | missing IDs do not fall back to latest/first/title/symbol matches | every Scene | `PHASE4_CORE_REQUIRED` |
| P4-ID-028 | all six required O/R/T/C/V/A fields are non-empty in result record | every real Scene | `PHASE4_CORE_REQUIRED` |

## 5. Cross-object leakage matrix

Create or select two objects O-A and O-B and at least one released Run for each. These operations are
read-only from the browser's perspective except for the explicitly created acceptance records.

| Test | Request/navigation | Required result | Failure evidence |
|---|---|---|---|
| XL-01 Run under wrong Object | open R-B from O-A history/context | reject or explicitly leave O-A context for authoritative O-B; never render mixed header/body | O-A header with R-B data |
| XL-02 Claim under wrong Run | request C-B with R-A | 404/403/safe unavailable | any Claim fallback or C-B drawer |
| XL-03 Task under wrong Run | deep-link T-B under R-A | 404/403/safe unavailable | matching-title T-A or T-B displayed under R-A |
| XL-04 Review under wrong Run | navigate V-B while R-A selected | reject; no Review B content | Review status/refs from B in A |
| XL-05 Artifact substitution | use A-B reference from R-A | authorization/binding failure; no bytes | 200 bytes or A-A fallback |
| XL-06 Evidence substitution | E-B in Claim C-A | Claim/lineage validation fails; no Evidence body | B provider values in A trace |
| XL-07 Calculation substitution | K-B in Claim C-A | reject; no calculated value | B value shown under A |
| XL-08 Object latest | O-A latest action | exact latest released R-A | globally latest R-B |
| XL-09 History Claim | click C from historical R-A1 | trace stays R-A1 | same metric Claim from R-A2 |
| XL-10 browser restore | refresh Back/Forward on A tuple after viewing B in another tab | each tab/context retains its own tuple | shared singleton switches A to B |

The suite scans the rendered DOM and accessible tree for the other object's ID, symbol, company
name, Claim IDs and known financial sentinel values. A negative scan supplements explicit joins; it
does not replace them.

## 6. Identity across SSE and reconciliation

- A connection URL is constructed from R only after R is captured from confirm/list/detail.
- Every parsed frame must have `data.run_id == R`. A mismatch is quarantined and fails the test; it
  is never passed to the reducer.
- `task_id` is accepted only if it is already in the actual graph or the same frame is the
  authoritative add event for that Task.
- A duplicate `event_id` or sequence may not append a second timeline, mutation, Task, Review or
  Claim.
- Snapshot reconciliation is keyed by O/R and its event sequence/revision. A newer snapshot for R-B
  cannot satisfy a gap for R-A.
- After terminal, the final snapshot's R/O/graph/lineage IDs must equal the accumulated projection.

## 7. Claim-to-Review-to-Task exact join

Phase 3 material Claims do not directly carry a Task ID. The only accepted derivation is:

```text
C.calculation_refs contains K
K.task_id == T
V.run_id == C.run_id == K.run_id == T.run_id == R
V.reviewed_claim_refs contains C
V.reviewed_calculation_refs contains K
```

If the Review expresses coverage through a `ReviewCheck.subject_refs`, that exact check must contain
C and/or K according to its check contract. A matching Review title/status is insufficient.

The Evidence join is the exact set required by the released metric/Claim contract:

```text
C.evidence_refs == M.evidence_ids == K.input_evidence_ids
```

Order may be normalized only where the backend contract declares a set. Proof commitments or
calculation snapshots that declare ordered inputs retain order.

## 8. Artifact identity

HTML and PDF are distinct A values. Each record must contain or resolve:

```text
A.artifact_id
A.research_object_id == O
A.run_id == R
A.report_id == released report/version for R
A.canonical_record_id == X
A.format/content_type/hash/size
```

The authorized byte response must identify the same A and have the expected media type, size and
SHA-256. Browser filenames and report titles are presentation checks only; they cannot establish
ownership. Revoking or expiring an authorized reference does not change A's identity.

## 9. Pass rule

An activated Scene identity result is PASS only when its applicable required `P4-ID-001..028` rows
pass and its O/R/T/C/V/A tuple is complete. Any cross-object content, inferred/fallback ID, missing
required identity, or mixed-version projection fails that activated Scene and its owning aggregate.
Inactive Phase 5 rows are `DEFINED_NOT_ACTIVATED`, not Phase 4 Core failures.
