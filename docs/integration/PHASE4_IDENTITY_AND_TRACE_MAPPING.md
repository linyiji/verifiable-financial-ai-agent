# Phase 4 Identity and Trace Mapping

Classification: `PROVISIONAL_CONTRACT_PREAUDIT`

## 1. Identity rule

The backend’s `run_id` is the mandatory join root for Phase 4. An id being globally shaped or globally unique is not permission to join it without the Run owner.

```text
ResearchObject.object_id
  └─ ResearchRun.run_id (ResearchRun.research_object_id == object_id)
       ├─ Task.task_id
       ├─ RuntimeEvent.event_id + sequence
       ├─ EvidenceRecord.evidence_id (+ object_id, producer_task_id?)
       ├─ CalculationRecord.calculation_id (+ task_id)
       ├─ MaterialFinancialClaim.claim_id (+ metric_id)
       ├─ ReviewRecord.review_id
       ├─ ProofRecord.proof_id (+ calculation_id)
       ├─ CanonicalExecutionRecord.record_id
       ├─ ReleasedResearchResult.result_id
       ├─ ReportArtifactRecord.artifact_id
       └─ capability gap/build/generated/validation/registration ids
```

Every Phase 4 read must start with the requested Run, establish its object, and then validate every nested or referenced record against that Run/object before returning a projection.

## 2. Actual identity inventory

| Requested identity | Backend carrier | Direct ownership fields | Required verified join | Current limitation |
|---|---|---|---|---|
| `object_id` | `ResearchObject` | `object_id` | N/A | Frontend calls it `id`; object history is not versioned state. |
| `run_id` | `ResearchRun` | `run_id`, `research_object_id` | Run → exact object | Authoritative root is strong. |
| `task_id` | `Task` | `task_id`, `run_id`, optional `parent_task_id` | Task.run = requested Run | No direct object id; projection must inject it. |
| `claim_id` | `MaterialFinancialClaim` | `claim_id`, `run_id`, `metric_id` | Claim.run = requested Run | No direct task/review/proof/report anchor. |
| `review_id` | `ReviewRecord` | `review_id`, `run_id`, reviewed ref lists | Review.run = requested Run; Claim must occur in `reviewed_claim_refs` or a check subject | Current flow is one aggregate review, not per-Claim UI records. |
| `calculation_id` | `CalculationRecord` | `calculation_id`, `run_id`, `task_id` | Calculation.run = requested Run; Task.run matches | Strong bridge from financial Claim to Task. |
| `proof_id` | `ProofRecord` | `proof_id`, `run_id`, `calculation_id` | Proof.run and calculation binding both match | Verification is a separate record; “generated” is not “valid”. |
| `artifact_id` | `ReportArtifactRecord` | `artifact_id`, `run_id`, canonical/result ids | Artifact.run, canonical.run and result.run all match | No object id, availability, authorization, or Claim anchors. |
| `report_id` | No distinct class | `released_result_id` is the closest released-report identity | Must be explicitly defined as result id or added as a distinct version id | Frontend currently does not carry a report id. |
| `capability_id` | Definition/requirement/generated/registration | capability id/version plus Run/Task on lifecycle records | Gap/build/registration Run and original Task match | Supporting identities must not enter the Research Task namespace. |
| `event_id` / sequence | `RuntimeEvent` | event id, run id, optional task id, sequence | Event.run = requested Run; sequence is per Run | SSE id is sequence, not JSON event id. |
| canonical record id | `CanonicalExecutionRecord` | `record_id`, `run_id`, `object_snapshot_ref` | Record.run = requested Run; object ref = Run object | Frontend calls it `canonicalRecordId`. |
| result id | `ReleasedResearchResult` | `result_id`, `run_id`, canonical record id | Result.run/canonical binding | Frontend only projects availability/released time today. |

## 3. Frontend six-scene identity model

The frontend invariant requires Object/Run/Task/Claim/Review/Artifact/Execution/ReleasedResult to carry the same `objectId`, `symbol` and `runId`. Backend records do not all duplicate those fields, but Phase 4 can map the invariant safely through a validated Run projection:

