# Phase 4 Frontend / Browser / Interaction Acceptance Execution Plan

Status: **AUTHORITATIVE ACCEPTANCE DESIGN — NOT IMPLEMENTED — NOT EXECUTED**

Owner: **D5 — Frontend / Browser / Interaction Acceptance**

Scope: future browser execution only; no Frontend, Backend, Playwright, schema, route, migration, or runtime implementation is authorized

```text
PHASE4_BROWSER_ACCEPTANCE_DESIGN_READY=YES
PHASE4_BROWSER_ACCEPTANCE_IMPLEMENTED=NO
PHASE4_BROWSER_ACCEPTANCE_EXECUTED=NO
PHASE4_ACCEPTANCE_IMPLEMENTATION_AUTHORIZED=NO
CURRENT_P4_E2E_NAMESPACE=001..106
CURRENT_INTERACTION_COVERAGE=69/69
HISTORICAL_INTERACTION_UNION=70/70
```

This plan defines how a later, independently governed browser harness must prove the approved
Frontend V8.1 interaction contract and an eventually approved V17 integration delta against one exact
Frontend/Backend candidate pair. It does not turn the current Demo frontend into integrated
evidence, adopt the V17 scaffold as source authority, or guess unfinished Backend contracts.

## 1. Authority and reconciliation

The execution authority, from strongest to weakest, is:

1. the Phase 4 Acceptance Coordinator's activation, result, evidence, and independence rules;
2. approved domain, identity, financial, release, persistence, SSE, and artifact semantics;
3. the final approved Backend Phase 4 contract freeze, when it exists;
4. the approved V8.1 baseline and its append-only E2E/interaction deltas;
5. an approved V17 Frontend Change Request, immutable V17 Candidate, and independent delta audit;
6. suite implementation details.

| Input | Coordinate/state used | Browser disposition |
|---|---|---|
| Approved Frontend V8.1 | `FRONTEND_BASELINE_V8.1`; source `d854c97789c98cca14fee3f4b3d7f00e0d5d137a`; tree `50114fa04c2a0ad81597283f5a487806e2e640cd`; governance carrier `e2aef1edc22631dc988c862c18972f0fd7630625` | Immutable parent and regression authority. The carrier changes governance only; its `apps/web` subtree equals the approved source. |
| V8.1 interaction ledger | `FRONTEND_INTERACTION_CORPUS_V8.1`; 69 current, one tombstone, 70 historical | Current executable interaction denominator and ID authority. |
| V8.1 E2E deltas | authoritative append-only `P4-E2E-101..106` delta on the promotion branch | Supersedes only the old execution treatment of `015` and appends six gates. |
| Existing Phase 4 E2E/Scene/SSE/ID designs | `PHASE4_E2E_ACCEPTANCE_SPEC.md`, activation matrix, browser Scene matrix, `P4-SSE-001..020`, `P4-ID-001..028` | Preserved; this document specifies future browser orchestration and evidence. |
| V17 preparation | `V17_FRONTEND_CONTRACT_PREPARATION.md`, dependency/file/interaction matrices, and draft `FCR_V17_PHASE4_CORE_INTEGRATION.md` | Provisional design input. The Change Request is `DRAFT_CHANGE`; Candidate SHA/build/interaction hashes are pending. |
| Backend drafts | `phase4-core/v1`, `phase4-runtime-event/v1`, and `phase4-identity-error-availability/v1`, inspected against `codex/phase3-contracts@11fe8173a25ff7ac08bae42340ba7c6fae591be5` | Concrete future-test input only. Every draft says `NOT_FINAL`; no browser harness may bake in unresolved fields or codes. |
| Backend acceptance catalogue | `P4-BE-001..030` | Required lower-layer counterparts; browser PASS never substitutes for Backend PASS. |
| V17 reference package | package SHA-256 `b90a356d666c30a07362f080fd418a2cf051c9b80483d308eac474dc51d79f31`; V17 HTML SHA-256 `1cc44c95017b2178e39138b1310e02c55d849dd71af50b63c074686a215ed18d` | Reference input only. Its incomplete/stale manifest must be corrected before Change approval. |

The old parent E2E row `P4-E2E-015` described the obsolete candidate-detail transition. The
approved V8.1 delta is the later authority for lifecycle: the row is retained only as
`RETIRED_TOMBSTONE`, has no result, is never executed, and is never reassigned to clear-search.

## 2. Candidate admission and exact-bit governance

No browser result is admissible until a preflight verifier authenticates one immutable pair:

```text
approved_frontend_parent_id = FRONTEND_BASELINE_V8.1
approved_frontend_parent_sha = d854c97789c98cca14fee3f4b3d7f00e0d5d137a
approved_frontend_change_request_revision
frontend_v17_candidate_sha
frontend_candidate_git_tree
frontend_clean_tree_fingerprint
frontend_package_lock_sha256
frontend_toolchain_identity
frontend_build_artifact_manifest_sha256
approved_v17_reference_manifest_sha256
frontend_scene_corpus_sha256
frontend_interaction_corpus_sha256

approved_phase3_backend_parent_sha
backend_phase4_candidate_sha
backend_candidate_git_tree
backend_clean_tree_fingerprint
backend_build_runtime_hash
database_revision
api_schema_version_and_sha256
event_contract_version_and_sha256
route_version
runtime_mode

browser_name_and_exact_revision
operating_system
locale = zh-CN
timezone = Asia/Shanghai
viewport_and_DPR
acceptance_catalog_and_oracle_hashes
```

The V17 Candidate must originate from a fresh clean source at the approved V8.1 SHA; governance
carrier records may be applied or referenced without changing the parent `apps/web` lineage. Tests
against the current dirty `main`, a branch name without a frozen SHA, a developer server whose
build hash is unknown, or a moving Backend do not produce acceptance results.

The final browser run uses the same `BACKEND_PHASE4_CANDIDATE_SHA` and
`FRONTEND_V17_CANDIDATE_SHA` for every claimed result. Evidence from Frontend B2 may not be combined
with B3, and evidence from Backend A may not be combined with A2. Any source, lockfile, contract,
reference, fixture, generated asset, Scene, interaction ledger, build configuration, or test-oracle
change creates a new Candidate/evidence applicability decision. Source changes always create a new
Candidate.

