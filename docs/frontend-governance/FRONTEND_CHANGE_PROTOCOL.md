# Frontend Change Protocol

Status: `GOVERNANCE_SPECIFICATION`

## 1. Purpose

This protocol governs Frontend changes from the approved V8 UX semantics through work labelled
Phase 4–7. It controls how a proposed change becomes a new baseline without silently weakening the
approved navigation, interaction, identity, trace, financial-authority, accessibility, responsive,
or six-Scene behavior.

This document is a governance rule. It does not approve a Frontend candidate, authorize a source
change, or redefine the content of a product phase. Phase names are planning metadata; the approved
specifications and baseline manifest remain authoritative.

## 2. Normative terms

### Approved Frontend Baseline

An immutable, independently accepted bundle of:

- Frontend source commit and clean-tree fingerprint;
- built artifact hash and build/toolchain identity;
- explicitly paired HTML/UX Reference version;
- approved product and Frontend/backend contract versions;
- six-Scene acceptance corpus;
- interaction-contract matrix and its complete inventory;
- required regression results, audit report, known limitations, and approval record.

A branch name, working directory, prototype file, screenshot, self-test result, or source SHA alone is
not an Approved Frontend Baseline.

### Frontend Change Request

The reviewed record that states why the baseline may change, what is allowed to change, affected
pages/components/contracts/Scenes, the reference relationship, and the tests required before work
begins. The request is the audit boundary; undeclared material deltas fail the audit.

### Frontend Candidate

One immutable proposed implementation at `candidate_sha`, with a reproducible build fingerprint,
created to satisfy one or more approved Change Requests. It is not a baseline and must not be
described as accepted merely because its own tests pass.

### Delta Audit

An independent, evidence-backed comparison of the Candidate against the immediately previous
Approved Frontend Baseline and the approved Change Request. It verifies both the intended delta and
the absence of undeclared semantic regression.

### New Approved Baseline

The Candidate after all required focused and cross-cutting regressions pass, the independent Delta
Audit returns `PASS`, and the promotion record binds every source, reference, contract, Scene,
interaction, test, and artifact coordinate. Promotion creates a new immutable baseline; it does not
rewrite the old one.

## 3. Required lifecycle

```text
Approved Frontend Baseline
  -> approved Frontend Change Request
  -> immutable Frontend Candidate
  -> Focused Regression
  -> Independent Delta Audit
  -> PASS
  -> New Approved Frontend Baseline
```

The only permitted states are:

```text
DRAFT_CHANGE
CHANGE_APPROVED
CANDIDATE_FROZEN
REGRESSION_RUNNING
READY_FOR_INDEPENDENT_AUDIT
AUDIT_PASS
AUDIT_FAIL
BASELINE_PROMOTED
SUPERSEDED
```

State rules:

1. `DRAFT_CHANGE` cannot authorize implementation or promotion.
2. `CHANGE_APPROVED` fixes scope; later scope growth requires an amended request and renewed review.
3. `CANDIDATE_FROZEN` requires an immutable SHA and a clean or fully fingerprinted tree. A changed
   Candidate is a new audit input and invalidates prior results that are not reproducibly applicable.
4. `READY_FOR_INDEPENDENT_AUDIT` requires all declared regressions to have executed successfully.
5. Only `AUDIT_PASS` may become `BASELINE_PROMOTED`.
6. `AUDIT_FAIL`, `BLOCKED`, `NOT_RUN`, `SKIPPED`, flaky retry-only success, and any qualified-pass
   wording do not permit promotion.
7. A superseded baseline remains retained and addressable for history, rollback, and audit.

## 4. Authority and separation of duties

| Role | Responsibility | Prohibited substitution |
|---|---|---|
| Change owner | authors reason, scope, impact, references, and expected behavior | cannot self-declare audit independence |
| Implementer | builds the Candidate within the approved request | cannot expand scope silently |
| Test owner | executes focused regression and retains raw evidence | cannot turn a failure into a waiver |
| Independent delta auditor | inventories and judges the actual delta | cannot rely only on implementer summaries |
| Baseline approver | promotes a passed Candidate and signs the manifest | cannot promote without independent `PASS` |

The independent auditor must not be the sole author of the material Candidate changes. Tool output
may support the audit, but the named auditor owns the comparison and decision.

## 5. Change types

`change_type` contains one or more of these closed values:

| Type | Meaning | Minimum focused regression |
|---|---|---|
| `UX_VISUAL` | layout, styling, visual hierarchy, typography, color, iconography, or content placement without intended behavior change | affected pages at governed viewports, reference comparison, visual states, responsive checks, accessibility checks |
| `INTERACTION` | control behavior, navigation, focus, state transition, overlay, history, keyboard, or journey changes | affected controls, their interaction-contract rows, positive/negative states, affected journeys, focus/history/keyboard checks |
| `BACKEND_CONTRACT` | HTTP/SSE DTO, status/event mapping, identity, adapter, artifact, error, or availability contract changes | adapter -> projection -> reducer/store -> page chain; contract fixtures; failure/unknown values; affected real-backend gates |
| `PRODUCT_SEMANTIC` | meaning of a Run, Object, Scheme, Task, Claim, Review, A/B/C view, authority boundary, status, or user-visible promise changes | approved Scenario Spec -> contract -> UI -> acceptance chain; all affected Scenes; safe-claim review |
| `ACCESSIBILITY` | semantic structure, name/role/value, focus order, keyboard behavior, announcement, contrast, motion, or assistive-technology behavior | affected components/pages plus keyboard, focus, semantics and automated/manual accessibility checks |
| `RESPONSIVE` | breakpoint, reflow, density, touch-target, overflow, viewport, orientation, or small-screen behavior | affected pages/components at all governed viewport classes plus keyboard/touch and content-loss checks |
| `BUG_FIX` | restores already-approved behavior without intentionally changing the product contract | reproduction test, affected contract/regression, adjacent-state test, and every scope implied by the bug's underlying type |
| `SCENARIO_CHANGE` | modifies Scene setup, data, steps, expected outcome, claim boundary, or evidence | affected Scene end-to-end, cross-cutting gates, Scene-version update, and consistency with related interaction contracts |

Classification rules:

- Use every applicable type. `BUG_FIX` is never a reduced-scope escape hatch.
- Regression scope is the union of all selected types, not the smallest category.
- If a visual change changes discoverability, reading order, control target, state visibility, or user
  interpretation, also classify it as `INTERACTION`, `ACCESSIBILITY`, or `PRODUCT_SEMANTIC`.
- A mock/fixture or Scene expectation change is `SCENARIO_CHANGE`, even when no production source is
  modified.
- A wire-shape rename is `BACKEND_CONTRACT`; if its displayed meaning changes, it is also
  `PRODUCT_SEMANTIC`.
- The independent auditor may add a missing classification. Missing classification is a finding and
  expands, never shrinks, the required regression set.

## 6. Change Request gate

Before implementation, create one record from
`FRONTEND_CHANGE_REQUEST_TEMPLATE.md`. All required fields must be concrete. In particular:

- `previous_baseline_sha` identifies the immediate approved implementation baseline;
- `reference_version` names the UX Reference used to judge the Candidate;
- `affected_pages`, `affected_components`, `affected_contracts`, and `affected_scenes` use explicit
  IDs or paths; use `NONE` only with a written rationale;
- `backend_dependency` names the exact dependency and disposition, not merely `yes`;
- `required_tests` is a list of stable test/gate IDs with environment and oracle;
- all `SCENE-01..06` rows are classified `AFFECTED` or `UNAFFECTED` with rationale;
- the union of baseline and Candidate controls has a planned disposition.

Approval freezes intended behavior, not the implementation technique. Any discovered requirement
that changes intended behavior returns the record to `DRAFT_CHANGE`.

## 7. Candidate gate

A Candidate is eligible for regression only when the evidence pack contains:

1. `change_id` and approved Change Request revision;
2. `previous_baseline_sha` and `candidate_sha`;
3. clean-tree proof, or a deterministic fingerprint of every staged, unstaged, and untracked input;
4. dependency lockfile and toolchain versions;
5. build command, build result, and build artifact SHA-256;
6. HTML/UX Reference ID and content hash;
7. contract, Scene, and interaction-matrix versions;
8. actual changed-file inventory;
9. environment/mode used by each test;
10. disclosure of Demo, fixture, placeholder, unavailable, and real-backend boundaries.

If the SHA, working-tree fingerprint, reference content, dependency graph, generated assets, or test
oracle changes, freeze a new Candidate and identify which evidence must be rerun.

A fully fingerprinted dirty tree may support a pre-audit, but cannot receive a promotion `PASS`.
Material Candidate source must be committed and the final decision audit must run against a clean
tree at `candidate_sha`.

## 8. Regression selection

Focused regression is derived mechanically from:

```text
declared change types
+ affected pages/components/contracts
+ affected Scenes
+ changed control classifications
+ actual diff reachability
+ cross-cutting invariants
= required regression set
```

The Change Request supplies the proposed set. The test owner and independent auditor both verify its
completeness. An undeclared reachable consumer is added to scope and recorded as a request defect.

The following cross-cutting invariants always run for a release Candidate:

- build and typecheck;
- primary navigation and exact Object/Run identity preservation;
- no frontend authority for deterministic financial values;
- A/B/C same-record and Claim Trace identity closure where exposed;
- no Demo/real provenance substitution;
- unknown/error/unavailable state behavior;
- representative accessibility and responsive smoke at every governed viewport class;
- browser console/runtime error check;
- 100% interaction-control classification.