| Frontend entity | Can map now? | Rule |
|---|---|---|
| Run | Yes | `run.id = run_id`; `objectId = research_object_id`; symbol/company from that object. |
| Task | Yes | Verify `Task.run_id`, then inject the Run’s object identity. |
| Financial Claim | Yes, with projection | Verify Claim.run; inject object; task is resolved through exact calculation records. |
| Review | Yes, with projection | Verify Review.run and reviewed Claim association; inject owner. Per-Claim entries require projection. |
| Artifact | Yes, with enrichment | Verify artifact/canonical/result/run chain, then inject object. Do not expose raw artifact ref. |
| Execution | Yes | Canonical record supplies run and object snapshot ref. |
| Released Result | Yes | Result supplies run and canonical id; inject object from verified Run. |
| Scene 5/6 Research View and comparison | No production contract today | Keep Demo-only until Phase 5 Object Memory. |

Conclusion: Scenes 1–4 identity closure is projectable in Phase 4. Scenes 5–6 identity closure remains valid as a frontend Demo invariant but does not prove production object history/comparison support.

## 4. Cardinality and join rules

The minimum rules that prevent cross-record contamination are:

1. `ResearchRun.research_object_id == requested object_id` whenever the route is object-scoped.
2. Every Task, event, calculation, Claim, review, proof, canonical record, result and artifact returned for a Run has `run_id == requested run_id`.
3. Every `EvidenceRecord` has both matching `run_id` and `object_id`.
4. Every Claim calculation ref resolves to a calculation in the same Run. Every referenced calculation’s Task resolves in that Run.
5. Every Claim evidence ref resolves to evidence in the same Run/object.
6. Every Claim judgment ref resolves to a typed/id-bearing judgment in the same Run or is returned explicitly unavailable. String matching inside arbitrary JSON is not a valid join.
7. A Review is associated with a Claim only through `reviewed_claim_refs` or a typed ReviewCheck subject relation; sharing a Run alone is insufficient for a per-Claim PASS.
8. A Proof is associated with a Claim only through an exact Claim calculation ref and the Proof’s exact `calculation_id`.
9. An artifact is associated with a Run only when artifact `run_id`, canonical `run_id`, released result `run_id`, artifact `canonical_record_id`, and artifact `released_result_id` all close.
10. A report Claim anchor is valid only in a representation produced from that exact released result/canonical record. It is not reusable across report versions.
11. Runtime sequence is scoped to Run. Never compare or resume a sequence globally.
12. “Latest” may select a Run only for an object overview. It must never repair a missing Run in Claim, comparison, report, review, artifact, or execution navigation.

## 5. Exact Phase 4 TraceContext projection

The existing frontend `TraceContext` is navigation state, not sufficient backend trace data. The backend should authoritatively compose a run-scoped projection equivalent to the following. Field casing may be adapted in `api/client.ts`; semantics may not.

```json
{
  "object_id": "OBJ-...",
  "symbol": "NVDA",
  "run_id": "RUN-...",
  "claim": {
    "claim_id": "CLM-...",
    "claim_type": "DETERMINISTIC_CALCULATION",
    "statement": "...",
    "metric_id": "METRIC-...",
    "canonical_value": "0.25",
    "unit": "RATIO",
    "display_value": "25.0",
    "display_unit": "%",
    "period": "FY2026",
    "period_basis": "FY",
    "actuality": "ACTUAL",
    "as_of": "2026-09-03",
    "currency": null
  },
  "primary_task_id": "TASK-...",
  "task_refs": ["TASK-..."],
  "evidence_refs": ["EVD-..."],
  "calculation_refs": ["CALC-..."],
  "judgment_refs": [],
  "review_refs": ["REVIEW-..."],
  "proof_refs": ["PROOF-..."],
  "report": {
    "report_id": "RESULT-...",
    "artifact_refs": ["RPT-HTML-...", "RPT-PDF-..."],
    "anchor": "opaque-stable-claim-anchor"
  },
  "review_anchor": "opaque-stable-review-anchor",
  "task_anchor": "opaque-stable-task-anchor",
  "execution": {
    "canonical_record_id": "CER-...",
    "anchor": "opaque-stable-execution-anchor",
    "event_refs": ["EVT-..."]
  },
  "proof_policy": "NOT_REQUIRED",
  "proof_status": "NOT_REQUIRED",
  "projection_sequence": 42,
  "projection_schema_version": "phase4-trace-v1"
}
```

`display_value`/`display_unit` above come from the matched `ReleasedFinancialMetric`; they must not be manufactured from Claim `value`/`unit`. `primary_task_id` is valid only if the backend explicitly chooses it. If a Claim has multiple supporting Tasks and no canonical primary, the frontend contract must accept `task_refs` without inventing a primary.

### Projection assembly