The preflight fails before test execution when the Change Request is not approved, a tree is dirty,
the build does not reproduce, a contract hash differs, or the interaction/Scene manifest is
incomplete. A failed preflight is retained as an attempt; it is not converted to `SKIPPED`.

## 3. Namespace lifecycle and aggregate denominator

The current authoritative lifecycle is exactly:

| Gate or variant | Lifecycle / activation | Phase 4 Core result treatment |
|---|---|---|
| `P4-E2E-001..014` | active, `PHASE4_CORE_REQUIRED` | `PASS` or `FAIL` |
| `P4-E2E-015` | `RETIRED_TOMBSTONE` | `result=null`; never execute or count |
| `P4-E2E-016..057` | active, `PHASE4_CORE_REQUIRED` | `PASS` or `FAIL` |
| `P4-E2E-058` FULL variant | active, `PHASE4_CORE_REQUIRED` | `PASS` or `FAIL` |
| `P4-E2E-058` INCREMENTAL variant | `PHASE5_ACTIVATED` | `DEFINED_NOT_ACTIVATED`; `result=null` |
| `P4-E2E-059` released Object Core variant | active, `PHASE4_CORE_REQUIRED` | `PASS` or `FAIL` |
| `P4-E2E-059` versioned Research View variant | `PHASE5_ACTIVATED` | `DEFINED_NOT_ACTIVATED`; `result=null` |
| `P4-E2E-060..061` | active, `PHASE4_CORE_REQUIRED` | `PASS` or `FAIL` |
| `P4-E2E-062` | `PHASE5_ACTIVATED` | `DEFINED_NOT_ACTIVATED`; `result=null` |
| `P4-E2E-063..096` | active, `PHASE4_CORE_REQUIRED` | `PASS` or `FAIL` |
| `P4-E2E-097` | `PHASE5_ACTIVATED` | `DEFINED_NOT_ACTIVATED`; `result=null` |
| `P4-E2E-098` | active, `PHASE4_CORE_REQUIRED` | `PASS` or `FAIL` |
| `P4-E2E-099..100` | `DEPLOYMENT_ACTIVATED` | `DEFINED_NOT_ACTIVATED`; `result=null` in Phase 4A |
| `P4-E2E-101..102` | active, `PHASE4_CORE_REQUIRED` | `PASS` or `FAIL` |
| `P4-E2E-103..104` | `PHASE5_ACTIVATED` | `DEFINED_NOT_ACTIVATED`; `result=null` |
| `P4-E2E-105..106` | active, `PHASE4_CORE_REQUIRED` | `PASS` or `FAIL` |

This yields 99 unique Phase 4 Core E2E IDs, four Phase 5-only IDs (`062`, `097`, `103`, `104`),
two deployment-only IDs, and one tombstone. Mixed IDs `058` and `059` have named variants and are
not duplicated in the unique-ID count.

Real `SCENE-01..04` are Phase 4 Core. Real `SCENE-05..06`, `P4-ID-021..022`, versioned Object/View
memory, `ComparisonDataset`, `IncrementalResearchSeed`, Object Writeback, and
Reuse/Refresh/Revalidate/Prevent remain `DEFINED_NOT_ACTIVATED`. Inactive rows do not appear in
PASS, FAIL, BLOCKED, SKIPPED, or denominator counts.

`NOT_IMPLEMENTED` is allowed only as the current design/preparation status. Once a required gate is
activated, absence, blockage, skip, not-run, retry-only success, or qualified success evaluates to
release `FAIL`.

## 4. Source-class and suite separation

Every attempt declares exactly one source class from the Coordinator vocabulary:

| Browser lane | Required source class | Purpose | Forbidden substitution |
|---|---|---|---|
| V8.1/V17 Demo regression | `DEMO_UX_ONLY` | 69 current interaction contracts, six scripted Demo Scenes, reducer/layout/a11y behavior | Cannot pass any real Backend, SSE, persistence, finance, identity, or real Scene gate |
| Deterministic Phase 4 Core | `INTEGRATED` | real Backend HTTP/SSE with controlled durable acceptance records | No frontend fixture, route fulfillment, HAR replay, service-worker response, or Demo store |
| Public supplement | `PUBLIC_REAL` | actual permitted provider/network behavior | No fallback to fixture/cache/Demo while retaining this label |
| Limited-network supplement | `LIMITED_REAL` | frozen limited-mode policy and real integrated UI | No inferred policy or hidden fixture substitution |
| Offline integrated supplement | `OFFLINE_INTEGRATED` | real local Backend/PostgreSQL/SSE with manifested Backend fixtures | Never called LIVE or used as public-provider proof |
| Stream fault lane | `CHAOS_SSE` | real frames through the byte-preserving chaos proxy | Proxy may not fabricate or edit business frames |
| Presenter-only lane | `DEMO_UX_ONLY` | isolated Presenter behavior if/when its reserved delta is approved and enabled | Never part of production navigation or a real Scene aggregate |

Phase 4 Core is not accepted from a LIVE smoke alone. The deterministic integrated corpus must
close all Backend, browser, identity, persistence, release, and artifact oracles. Public, limited,
offline, and Presenter results remain separately labeled and enter an aggregate only under their
own activation rules.

## 5. Future execution topology and order

One acceptance run provisions:

```text
content-addressed Frontend build
  -> browser control context ---------+
  -> browser navigation/negative tabs +--> exact Backend candidate
  -> chaos browser -> frame proxy -----+       -> isolated PostgreSQL
                                               -> isolated artifact store

independent oracle client ------------------> HTTP projections / persisted event ledger
restart supervisor ------------------------> Backend / worker / PostgreSQL lifecycle
evidence collector ------------------------> immutable sanitized evidence bundle
```

The control browser is a comparison witness, not domain truth. The oracle client captures Backend
responses and persisted records before the DOM assertion. No test-only store setter, business-state
button, fake event generator, response fulfillment, or database repair is exposed to the app.

Execution proceeds in this order:

1. authenticate both candidates, manifests, builds, contracts, environment, browser revision, and
   clean trees;
2. run the approved V8.1 reference control and the V17 Candidate `DEMO_UX_ONLY` regression,
   classifying all current interactions and six Demo Scenes separately;
