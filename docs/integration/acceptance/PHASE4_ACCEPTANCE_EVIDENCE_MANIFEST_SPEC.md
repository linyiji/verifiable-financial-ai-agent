# Phase 4 Acceptance Evidence Manifest Specification

Status: **AUTHORITATIVE DESIGN — NOT IMPLEMENTED — NOT EXECUTED**

## 1. Purpose

The evidence bundle makes every future gate result reproducible, candidate-bound and independently auditable. A screenshot or prose claim alone is never sufficient. The root manifest identifies exact bits and content-addresses every retained evidence object.

No bundle may contain secrets, credentials, cookies, bearer tokens, private provider payloads, hidden chain-of-thought, private prompts, or unredacted licensed bodies. Sanitization must preserve IDs, status, sequence, hashes, sizes, media types, timestamps and semantic fields needed by the oracle.

## 2. Bundle layout

```text
phase4-acceptance/<acceptance_run_id>/
  manifest.json
  manifest.sha256
  candidates/
    backend.json
    frontend.json
    contracts.json
    environment.json
  results/
    p4-be.json
    p4-e2e.json
    p4-sse.json
    p4-id.json
    scenes.json
    interactions.json
    aggregate.json
  attempts/<attempt_id>/attempt.json
  http/<attempt_id>/request-ledger.jsonl
  sse/<attempt_id>/frame-ledger.jsonl
  projections/<attempt_id>/*.json
  artifacts/<attempt_id>/metadata.json
  artifacts/<attempt_id>/authorized-bytes/*
  browser/<attempt_id>/trace.zip
  browser/<attempt_id>/console.jsonl
  browser/<attempt_id>/screenshots/*
  browser/<attempt_id>/responsive.json
  logs/<attempt_id>/sanitized/*
  audit/audit-report.json
  audit/rerun-ledger.json
```

Names may differ in implementation, but every logical object above is mandatory when applicable and must be referenced from the root manifest by relative path plus SHA-256. An external evidence store may replace the directory only when locators are immutable, access-controlled and content-addressed.

## 3. Root manifest

The root is UTF-8 JSON with sorted object keys, no insignificant whitespace, RFC 3339 UTC timestamps and lowercase `sha256:<64-hex>` digests. Arrays whose order has meaning retain observed order; set-like arrays are sorted before canonicalization.

```json
{
  "schema_version": "phase4-acceptance-evidence-v1",
  "acceptance_run_id": "P4A-...",
  "created_at": "2030-01-01T00:00:00Z",
  "coordinator": "...",
  "auditor": "...",
  "independence_declaration_ref": "audit/audit-report.json",
  "candidate_pair": {
    "approved_phase3_backend_parent_sha": "<40-hex>",
    "backend_phase4_candidate_sha": "<40-hex>",
    "backend_tree_sha": "<40-hex>",
    "backend_clean": true,
    "backend_build_hash": "sha256:<hex>",
    "frontend_parent_baseline_id": "FRONTEND_BASELINE_V8.1",
    "frontend_parent_sha": "d854c97789c98cca14fee3f4b3d7f00e0d5d137a",
    "frontend_change_request_id": "FCR-...",
    "frontend_change_request_revision": "...",
    "frontend_v17_candidate_sha": "<40-hex>",
    "frontend_tree_sha": "<40-hex>",
    "frontend_clean": true,
    "frontend_build_hash": "sha256:<hex>"
  },
  "contracts": {
    "database_revision": "...",
    "api_schema_version": "...",
    "api_schema_hash": "sha256:<hex>",
    "event_contract_version": "...",
    "event_contract_hash": "sha256:<hex>",
    "route_version": "...",
    "acceptance_catalog_hash": "sha256:<hex>",
    "crosswalk_hash": "sha256:<hex>"
  },
  "execution": {
    "source_classes": ["INTEGRATED", "CHAOS_SSE"],
    "runtime_mode": "...",
    "environment_ref": "candidates/environment.json",
    "started_at": "2030-01-01T00:00:00Z",
    "completed_at": "2030-01-01T01:00:00Z"
  },
  "result_refs": {
    "p4_be": {"path": "results/p4-be.json", "sha256": "sha256:<hex>"},
    "p4_e2e": {"path": "results/p4-e2e.json", "sha256": "sha256:<hex>"},
    "p4_sse": {"path": "results/p4-sse.json", "sha256": "sha256:<hex>"},
    "p4_id": {"path": "results/p4-id.json", "sha256": "sha256:<hex>"},
    "scenes": {"path": "results/scenes.json", "sha256": "sha256:<hex>"},
    "interactions": {"path": "results/interactions.json", "sha256": "sha256:<hex>"},
    "aggregate": {"path": "results/aggregate.json", "sha256": "sha256:<hex>"}
  },
  "attempt_index": [],
  "bundle_hash": "sha256:<hex>"
}
```

