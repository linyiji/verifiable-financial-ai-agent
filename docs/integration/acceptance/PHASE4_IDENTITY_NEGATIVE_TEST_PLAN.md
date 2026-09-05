# Phase 4 Identity, Security, and Cross-Object Negative Test Plan

Status: **ACCEPTANCE DESIGN READY — NOT IMPLEMENTED — NOT EXECUTED**

Owner: D3 — Identity / Security / Cross-Object

Authority date: `2026-09-04` (Asia/Shanghai)

```text
P4_ID_ASSERTIONS_DEFINED=28/28
P4_ID_PHASE4_CORE_REQUIRED=26
P4_ID_PHASE5_DEFINED_NOT_ACTIVATED=2
P4_SSE_GATES_REFERENCED=20/20
SCENE_01_04_IDENTITY_COVERAGE=4/4
SCENE_05_06_STATE=DEFINED_NOT_ACTIVATED
V8_1_CURRENT_INTERACTION_CORPUS_ACKNOWLEDGED=69/69
V8_1_HISTORICAL_INTERACTION_UNION_ACKNOWLEDGED=70/70
IDENTITY_ACCEPTANCE_IMPLEMENTED=NO
IDENTITY_ACCEPTANCE_EXECUTED=NO
PHASE4_PRODUCTION_IMPLEMENTATION_AUTHORIZED=NO
```

This document defines future tests only. It does not change application code, test code, routes,
schemas, migrations, persistence, fixtures, or runtime behavior. It preserves the assertion
semantics in `PHASE4_IDENTITY_ASSERTION_MATRIX.md`, the activation rules in the parent and V8.1
delta matrices, and the fetch-stream decision in `PHASE4_SSE_BROWSER_ACCEPTANCE.md`.

## 1. Authority, scope, and non-negotiable result

| Input | Coordinate / disposition |
|---|---|
| Frontend V8.1 baseline manifest and interaction ledger | governance carrier `e2aef1edc22631dc988c862c18972f0fd7630625`; approved source `d854c97789c98cca14fee3f4b3d7f00e0d5d137a`; authoritative, immutable |
| V8.1 E2E assertion and activation deltas | authoritative append-only definitions from the V8.1 baseline Git object; `015` tombstone and `101..106` preserved |
| Identity, E2E, activation, browser-Scene, SSE, preaudit, mapping, and blocker inputs | repository `docs/integration/PHASE4_*`; identity/E2E/SSE assertion semantics preserved |
| Phase 4 Backend drafts | API schema, runtime-event, identity/error/availability and blocker-closure documents, explicitly `NOT_FINAL`; used as design targets, not executed authority |
| V17 preparation outputs | normalized contract preparation and dependency matrix are provisional/blocked; used only to enumerate adapter and shared-state negatives |
| Phase 3 Backend inspected by the draft/current repository | `codex/phase3-contracts@11fe8173a25ff7ac08bae42340ba7c6fae591be5`; confirms current route/model/auth gaps but cannot pass Phase 4 |
| Final V17 Integration Readiness Review/governed Candidate and final Backend Contract Freeze | not available; mandatory implementation-entry inputs and never inferred here |

The identity root is the requested Run, validated against its exact Research Object. Every nested
record must then close to that Run and Object through explicit identifiers:

```text
Object O
  <- Goal.research_object_id
  <- Scheme.research_object_id
  <- Run.research_object_id

Run R
  <- Task.run_id
  <- RuntimeEvent.run_id
  <- Evidence.run_id + Evidence.object_id
  <- Calculation.run_id
  <- Claim.run_id
  <- Review.run_id
  <- Proof.run_id
  <- CanonicalExecutionRecord.run_id + object_snapshot_ref
  <- ReleasedResearchResult.run_id
  <- ReportArtifact.run_id
```

A globally unique-looking ID is not permission to skip its owner join. Symbol, company name,
title, metric name, filename, array position, active tab, cached selection, current route text, and
"latest" are not identity. The only Phase 4 Core use of "latest" is the explicitly requested
Object overview projection `latest_released_run_id`, selected from valid released Runs owned by that
exact Object.

Every mismatch in this plan fails closed. A pass requires all of the following:

- a compound Backend lookup is non-success under the final frozen error contract; where a
  legitimate Run-only response cannot carry the browser's Object context, the adapter rejects the
  operation before committing any DOM state;
- no redirect or second read silently substitutes another ID;
- no mismatched domain fields or bytes are returned before the failure;
- the browser renders a safe unavailable/not-found/forbidden state for the original URL;
- the prior valid Object/Run/Claim/Task is not displayed as a fallback;
- no mutation request is issued while handling a read failure;
- logs, telemetry, accessible text, DOM, caches, and error details disclose no unauthorized body.

An authorized actor who may access both Objects is used for identity-substitution cases. This proves
that a rejection is caused by owner mismatch rather than by an unrelated authorization denial.
Separate unauthorized-actor cases prove access control.

## 2. Exact A/B corpus and fixture protocol

The later harness must create an isolated database, artifact namespace, Backend instance, and
browser profile. IDs are captured from successful Backend responses and persisted records; no test
derives IDs from labels or assumes Demo ID formats.

### 2.1 Principals