3. scan the production build/module graph and browser startup for Demo/Presenter reachability;
4. seed two distinct authorized Objects A and B plus positive, unavailable, failed, tampered, and
   cross-owned Backend records through reviewed acceptance setup boundaries;
5. execute real `SCENE-01..04`, including the positive and negative paths below;
6. execute `P4-SSE-001..020` through direct/control and chaos lanes as applicable;
7. execute restart/reopen and same-context cross-tab leakage variants;
8. run accessibility, keyboard, navigation, overlay, responsive, console, and runtime-error passes;
9. freeze evidence, calculate all gate results, and hand the bundle to an independent auditor.

One journey may provide evidence for multiple mapped gates only when the evidence manifest names
every oracle independently. Passing one gate never automatically marks another gate PASS.

Every activated real Scene ends with a non-empty `(objectId O, runId R, taskId T, claimId C,
reviewId V, artifactId A)` tuple captured from Backend responses. Claim Trace and release closure
also capture Calculation K, Evidence E, Proof/verification where required, canonical/execution X,
and released result L. Display text, ID prefixes, array positions, or current/latest state cannot
select any member of the tuple.

## 6. Real Scene execution

### SCENE-01 — Full Financial Research

Use Object A and FULL mode. Select/create A from authoritative Object responses, enter a goal,
prepare a backend-authored `SCHEME_ONLY` draft, regenerate once, and prove that no Run, Task, or
graph exists before confirm. Double-click confirm, lose the first response, retry the same body/key,
and repeat after Backend restart. Capture one Run R, one planned graph, one scheduler admission,
one `run.created`, and one `run.started`.

Observe R through actual HTTP and SSE to terminal release. Assert the immutable Initial Plan,
authoritative Actual Path, exact Tasks, review/proof/release ordering, and final projection. Open one
released financial metric and compare the DOM to the captured Backend metric/Claim. Open Report A,
Financial Review B, and Execution C and prove one Object/Run/canonical record. Verify authorized
HTML bytes and a separately identified PDF representation. The corpus must exercise both PDF
AVAILABLE and explicit PDF non-available behavior; PDF optionality for one release never permits
HTML/PDF identity merging or Demo fallback.

Positive outcome is a released, identity-closed, integrity-valid result. Negative variants cover
expired/mismatched draft, different request under the same idempotency key, Review/Proof/material
output failure, unavailable artifact representation, cross-owned Claim/artifact, and unknown schema.
Restart variants cover confirmation, nonterminal SSE, terminal reopen, Review, A/B/C, artifact
metadata/bytes, and terminal cursor.

Primary mapping: `P4-E2E-004..028`, `040..047`, `065..076`, `083`, `085`, `092..096`, `098`,
`101..102`, `105..106`; `P4-BE-002..010`, `015`, `017..030`; applicable
`P4-SSE-001..019`; `P4-ID-001..020`, `023..028`.

### SCENE-02 — Dynamic Research Path

Capture planned graph P before runtime. The real Backend's approved replan—not the Demo peer story—
chooses the mutation. Assert `replan.requested` and `replan.approved` identity, one backend-added
Task, exact edge changes, one graph-version increment, and an unchanged P. Sparse graph events
trigger atomic projection refresh; they never let the browser invent a Task label, dependency,
agent, skill, or status.

Open every trigger/added/affected Task by exact ID. Disconnect between graph frames, refresh after
the add and before version publication, inject only permitted delay/reorder/duplicate behavior, and
prove final convergence to the authoritative graph with one added Task and one mutation history
entry. Continue the same Run to a released identity tuple.

Negative variants reject unknown mutation types, cross-Run Task references, cycles, duplicate Task
IDs, graph version regression, and Demo labels applied to different Backend facts. Restart preserves
P and reconstructs the exact actual graph/version from persistence.

Primary mapping: `P4-E2E-029..036`, `063`, `065..073`, `076..089`, `092..096`, `098`;
`P4-BE-007..019`, `020..030`; `P4-SSE-002..014`, `015`, `017..020`;
`P4-ID-001`, `004`, `006..020`, `023..028`.

### SCENE-03 — Self-Correction and Financial Review

Capture a financial Task T and mismatched Evidence candidates. Observe
`task.self_correcting` followed by `task.correction_resolved` on the same T; the graph Task count and
version do not change. The rejected Calculation is not released. The corrected Calculation K uses
the exact period-aligned Evidence set, and the exact Backend Review/check covers the Claim and K.

Exercise Complete/Exception and All/Open/Resolved filters. Visible rows and counts must derive from
the same Review/correction projection; `review.resolved` is not reinterpreted as a single repaired
exception. Refresh while the correction timeline is focused, then finish the release and close
A/B/C identity.

The release-negative variant deliberately leaves Review at REVIEW/BLOCK or produces a semantic
mismatch. Results and downloads remain unavailable and the Run terminates safely; the frontend
cannot repair or promote it. Restart preserves the correction/check identities and resolved/open
history.

Primary mapping: `P4-E2E-034`, `040..043`, `063`, `065..073`, `076..090`, `092..095`, `098`;
`P4-BE-007..010`, `015..024`, `028..030`; applicable `P4-SSE-001..018`;
`P4-ID-001`, `004`, `006..020`, `023..028`.

### SCENE-04 — Claim Trace / Verifiable Research

Before clicking, capture one released metric M and exact C/K/T/E/V/X/A relations from Backend
records. Execute this exact path:

```text
Report metric/anchor
  -> Claim C
  -> exact Review V and check
  -> Task T derived through K.task_id
  -> Calculation K
  -> every Evidence E in the authoritative support/input set
  -> Proof/verification when policy requires
  -> exact Execution/CER X row
  -> original Report anchor for C
```

At every transition assert O/R/T/C/V/A/K/E/X before following the next action. Exercise nested
drawers, X/footer/Escape close, two Back/Forward transitions, hard refresh with the Claim drawer
open, unavailable retained detail, exact highlight/focus, and underlying scroll restoration.

Repeat with Claim B under Run A, Artifact B under Run A, historical C under a newer same-Object Run,
and missing C/K/E. Each fails closed with no latest/first/title/symbol/metric-name fallback and no B
sentinel in A's DOM, accessibility tree, or retained store.

