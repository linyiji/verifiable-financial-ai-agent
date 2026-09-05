# Phase 4A Identity, Error, and Availability Contract

Status: `PROVISIONAL_CONTRACT_DRAFT`  
Version: `phase4-identity-error-availability/v1`  
Freeze state: `NOT_FINAL`  
Inspected backend: `codex/phase3-contracts@11fe8173a25ff7ac08bae42340ba7c6fae591be5`
Phase 4A access profile: `phase4-local-single-user-trusted/v1`

This contract is fail-closed. It defines public projection behavior; it does not authorize backend
or frontend implementation.

## 1. Identity root and resolution algorithm

`run_id` is the primary join root. Every Run-scoped read executes this algorithm before returning
any body:

1. Resolve the exact requested `ResearchRun`; do not substitute a latest Run.
2. Resolve `ResearchRun.research_object_id` to one exact `ResearchObject` under server-internal
   scope `LOCAL_SINGLE_USER`. Phase 4A performs no account authentication, but the request body
   never supplies access or ownership truth.
3. Resolve every requested/nested record by its canonical ID within the Run-scoped repository view.
4. Verify every direct `run_id`; verify every Evidence `object_id`; verify every indirect reference
   through the exact canonical chain.
5. Verify the response's event watermark and revision belong to that same Run snapshot.
6. Return the projection only if all material identities close. Otherwise fail with the rules below.

```text
ResearchObject O
  -> ResearchRun R
     -> Goal G -> confirmed Scheme S -> immutable planned graph / mutable actual graph
     -> Task T
     -> Evidence E
     -> Calculation K -> Task T and Evidence E
     -> Released Metric M -> Calculation K and Evidence E
     -> Claim C -> Metric M, Calculation K and Evidence E
     -> Review V / Check VC -> exact Claim/Calculation subjects
     -> Proof P / verification -> exact Calculation K
     -> Canonical Execution X -> O/R and all released refs
     -> ReleasedResult L -> R/X and typed M/C closure
     -> Report A -> R/X/L and separate representation artifacts
```

Global uniqueness of an ID is not permission to skip Run/Object verification.

The applied UAC-006 profile is `LOCAL_SINGLE_USER_TRUSTED_V1`: authentication/provider and
tenant/workspace/user ownership models are NONE, while exact identity validation is mandatory.
Request JSON may not use `user_id`, `actor_id`, `tenant_id`, `workspace_id` or `principal_id` as
authority. Cache/idempotency context uses server literal `LOCAL_SINGLE_USER`; no access-control
table or entity is added. See `PHASE4_ACCESS_MODE_DECISION_V1.md` for the complete owner decision
and its public-deployment limitations.

## 2. Cardinality and ownership rules

| Record | Required closure | Failure |
|---|---|---|
| Goal | `G.research_object_id == O.object_id`; `R.goal_id == G.goal_id` | `IDENTITY_MISMATCH` |
| Scheme | `S.research_object_id == O`; `S.goal_id == G`; `R.scheme_id == S.scheme_id`; confirmed | `IDENTITY_MISMATCH` |
| Planned/actual graph | both graph `run_id == R`; graph IDs equal the Run refs | `INTEGRITY_FAILURE` |
| Task | `T.run_id == R`; parent and dependency IDs resolve to Tasks in R | `IDENTITY_MISMATCH` or `INTEGRITY_FAILURE` for corrupt persisted closure |
| RuntimeEvent | event `run_id == R`; optional `task_id` resolves in R at/after an authoritative add | `IDENTITY_MISMATCH`; trigger projection recovery |
| Evidence | `E.run_id == R` and `E.object_id == O`; producer Task, if present, belongs to R | `IDENTITY_MISMATCH` |
| Calculation | `K.run_id == R`; `K.task_id` is a Task in R; all input Evidence owns R/O | `IDENTITY_MISMATCH` |
| Metric | enclosing released result owns R; `M.calculation_id` resolves to K; Evidence set closes | `INTEGRITY_FAILURE`; result not available |
| Claim | `C.run_id == R`; exact `metric_id`; canonical semantics and K/E sets equal M | `IDENTITY_MISMATCH` or `INTEGRITY_FAILURE` |
| Review | `V.run_id == R`; Claim association exists only through `reviewed_claim_refs` or typed Check subjects; K is reviewed | `IDENTITY_MISMATCH`; never claim PASS from shared Run alone |
| Proof | proof record owns R and exact K; requirement comes from exact policy decision; validity requires verification | `IDENTITY_MISMATCH` or `UNAVAILABLE` |
| Canonical | `X.run_id == R`; non-null `object_snapshot_ref == O`; all referenced released records own R | `INTEGRITY_FAILURE` |
| Released result | `L.run_id == R`; `L.canonical_record_id == X`; typed result validators close M/C/K/E | `INTEGRITY_FAILURE`; never `RELEASED` |
| Artifact | artifact `run_id == R`; canonical/result IDs equal X/L; byte hash/size/type equal record | `IDENTITY_MISMATCH` or `INTEGRITY_FAILURE`; no bytes |