| Alias | Frozen setup requirement | Purpose |
|---|---|---|
| `U_AB` | authenticated principal authorized for both `O_A` and `O_B` under the same final actor/tenant/workspace policy | pure identity and cross-object tests |
| `U_A` | authenticated principal authorized for `O_A` but not `O_B` | authorization and existence-disclosure tests |
| `U_NONE` | authenticated principal with no authority for either object | authorization/default-deny tests |
| `U_ANON` | request with no valid authentication credential | authentication tests |

Principal, tenant, workspace, and credential form are contract parameters until the final Backend
contract freezes them. They must be named in the candidate manifest and may not be simulated by a
frontend-only flag.

### 2.2 Objects, Runs, and collisions

| Alias | Required state |
|---|---|
| `O_A` | first persisted Research Object with captured `object_id`, symbol `S_A`, and name `N_A` |
| `O_B` | second persisted Research Object where `O_B != O_A`, `S_B != S_A`, and `N_B != N_A` |
| `R_A0` | earlier valid released Run owned by `O_A` |
| `R_A1` | later valid released Run owned by `O_A`; it is `O_A.latest_released_run_id` |
| `R_A_live` | optional nonterminal Run owned by `O_A`, used for SSE/reconnect isolation |
| `R_B1` | valid released Run owned by `O_B`, committed after `R_A1` where practical so a global-newest bug selects B |
| `R_B_live` | optional nonterminal Run owned by `O_B`, used concurrently with `R_A_live` |

Both released Object chains must contain the full tuple below. Subscript `q` is one of `A0`, `A1`,
or `B1`:

```text
R_q -> T_q -> K_q -> E_q
R_q -> M_q -> C_q -> K_q + E_q
R_q -> V_q -> C_q + K_q
R_q -> P_q -> K_q                  (MUST_PROVE corpus)
R_q -> X_q -> T_q/E_q/K_q/C_q/V_q/P_q
R_q -> Y_q -> X_q                  (Y = ReleasedResearchResult)
R_q -> H_q/PDF_q -> X_q/Y_q        (distinct HTML/PDF artifact identities)
```

For the required six-field tuple, `A_q` is the exact AVAILABLE representation selected by the
scenario (`A_q=H_q` or `A_q=PDF_q`); both representation slots retain independent identities and
availability. The artifact-integrity corpus contains AVAILABLE HTML and PDF records so both byte
paths can be exercised.

The mandatory A-side metric uses Backend-authored
`canonical_value="0.6547"`, `canonical_unit="RATIO"`, `display_value="65.47"`, and
`display_unit="%"`. The B-side material metric must have a visibly different sentinel value. The
following human-readable fields are deliberately equal across A and B: at least one Task title or
goal, metric name, Claim title/presentation label, Review status/label, report title, and artifact
download filename. This collision makes title/metric/filename fallback observable. Provider source
locators and formulas may also collide; their IDs and owners must remain distinct.

`R_A0` and `R_A1` contain the same metric name but distinct `C_A0`, `C_A1`, `K_A0`, `K_A1`, `V_A0`,
`V_A1`, `X_A0`, `X_A1`, results, and artifacts. This pair is the historical-versus-latest oracle.
The earlier records and artifact bytes are hashed before `R_A1` is created and must remain
unchanged.

### 2.3 Creation and corruption boundaries

Normal A/B records are created through the reviewed public prepare/confirm/runtime/release path.
They are not assembled from frontend fixtures. Invalid stored-reference cases use an isolated
test-only repository seeding seam after valid A and B records exist. The seam may insert a copy of
an A projection/record with one exact B reference; it may not modify production code or create a
public mutation endpoint. The response under test is always obtained through the production API
projection path.

Each invalid seed changes exactly one relation. Examples are `C_A.evidence_refs += E_B`,
`C_A.calculation_refs = [K_B]`, `P_A.calculation_id = K_B`, `Y_A.canonical_record_id = X_B`, and
`H_A.released_result_id = Y_B`. The test first proves that the isolated A and B source records are
valid, applies the one-edge corruption, then requires the read/release/projection to fail. This
prevents a broad malformed fixture from hiding which invariant was exercised.

## 3. Layered execution model

The same invariant is tested at independent layers:

| Layer | Action | Required oracle |
|---|---|---|
| Backend domain/contract | validate or compose a record with one foreign reference | validation rejects it, or serialization returns the frozen integrity error with no projection |
| Backend integration | request a valid B ID under an A-scoped route or request an A record containing one seeded B edge | HTTP status/code is exact after contract freeze; response contains no foreign record/body |
| Frontend adapter | feed the adapter a production-shaped mismatched response | adapter rejects the complete projection; it does not drop the bad field and keep a partial success |
| Integrated browser | open the stale/mismatched deep link using real HTTP | original route remains identifiable; safe error is visible; no fallback entity or cross-object DOM content |
| Restart/reopen | restart Backend, clear browser state, and repeat | durable ownership and rejection are unchanged |
| Independent audit | rerun critical substitutions with freshly captured IDs | raw request, response, persistence, DOM, and cache evidence agree |

No frontend fixture, mocked fulfilled response, DOM-to-DOM comparison, or unit-only validation can
satisfy the integrated P4-ID result.

## 4. Entity-by-entity cross-object and cross-Run negatives

