# Frontend Baseline Policy

Status: `GOVERNANCE_SPECIFICATION`

## 1. Policy decision

An Approved Frontend Baseline is a signed, immutable evidence bundle, not simply a commit. It is the
only permitted starting point for a governed Frontend change and the only valid “before” side of a
Delta Audit.

This policy separates three coordinates that must never be conflated:

1. the approved UX/product semantic reference;
2. the implemented Frontend source and build;
3. the independently accepted baseline record binding the first two.

## 2. Baseline manifest

Each approved baseline must have a unique ID such as `FRONTEND_BASELINE_V9.0.0` and one immutable
manifest with these fields:

| Field | Requirement |
|---|---|
| `baseline_id` | unique, monotonic Frontend baseline version |
| `status` | `APPROVED`, later optionally `SUPERSEDED` or `REVOKED`; history is retained |
| `approved_at` | ISO-8601 timestamp with timezone |
| `approved_by` | named accountable approver(s) |
| `source_repository` | canonical repository identity |
| `source_branch` | informational branch name; never the immutable identity |
| `source_sha` | full commit SHA |
| `source_tree_state` | exactly `CLEAN`; dirty source cannot be promoted |
| `source_tree_fingerprint` | SHA-256 of the governed source manifest |
| `build_artifact_sha256` | hash of the exact accepted deployable artifact |
| `build_command` | reproducible command |
| `toolchain` | Node, package manager, lockfile hash, browser/test runner versions |
| `ux_reference_version` | explicit ID governed by `FRONTEND_REFERENCE_VERSIONING.md` |
| `ux_reference_sha256` | content hash of the exact reference artifact set |
| `frontend_version` | implementation version paired to the reference |
| `product_contract_versions` | approved product/semantic specifications |
| `backend_contract_versions` | exact DTO/event/status/artifact contract inputs or compatibility manifest |
| `scene_corpus_version` | version and hash covering `SCENE-01..06` plus any later Scenes |
| `interaction_matrix_version` | version and hash covering all active rows and tombstones |
| `viewport_matrix` | named viewport widths/heights, DPR, orientation, zoom expectations, and browser coverage |
| `accessibility_profile` | governing standard/version plus automated and manual checks |
| `change_ids` | all Change Requests included since the previous baseline |
| `previous_baseline_id` | immediate lineage parent; `NONE` only for a seed baseline |
| `previous_baseline_sha` | immediate parent source SHA; `NONE` only for a seed baseline |
| `regression_evidence` | stable links/paths and hashes for required results |
| `delta_audit_id` | independent audit record |
| `audit_result` | exactly `PASS` |
| `known_limitations` | truthful Demo/real, placeholder, unavailable, deferred, and environment boundaries |
| `manifest_sha256` | hash/signature over the completed manifest |

The manifest must also include a sorted file-to-SHA-256 list for reference assets, Scene definitions,
interaction contracts, and generated build outputs used as evidence.

## 3. Semantic contents of a baseline

The baseline preserves at least these V8 principles unless an approved `PRODUCT_SEMANTIC` change
explicitly supersedes one:

1. Primary navigation remains New Task / Runs / Research Objects.
2. Every start creates a new Research Run.
3. AI Research presents the governed five-step progression.
4. Initial Research Plan and Actual Research Path remain distinct.
5. Normal self-correction/replan is automatic; only true scope/cost/capability gates require user
   action.
6. Report, Financial Review, and Execution views derive from one canonical research record.
7. Research Claim remains the cross-view trace anchor.
8. The Frontend does not author authoritative deterministic financial values.
9. Backend runtime state, calculations, review, claims, and report artifacts remain authoritative.

The detailed source is `../frontend_v8/00_FRONTEND_READ_FIRST.md` and its approved companion
contracts. Copying this list into a new document does not silently version or replace those sources.

## 4. Seed-state rule for V8

Repository evidence currently establishes:

- an approved V8 HTML/UX semantic reference at
  `../../frontend_reference/financial_agent_workspace_v8_dynamic_path.html` with the V8 Frontend
  contract package;
- a remediated pre-integration React Candidate identified in existing evidence as
  `a850bce3cf0b8a72bc28c7ce16a67e9f83be0c84`;
- Candidate self-acceptance claims for six Scenes, regressions, and 64 interaction classifications;
- an explicit outstanding requirement for independent Frontend delta verification.