`ProofResult` currently lacks `run_id` and `calculation_id`; by itself it is not sufficient Phase 4
proof identity. It must be joined to a durable, Run-bound proof request/record or returned as
`UNAVAILABLE`. `CanonicalExecutionRecord.object_snapshot_ref` is optional in the Phase 3 type but
is mandatory and equal to O in a Phase 4 released projection.

## 3. Exact Claim Trace contract

`GET /api/research-runs/{run_id}/trace/{claim_id}` returns the exact `TraceBundleV1` shape below.

```json
{
  "schema_version":"phase4-trace/v1",
  "projection_revision":14,
  "projection_sequence":42,
  "object_id":"OBJ-...",
  "run_id":"RUN-...",
  "claim_id":"CLAIM-...",
  "metric_id":"METRIC-...",
  "calculation_id":"CALC-...",
  "anchor_manifest_id":"ANCHOR-MANIFEST-...",
  "anchor_manifest_sha256":"sha256:<64 lowercase hex>",
  "claim":{},
  "released_metric":{},
  "task_refs":[{"task_id":"TASK-...","availability":{}}],
  "primary_task_id":null,
  "evidence_refs":[{"evidence_id":"EVD-...","availability":{}}],
  "calculation_refs":[{"calculation_id":"CALC-...","availability":{}}],
  "judgment_refs":[],
  "review_refs":[{"review_id":"REVIEW-...","check_ids":["CHECK-..."],"availability":{}}],
  "proof_refs":[{"proof_id":"PROOF-...","calculation_id":"CALC-...",
    "requirement":"MUST_PROVE","status":"VERIFIED","verification_id":"VERIFY-...",
    "availability":{}}],
  "canonical_record_id":"CER-...",
  "released_result_id":"RESULT-...",
  "report":{"report_id":"RESULT-...","representations":[
    {"format":"HTML","artifact_id":"RPT-HTML-...","availability":{},
      "claim_anchor":{"anchor_id":"ANCHOR-HTML-...","anchor_kind":"REPORT_CLAIM",
        "object_id":"OBJ-...","run_id":"RUN-...","claim_id":"CLAIM-...",
        "metric_id":"METRIC-...","report_id":"RESULT-...",
        "released_result_id":"RESULT-...","canonical_record_id":"CER-...",
        "format":"HTML","artifact_id":"RPT-HTML-...","availability":{}}},
    {"format":"PDF","artifact_id":null,"availability":{},
      "claim_anchor":{"anchor_id":null,"anchor_kind":"REPORT_CLAIM",
        "object_id":"OBJ-...","run_id":"RUN-...","claim_id":"CLAIM-...",
        "metric_id":"METRIC-...","report_id":"RESULT-...",
        "released_result_id":"RESULT-...","canonical_record_id":"CER-...",
        "format":"PDF","artifact_id":null,"availability":{}}}
  ]},
  "review_anchors":[{"anchor_id":"ANCHOR-REVIEW-...","anchor_kind":"REVIEW_CHECK",
    "object_id":"OBJ-...","run_id":"RUN-...","claim_id":"CLAIM-...",
    "review_id":"REVIEW-...","check_id":"CHECK-...","availability":{}}],
  "task_anchors":[{"anchor_id":"ANCHOR-TASK-...","anchor_kind":"TASK",
    "object_id":"OBJ-...","run_id":"RUN-...","claim_id":"CLAIM-...",
    "task_id":"TASK-...","availability":{}}],
  "execution_anchors":[{"anchor_id":"ANCHOR-EXEC-...","anchor_kind":"EXECUTION_EVENT",
    "object_id":"OBJ-...","run_id":"RUN-...","claim_id":"CLAIM-...",
    "canonical_record_id":"CER-...","task_id":"TASK-...",
    "event_refs":["EVT-..."],"availability":{}}],
  "availability":{"status":"AVAILABLE","reason_code":null,"retryable":false}
}
```