`IDN-*` labels below are test cases under the frozen `P4-ID-*` assertions; they are not new gate
IDs. In sections 4–8 coverage cells, `ID-`, `BE-`, `E2E-`, and `SSE-` are compact forms of the
`P4-ID-`, `P4-BE-`, `P4-E2E-`, and `P4-SSE-` namespaces.

| Case | Exact setup and action as `U_AB` | Required fail-closed oracle | Primary gates |
|---|---|---|---|
| `IDN-OBJ-01` Object | retain cached `S_A/N_A`, then navigate to missing `O_X`; separately request `O_A` while the route declares `O_B` | missing/mismatched Object stays unavailable; neither symbol/name nor cached Object repairs the ID | ID-001, 025–027; E2E-057, 063, 070, 073 |
| `IDN-GOAL-01` Goal | prepare for `O_A`; seed/observe a response whose Goal owns `O_B` | the entire draft is rejected; Scheme and confirm controls are unavailable; no Run is created | ID-002, 004, 026–027; BE-002/003/030; E2E-017–025, 070, 074 |
| `IDN-SCHEME-01` Scheme | prepare for `O_A`; substitute Scheme owner `O_B`, Goal `G_B`, non-null pre-confirm `confirmed_at`, or confirm `D_B` from A state | draft/confirm fails without selecting another draft; no A or B Run is admitted | ID-003–005, 026–027; BE-002–005/030; E2E-024–025, 074–075 |
| `IDN-RUN-01` Run B under Object A | ensure `R_B1` is absent from `GET O_A/runs`; open browser route containing `O_A + R_B1` | browser/API composition refuses mixed context; no A header with B body and no automatic switch to `O_B` | ID-001, 004, 006, 025–027; BE-001/010/030; E2E-005–007, 061, 070, 073, 076 |
| `IDN-GRAPH-01` Graph | seed one A Task parent/dependency or actual-graph node ref to `T_B1`; request A projection | projection fails as a whole; planned/actual graph is not pruned, relabeled, or repaired by matching Task title | ID-007–008, 026–027; BE-007/018/019/030; E2E-027–036, 071, 073, 088–089 |
| `IDN-TASK-01` Task B under Run A | deep-link `T_B1` while route and projection root are `R_A1`; repeat with same-title `T_A1` present | safe unavailable; neither `T_B1` nor same-title `T_A1` opens; A route/tab/focus origin remains | ID-008, 020, 025–027; BE-007/024/030; E2E-034, 036, 043, 050, 054, 073, 094 |
| `IDN-EVD-01` Evidence B in Claim A | seed `C_A1` or `K_A1` to reference `E_B1`; request Claim detail and Trace | no Evidence body or A Claim projection is returned; source locator/metric equality does not repair the edge | ID-011–012, 014, 020, 025–027; BE-022/024/030; E2E-051, 071–073, 092, 094 |
| `IDN-CAL-01` Calculation B in Claim A | seed `C_A1.calculation_refs=[K_B1]` while a same-formula `K_A1` exists | Claim/Trace/release projection fails; B value is never shown and K_A is not chosen by formula or metric name | ID-012–014, 020, 025–027; BE-020–024/030; E2E-052, 071–073, 092–095 |
| `IDN-CLM-01` Claim B under Run A | request `GET /research-runs/R_A1/claims/C_B1` and `/trace/C_B1`; open equivalent browser deep link | exact compound lookup fails; no B Claim and no latest/same-title A Claim appears | ID-014, 020, 025–027; BE-022/024/030; E2E-042, 048–055, 073, 094 |
| `IDN-REV-01` Review B under Run A | route/focus requests `V_B1` from `R_A1`; separately seed A result/trace to reference `V_B1` | no Review B content; no aggregate PASS or same-status Review is accepted as coverage of `C_A1/K_A1` | ID-015–016, 020, 025–027; BE-023/024/030; E2E-040–043, 053, 072–073, 094–095 |
| `IDN-PRF-01` Proof | seed `P_A1.run_id=R_A1` with `calculation_id=K_B1`, or insert `P_B1` into A Trace/CER | projection/release fails; proof generation or verification status alone cannot validate the foreign calculation | ID-012, 017–018, 020, 025–027; BE-024/028/030; E2E-072–073, 094–095 |
| `IDN-CAN-01` Canonical | seed `Y_A1.canonical_record_id=X_B1`, or `X_A1.object_snapshot_ref=O_B`, or a foreign ref in `X_A1` | A/B/C, result, artifact, and release become unavailable; no partial tab may retain success | ID-017–020, 025–027; BE-024–030; E2E-047, 054, 072–073, 094–098 |
| `IDN-RES-01` Result | seed the A projection/artifact group with `Y_B1`, or request a result projection whose enclosing Run is A and result owner is B | result and all released views fail; report presence is not release authority and no newest Result is substituted | ID-013–014, 017–020, 025–027; BE-020–030; E2E-006, 047–055, 072–073, 092–098 |
| `IDN-ART-01` Artifact B under Run A | request `GET /research-runs/R_A1/artifacts/H_B1/content`; also substitute B metadata in A group | binding fails before bytes; no A artifact fallback; HTML and PDF identities remain distinct | ID-019–020, 025–027; BE-025–027/030; E2E-045–046, 072–073, 096 |
| `IDN-EVT-01` Event/stream | subscribe to `R_A_live` and inject no frame; run B concurrently and observe real B frames only on B's stream; separately seed/route any persisted mismatch through Backend test setup | any frame whose route/subscription/data Run disagree is quarantined before reducer dispatch; no A task/progress mutation | ID-008–010, 023, 025–027; BE-011–019/030; SSE-001–020; E2E-068, 071–073, 077–091 |