| Trace step | Authoritative source | Current directness | Phase 4 requirement |
|---|---|---|---|
| Typed Claim | `ReleasedResearchResult.material_claims` | Direct by `(run_id, claim_id)` | Exact lookup; no global/latest fallback. |
| Released metric | `released_metrics`, matched by `metric_id` | Direct | Verify Claim semantics equal metric canonical semantics. |
| Task | Claim calculation refs → CalculationRecord.task_id | Indirect | Resolve all and verify same Run; define primary explicitly. |
| Evidence | Claim/equivalent metric evidence refs | Direct refs | Resolve same Run/object and authorize detail. |
| Calculation | Claim calculation refs | Direct refs | Return typed record/detail, never recompute. |
| Judgment | Claim judgment refs → released judgment | Untyped/indirect | Type the required subset or mark unavailable. |
| Review | ReviewRecord.reviewed_claim_refs / checks | Indirect | Return matching review/check projection, not all Run reviews as Claim reviews. |
| Proof | Calculation ids → ProofRecord.calculation_id + verification | Indirect | Project requirement and verification result; no validity inference in frontend. |
| Report anchor | Renderer-produced anchor manifest | Missing | Add stable per-artifact/per-report anchor metadata. |
| Execution anchor | canonical record + Task/event ids | Partly available | Return canonical id, exact Task anchor and safe event refs. |

## 6. Financial metric lineage closure

For every displayed material metric, Phase 4 must preserve this closure:

```text
ReleasedFinancialMetric.metric_id
  ├─ canonical_value + canonical_unit
  ├─ display_value + display_unit
  ├─ period + period_basis + actuality + as_of + currency
  ├─ calculation_id → CalculationRecord
  ├─ evidence_ids[] → EvidenceRecord[]
  ├─ MaterialFinancialClaim.metric_id → claim_id(s)
  └─ calculation_id → ProofRecord/Verification (according to proof policy)
```

The current frontend `FinancialMetric` loses all but a display period/value and estimate boolean. It must not be used as the Phase 4 release boundary. In particular:

- `RATIO` does not imply `%`;
- `period` does not imply `period_basis` unless the backend has validated it;
- a calculation completing does not imply a released metric;
- a generated proof does not imply a valid proof;
- absence of a ProofRecord does not imply `NOT_REQUIRED` without the policy decision.

## 7. Contamination cases that must fail closed

### Run A → Claim B

Reject before projection when `claim.run_id != route.run_id`, even if `claim_id` exists globally. The frontend already looks up Claims by `(runId, claimId)`; the HTTP API and projection builder must preserve that compound scope.

### Object A → ReportArtifact B

Reject unless all are true:

```text
Run.research_object_id == route.object_id
Artifact.run_id == Run.run_id
CanonicalRecord.run_id == Run.run_id
CanonicalRecord.object_snapshot_ref == route.object_id
Artifact.canonical_record_id == CanonicalRecord.record_id
ReleasedResult.run_id == Run.run_id
Artifact.released_result_id == ReleasedResult.result_id
```

The authorized byte-delivery route must repeat these checks; metadata authorization alone is insufficient.

### Comparison Claim → latest unrelated Run

Comparison input must carry exact `previous_run_id` and `current_run_id`, both verified to the same `object_id`. Each item’s `source_run_id` and optional `claim_id` must resolve within one of those two Runs as defined by the item. Missing Claims render unavailable; the UI must never fall back to the object’s newest Run.

## 8. Anchors are scoped references, not global identities

Frontend `reportAnchor`, `reviewAnchor`, `taskAnchor` and `executionAnchor` currently resemble DOM ids. Phase 4 should treat them as opaque projection fields whose validity is scoped to `(object_id, run_id, claim_id, report_id/canonical_record_id)`. If the frontend converts them to DOM ids, it must do so deterministically and without changing the owning ids.

The current professional HTML renderer lists material Claims but does not emit a reviewed per-Claim anchor manifest. Therefore full Report → Claim → Report round-trip remains blocked until anchors are produced and tested against the actual representation.

## 9. Phase boundary

- Phase 4: Run-rooted identity projection, Claims/Trace for one exact Run, safe artifacts, exact event/task lineage.
- Phase 5+: applied Object Memory, version snapshots, comparison semantics, durable incremental strategy.
- Demo-only until Phase 5: Scene 5/6 comparison content and history values.
- Deployment RP2+: deployment/source/component status added to these projections only when authoritative.