All anchor IDs are opaque and scoped to the tuple `object_id`, `run_id`, `claim_id`, and
`report_id`/`canonical_record_id`. They are not global DOM IDs. A renderer-produced report anchor
must name the exact representation/report Claim. Review anchors name an exact durable `check_id`;
Task anchors name an exact Task; execution anchors name exact safe event rows in X/R. Missing anchor
metadata does not fall back to a title or first match: the anchor remains present with
`UNAVAILABLE/DETAIL_NOT_RETAINED` and the action is disabled.

Claim-to-Task derivation is exactly:

```text
C.calculation_refs contains K.calculation_id
K.task_id == T.task_id
C.run_id == K.run_id == T.run_id == R
```

There is no text-based, formula-name, metric-name, company-name, array-position, `first`, or `latest`
join. All verified distinct Tasks produce `task_refs[]`. `primary_task_id` is non-null only when an
explicit durable Backend relation selects one of those Tasks. Singleton cardinality alone does not
establish business primacy; without that relation it remains null. Judgment detail requires a
typed/id-bearing same-Run record; untyped JSON may be cited only as unavailable retained detail.

## 4. Error envelope

Every non-stream JSON error uses:

```json
{
  "schema_version":"phase4-error/v1",
  "error":{
    "code":"NOT_FOUND",
    "message":"safe user-facing text",
    "retryable":false,
    "recovery":"NONE | RETRY | SNAPSHOT_RELOAD | REAUTHENTICATE",
    "request_id":"opaque-or-null",
    "resource":{"type":"research_run","id":"RUN-..."},
    "details":{}
  }
}
```

`details` is allowlisted and never contains filesystem paths, internal artifact refs, raw provider
payloads, SQL, stack traces, secrets, prompts, or hidden chain-of-thought.

| Public code | HTTP | Retryable | Recovery | Required behavior |
|---|---:|---:|---|---|
| `NOT_FOUND` | 404 | no | `NONE` | exact resource does not exist; never substitute |
| `UNAUTHENTICATED` | 401 | no | `REAUTHENTICATE` | reserved for a future governed access profile; not normally generated in Phase 4A local mode |
| `FORBIDDEN` | 403 | no | `NONE` | reserved for a future governed access profile; not normally generated in Phase 4A local mode |
| `UNAVAILABLE` | 409 | no | `NONE` | known retained resource/detail cannot be supplied; stable reason required |
| `NOT_GENERATED` | 409 | no | `NONE` | generation record/attempt absent |
| `NOT_RELEASED` | 409 | no while current state unchanged | `SNAPSHOT_RELOAD` for a live Run | release boundary is not satisfied |
| `CONFLICT` | 409 | no | `NONE` | idempotency hash, consumed draft, version, or state conflict |
| `INVALID_CURSOR` | 400 | no | `SNAPSHOT_RELOAD` | malformed, negative, unknown opaque, cross-Run, expired, or filter-mismatched cursor |
| `CURSOR_AHEAD` | 409 | no | `SNAPSHOT_RELOAD` | numeric sequence is greater than durable Run tail |
| `SCHEMA_INCOMPATIBLE` | 409 | no | `NONE` | unsupported DTO/status/payload contract version |
| `IDENTITY_MISMATCH` | 404 on public nested routes | no | `NONE` | resolved ID belongs to another Run/Object; fail closed |
| `INTEGRITY_FAILURE` | 500 | no | `SNAPSHOT_RELOAD` | expected persisted closure/hash/cardinality is corrupt; withhold data/bytes |
| `UNSUPPORTED_EVENT` | 409 | no | `SNAPSHOT_RELOAD` | raw event/payload cannot be safely normalized |
| `TERMINAL` | 409 | no | `NONE` | mutation/start attempted against a terminal Run |
| `REQUEST_VALIDATION_ERROR` | 422 | no | `NONE` | structurally invalid request without mutation |
| `TRANSIENT_BACKEND_ERROR` | 503 | yes | `RETRY` | bounded backoff; retain last valid snapshot as stale |
| `INTERNAL_ERROR` | 500 | no | `NONE` | allowlisted generic failure with no internal detail |