For `IDN-RUN-01`, a direct `GET /research-runs/R_B1` is legitimate when made in an unscoped B
context by `U_AB`. The negative is the compound browser/Object context `O_A + R_B1`, or an
Object-scoped collection/projection that includes B. The suite must not incorrectly require a
valid globally Run-scoped read to fail merely because the same principal can access both Objects.

## 5. No-fallback matrix

| Case | Setup/action | Forbidden repair and required result | Coverage |
|---|---|---|---|
| `IDN-FB-01` historical Claim | open exact `R_A0/C_A0`, then create or visit `R_A1/C_A1`; refresh/Back to the historical URL | must stay on `R_A0/C_A0`; never use `C_A1` with the same metric name | ID-006, 014, 020, 023–027; E2E-061, 063, 094, 098 |
| `IDN-FB-02` latest Run | make `R_B1` globally newest; request `O_A` latest state | must return `R_A1`; never global newest `R_B1` | ID-001, 006, 013–020, 027; BE-028–030; E2E-060, 070, 073 |
| `IDN-FB-03` missing Claim | request `C_X` under `R_A1` while `C_A1` has the same title/metric sought by UI state | unavailable/not-found; never first/latest/same-title Claim | ID-014, 020, 027; BE-022/024/030; E2E-042, 048–055, 073, 094 |
| `IDN-FB-04` symbol | retain `S_A` in browser state, request missing `O_X` or mismatched `O_B` | never resolve `O_A` by symbol; route ID remains the failed target | ID-001, 025–027; BE-028–030; E2E-057, 063, 073, 101 |
| `IDN-FB-05` title | use identical Task/report/Review titles in A/B; request missing or foreign ID | no string lookup, no DOM text search as identity, no first match | ID-008, 015–020, 025–027; E2E-036, 042–055, 073, 094 |
| `IDN-FB-06` metric name | use same metric name in `R_A0`, `R_A1`, and `R_B1`; request a missing/foreign Claim or Calculation | no metric-name join; exact `metric_id`, Claim, K, Run, and result refs are required | ID-012–014, 020, 027; BE-020–024/030; E2E-092–095 |
| `IDN-FB-07` first/index | reorder returned Tasks, Claims, Reviews, representations, and comparison rows without changing IDs | route target is unchanged; array position cannot select an entity | ID-008, 013–020, 027; E2E-029–036, 040–55, 094–096 |
| `IDN-FB-08` representation | make PDF unavailable and HTML available, then activate/request PDF | disabled safe reason; never return HTML bytes under PDF ID/name | ID-019, 027; BE-025–027; E2E-045–046, 096 |
| `IDN-FB-09` schema/version | return unknown projection major, stale draft version, or unsupported entity version | fail `SCHEMA_INCOMPATIBLE`/frozen error; never retry using latest compatible record | ID-003–005, 023, 027; BE-002–004/007–009; E2E-023–025, 074–077, 105 |
| `IDN-FB-10` unavailable body | omit an Evidence/Calculation body with an explicit durable unavailable state | retain all IDs and show unavailable; do not source a body from another Run, Demo, cache, or raw artifact | ID-011–012, 020, 025–027; E2E-051–052, 065–067, 094 |

## 6. Shared browser-state and cache leakage

| Case | Exact action | Required oracle | Primary mapping |
|---|---|---|---|
| `IDN-STATE-01` two tabs | in one browser context open `O_A/R_A1/C_A1` in tab A and `O_B/R_B1/C_B1` in tab B; alternate activity, retry, dismiss, and focus | each tab keeps its own tuple and DOM sentinels; a singleton store must not switch A to B | ID-020, 023–027; E2E-063, 073, 105–106; interactions 063, 069–070 |
| `IDN-STATE-02` concurrent streams | open `R_A_live` and `R_B_live`; allow interleaved real frames and heartbeats | one active stream per page/Run; B events and heartbeat timing cause zero A domain mutation | ID-009–010, 025–027; SSE-001–005, 014; E2E-068, 071–073, 083 |
| `IDN-STATE-03` Back/Forward | A Claim → B Object → browser Back/Forward through Claim/Task/Review overlays | every history entry restores its exact O/R/T/C/V/A and focus/scroll; no mutation request | ID-020, 024–027; SSE-014; E2E-044, 055, 063–064, 098 |
| `IDN-STATE-04` refresh | refresh A while B was most recently used in another tab; repeat at nonterminal cursor N and terminal | snapshot/cache key includes exact R/O; A resumes A only and terminal state stays terminal | ID-023, 025–027; SSE-012–013, 017; E2E-077, 087–088, 098 |
| `IDN-STATE-05` new context | close browser, create a clean context, reopen exact A deep link after Backend restart | business state comes from Backend persistence; no local/session/IndexedDB requirement and no B residue | ID-023, 025–028; SSE-013, 017; E2E-063, 087–088, 098 |
| `IDN-STATE-06` failed read/cache | first load B successfully, then request missing/unauthorized A target that shares a query key shape | failed request renders failure; stale B success is not retained as A content | ID-001, 020, 023, 025–027; E2E-057, 063, 073, 105 |
| `IDN-STATE-07` alert retry | fail an A read, navigate nowhere, activate Retry; then make the same A read succeed or fail again | request repeats the exact A URL/IDs; no new Run, B read, Demo substitution, or route reset | ID-023, 025–027; E2E-105; interaction 069 |
| `IDN-STATE-08` alert dismiss | dismiss a missing/cross-object A alert after B was previously viewed | only alert state changes; no retry, navigation, entity replacement, or domain mutation | ID-024–027; E2E-106; interaction 070 |

