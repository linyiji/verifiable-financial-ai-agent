# Frontend Change Request Template

Copy this template for every governed Frontend change. Replace every placeholder. `NONE` requires a
reason; blank fields are invalid.

## 1. Record

```yaml
change_id: FCR-YYYY-NNNN
status: DRAFT_CHANGE
title: <short title>
change_type:
  - UX_VISUAL | INTERACTION | BACKEND_CONTRACT | PRODUCT_SEMANTIC
  - ACCESSIBILITY | RESPONSIVE | BUG_FIX | SCENARIO_CHANGE
reason: >-
  <problem, evidence, desired outcome, and why the current approved baseline should change>

affected_pages:
  - <route and page ID, or NONE with rationale>
affected_components:
  - <component path/name, or NONE with rationale>
affected_contracts:
  - <contract ID/version, adapter/event/DTO/interaction ID, or NONE with rationale>
affected_scenes:
  - <SCENE-01..06 and any later stable Scene IDs; detailed classification is mandatory below>

backend_dependency:
  required: true | false
  baseline_sha_or_contract_version: <exact coordinate or NONE>
  dependency: <endpoint/event/DTO/status/artifact/projection or NONE>
  readiness: AVAILABLE | PENDING | BLOCKED | NOT_APPLICABLE
  fallback_and_provenance: <truthful behavior; no silent real-to-fixture substitution>

reference_version: UX_REFERENCE_V<N>@<revision>#sha256:<hash>
frontend_target_version: FRONTEND_V<N>@<revision>
reference_relationship: EXACT_TARGET | COMPATIBLE_WITH_DECLARED_DELTA | MISMATCH
reference_mismatch_record: <ID or NONE>

previous_baseline_id: FRONTEND_BASELINE_V<N>
previous_baseline_sha: <full immutable commit SHA>
candidate_sha: PENDING
candidate_tree_fingerprint: PENDING
candidate_build_sha256: PENDING

required_tests:
  - id: <stable gate/test ID>
    environment: <browser/viewport/mode/backend coordinate>
    oracle: <authoritative expected result>
    evidence: PENDING

audit_result: NOT_RUN
audit_id: PENDING
```

## 2. Before/after semantic contract

### Current approved behavior

Describe the user-visible behavior, source of authority, identity context, loading/error/unavailable
states, accessible behavior, responsive behavior, and exact baseline evidence.

### Proposed behavior

Describe the same dimensions after the change. State what must remain unchanged.

### Non-goals

- <explicit behavior, page, contract, Scene, or claim that this request does not authorize>

### Acceptance statements

Use observable statements. Do not use “looks right,” “works,” or implementation-only criteria.

1. Given `<state>`, when `<action/event>`, then `<observable result and authority>`.
2. Given `<negative/error state>`, when `<action/event>`, then `<safe result>`.

## 3. Change-type rationale

| Type | Selected | Rationale | Regression consequence |
|---|---:|---|---|
| `UX_VISUAL` | yes/no | | affected pages + responsive + accessibility |
| `INTERACTION` | yes/no | | affected controls + journeys |
| `BACKEND_CONTRACT` | yes/no | | adapter -> projection -> reducer/store -> page |
| `PRODUCT_SEMANTIC` | yes/no | | Scenario Spec -> contract -> UI -> acceptance |
| `ACCESSIBILITY` | yes/no | | semantic, keyboard, focus, announcement, contrast/motion |
| `RESPONSIVE` | yes/no | | all governed viewports, reflow, touch, overflow, zoom |
| `BUG_FIX` | yes/no | | reproduction + underlying type scopes + adjacent states |
| `SCENARIO_CHANGE` | yes/no | | affected Scene + shared gates + corpus version |

The required test scope is the union of all selected rows.

## 4. Impact and reachability

| Changed input/module | Direct consumers | Reachable pages | Contracts | Controls | Scenes | Test IDs |
|---|---|---|---|---|---|---|
| | | | | | | |

Include source, CSS/assets, dependencies, configuration, fixtures, generated artifacts, adapters,
projections, reducers/stores, and test oracles. Update this table if the actual Candidate diff grows.

## 5. Six-Scene declaration

Every row is mandatory. `UNAFFECTED` requires a concrete reachability rationale.

| Scene ID | Stable intent | Impact | Reason | Version before -> after | Required Scene/shared gates | Result/evidence |
|---|---|---|---|---|---|---|
| `SCENE-01` | Full Financial Research | AFFECTED / UNAFFECTED | | | | PENDING |
| `SCENE-02` | Dynamic Research Path | AFFECTED / UNAFFECTED | | | | PENDING |
| `SCENE-03` | Self-Correction and Financial Review | AFFECTED / UNAFFECTED | | | | PENDING |
| `SCENE-04` | Claim Trace / Verifiable Research | AFFECTED / UNAFFECTED | | | | PENDING |
| `SCENE-05` | Research Object Accumulation | AFFECTED / UNAFFECTED | | | | PENDING |
| `SCENE-06` | Incremental Returning User | AFFECTED / UNAFFECTED | | | | PENDING |