The inspected backend's `RESOURCE_NOT_FOUND` maps to public `NOT_FOUND`. Its current envelope is a
compatible base but lacks schema version, retryability, recovery, and allowlisted resource data;
those additions are `PROJECTION_ONLY`. A raw `KeyError`/`ValueError` raised after SSE response
headers is not a compliant error response.

## 5. Availability behavior

| Resource/action | `AVAILABLE` condition | Non-available outcome |
|---|---|---|
| Results/A tab | Run is `RELEASED`; L/X/review/proof/material-output closure passes | disable Results for all other states; `NOT_RELEASED`, `UNAVAILABLE`, or `FAILED` |
| Financial Review/B tab | exact Review record exists and closes to R; released view additionally requires X/L | before review `PENDING`; terminal-before-review `NOT_GENERATED`; corrupt relation `UNAVAILABLE` |
| Execution/C tab | exact canonical X exists and owns O/R | `NOT_GENERATED` before canonicalization; `INTEGRITY_FAILURE` on mismatch |
| Claim detail | exact C in L for R and M/K/E closure passes | requested absent C: `NOT_FOUND`; referenced detail not retained: typed `UNAVAILABLE` entry |
| Proof | exact policy plus Run-bound proof/verification records | never infer `NOT_REQUIRED` from absence; return `UNAVAILABLE/PROOF_POLICY_UNKNOWN` |
| HTML/PDF action | exact representation `AVAILABLE`, authorized ref present, byte integrity passes | action disabled; show per-representation safe reason |
| Report/review/task/execution anchor | exact scoped anchor manifest entry exists | durable unavailable panel; no search or fallback |
| Released Object state | at least one valid released Run owned by O | `latest_released_run_id=null` plus `NOT_RELEASED/NO_RELEASED_RUN` |

A response may contain an ID plus unavailable detail when the authoritative parent record retains
the reference but the detail body is not retained. The ID must remain visible in the projection so
the loss is auditable. It must not become an empty list. A missing expected child that is required
for release closure is an integrity failure, not benign unavailable detail.

## 6. Result and artifact blocking rules

- Any `FAILED`, `IDENTITY_MISMATCH`, `INTEGRITY_FAILURE`, unknown proof policy, required proof without
  valid verification, missing material calculation/evidence/Claim, or unsuccessful Review blocks
  Results and all artifact actions.
- Successful professional release requires one available, integrity-valid HTML representation.
  PDF remains an independent optional slot and may be explicitly `NOT_GENERATED` or `FAILED`
  without falsifying HTML availability or the release.
- `NOT_RELEASED` blocks A/B/C released views and artifacts but permits live Run projection.
- `NOT_GENERATED` disables only the absent resource unless it is mandatory to the release boundary.
- `TRANSIENT_BACKEND_ERROR` retains the last valid UI snapshot marked stale; it cannot advance
  status, progress, proof, result, or release.