Therefore this governance package records the following conservative seed status:

```text
UX_REFERENCE_V8_SEMANTICS = APPROVED_INPUT
FRONTEND_V8_REMEDIATION_CANDIDATE = NOT_AN_APPROVED_IMPLEMENTATION_BASELINE
INDEPENDENT_DELTA = PENDING
```

The first implementation baseline governed here must be created by auditing an immutable Candidate
against the V8 semantic reference and other approved inputs. Existing self-acceptance evidence may
be reused as supporting evidence only after exact SHA/build applicability is verified; it cannot
replace the independent audit.

This first-baseline ratification is the sole bootstrap exception to the normal baseline-to-baseline
flow. It uses the approved V8 reference as the semantic “before” side, inventories every exposed
Candidate control and all six Scenes, and permits no new product semantic unless separately approved.
After ratification, every change uses the immediately previous implementation baseline.

## 5. Promotion criteria

A Candidate may be promoted only when all are true:

- the Change Request was approved before or explicitly re-approved after the final scope was known;
- `candidate_sha`, tree fingerprint, dependency lock, and build artifact are frozen;
- the source tree is clean and all material source/reference inputs are committed or stored as
  immutable, content-addressed governed artifacts;
- UX Reference/Frontend compatibility is explicit and content-hashed;
- the actual diff is fully accounted for by approved Change Requests;
- required type-specific regressions pass;
- every affected Scene and all shared cross-cutting gates pass;
- the interaction inventory is 100% classified;
- the independent Delta Audit is `PASS`;
- required integrated tests use authoritative HTTP/SSE and backend records where the Candidate makes
  an integrated claim;
- Demo evidence is reported separately and is not counted as integrated evidence;
- known limitations and unavailable capabilities are visible and truthful;
- the proposed manifest is complete and hashes to the audited inputs.

Promotion is atomic: the source SHA, build artifact, references, tests, audit, and manifest become
approved together. Partial approval is not a Frontend baseline.

## 6. Immutability and supersession

- Never retag, force-move, or rebuild an Approved Baseline in place.
- A dependency-only or rebuild-only change produces a new Candidate because output identity changed.
- Corrections to a manifest are append-only amendments. If an identity-bearing field was wrong, the
  baseline is revoked and a corrected Candidate is audited.
- A New Approved Baseline changes the predecessor status to `SUPERSEDED` but does not delete it.
- All Scene and interaction tombstones remain part of history.
- Retain enough source, lockfile, build, reference, test, and audit material to reproduce the basis
  of the decision.

## 7. Baseline selection

The default parent is the highest/latest non-revoked Approved Frontend Baseline on the product's
declared release line. A Candidate based on an older baseline must state why and must audit:

1. its change against that older parent; and
2. its divergence from the current approved baseline.

It cannot silently replace newer accepted semantics. Parallel Candidates do not become mutual
parents merely because their branches contain each other's commits.

## 8. Baseline scope and phase labels

A baseline manifest lists the phase specification(s) it implements by exact document/version. Phase
labels do not loosen acceptance:

- Phase 4 integration must retain V8 semantics while adding authoritative backend projection;
- later trust, capability, output, object, comparison, or other Phase 5–7 work remains subject to
  the same semantic delta controls;
- inconsistent phase numbering across planning documents must be resolved by naming the governing
  specification, not by guessing from the number;
- a future Phase 7 scope is not accepted until its product and contract inputs are versioned.

## 9. Revocation and rollback

An approved baseline may be marked `REVOKED` if evidence is falsified, a release-blocking security or
identity defect is discovered, or the accepted artifact cannot be reproduced/identified. Revocation
must include reason, time, approver, affected releases, and replacement/rollback instruction.

Rollback means deploying or selecting a previously approved, non-revoked artifact. Editing the old
artifact to contain a fix is prohibited. A corrective forward Candidate follows the full Change
Protocol.

## 10. Minimum baseline index

Maintain an append-only index with one row per baseline:

| Baseline ID | Frontend SHA | Build SHA-256 | UX Reference | Scene corpus | Interaction matrix | Audit | Status |
|---|---|---|---|---|---|---|---|

No row may say `APPROVED` unless the linked audit says `PASS` and all coordinates match.