Primary mapping: `P4-E2E-042..055`, `063`, `065..073`, `087..088`, `092..096`, `098`,
`105..106`; `P4-BE-007`, `009..010`, `017`, `020..030`; `P4-SSE-013..014`, `017`;
`P4-ID-001`, `006`, `011..020`, `023..028`.

### Inactive real Scenes and Demo compatibility

Real `SCENE-05` and `SCENE-06` are recorded exactly as:

```json
{"activation_state":"DEFINED_NOT_ACTIVATED","result":null}
```

They are not run as real Backend scenarios and do not fail Phase 4 Core. Their shared pages may run
Core Released Object regressions, and their frozen Demo stories may run in `DEMO_UX_ONLY` solely to
prove V8.1 compatibility. Interaction `067`'s no-authoritative-source disabled reason may be checked
as auxiliary Phase 4 UX evidence, but `P4-E2E-103` receives no integrated result. Interaction `068`
and `P4-E2E-104` likewise remain inactive for real Incremental behavior.

No Phase 4 UI or evidence may claim `ResearchObjectVersion`, `ResearchViewVersion`, Research Memory,
ComparisonDataset, IncrementalResearchSeed, reuse/refresh/revalidate/prevent, Claim Diff, or Object
Writeback as real.

## 7. Complete V8.1 interaction regression

The Candidate interaction inventory is counted by handler-equivalent user intent, not by DOM-node
count. Repeated renderings of the same action remain one interaction; static projection content is
not a control. The future machine inventory binds each row to page/component, accessible name/role,
route/backend effect, focus/history behavior, responsive rendering, Scene, activation, and test ID.

The following disjoint ranges cover all 69 current interactions and the one historical tombstone:

| Interaction IDs | V17 impact expected by the current draft | Required Candidate regression | E2E mapping |
|---|---|---|---|
| `001` | unchanged | New Task primary navigation, one selected item, route/history | `001` |
| `002..003` | changed | Runs/Objects navigation loads authoritative collections with loading/empty/error/retry | `002..003`, `065..067` cross-cutting |
| `004` | unchanged | new-run CTA opens Object-first wizard without mutation | `004` |
| `005..007` | changed | live/completed/nonterminal cards open exact Run/status/result/action without fallback | `005..007`, `070..076` |
| `008` | unchanged | create modal opens accessibly and performs no POST | `008` |
| `009` | changed | exact authoritative Object selection and goal binding | `009` |
| `010..011` | unchanged | backdrop/X close top modal and restore focus without mutation | `010..011` |
| `012..013` | changed | real search loading/result/none/error and exact candidate identity | `012..013`, `067` |
| `014` | unchanged | cancel closes with zero create requests | `014` |
| `015` | tombstone | no control exists; inventory proves ID is not reused | `015`, `RETIRED_TOMBSTONE` |
| `016` | changed | idempotent exact Object creation | `016`, `067` |
| `017..022` | unchanged | goal templates/custom text/back retain exact Object and entered text | `017..022` |
| `023..025` | changed | validation, honest prepare/regenerate, durable exactly-once confirm/start | `023..025`, `074..075` |
| `026..036` | changed | lifecycle, steps, tabs, planned/actual/compare, mutations and Tasks from authoritative projection | `026..036`, `076..091` |
| `037..039` | unchanged | Task drawer X/footer/Escape, topmost close and exact focus restoration | `037..039` |
| `040..043` | changed | Review mode/filters/counts and exact Claim/Task/check relations | `040..043`, `092..095` |
| `044` | unchanged | Results back-to-Run returns exact Run and creates history transition | `044` |
| `045..054` | changed | artifacts, A/B/C, Claim/Review/Task/Evidence/Calculation/Execution actions retain exact canonical IDs and availability | `045..054`, `072`, `092..096` |
| `055..056` | unchanged | Claim close restores origin; Objects create CTA preserves return route | `055..056` |
| `057..063` | changed | exact Object Core, FULL entry, tabs/latest/history, Phase 5 boundary, URL/history/refresh | `057..063`, `070..076`, `097..098` by activation |
| `064` | unchanged | actionable breadcrumb versus non-control context | `064` |
| `065` | changed | clear search clears query/results/selection/status and sends no create request | `101` |
| `066` | changed | FULL selected programmatically; same Object/FULL prepare-confirm; no inferred source | `102` |
| `067` | changed | Incremental selectable only with authoritative same-Object released source; otherwise adjacent/programmatic disabled reason | `103`, real gate Phase 5 |
| `068` | unchanged | only real Incremental Task projection is interactive; memory/comparison/result milestones stay static | `104`, real gate Phase 5 |
| `069` | changed | retry repeats exact authoritative read, shows busy, retains route/entity, never substitutes Demo | `105` |
| `070` | unchanged | dismiss removes only current alert; no network/domain/navigation effect | `106` |

The expected V17 disposition is 21 unchanged and 48 changed current rows. Candidate freeze must
derive these counts from actual reachability rather than accepting the draft table by assertion.
Every changed row runs old non-superseded behavior plus its new Backend/negative behavior. All 69
current rows run in the Candidate's `DEMO_UX_ONLY` regression; all Core-real rows also run against
the integrated Backend where the control is present.

Required completeness equations are:

```text
current active = 001..014 + 016..070 = 69
current classified and tested = 69/69 = 100%
retired tombstones = 015 = 1
historical union classified = 70/70 = 100%
```

An absent, duplicated, unclassified, silently merged, or newly exposed ungoverned control fails the
Candidate interaction audit.

## 8. V17 interaction-delta governance

The current authoritative E2E namespace ends at `106`. The draft V17 Change Request and interaction
impact matrix reserve the following identifiers but do not yet activate or freeze them:

| Reserved interaction/gate | Draft intent | Draft activation and required future browser behavior |
|---|---|---|
| `071` / `P4-E2E-107` | Execution actor-type filter | Proposed Core. Filter only authorized rows from the same O/R/X; programmatic selected state, keyboard operation, announced empty state, no domain mutation, no hidden/raw-field search. |
| `072` / `P4-E2E-108` | Execution safe free-text search | Proposed Core. Search allowlisted normalized fields only; clearable labeled input, live count, focus retained, safe unsupported-query failure, no identity/canonical change. |
| `073` / `P4-E2E-109` | Presenter Scene selector | Proposed Demo-only/deployment activation. Select only a manifested Demo Scene with visible Demo provenance and zero production-state effect. |
| `074` / `P4-E2E-110` | Presenter reset | Proposed Demo-only. Reset isolated presentation state with zero Backend mutation/request. |
| `075` / `P4-E2E-111` | Presenter previous | Proposed Demo-only. Move one step; first boundary is disabled/no-op and programmatically clear. |
| `076` / `P4-E2E-112` | Presenter next | Proposed Demo-only. Move one step; final boundary is disabled/no-op and programmatically clear. |

These are reservations, not part of the current `P4-E2E-001..106` result matrix. Before execution,
an approved append-only E2E delta must freeze their text, activation, mappings, inventories, and
evidence. It must not modify `001..106` or consume tombstone `015`. If actual V17 implementation
adds, removes, combines, or changes any intent, amend and approve the Change Request before Candidate
freeze; allocate the next monotonic ID after the approved reservations. Do not fold a distinct
handler/effect into an existing row to preserve a preferred count.

If the reservations are approved unchanged, expected inventories become 71/71 in production
default, 75/75 in Presenter-enabled Demo, and 76/76 for the all-mode historical union including
`015`. Until then, the only authoritative completeness claim remains 69/69 current and 70/70
historical.

## 9. Navigation, deep-link, history, focus, scroll, and overlay execution

### Route and subscription oracle

The V8.1 route contract preserves `/new`, `/runs`, `/objects`, `/objects/{objectId}`, and
`/runs/{runId}` with Results and exact context carried by reviewed URL fields for tab, Claim,
report anchor, Task, Task anchor, origin, Object, and mode. A V17 route change requires an approved
delta; it may not remove exact entity/context restoration.

For each page family, direct-load a valid URL, a missing URL, an Object-B/Run-A mixed URL, and a
terminal URL in a clean browser context. On valid routes the URL IDs, Backend records, observable
DOM IDs, heading/context, and active subscription agree. On invalid/mixed routes the UI shows a safe
unavailable/not-found state and keeps the requested identity; it does not redirect to latest or
first. Back/Forward never sends a mutation request, and navigation to another Run aborts the old
subscription before the new one can affect the page.

### Focus and keyboard oracle

For every affected control, record accessible role/name/value/description, focus before action,
focus after action, and keyboard/pointer equivalence. Required behaviors include:

- modal initial focus enters the intended search/action control;
- Tab/Shift+Tab remain within the topmost modal/drawer;
- background and any covered overlay are inert;
- Escape closes only the topmost surface;
- X, footer close, backdrop where allowed, Escape, and Browser Back restore the exact invoking
  control when it still exists, with a deterministic reviewed fallback only when the caller was
  legitimately removed;
- Results/Object/Path tabs expose linked tab/tabpanel semantics and roving ArrowLeft/ArrowRight;
- selection controls expose selected/pressed state; progress exposes the Backend value;
- loading/reconnecting uses status semantics without alert storms; actionable errors use alert
  semantics; empty/filter counts and search state are announced;
- disabled Incremental/PDF/anchor actions have visible and programmatic reasons and produce no
  request or state change.

Automated accessibility scans supplement, but do not replace, the keyboard/focus scripts. A scan
PASS cannot excuse wrong entity focus, unreachable controls, or a broken close/return journey.

### Scroll and highlight oracle

Capture `scrollY`, scrolling-element dimensions, focused element identity, and target bounding box
at each transition. Primary page navigation starts at top. Opening/closing an overlay preserves the
underlying scroll. Browser pop restores the recorded page scroll. Claim Trace locate actions scroll
the exact same-Run anchor into view, focus it, and apply the transient highlight without changing
identity. Refresh and Back/Forward reproduce the same anchor from Backend data and URL state.

### Overlay oracle

For create modal, Claim drawer, Task drawer, and unavailable Evidence/Calculation panels verify:

- exactly one top surface has `role=dialog` and `aria-modal=true`;
- the surface has an accessible name; the document root/background is inert;
- body scroll is locked while any overlay is open and restored only after the stack empties;
- a stacked child makes its parent inert, and closing the child reactivates the parent;
- backdrop clicks affect only the topmost permitted modal;
- no hidden/covered control receives pointer or keyboard activation;
- route commit, refresh, and history close/reopen paths do not leak inertness, scroll lock, focus
  sentinels, or duplicate overlays.

These checks principally close `P4-E2E-010..011`, `037..039`, `044`, `047..055`, `063..064`,
`105..106`, `P4-ID-020`, `023..027`, and `P4-SSE-014`, `017` where navigation changes a stream.

## 10. Page/state browser matrix

Every Phase 4 page is exercised in content, loading, empty, error/unavailable, and relevant overlay
or terminal states. The matrix is distributed across Scenes but the evidence index must prove every
cell was run.

| Surface | Positive browser oracle | Negative browser oracle | Refresh/restart oracle |
|---|---|---|---|
| New Task / Object modal | exact Object, clear-search, goal, FULL, Scheme-only preview, regeneration, one confirm/start | invalid/no-result search, missing Object, cross-owned Object, stale/expired draft, changed key body, Incremental disabled, zero mutation on cancel/clear | draft and idempotency outcome survive Backend restart; ambiguous retry uses same body/key |
| Runs | stable global ordering/filter/cursor, live/completed/nonterminal cards, exact status/progress/activity | malformed/filter-mismatched cursor, unknown enum, unauthorized row, empty collection, failed retry with no Demo data | list/detail remain consistent after hard refresh and Backend restart |
| Run Plan/Workspace | snapshot cursor, immutable plan, authoritative actual graph, Task drawers, correction/capability/review state | sparse/unknown/cross-Run event, gap/order error, Task mismatch, failed Run cannot expose Results | resume from exact cursor; one active subscription; reconstructed graph/Tasks equal fresh projection |
| Results A/B/C | one O/R/X; Backend metric display; exact Review/Execution; release-only availability | nonreleased/failed Run, mismatched canonical ID, unavailable detail, no hidden reasoning/raw stringify | selected tab/Claim/anchor and exact records rebuild from persistence |
| Claim Trace | exact C→V→T→K/E→Proof→X→report anchor and nested return | missing and cross-owned C/T/V/K/E/A, unavailable retained body, no title/latest fallback | route/focus/scroll/highlight restore after refresh, Back/Forward, Backend restart |
| Artifacts | distinct HTML/PDF slots; authorized bytes match metadata; cooldown prevents duplicate user action | unavailable slot disabled, wrong owner/media/size/hash/authorization yields zero bytes and no Demo fallback | reauthorize exact artifact after restart; immutable ID/hash/bytes stay equal |
| Objects / Object detail | exact collection/detail, released Core, object-scoped Run history, exact historical row, one `latest_released_run_id`, FULL entry | symbol/name/latest-global fallback, newer nonreleased Run replacing release, Phase 5 views claiming real data | Object/Run/result/artifact links survive new context and Backend restart |
| Alerts | retry repeats exact read with busy state and route identity; dismiss changes presentation only | repeated failure remains safe/stale; retry/dismiss cannot mutate domain or navigate/substitute | after Backend recovery, retry loads the same requested entity; refresh never resurrects dismissed error as domain truth |