- `INVALID_CURSOR`, `CURSOR_AHEAD`, `UNSUPPORTED_EVENT`, and `SCHEMA_INCOMPATIBLE` stop event
  reduction and require an authoritative snapshot recovery.
- Phase 4A does not normally emit `FORBIDDEN`; public `IDENTITY_MISMATCH` exposes no body or owner
  fact from the resolved foreign record.

## 7. Negative identity cases

| Case | Required result |
|---|---|
| request Run B under Object A history | reject or navigate wholly to B's authoritative context; never mixed A/B projection |
| request Claim B under Run A | 404 fail-closed; no Claim A fallback |
| request Task B under Run A | 404 fail-closed; no same-title Task |
| request Review B/check B under Run A | 404 fail-closed; no status leakage |
| place Evidence or Calculation B in Claim A trace | `INTEGRITY_FAILURE`; no B value/provider body |
| associate Proof B by matching formula/capability name | forbidden join; proof unavailable/integrity failure |
| use Artifact B content URL with Run A | 404 `IDENTITY_MISMATCH`; zero bytes |
| use globally latest released Run B for Object A | forbidden; A state remains unchanged/unavailable |
| use a historical Claim ID with a newer same-object Run | 404; no same-metric fallback |
| pass Event ID from Run B as Run A cursor | `INVALID_CURSOR`; never reveal/replay B |

## 8. Field classifications and missing authority

| Required field/relation | Classification | Closure action |
|---|---|---|
| direct Run/Task/Evidence/Calculation/Claim/Review/ProofRecord/Canonical/Result/Artifact IDs | `EXISTING_BACKEND` | preserve exact values |
| injected `object_id` on nested public projections | `PROJECTION_ONLY` | derive only through verified Run |
| Claim `task_refs`, `review_refs`, `proof_refs` | `PROJECTION_ONLY` | exact K/review-subject/proof-K joins |
| stable Review `check_id` and check-to-correction relation | `BACKEND_FIELD_REQUIRED` | persist canonical IDs/refs before claiming resolved history |
| typed Judgment identity/details | `BACKEND_FIELD_REQUIRED` for detail; unavailable wrapper is `PROJECTION_ONLY` | no arbitrary JSON text join |
| report/review/task/execution anchor manifest | `BACKEND_FIELD_REQUIRED` | produced and persisted by authoritative renderer/projection owner |
| availability/error wrappers and safe redaction | `PROJECTION_ONLY` | map verified state using this contract |
| artifact byte delivery | `ADDITIVE_ROUTE_REQUIRED` | use a non-bearer same-origin path and repeat LOCAL_SINGLE_USER context plus full O/R/X/L/artifact binding/integrity checks on every GET |
| direct public exposure of internal `artifact_ref`/`raw_artifact_ref` | `SEMANTIC_CONFLICT` | omit from public DTOs |
| cross-object/latest/first/text repair | `SEMANTIC_CONFLICT` | prohibited |
| versioned Object/Research View, memory, comparison, incremental, writeback | `PHASE5_DEFERRED` | absent from Core |

## 9. Acceptance oracles

Positive same-Run closure: `P4-ID-001..020`, `023..028`, `P4-E2E-069..072`, `092..096`.  
Negative cross-object/Run closure: `P4-ID-025..027`, `P4-E2E-073`, artifact substitution in
`P4-E2E-096`.  
Missing/unavailable detail: `P4-E2E-046`, `051..054`, `086`, `092`.  
Restart persistence: `P4-ID-023`, `P4-E2E-098`.  
Unknown version/value: `P4-E2E-032`, `077`, `084`, `088`; event cases `P4-SSE-011..013`, `018`.  
Authorization: `P4-ID-025..027`, `P4-E2E-073`, `096`.

An oracle passes only from captured HTTP/SSE responses, durable database rows, and delivered-byte
hashes. DOM text, route text, fixture assumptions, or a successful status code alone are not proof.