`bundle_hash` is computed over a sorted manifest of every retained file digest, excluding `manifest.sha256` and with the root `bundle_hash` field temporarily set to `null`. The implementation must document its exact canonicalization algorithm and include a verifier.

## 4. Candidate and environment evidence

### Backend

Record branch/ref for context, full SHA, Git tree, clean `git status` witness, dependency lock hashes, Python/runtime versions, OS/container image, build/package hashes, migration revision, configuration schema hash and startup command. Environment values are allow-listed; secret values are replaced by a typed redaction marker and are never hashed in a way that enables guessing.

### Frontend

Record V8.1 parent manifest, approved Change Request and revision, V17 full SHA/tree/clean witness, changed-file inventory, lockfile/toolchain versions, reference IDs and hashes, Scene and interaction corpus hashes, build command and per-asset hashes. The served asset hashes must equal the audited build.

### Same-candidate witness

The Backend exposes or logs a non-secret build identity; the Frontend served assets are hashed by the harness. The browser HTTP/SSE ledgers must point to those same identities. Evidence from a prior build or another running process fails applicability even when source SHAs appear equal.

## 5. Gate result record

Every defined gate has exactly one lifecycle record per acceptance run:

```json
{
  "gate_id": "P4-BE-001",
  "catalog_contract_hash": "sha256:<hex>",
  "activation_scope": "PHASE4_CORE_REQUIRED",
  "activation_state": "REQUIRED",
  "result": "PASS",
  "source_class": "INTEGRATED",
  "attempt_ids": ["ATT-..."],
  "final_attempt_id": "ATT-...",
  "evidence_refs": [{"path": "...", "sha256": "sha256:<hex>"}],
  "mapped_gate_results": ["P4-E2E-...", "P4-ID-..."],
  "decided_at": "2030-01-01T00:00:00Z",
  "decision_owner": "independent-auditor"
}
```

Allowed lifecycle/result combinations are closed:

| Lifecycle | `activation_state` | `result` |
|---|---|---|
| active and required | `REQUIRED` | `PASS` or `FAIL` only |
| defined future gate | `DEFINED_NOT_ACTIVATED` | `null` |
| historical tombstone | `RETIRED_TOMBSTONE` | `null` |

`NOT_IMPLEMENTED` is allowed only in a separate design/readiness field before execution. It is not a release result. A required gate with no applicable attempt is emitted as `FAIL` with `failure_code=REQUIRED_EVIDENCE_ABSENT`.

## 6. Attempt and failure history

Failed attempts are append-only and remain part of the bundle after a later PASS.

```json
{
  "attempt_id": "ATT-...",
  "gate_ids": ["P4-SSE-006"],
  "candidate_pair_hash": "sha256:<hex>",
  "candidate_shas": {"backend": "...", "frontend": "..."},
  "source_class": "CHAOS_SSE",
  "environment_hash": "sha256:<hex>",
  "started_at": "2030-01-01T00:00:00Z",
  "completed_at": "2030-01-01T00:01:00Z",
  "outcome": "PASS",
  "failure": null,
  "rerun_reason": "environmental cause proven by ...",
  "source_changed_since_previous_attempt": false,
  "previous_attempt_id": "ATT-...",
  "final_disposition": "ACCEPTED_AS_FINAL_ATTEMPT",
  "evidence_refs": []
}
```

If source or another Candidate-defining input changed, the attempt belongs to a new Candidate and cannot overwrite or cure the old Candidate's failure. If source did not change, the rerun reason must identify independently verifiable environmental or nondeterministic evidence. An unexplained deterministic fail-then-pass remains a gate failure.

## 7. HTTP request ledger

Each entry records monotonic observation index, timestamp, browser/context ID, method, normalized route template, safe query keys, request-body semantic hash, idempotency-key fingerprint, response status, response content type, response schema version, response semantic hash, entity IDs, server build identity and matching projection/artifact references.

Request and response bodies are stored only as an allow-listed sanitized projection. Remove credentials and provider bodies while retaining fields required to prove identity, canonical/display finance, release, review, projection sequence and artifact metadata. Route interception or response fulfilment is recorded and causes integrated gates to fail; passive observation and an authorized chaos connection abort are distinguished explicitly.