The browser evidence scans the DOM and accessible tree for the other Object's ID, symbol, company
name, Claim/Task/Review/artifact IDs, and known financial sentinel. The scan supplements exact
record joins; it never replaces them. HTTP cache, application query cache, service-worker cache,
SSE reducer state, URL state, and any persisted browser storage are inspected separately.

## 7. Authorization negatives

| Case | Action | Required result |
|---|---|---|
| `IDN-AUTH-01` no authentication | `U_ANON` requests every Object, Run, projection, Claim, Trace, Review, Execution, artifact metadata/content, and SSE surface | the final frozen authentication error on every route; no stream admission, metadata, bytes, counts, titles, existence detail, or cache reuse |
| `IDN-AUTH-02` unauthorized Object | `U_A` requests `O_B`, `R_B1`, and every captured B nested ID | the final nondisclosing 403-or-404 contract consistently; no difference that reveals which nested B IDs exist |
| `IDN-AUTH-03` ID possession | copy B Claim, Trace, artifact content URL, SSE cursor, and canonical/result IDs from `U_AB` into `U_A` requests | possession is not authority; each request is re-authorized and fails without partial data |
| `IDN-AUTH-04` authorized mismatch | `U_AB` performs all `IDN-*` substitutions | still fails identity; broad access does not permit cross-Run composition |
| `IDN-AUTH-05` artifact recheck | obtain metadata/authorized reference as `U_AB`, then fetch bytes as `U_A`, after expiry/revocation if supported, and after Backend restart | byte route independently rechecks authority and current reference validity; no bytes on failure |
| `IDN-AUTH-06` idempotency scope | reuse a confirm key across principal/tenant/workspace or with a B draft/body | it never returns or creates another principal's Run; same-scope same-hash alone may replay |
| `IDN-AUTH-07` errors/logs | trigger unauthorized and identity-mismatch reads, including artifacts and Evidence | safe error envelope and sanitized logs contain request/correlation IDs only; no secrets, raw provider body, storage path, signed token, or hidden reasoning |
| `IDN-AUTH-08` shared cache | use the same browser and reverse-proxy process for `U_AB`, then `U_A`; request identical URLs where credentials differ | response/cache varies by authorization; A-only user never receives warmed B content |

The current design sources disagree on whether authentication is Phase 4 mandatory and do not
freeze principal or tenant semantics. Therefore these cases are mandatory designs but may not be
implemented against guessed headers or roles. The final contract must select exact authentication,
authorization, cache, and nondisclosure behavior first.

## 8. Integrity negatives

| Case | Corruption/action | Required result | Coverage |
|---|---|---|---|
| `IDN-INT-01` nested owner | seed any one foreign Run/Object edge from section 4 | response/release fails atomically; foreign record is never omitted to manufacture a partial success | ID-007–020, 025–027; BE-007/022–030 |
| `IDN-INT-02` canonical closure | alter `X.object_snapshot_ref`, `Y.canonical_record_id`, an A/B/C canonical ID, or required X refs | released views unavailable; status cannot remain RELEASED for acceptance | ID-017–020; BE-023–030; E2E-094–098 |
| `IDN-INT-03` Review/proof closure | remove exact Claim/K coverage, mark proof generated but not valid, or bind proof to foreign K | release fails; browser cannot infer Review PASS or Proof valid | ID-012, 015–018, 020; BE-023/024/028/030; E2E-092, 094–095 |
| `IDN-INT-04` artifact hash | alter one byte while metadata hash/size remain original | content route returns `INTEGRITY_FAILURE` under final contract and zero bytes | ID-019; BE-026–027; E2E-096 |
| `IDN-INT-05` artifact size/media | mismatch size, content type, format, or `Content-Disposition`; request HTML as PDF and vice versa | no bytes; no MIME sniffing or other-representation fallback | ID-019, 027; BE-025–027; E2E-045–046, 096 |
| `IDN-INT-06` raw location | inspect metadata, JSON, DOM, logs, redirect, and headers | no filesystem path, `artifact://`, raw store key, permanent public URL, or secret query string is exposed | ID-019, 025; BE-025–027; E2E-066–067, 096 |
| `IDN-INT-07` event identity | deliver a complete real duplicate/out-of-order frame through the allowed chaos proxy; Backend contract test separately supplies a malformed/cross-Run frame without calling it a real business frame | duplicate is idempotent; disorder/cross-Run is quarantined and reconciled; no speculative entity mutation | ID-009–010, 023, 025–027; BE-011–019/030; SSE-002–013, 019–020 |
| `IDN-INT-08` persistence | hash A/B tuples and artifacts; restart Backend and reopen terminal and nonterminal URLs | exact IDs, owners, immutable history, terminal state, Review, A/B/C, and bytes persist | ID-005–020, 023, 028; BE-004/017/022–030; SSE-013, 015–017; E2E-075, 087–088, 098 |