The authoritative Phase 4 integrated Candidate additionally follows
`../integration/PHASE4_E2E_ACCEPTANCE_SPEC.md`; Demo-only results never satisfy its real-backend
variants.

## 9. Six stable Scenes

The acceptance IDs are permanent:

| Scene ID | Stable intent |
|---|---|
| `SCENE-01` | Full Financial Research |
| `SCENE-02` | Dynamic Research Path |
| `SCENE-03` | Self-Correction and Financial Review |
| `SCENE-04` | Claim Trace / Verifiable Research |
| `SCENE-05` | Research Object Accumulation |
| `SCENE-06` | Incremental Returning User |

Every Change Request must classify every Scene. If a Scene is `AFFECTED`, rerun that complete Scene
plus the shared cross-cutting gates. A Scene is affected when its setup, data, step, control,
contract, visual oracle, expected result, provenance, or product claim changes.

Scene IDs are not renamed or recycled. A materially new acceptance story receives a new ID. A
retired Scene remains as a tombstone with its last version, reason, replacement, and approval. A
change to Scene content increments the Scene corpus version and is never hidden inside a fixture
refresh.

## 10. Interaction-contract evolution

The current matrix starts with the 64 stable contracts mapped one-to-one to `P4-E2E-001..064` in
`../integration/PHASE4_E2E_ACCEPTANCE_SPEC.md`. For each Candidate, compare the baseline and
Candidate control inventories and mark every union row exactly one of:

| Disposition | Rule |
|---|---|
| `ADDED` | new exposed control; allocate the next monotonic interaction ID and add an acceptance contract |
| `REMOVED` | baseline control no longer exposed; retain its ID as a tombstone and require product-semantic approval |
| `CHANGED` | same user intent remains but behavior, presentation contract, accessibility, route, state, or backend effect changed; retain its ID and version the row |
| `UNCHANGED` | contract and exposed behavior are unchanged; retain its ID and prove required regression or justified non-reachability |

IDs are never reused or renumbered. DOM nodes are not the inventory unit: one logical control with
responsive renderings is one contract; distinct user intents are distinct contracts.

Two completeness equations must equal 100%:

```text
classified union rows / (baseline rows union candidate rows) = 100%
classified currently exposed Candidate controls / all currently exposed Candidate controls = 100%
```

An `ADDED`, `REMOVED`, or `CHANGED` row requires a Change Request link, expected behavior, affected
Scenes, accessibility behavior, responsive behavior, and test IDs. Any unclassified control fails
the Candidate gate.

## 11. Independent Delta Audit and promotion

The auditor follows `FRONTEND_DELTA_AUDIT_POLICY.md` and returns only `PASS` or `FAIL`. `PASS`
requires:

- exact baseline, Candidate, and reference coordinates;
- all actual deltas declared and authorized;
- required regressions passed on the frozen Candidate;
- all affected Scenes and shared gates passed;
- 100% interaction classification;
- no unresolved severity P0/P1 finding;
- no reference mismatch, evidence gap, skipped required test, or false provenance claim.

After `PASS`, the baseline approver creates the new manifest defined by
`FRONTEND_BASELINE_POLICY.md`. Promotion must not alter the audited Candidate. If it does, the audit
is invalid and must be rerun on the promoted bits.

## 12. Phase 4–7 application

- Every Phase 4–7 Candidate starts from the latest Approved Frontend Baseline, not from an
  unapproved predecessor or an arbitrary prototype.
- Phase work may add contracts and Scenes, but cannot weaken V8 semantics without an explicit
  `PRODUCT_SEMANTIC` Change Request.
- If different roadmap documents use different phase numbering, the Change Request records the
  governing document and version. A phase number alone never defines scope.
- No canonical Phase 7 product definition is assumed by this protocol. When defined, it enters as
  a versioned product/contract input and follows the same gates.
- Multiple approved requests may share one Candidate only when their scopes and test unions are
  recorded. The audit must report each request separately and the combined delta.

## 13. Failure, correction, and rollback

- A failed audit returns the Candidate to implementation; it does not mutate the current baseline.
- Fixes create a new Candidate SHA and a delta from both the approved baseline and the failed
  Candidate.
- An urgent fix uses the same lifecycle. It may reduce unrelated regression only through documented
  risk analysis; it cannot skip independent audit, Scene declaration, interaction inventory, or
  reference binding.
- Rollback selects a previously approved immutable baseline. A new forward change after rollback
  still requires a Change Request and audit.

## 14. Governance readiness

These policies are complete enough to govern a future Candidate. They do not retroactively convert
the V8 remediation Candidate into an Approved Frontend Baseline.

```text
FRONTEND_CHANGE_GOVERNANCE_READY = YES
FRONTEND_CANDIDATE_APPROVED_BY_THIS_DOCUMENT = NO
```