If affected, rerun the entire Scene plus all shared cross-cutting gates. Demo and integrated results
are separate evidence classes.

## 6. Interaction-contract delta

Attach the complete machine-readable matrix. Summarize it here. The starting V8 inventory maps the
64 rows to `P4-E2E-001..064`.

| Interaction ID | Control/user intent | Baseline state | Candidate state | Disposition | Change ID | A11y/responsive effect | Scene IDs | Test IDs |
|---|---|---|---|---|---|---|---|---|
| | exposed/absent | exposed/absent | `ADDED` / `REMOVED` / `CHANGED` / `UNCHANGED` | | | | | |

```yaml
interaction_summary:
  baseline_rows: 64
  candidate_exposed_controls: <count>
  added: <count>
  removed: <count>
  changed: <count>
  unchanged: <count>
  union_rows: <count>
  classified_union_rows: <count>
  union_classification_percent: <must equal 100>
  classified_candidate_exposed_controls: <count>
  candidate_exposed_classification_percent: <must equal 100>
  matrix_version_before: <version/hash>
  matrix_version_after: <version/hash>
```

Removed IDs remain tombstones. Added controls receive the next monotonic ID. IDs are never reused or
renumbered.

## 7. Reference delta

| Item | Baseline | Candidate target | Intentional difference | Approval/test |
|---|---|---|---|---|
| UX Reference | | | | |
| page/state captures | | | | |
| product terminology | | | | |
| accessibility | | | | |
| responsive behavior | | | | |
| Scene corpus | | | | |
| interaction matrix | | | | |

If a superseded reference is used for historical comparison, record it below. It has no current
acceptance authority.

```yaml
superseded_reference_comparison:
  used: false
  compared_reference: NONE
  current_reference: <exact version/hash>
  purpose: NONE
  mismatch_record: NONE
```

## 8. Regression plan and results

| Test/gate ID | Why required | Mode/source | Viewport/browser | Oracle | Result | Evidence hash/location |
|---|---|---|---|---|---|---|
| | | | | | NOT_RUN | |

Mandatory release-Candidate cross-cutting rows include build/typecheck, identity preservation,
financial-authority boundary, provenance, unavailable/error states, accessibility smoke, responsive
smoke, runtime/console errors, and interaction classification completeness.

## 9. Candidate freeze

```yaml
candidate_freeze:
  candidate_sha: <full SHA>
  tree_state: CLEAN
  tree_fingerprint: sha256:<hash>
  lockfile_sha256: <hash>
  build_command: <command>
  toolchain: <versions>
  build_artifact_sha256: <hash>
  reference_manifest_sha256: <hash>
  scene_corpus_sha256: <hash>
  interaction_matrix_sha256: <hash>
  frozen_at: <timestamp with timezone>
```

A dirty `FULLY_FINGERPRINTED` snapshot may be recorded for a non-decisional pre-audit, but it must
be committed and refrozen as `CLEAN` before an independent audit can return `PASS` or promote it.

## 10. Approvals and independent audit

```yaml
change_approval:
  decision: APPROVED | REJECTED | NEEDS_REVISION
  approver: <name>
  approved_revision: <record revision/hash>
  decided_at: <timestamp>

independent_delta_audit:
  audit_id: <ID>
  auditor: <name>
  independence_statement: <statement>
  baseline_verified: true | false
  candidate_verified: true | false
  reference_pair_verified: true | false
  required_tests_passed: <passed>/<required>
  affected_scenes_passed: <passed>/<affected>
  interaction_classification: <classified>/<union and percent>
  unresolved_p0: <count>
  unresolved_p1: <count>
  audit_result: PASS | FAIL
  report_hash_or_location: <immutable evidence>
  decided_at: <timestamp>
```

## 11. Baseline promotion

Complete only after independent `PASS`.

```yaml
promotion:
  new_baseline_id: FRONTEND_BASELINE_V<N>
  new_baseline_manifest_sha256: <hash>
  promoted_candidate_sha: <must equal audited candidate_sha>
  promoted_build_sha256: <must equal audited build hash>
  previous_baseline_id: <ID>
  previous_baseline_sha: <full SHA>
  approver: <name>
  promoted_at: <timestamp>
  decision: BASELINE_PROMOTED | NOT_PROMOTED
```

If any promoted coordinate differs from the audit, set `NOT_PROMOTED` and audit the new Candidate.