Chaos tests may only drop, delay, duplicate, or reorder complete real frames. A deliberately invalid
frame belongs to Backend contract testing and must not be labeled `CHAOS_SSE` or used as evidence
that the Backend emitted it.

## 9. Exhaustive P4-ID crosswalk

`PHASE4_ACCEPTANCE_GATE_CROSSWALK.md` is the single mapping authority. The table below adds D3
negative-case detail and does not redefine it. `P4-BE-001..030` are coordinator-owned stable gate
IDs, while their wire contracts remain provisional until Backend Contract Freeze. Numeric entries
in the P4-BE, P4-E2E, and P4-SSE columns inherit those full namespace prefixes. Interaction numbers
use the approved V8.1 ledger: `001..014` and `016..070` are active; `015` is a tombstone. Real Scenes
05/06 and `P4-ID-021/022` remain inactive in Phase 4 Core.

The explicit SSE coverage set is:

```text
P4-SSE-001, P4-SSE-002, P4-SSE-003, P4-SSE-004, P4-SSE-005,
P4-SSE-006, P4-SSE-007, P4-SSE-008, P4-SSE-009, P4-SSE-010,
P4-SSE-011, P4-SSE-012, P4-SSE-013, P4-SSE-014, P4-SSE-015,
P4-SSE-016, P4-SSE-017, P4-SSE-018, P4-SSE-019, P4-SSE-020
```

| P4-ID | Negative acceptance focus | P4-BE dependency | P4-E2E | P4-SSE | Scene | Direct interaction coverage |
|---|---|---|---|---|---|---|
| `P4-ID-001` | missing/mismatched Object; symbol/cache may not repair route | 028–030 | 003, 009, 016, 057, 059, 063, 070, 073, 101 | — | 01–04; 05–06 later | 003, 009, 013, 016, 056–064, 065 |
| `P4-ID-002` | Goal owner differs from selected Object | 002–003, 030 | 017–025, 070, 074, 102 | — | 01; 06 later | 017–025, 066 |
| `P4-ID-003` | Scheme owner/Goal mismatch, confirmed preview, stale version | 002–003, 030 | 024, 070, 074 | — | 01; 06 later | 024, 066–067 |
| `P4-ID-004` | confirmed Run differs from exact Object/Goal/Scheme | 002–007, 030 | 025, 070, 074–075, 102 | — | newly created core Runs; 06 later | 025, 066 |
| `P4-ID-005` | key/body/draft/actor mismatch; retry/restart creates no second Run | 004–006, 017 | 025, 075, 098 | — | 01; 06 later | 025 |
| `P4-ID-006` | list/history row points to foreign/stale detail or global latest | 001, 010, 028–030 | 002, 005–007, 060–061, 070, 076, 098 | — | 01–04; 05–06 later | 002, 005–007, 060–061 |
| `P4-ID-007` | graph owner mismatch; planned graph mutated; mixed-revision graph | 007–009, 018–019, 030 | 027, 029–036, 071, 077, 088–091 | 012–013, 020 | 01–03; 06 later | 027, 029–036 |
| `P4-ID-008` | foreign Task/parent/dependency or same-title Task fallback | 007, 018–019, 030 | 027, 034–036, 043, 050, 054, 071, 073, 089–091 | 003, 010–014, 019–020 | 01–04; 05–06 later | 027, 034–036, 043, 050, 054; 068 later |
| `P4-ID-009` | stream/event Run mismatch or invalid Task is never dispatched | 007–019, 030 | 026–036, 068, 071, 073, 077–091 | 001–020 | 01–04; 05–06 later | 026–036, 063 |
| `P4-ID-010` | replan/correction/capability changes Run/Task mid-lifecycle | 007, 018–019, 030 | 031–036, 071, 073, 082, 084, 089–091 | 003, 009–013, 019–020 | 01 capability; 02–03 | 031–036, 043 |
| `P4-ID-011` | Evidence B in Claim/K A; missing owner; locator fallback | 020, 022, 024, 030 | 051, 071–073, 092, 094–095 | 012–013, 015–017 | 01, 03, 04; 06 later | 051 |
| `P4-ID-012` | Calculation B in Claim A; foreign Task/Evidence; formula fallback | 020–024, 030 | 050, 052, 054, 071–073, 090, 092–095 | 012–013, 015–017 | 01, 03, 04; 06 later | 050, 052, 054 |
| `P4-ID-013` | metric points to foreign K/result/X or is selected by name | 020–024, 030 | 047–048, 069, 072–073, 092–095 | 012–013, 015–017 | 01, 03–04; 05–06 later | 047–048 |
| `P4-ID-014` | Claim B under Run A; semantic/ref/name mismatch | 020–024, 030 | 042, 048–055, 069, 072–073, 092–095 | 012–013, 015–017 | 01, 03–04; 05–06 later | 042, 048–055 |
| `P4-ID-015` | Review B/Run mismatch or Review does not cover exact C/K | 023–024, 030 | 040–043, 053, 072–073, 094–095 | 012–013, 015–017 | 01–04 at release | 040–043, 053 |
| `P4-ID-016` | adapter invents per-Claim Review ID or joins by status/title | 023–024 | 040–043, 053, 072, 094–095 | 012–013, 015–017 | 01–04 at release | 040–043, 053 |
| `P4-ID-017` | X owns foreign Run/Object or foreign lineage refs | 007, 023–030 | 047, 054, 072–073, 094–098 | 012–013, 015–017 | 01–04 at release | 047, 054 |
| `P4-ID-018` | Result or A/B/C carries a different X/Run/Object | 020, 023–030 | 047, 072–073, 092, 094–098 | 012–013, 015–017 | 01–04 at release | 047 |
| `P4-ID-019` | artifact owner/report/X/result mismatch; wrong bytes/format | 025–027, 030 | 045–047, 072–073, 096, 098 | 013, 015–017 | 01–04 at release | 045–047 |
| `P4-ID-020` | any route/overlay loses O/R/T/C/V/A/K/E/X or anchor scope | 022–027, 030 | 042–055, 063, 072–073, 087–088, 094–096, 098 | 013–014, 017 | 04 plus all released core regressions | 042–055, 063–064 |
| `P4-ID-021` | Object version source Run owns another Object or earlier version changes | future Phase 5 gate required | Phase 5 variants 059, 061, 097–098, 103 | 013–014, 017 regression | **05–06 inactive** | 059, 061, 067; result null |
| `P4-ID-022` | comparison Claim uses current/latest rather than row source Run | future Phase 5 gate required | 062, 094, 097, 104 | 013–014, 017 regression | **05–06 inactive** | 062, 068; result null |
| `P4-ID-023` | refresh/new browser/restart changes tuple or uses browser storage | 007–010, 017, 022–030 | 063, 076, 087–088, 098, 105 | 012–014, 017 | 01–04; 05–06 later | 063, 069 |
| `P4-ID-024` | Back/Forward changes tuple or emits mutation | 007, 010, 022–030 | 044, 055, 063–064, 098 | 014 | 01–04; 05–06 later | 044, 055, 063–064 |
| `P4-ID-025` | B IDs/sentinels leak through DOM, network projection, cache, or SSE | 007, 022–030 | 065–073, 088, 094–096, 098, 105–106 | 003, 010–014, 017–020 | 01–04; 05–06 later | 045–055, 057–064, 069–070 |
| `P4-ID-026` | every cross-Run/Object substitution is rejected | 030 plus target entity gate | 042, 045–055, 057, 061, 070–073, 094, 096 | 003, 018 | 01–04; 05–06 later | 042, 045–055, 057, 061 |
| `P4-ID-027` | no missing-ID latest/first/title/symbol/metric/format repair | 001, 010, 022–030 | 006, 042, 048–055, 057, 060–063, 073, 094, 101, 105 | 013–014, 017–018 | 01–04; 05–06 later | 006, 042, 048–055, 057, 060–063, 065, 069 |
| `P4-ID-028` | any empty O/R/T/C/V/A in an activated real result | 007, 022–030 | 072, 094–096, 098 | 013, 015–017 | 01–04; 05–06 after activation | all tuple-opening interactions |