## 11. SSE behavior visible through the browser

The D2 chaos plan owns stream mechanics; D5 owns the user-visible and navigation-facing oracle. All
twenty SSE gates are exercised through the production transport against actual Backend SSE:

| SSE coverage | Browser-visible execution |
|---|---|
| `P4-SSE-001..005` | Prove actual `text/event-stream`, exact R, valid named frames, contiguous producer order, unique opaque IDs, and heartbeat with zero domain/UI mutation. |
| `P4-SSE-006..009` | Disconnect after committed N; retain state and show reconnecting/stale; numeric resume sends N, opaque resume yields the same suffix, and final committed range has no gap. |
| `P4-SSE-010..012` | Duplicate causes no second visible entity/timeline row; delayed/out-of-order/gap is quarantined; snapshot race applies every post-watermark fact once and converges. |
| `P4-SSE-013..014` | Hard refresh and Run→other route→Back install exact snapshot, close stale subscription, open exactly one restored subscription, and converge without mutation. |
| `P4-SSE-015..017` | Success closes only after release then `run.completed`; failure closes on `run.failed` with Results disabled; terminal refresh/new context does not reconnect forever. |
| `P4-SSE-018` | Negative, signed/noncanonical, unknown opaque, other-Run opaque, and ahead cursors fail before stream headers under the frozen code; no replay-from-zero or foreign disclosure. |
| `P4-SSE-019` | Disconnect within capability validation; resume preserves same T and exact gap/build/approval/registration/resume order with no graph Task addition. |
| `P4-SSE-020` | Disconnect between graph frames/version; stale is allowed temporarily, but one atomic projection refresh yields one graph version and no fabricated Task. |

The chaos proxy may only drop, delay, duplicate, reorder, or disconnect after complete real frames.
Every delivered frame hash must match an upstream frame hash from the same Run. The final browser
projection is compared with a fresh Backend snapshot and persisted event ledger, not with another
browser as the sole oracle.

## 12. Responsive and visual execution

The mandatory V8.1 desktop matrix is Chrome/Chromium at CSS widths
`1024, 1280, 1366, 1440, 1920`, height `900`, DPR `1`, zoom `100%`, landscape, with the exact browser
revision bound in the Candidate manifest. The primary integrated Scene pass runs at `1366x900`.

All six page families—New Task, Runs, Objects, Object detail, Run Workspace, and Results—render at
all five widths. For every V17-affected page/state, capture the densest content state; loading,
empty, error/unavailable, long safe text, filter-empty, reconnecting, and overlay states are
distributed so every state appears at each affected breakpoint class. At 1024, additionally run
full keyboard journeys with the Task/Claim overlay stack. Later approved V17 viewports are added;
they never replace these inherited widths silently.

The machine assertions are:

- no document-level horizontal overflow and no clipped/unreachable action;
- intentional local graph/table scrolling is bounded to its named region and does not hide focus;
- metadata, identity, availability, disabled reason, tabs, alerts, downloads, and breadcrumbs do
  not disappear to make layout pass;
- DOM/accessible reading order remains logical after visual reflow;
- focused controls and exact trace targets are visible and not covered by sticky/overlay elements;
- dialog/drawer fits the viewport, traps focus, and preserves a usable close action;
- long IDs, company names, safe errors, percentages, and timestamps wrap without changing text;
- touch/click targets and spacing remain operable at every governed width.

Reference comparison is three-way: approved V8.1 reference → approved V17 visual delta → actual
Candidate. Global pixel equality is not required for an approved visual delta, but every changed
region must be declared and every unchanged semantic/control region must remain equivalent. A
pixel threshold cannot hide missing text, identity, status, control, focus indicator, or overflow.

## 13. Console, runtime, network, and production-isolation execution

Install collectors before the first application script executes. Retain console messages,
`pageerror`, unhandled rejection, request failure, HTTP response status/content type, navigation,
download, worker/service-worker registration, and unexpected popup records.

An activated test fails on any application exception, unhandled rejection, React warning, schema or
identity validation error not intentionally under test, unexpected request failure/status, wrong
content type, infinite reconnect, duplicate mutation, or unexpected console warning/error.
Expected negative HTTP responses and intentional chaos disconnects must match the exact case ledger
and must not emit application errors. The inherited V8.1 favicon 404 is not a blanket allowlist: it
may be recorded as the exact non-application known limitation only if the approved V17 Change
Request retains it; any different URL/status/source fails.

For public/limited production composition, fail if any request is fulfilled by the harness, a
service worker/HAR/static JSON supplies domain state, or a frontend fixture/Demo ID/data URL appears
in a response-to-DOM chain. Scan source and the built module graph for reachable
`DemoFrontendDataSource`, `DemoRuntimeTransport`, Demo stores/scenarios, `RUN-DEMO`, hard-coded
financial values, data-URL artifacts, Presenter code, raw internal artifact paths, or frontend
financial formula implementations.

Then force every principal read to fail once. The UI must remain explicit loading/stale/error or
unavailable, preserve route/entity identity, and expose retry where authorized. It must not switch
to NVIDIA/NVDA, Object A/B's neighbor, a Demo Run, cached frontend fixture, local report, or local
financial value. This negative proves no-Demo substitution more strongly than bundle scanning
alone.