## 8. SSE frame ledger

Every connection and complete real frame is recorded before and after the chaos proxy:

```json
{
  "connection_id": "SSE-...",
  "arrival_index": 17,
  "proxy_delivery_index": 19,
  "observed_at": "...Z",
  "wire_id": "42",
  "wire_event": "task.progress",
  "data_event_id": "opaque-event-id",
  "run_id": "...",
  "task_id": "...",
  "sequence": 42,
  "timestamp": "...Z",
  "payload_semantic_hash": "sha256:<hex>",
  "complete_frame_hash": "sha256:<hex>",
  "proxy_operation": "DELAY",
  "client_disposition": "BUFFERED",
  "projection_hash_after": "sha256:<hex>"
}
```

Allowed `proxy_operation` values are `PASS`, `DROP`, `DELAY`, `DUPLICATE`, and `REORDER`. The pre/post frame hashes prove the proxy did not edit a frame. Heartbeat comments are retained separately and must produce no projection mutation. The ledger also records request cursor, response content type, close reason, terminal event and reconciliation requests.

## 9. Projection and browser evidence

At each named checkpoint retain:

- authoritative Run projection body/hash, schema version, `last_sequence`, revision and graph version;
- independent reads of Run, Task/graphs, Claims, Review, CER/result and artifact metadata where the atomic projection is being verified;
- browser route, history index, current Object/Run/Claim/Task/tab, focus target, scroll coordinates and DOM semantic snapshot;
- control-browser and chaos-browser normalized projection hashes;
- console messages, page errors, unhandled rejections and failed requests;
- responsive results for 1024, 1280, 1366, 1440 and 1920 widths at the governed height;
- browser trace and minimal screenshots needed to inspect focus, overlays, errors and visual availability.

DOM snapshots include backend IDs and visible semantic text but exclude arbitrary page content not needed for acceptance.

## 10. Financial, trace and release evidence

For each accepted material metric, retain one joined record containing:

```text
metric_id, run_id
canonical_value, canonical_unit
display_value, display_unit
period, period_basis, actuality, as_of, currency
claim_id(s), calculation_id, evidence_id(s), proof_id(s)
review_id/check identity
canonical_record_id, released_result_id
report/artifact anchor identity
browser visible text and target identity
```

The `0.6547 RATIO -> 65.47 % -> 65.47%` witness is mandatory. The evidence must show that browser source code did not calculate financial truth and that visible values equal captured Backend display fields.

A released-result evidence record includes the Backend release-gate decision, valid Review, terminal CER, required Proof disposition, ReleasedResearchResult identity, terminal event ordering and artifact consistency. A report that is present but semantically unavailable is recorded as unavailable and cannot satisfy release gates.

## 11. Artifact evidence

HTML and PDF are separate evidence rows and identities. For each representation retain:

```text
artifact_id
object_id
run_id
canonical_record_id
released_result_id/report_id according to the frozen contract
format
content_type
size
declared hash
actual authorized-byte count and SHA-256
authorization decision
safe delivery locator fingerprint
renderer identity/version
availability/failure code
```

The test fetches bytes through the authorized delivery boundary, independently measures size/type/hash, and compares them with metadata. A raw filesystem or internal `artifact://` path in any public response fails. Tampered, cross-object, unauthorized or wrong-media responses fail closed and must never fall back to Demo bytes.

## 12. Sanitization and integrity

Sanitization is allow-list based and versioned. Each sanitized object records its source class, sanitizer version and pre-sanitization record locator available only to an authorized evidence custodian when legally permitted. Do not retain a raw licensed provider body merely to strengthen the bundle.

Required validation before audit:

1. verify every referenced path exists and its digest matches;
2. reject absolute, parent-traversal or external mutable locators;
3. scan for known secret names and high-risk token patterns;
4. verify all gate IDs exist in the content-hashed catalogue;
5. verify inactive/tombstone rows have `result=null`;
6. verify every required row is binary and has evidence;
7. recompute attempt, artifact, result-file and bundle hashes;
8. verify Candidate and served-bit identities agree across every ledger.

## 13. Retention and audit handoff

The final bundle is immutable after audit begins. Corrections produce a new bundle revision with a parent digest; they do not edit prior evidence. Retention duration and access controls follow the release policy, but gate summaries, hashes, Candidate identities and failed-attempt history must remain sufficient to reconstruct the decision.

The independent auditor signs or content-addresses the final report and aggregate only after raw evidence inspection and critical reruns. The aggregate remains `FAIL` until that independent decision is `PASS`.