### V8.1 append-only interaction disposition

| E2E gate / interaction | Identity/security assertion |
|---|---|
| `P4-E2E-101` / `065` clear-search | clears query, result and selected Object together; zero Object mutation; no stale symbol/Object fallback (`ID-001`, `025`, `027`) |
| `P4-E2E-102` / `066` FULL | prepare/confirm retain exact O and FULL; no Incremental source is inferred (`ID-002..004`) |
| `P4-E2E-103` / `067` Incremental | real selection requires exact released same-Object source Run (`ID-021`, `027`); Phase 5 result is `null` now, while disabled/no-source UX may regress earlier |
| `P4-E2E-104` / `068` Incremental Task | exact current-Run Task only (`ID-008`, `021..022`); `DEFINED_NOT_ACTIVATED` for real Phase 4 Core |
| `P4-E2E-105` / `069` retry | repeats the exact failed read and preserves route/entity identity (`ID-023`, `025`, `027`) |
| `P4-E2E-106` / `070` dismiss | alert-only state change; no retry, mutation, navigation, or entity substitution (`ID-024..027`) |

`P4-E2E-015` is a `RETIRED_TOMBSTONE`. It is never executed, never reused, and never included in a
current interaction or identity denominator.

## 10. Evidence retained and binary decision

Every P4-ID attempt retains, under the common evidence manifest:

- attempt ID, candidate pair, clean-tree fingerprints, database revision, contract versions,
  environment, source class, timestamp, and principal-policy identifier;
- the A/B identity ledger and precondition queries proving each source record is valid and distinct;
- sanitized request method/path/headers, response status/error code/body hash, and request ID;
- persisted ownership rows or projection snapshots before and after the action;
- browser URL/history entry, DOM/accessibility scan, focus/scroll target, screenshot, trace, console and
  page errors;
- cache/storage/service-worker inventory and network ledger for shared-state tests;
- SSE request cursor plus upstream/downstream frame hashes for mapped stream cases;
- artifact metadata, authorized-content response headers, byte count, SHA-256, and proof that no bytes
  were returned on a negative;