Execution C may render only allowlisted observable facts. Search/filter tests and DOM/console
snapshots must never reveal prompts, raw completions, scratch state, hidden Chain-of-Thought,
provider bodies, secrets, internal paths, or raw arbitrary input/output serialization.

## 14. Presenter isolation

Presenter is not production navigation. The production-default build has
`VITE_ENABLE_PRESENTER=false`, exposes no Presenter control/route, imports no reachable Presenter or
Demo authority module, and cannot be activated by query string, local storage, URL, runtime response,
or browser devtools state. The module-graph scan and an attempted deep link prove this negative.

If the reserved Presenter delta is later approved, run a separately hashed Presenter-enabled Demo
build under `DEMO_UX_ONLY`. Exercise Scene selector, reset, previous, and next with boundary disabled
states, visible Demo provenance, deterministic step state, keyboard/accessibility, and governed
widths. Record zero production Backend mutation and zero ability to replace the integrated store,
route, candidate result, or source class. Presenter gates/results never enter
`PHASE4_CORE_E2E_RESULT` and cannot prove real Scenes 01–06.

## 15. Restart, reopen, and shared-state matrix

The future suite executes each row against the exact persisted database/artifact volume without
rebuilding either candidate:

| Restart/reopen point | Required result |
|---|---|
| lost confirm response, same browser | same key/body returns same R; one draft consumption, Run, graph, scheduler admission, `run.created`, `run.started` |
| Backend/worker restart after confirm commit | pending admission starts once or acknowledged admission does not restart; UI reopens exact R |
| Backend restart during nonterminal SSE at N | UI remains stale/reconnecting, resumes after the committed cursor, and converges without reset/duplicate |
| PostgreSQL restart during a recoverable stream | same durable event log/tail and snapshot identities return; no in-memory success can substitute |
| hard browser refresh at nonterminal N | fresh atomic snapshot/cursor plus SSE suffix equals uninterrupted Backend state |
| Run→other page/Run→Back/Forward | old subscription is closed, exact route/scroll/focus and one correct subscription restore, no mutation repeats |
| new browser context after success terminal | Object, Run, Review, A/B/C, proof state, artifact metadata/authorized bytes, and terminal cursor reopen from Backend persistence |
| new browser context after failure terminal | FAILED and safe reason persist; A/B/C/downloads remain unavailable; no success tail or reconnect loop |
| same browser context, simultaneous A and B tabs | each tab retains its tuple/subscription; navigation or retry in B cannot switch A's shared state |
| Backend restart with missing/cross-owned URL | remains not-found/unavailable; restart never repairs to latest/first/title/symbol/metric-name match |

`P4-E2E-098`, `P4-BE-004..017`, `P4-BE-022..030`, `P4-SSE-007..009`, `013..017`, and
`P4-ID-005`, `009`, `020`, `023..027` receive the applicable evidence. Restart success is not
proved by retained browser memory: storage is cleared or a new context is used where specified.

## 16. Backend/SSE/identity crosswalk for browser evidence

This table references, but does not redefine, the authoritative catalogues. Every `P4-BE-001..030`,
`P4-SSE-001..020`, and `P4-ID-001..028` is represented.

| Browser capability | P4-BE | P4-E2E | P4-SSE | P4-ID | Principal browser evidence |
|---|---|---|---|---|---|
| Runs collection/list-detail | `001`, `010` | `002`, `005..007`, `076`, `105` | — | `001`, `006`, `023`, `025..027` | HTTP collection/detail ledger, order/cursor, exact card/route DOM, retry trace |
| Prepare/Scheme/FULL | `002..003` | `017..024`, `074`, `101..102` | — | `002..004`, `027` | request/draft hashes, no-Run counts, Scheme DOM/accessibility snapshot, regeneration diff |
| Confirm/exactly-one/auto-start | `004..006` | `025..026`, `075`, `098` | `001..004`, `015..017` as lifecycle evidence | `004..005`, `007..009`, `023`, `026..027` | click/network ledger, one outcome/Run/admission, response-loss and restart trace |
| Atomic projection/revision/list consistency | `007..010` | `005..007`, `026..043`, `060..061`, `076..089`, `098`, `105` | `012..014`, `017`, `020` | `001`, `004`, `006..020`, `023..027` | projection/ETag hashes, DOM normalized diff, route/entity IDs, restart response |
| Cursor/replay/terminal durability | `011..017` | `063`, `073`, `078..087`, `098` | `006..018` | `005`, `009`, `017..019`, `023..027` | connection headers, frame ledger, terminal order/count, close/no-reconnect, DB restart |
| Event normalization/graph recovery | `018..019` | `026..036`, `068`, `077`, `082..091` | `002..005`, `010..013`, `015..016`, `019..020` | `007..010`, `023`, `027` | parsed envelope, quarantine/reconcile trace, exact graph/Task/timeline cardinalities |
| Lossless finance/ratio semantics | `020..021` | `069`, `092..095` | — | `011..020`, `028` | captured metric/Claim tuple, visible accessible text, bundle/source authority scan |
| Claim/Review/Trace/A-B-C | `022..024` | `040..055`, `063`, `072..073`, `090`, `092..095`, `098` | `013..014`, `017` for reopen | `011..020`, `023..028` | exact route/anchor/focus chain, Review/check and canonical joins, unavailable/cross-owned negatives |
| Artifact metadata/content/integrity | `025..027` | `045..046`, `072..073`, `096`, `098` | — | `019..020`, `023`, `025..027` | representation DTO, authorized response, bytes, content type/length, recomputed SHA-256 |
| Released Object Core/latest/rejection | `028..030` | `003`, `057`, Core `059`, `060..061`, `063`, `070..073`, `076`, `094`, `096`, `098`, `105` | `003`, `018` where stream/cursor identity applies | `001`, `006`, `018..020`, `023..028` | Object/Run/Result join, historical/latest route trace, A/B sentinel scans and zero-byte denials |
| Complete stream lifecycle | supporting `006..019`, `030` | `063`, `068`, `077..091`, `098` | `001..020` | `007..010`, `023..027` | direct/control/chaos frame hashes and final Backend/browser convergence |
| Phase 5 identity boundary | future Backend gates only after freeze | `058` Incremental, `059` versioned, `062`, `097`, `103..104` | future regression only after activation | `021..022` | `DEFINED_NOT_ACTIVATED`, `result=null`; Demo/disabled evidence stored separately |

The mandatory financial witness is:

```text
Backend canonical_value = "0.6547"
Backend canonical_unit  = "RATIO"
Backend display_value   = "65.47"
Backend display_unit    = "%"
Browser visible         = "65.47%"
```

`0.6547%`, unlabelled `0.6547`, client multiplication, a component-to-component copy without a
Backend record, or any frontend financial calculation fails the affected gates.

## 17. Evidence package and browser PASS/FAIL oracle

Each browser attempt contributes content-addressed records to
`PHASE4_ACCEPTANCE_EVIDENCE_MANIFEST_SPEC.md`:

- exact candidate pair, clean-tree witnesses, build/module manifests, contract/database versions,
  browser/environment identity, source class, Scene and interaction corpus hashes;
- HTTP request ledger with method, reviewed URL template, status/content type, safe request ID,
  requested and returned entity IDs, sanitized semantic fields, and response hash;
- SSE connection/frame/apply ledgers, complete-frame hashes, cursor headers, chaos parentage,
  projection snapshots, convergence diff, and terminal/restart records;
- semantic DOM and accessibility snapshots, control inventory, accessible name/role/value,
  focus/scroll/overlay/history logs, responsive assertions/screenshots, and browser traces;
- artifact group metadata, authorization result, exact downloaded bytes under controlled evidence
  storage, recomputed byte length/hash/media type, and HTML/PDF identity comparison;
- console/page/unhandled/network records, production module-graph/Demo reachability scan, and
  expected-negative allowlist tied to exact test cases;
- append-only failed-attempt records containing attempt ID, candidate SHAs, environment, timestamp,
  failure, rerun reason, whether source changed, and final disposition.

Screenshots and another DOM component are supporting evidence only. The authoritative browser
oracle is captured Backend state joined to visible/accessibility state and, for artifacts, the
authorized bytes.

An activated browser gate is `PASS` only when its positive, required negative, identity,
availability/error, restart/reopen where applicable, evidence-integrity, and source-class assertions
all pass on the exact manifested pair. It is `FAIL` for wrong/missing data, fallback, cross-object
content, unauthorized bytes, unknown contract guessed as known, an unexpected console/runtime
error, missing evidence, or a required unexecuted variant.

Retries never erase failures. A deterministic failure on unchanged source remains evidence unless
an independently demonstrated environmental defect invalidates that attempt. A source change makes
the rerun a new Candidate. There is no `PASS_WITH_WARNING`, `MOSTLY_PASS`, or conditional release
PASS.

## 18. Independent audit handoff

Implementation teams may run this plan for self-test but may not declare final acceptance. The
independent auditor authenticates the exact candidates and manifests, verifies applicability and
all denominators, inspects raw ledgers, reruns the critical real Scenes and cross-object/SSE/restart/
financial/artifact paths, verifies 69/69 interaction classification, and checks that no Demo or
Presenter evidence entered an integrated result.

The browser portion can contribute `PASS` to Phase 4 Core only when:

```text
all 99 unique Phase 4 Core P4-E2E gates pass
AND real SCENE-01..04 pass
AND P4-SSE-001..020 pass
AND Core P4-ID-001..020 and 023..028 pass
AND current interaction regression is 69/69
AND real SCENE-05..06 and all other inactive rows retain result=null
AND P4-E2E-015 retains result=null
AND no Demo/Presenter substitution is present
AND browser evidence is complete and candidate-bound
AND independent audit returns PASS
```

## 19. Open execution blockers and stop condition

This D5 design does not create a second conflict register. The Coordinator package's 18 `UAC-*`
rows remain the canonical unresolved semantic-conflict count. The browser-reachable blockers are:

| Existing owner | Browser impact |
|---|---|
| `UAC-001`, `BD-001..012`, `P4-BLOCKER-01..08` | Backend contract family and implementation are not final; all integrated lanes remain unexecutable. |
| `UAC-003`, `010`, `018` | version negotiation, total enum/payload/error maps, and safe negative status behavior cannot be guessed. |
| `UAC-004`, `008..011` | cursor-ahead, projection revision/sequence, atomic publication, and all-path terminal behavior block authoritative refresh/restart/SSE oracles. |
| `UAC-005..007` | replay metadata, actor/tenant scope, durable idempotency/admission and one-start accounting block confirm acceptance. |
| `UAC-012..017` | Claim/Review/check/anchor/artifact/latest-release wire authority is not frozen; Trace, A/B/C, artifact, and release browser cases cannot execute. |
| Draft V17 governance | Change Request is not approved, Candidate is absent, reference manifest is defective, and `P4-E2E-107..112` are reservations rather than an approved append-only delta. |
| PDF corpus decision | Backend draft makes PDF an independent optional slot, while an older Scene wording expects two AVAILABLE downloads. Execution must include available-PDF and unavailable-PDF corpora, and the final freeze must state which is required for the Scene versus release. |
| Progress vocabulary | current V17 preparation and Backend draft use differing progress-method tokens; browser asserts the final frozen method and never hard-codes either draft token. |

The last two rows are browser views of existing `UAC-008`, `016`, and `017`, not additional package
conflicts. Therefore:

```text
P4_BE_GATES_REFERENCED=30/30
P4_E2E_GATES_REFERENCED=106/106
P4_SSE_GATES_REFERENCED=20/20
P4_ID_ASSERTIONS_REFERENCED=28/28
SCENE_01_04_COVERAGE=4/4
SCENE_05_06_STATE=DEFINED_NOT_ACTIVATED
INTERACTION_CURRENT_COVERAGE=69/69
HISTORICAL_INTERACTION_UNION=70/70
UNRESOLVED_ACCEPTANCE_SEMANTIC_CONFLICTS=18
```

Stop after this documentation design. Do not implement the browser harness until the immutable
Phase 3 Backend Candidate, Backend Independent Audit PASS, Financial Semantics Audit PASS, approved
Backend Phase 4 Final Contract Freeze, approved V17 Change Request/reference delta, and immutable
Frontend V17 Candidate are all available.