- Backend restart and new-browser-context witness where required;
- deterministic failure history, rerun reason, source-change flag, and final disposition.

No evidence bundle contains credentials, raw licensed provider bodies, provider API keys, raw
artifact storage locations, prompts, hidden chain-of-thought, or model scratch state.

For an activated assertion the outcome is only `PASS` or `FAIL`. A missing test, unavailable
harness, blocked contract, skipped negative, partial response, console/runtime error, foreign DOM
sentinel, nondeterministic-only success, or qualified result evaluates to `FAIL` at release time.
During the present design stage, `NOT_IMPLEMENTED` describes harness status only. `P4-ID-021` and
`022` are `DEFINED_NOT_ACTIVATED` with `result=null` until Phase 5 activation.

## 11. Unresolved upstream contract conflicts

The acceptance semantics above are not ambiguous: mismatches fail closed and fallback is forbidden.
The following upstream wire/implementation contracts are unresolved and must be frozen before test
implementation. They are not waivers and no test may choose the closest current behavior.

| Conflict | Observed conflict | Required freeze decision |
|---|---|---|
| `P4-ID-CF-01` Backend contract status | `PHASE4_BACKEND_API_SCHEMA_DRAFT.md` is `PROVISIONAL_CONTRACT_DRAFT / NOT_FINAL`; no Final Contract Freeze or V17 review was available | bind final route/schema/event versions and exact candidate coordinates |
| `P4-ID-CF-02` authentication scope | `09_API_CONTRACT_V1.md` says auth is not competition-MVP core and leaves `user_id/workspace_id/actor_id` optional; Phase 4 draft requires every request to authenticate | freeze principal, tenant/workspace ownership, credential form, route coverage, and restart/cache behavior |
| `P4-ID-CF-03` identity/auth error wire | identity authority permits `404/403/safe unavailable`; only artifact text suggests `IDENTITY_MISMATCH`/404; the common exact status/code/privacy policy is absent | select one exact status/code/body and nondisclosure rule per missing, mismatched, unauthenticated, and unauthorized case |
| `P4-ID-CF-04` Object + Run compound scope | public Run detail/projection paths are Run-only; no Backend route receives both `object_id` and `run_id` | freeze whether the Backend exposes an Object-bound Run route/assertion or the browser adapter must compare Object and Run before any render |
| `P4-ID-CF-05` nested detail surfaces | exact Task, Evidence, Calculation, and Proof detail routes (or complete durable unavailable contracts) are absent | freeze compound Run-scoped lookups and safe field/authorization schemas; no frontend synthesis |
| `P4-ID-CF-06` Review selection | `/review-view` has no `review_id`; current projection is aggregate/ref-only and `ReviewCheck` lacks stable `check_id` | freeze exact Review/check selector, stable identity, Claim/K coverage, and correction history semantics |
| `P4-ID-CF-07` Trace and anchors | Trace route, typed Judgment subset, primary/multiple Task rule, and representation-scoped report/review/task/execution anchors are absent | freeze `TraceBundleV1` and immutable anchor manifest; unavailable is allowed, guessed linkage is not |
| `P4-ID-CF-08` Artifact exposure | stored artifact has no direct Object/availability/auth/failure/anchor fields; current route does not deliver authorized bytes and internal `artifact_ref` is path-like | freeze grouped metadata, Object resolution, independent HTML/PDF slots, authorization, integrity headers/errors, expiry/revocation, and no-raw-ref rule |
| `P4-ID-CF-09` release cardinality/closure | several persisted canonical/result/artifact refs are optional or validated only for a typed financial subset; route-level all-entity closure is not frozen | freeze required release-time X/Y/V/P/artifact cardinality and atomic failure semantics |
| `P4-ID-CF-10` atomic projection/SSE watermark | current separate reads have no shared revision/sequence; the draft requires a new atomic projection and durable revision | freeze transactionally consistent `projection_revision`, `projection_sequence`, event schema, and reconciliation error behavior |
| `P4-ID-CF-11` V17 browser identity state | V17 Integration Readiness Review/preparation was unavailable; V8.1 HTTP/SSE adapters are intentionally fail-closed placeholders | freeze URL grammar, adapter cache keys, auth variation, shared-store isolation, focus/scroll serialization, and retry behavior in the V17 Candidate |

`P4-ID-021/022` depend on Phase 5 Object Memory, Research View versioning, comparison, and exact
source-Run contracts. Their absence is an explicit inactive phase boundary, not a Phase 4 Core
contract conflict and not a Phase 4 failure.

```text
UNRESOLVED_IDENTITY_ACCEPTANCE_SEMANTIC_CONFLICTS=0
UPSTREAM_IDENTITY_CONTRACT_CONFLICTS_AWAITING_FREEZE=11
NO_CLOSEST_MATCH_REPAIR=REQUIRED
NO_AUTOMATIC_LATEST_REPAIR=REQUIRED
```

## 12. Stop condition

Do not implement this plan until the immutable Phase 3 Backend candidate and independent audit,
Financial Semantics audit, final Phase 4 Backend Contract Freeze, and Frontend V17 preparation are
complete. At that point, reconcile the provisional P4-BE references to the coordinator-owned final
catalogue without changing any P4-ID assertion or negative oracle.
