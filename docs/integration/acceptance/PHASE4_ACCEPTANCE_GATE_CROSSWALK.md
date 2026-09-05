# Phase 4 Acceptance Gate Crosswalk

Status: **AUTHORITATIVE DESIGN CROSSWALK — NOT EXECUTED**

This is the single mapping authority among Backend, browser E2E, SSE, identity, Scene and interaction namespaces. A mapping does not allow one layer to substitute for another: each gate keeps the oracle defined by its owning catalogue.

## 1. Namespace and lifecycle ledger

### P4-E2E

The following ranges exhaust all 106 defined IDs without reuse:

| Gate/range | Lifecycle / activation | Current result rule |
|---|---|---|
| `P4-E2E-001..014` | active, `PHASE4_CORE_REQUIRED` | binary when executed |
| `P4-E2E-015` | `RETIRED_TOMBSTONE` | `null`; excluded from denominators |
| `P4-E2E-016..057` | active, `PHASE4_CORE_REQUIRED` | binary when executed |
| `P4-E2E-058` FULL variant | active, `PHASE4_CORE_REQUIRED` | binary when executed |
| `P4-E2E-058` INCREMENTAL variant | `PHASE5_ACTIVATED` | `DEFINED_NOT_ACTIVATED`, result `null` |
| `P4-E2E-059` Core Object tabs/current release view | active, `PHASE4_CORE_REQUIRED` | binary when executed |
| `P4-E2E-059` versioned Research View variant | `PHASE5_ACTIVATED` | `DEFINED_NOT_ACTIVATED`, result `null` |
| `P4-E2E-060..061` | active, `PHASE4_CORE_REQUIRED` | binary when executed |
| `P4-E2E-062` | `PHASE5_ACTIVATED` | `DEFINED_NOT_ACTIVATED`, result `null` |
| `P4-E2E-063..096` | active, `PHASE4_CORE_REQUIRED` | binary when executed |
| `P4-E2E-097` | `PHASE5_ACTIVATED` | `DEFINED_NOT_ACTIVATED`, result `null` |
| `P4-E2E-098` | active, `PHASE4_CORE_REQUIRED` | binary when executed |
| `P4-E2E-099..100` | `DEPLOYMENT_ACTIVATED` | `DEFINED_NOT_ACTIVATED`, result `null` for Phase 4A |
| `P4-E2E-101..102` | active, `PHASE4_CORE_REQUIRED` | binary when executed |
| `P4-E2E-103..104` | `PHASE5_ACTIVATED` | `DEFINED_NOT_ACTIVATED`, result `null` |
| `P4-E2E-105..106` | active, `PHASE4_CORE_REQUIRED` | binary when executed |

This yields 99 unique Phase 4 Core E2E IDs, four Phase 5-only unique IDs (`062`, `097`, `103`, `104`), two deployment-only IDs and one tombstone. Mixed `058`/`059` retain their shared IDs and variant-specific activation.

### Other namespaces

| Namespace | Defined | Phase 4 Core | Inactive/tombstone |
|---|---:|---:|---|
| `P4-BE` | authoritative count is the Backend gate catalogue | all rows marked Core | none unless later appended with explicit activation |
| `P4-SSE-001..020` | 20 | 20 | 0 |
| `P4-ID-001..028` | 28 | 26 (`001..020`, `023..028`) | `021..022` Phase 5 |
| Scenes | 6 | real `01..04` | real `05..06` Phase 5 |
| interactions | 70 historical | 69 currently exposed regression rows | `015` tombstone |

## 2. Authoritative capability chains

An em dash means that layer has no independent gate for the capability; it does not mean the capability is untested. Interaction IDs refer to the approved Frontend interaction ledger, not to same-numbered gates after row 064.

| Capability / owned question | P4-BE | P4-E2E | P4-SSE | P4-ID | Real Scene | Interaction |
|---|---|---|---|---|---|---|
| Primary shell navigation | — | `001..003` | — | `001`, `006`, `024` | `01..04` | `001..003` |
| Global Run collection | `001`, `010` | `002`, `005..007`, `076` | — | `006`, `023`, `027` | `01..04` | `002`, `005..007` |
| Released Object Core | `028`, `029` | `003`, `057`, `059` Core, `060..061`, `076`, `098` | — | `001`, `006`, `018`, `023`, `027..028` | `01..04` | `003`, `057`, `059..061` |
| Create/search Object and clear state | `028`, `030` | `008..014`, `016`, `056`, `101` | — | `001`, `025..027` | `01` | `008..014`, `016`, `056`, `065` |
| Goal and FULL-mode binding | `002`, `003` | `017..023`, `074`, `102` | — | `002..003` | `01` | `017..023`, `066` |
| Prepare draft identity | `002` | `023..024`, `074` | — | `002..003` | `01` | `023..024` |
| Prepare Scheme semantics | `003` | `017..024`, `074` | — | `002..003` | `01` | `017..024` |
| Durable confirm idempotency | `004` | `025`, `075` | — | `004..005` | `01` | `025` |
| Exactly-one Run/admission | `005`, `006` | `025..026`, `075` | `001` | `004..005`, `009` | `01` | `025..026` |
| Atomic RunProjection | `007` | `005`, `026..043`, `077`, `088` | `012..013` | `006..020`, `023` | `01..04` | `005`, `026..043` |
| Projection sequence/watermark | `008` | `077`, `081`, `087..088` | `002`, `004`, `009`, `012..013` | `009`, `023` | `01..04` | `026`, `063` |
| Projection revision/list consistency | `009`, `010` | `005..007`, `060..061`, `076..077`, `087..089`, `098` | `012..014`, `020` | `006..007`, `023..024` | `01..04` | `005..007`, `060..063` |
| Actual Backend SSE source/envelope | `018` | `068`, `083` | `001..005` | `009`, `025` | `01..04` | `026..036` |
| Numeric cursor replay | `011` | `079`, `081` | `007`, `009` | `009`, `023` | `01..04` | `063` |
| Opaque cursor replay | `012` | `080`, `081` | `008..009` | `009`, `023` | `01..04` | `063` |
| Unknown/negative cursor rejection | `013` | `073`, `079..080` negative variants | `018` | `009`, `026..027` | `01..04` | `063` |
| Cursor-ahead rejection | `014` | `079..080` negative variants | `018` | `009`, `026..027` | `01..04` | `063` |
| Disconnect and gap-free merge | `011..012` | `078..081` | `006..009` | `009`, `023` | `01..04` | `063` |
| Duplicate idempotence | `007..008` | `082`, `088` | `010` | `008..010`, `023` | `01..04` | `026..043` |
| Delayed/out-of-order/gap defense | `007..009`, `018` | `084`, `088` | `011..012` | `007..010`, `023` | `01..04` | `026..043` |
| Snapshot race and refresh | `007..009` | `077`, `087..088` | `012..013` | `006..010`, `023` | `01..04` | `063` |
| Back/Forward subscription lifecycle | `007`, `010` | `063`, `087..088`, `098` | `014`, `017` | `023..024` | `01..04` | `063` |
| Terminal success | `015` | `006`, `085`, `088`, `098` | `015`, `017` | `006`, `017..019`, `023`, `028` | `01..04` | `006`, `044..055`, `060..061` |
| Terminal failure/no Results | `016` | `007`, `086`, `088`, `098` | `016..017` | `006`, `015`, `017..019`, `023` | `01..04` negative variants | `007`, `040..047` |
| PostgreSQL restart replay/reopen | `017` | `075`, `087`, `098` | `007..009`, `013`, `017` | `005`, `009`, `023` | `01..04` | `025`, `044..063` |
| Event normalization/unknown values | `018` | `026`, `028`, `032`, `068`, `083..086`, `089..091` | `002`, `015..016`, `019..020` | `009..010`, `027` | `01..03` | `026`, `028`, `032`, `035..036` |
| Sparse graph event recovery | `019` | `029..036`, `084`, `088..089` | `011..013`, `020` | `007..010`, `023` | `02` | `029..036` |
| Dynamic Graph | `007..009`, `019` | `029..036`, `089` | `012..013`, `020` | `007..010`, `023` | `02` | `029..036` |
| Self-Correction | `007`, `018` | `034`, `040..043`, `090`, `095` | `012..013` | `010..018`, `020`, `023` | `03` | `034`, `040..043` |
| Capability Waiting/resume | `007`, `018` | `026`, `034`, `091` | `019` | `008..010`, `023` | `01` | `026`, `034` |
| Lossless ReleasedFinancialMetric | `020` | `069`, `092`, `094..095` | — | `011..020`, `028` | `01`, `03`, `04` | `040..055` |
| Ratio/percentage semantics | `021` | `069`, `092..093` | — | `013..014`, `018`, `020` | `01`, `04` | `047..049` |
| Claim detail and missing detail | `022` | `042`, `048..055`, `092`, `094` | — | `011..014`, `020`, `025..027` | `03`, `04` | `042`, `048..055` |
| Review/check projection | `023` | `040..043`, `053`, `090`, `094..095` | — | `015..016`, `020`, `025..027` | `01`, `03`, `04` | `040..043`, `053` |
| Claim Trace closure | `024` | `042..055`, `063`, `094` | `013..014` for navigation/reopen | `011..020`, `023..027` | `04` | `042..055` |
| One canonical A/B/C record | `020`, `023..025` | `047`, `092`, `094..095` | — | `013..020`, `028` | `01`, `03`, `04` | `047..055` |
| Proof policy/verification visibility | `020`, `024` | `072`, `092`, `094..095` | — | `013..018`, `020` | `01`, `03`, `04` | `047..055` |
| Artifact metadata | `025` | `045..046`, `072`, `096`, `098` | — | `019`, `023`, `025..027` | `01`, `04` | `045..046` |
| Authorized artifact bytes | `026` | `045..046`, `073`, `096`, `098` | — | `019`, `025..027` | `01`, `04` | `045..046` |
| Artifact size/hash/media integrity | `027` | `045..046`, `096`, `098` | — | `019`, `023`, `026` | `01`, `04` | `045..046` |
| Cross-object/cross-Run rejection | `030` | `057`, `060..063`, `070..073`, `094`, `096`, `098` | `003`, `018` | `001..020`, `023..028` as applicable | `01..04` | `057`, `060..063` |
| Latest released Run exactness | `029` | `006`, `059` Core, `060..061`, `076`, `098` | — | `006`, `018`, `023..024`, `027` | `01..04` | `006`, `059..061` |
| Retry preserves route/entity | relevant failed-read gate | `012`, `023`, `105` | `006..014` when stream retry | `023..027` | `01..04` | `012`, `023`, `069` |
| Alert dismiss has no mutation | — | `106` | — | `024..025` | `01..04` | `070` |
| Browser deep-link/focus/scroll/overlay | supporting entity gates | `010..011`, `037..039`, `044`, `047..055`, `063..064` | `014`, `017` where subscription changes | `020`, `023..024` | `01..04` | same E2E-numbered interactions |
| Responsive/accessibility/console | — | each affected interaction plus suite-wide browser oracle | — | shared-state part of `025` | `01..04` | all current `001..014`, `016..070` |
| Demo/real provenance separation | — | `065..068` | `001` | `025`, `028` | `01..04` | all current interactions by suite |
| Phase 5 Object Memory/comparison | future Backend namespace only after freeze | `058` incremental, `059` versioned, `062`, `097`, `103..104` | future applicable regression | `021..022` | real `05..06` | `058..063`, `067..068` |
| Deployment truth/policy | future deployment Backend gates | `099..100` | applicable regression only after activation | applicable identity regression | release-profile Scenes | no current interaction assigned |

## 3. Exhaustive SSE-to-parent mapping

| P4-SSE | Parent E2E | Principal Backend support | Identity |
|---|---|---|---|
| `001` | `068` | `006`, `018` | `009`, `025` |
| `002` | `068`, `083` | `018` | `009` |
| `003` | `071..073` | `030` | `009`, `025..026` |
| `004` | `083` | `008`, `018` | `009` |
| `005` | `083` | `018` | `009` |
| `006` | `078` | `011` | `009`, `023` |
| `007` | `079` | `011` | `009`, `023` |
| `008` | `080` | `012` | `009`, `023` |
| `009` | `081` | `011..012` | `009`, `023` |
| `010` | `082` | `007..008` | `008..010`, `023` |
| `011` | `084`, `088` | `007..009`, `018` | `007..010`, `023` |
| `012` | `077`, `088` | `007..009` | `009`, `023` |
| `013` | `087..088` | `007..009` | `009`, `023` |
| `014` | `063`, `098` | `007`, `010` | `023..024` |
| `015` | `085` | `015` | `017..019`, `023` |
| `016` | `086` | `016` | `017..019`, `023` |
| `017` | `085..087`, `098` | `015..017` | `023` |
| `018` | `073`, `079..080` negative variants | `013..014`, `030` | `009`, `026..027` |
| `019` | `081..083`, `091` | `007`, `018` | `008..010`, `023` |
| `020` | `081..084`, `089` | `007..009`, `019` | `007..010`, `023` |

## 4. Identity lifecycle mapping

| P4-ID range | Principal capability | Backend gates | Browser gates | Activation |
|---|---|---|---|---|
| `001..005` | Object/prepare/confirm identity | `002..005`, `028`, `030` | `003`, `008..025`, `070`, `074..075`, `101..102` | Core |
| `006..010` | Run/list/graph/Task/event identity | `006..019`, `029..030` | `002`, `005..007`, `026..036`, `068`, `071`, `076..091`, `098` | Core |
| `011..014` | Evidence/Calculation/metric/Claim identity | `020..024`, `030` | `042`, `048..055`, `069`, `071..073`, `092..095` | Core |
| `015..020` | Review/CER/result/artifact/trace identity | `015..030` as applicable | `040..055`, `072..073`, `085..086`, `092..098` | Core |
| `021..022` | versioned Object/comparison identity | future frozen Backend gates | `058` incremental, `059` versioned, `062`, `097`, `103..104` | Phase 5; result null now |
| `023..024` | durable reopen and navigation tuple | `007..017`, `022..030` | `044`, `048..064`, `076..098`, `105` | Core |
| `025..027` | leakage, rejection and no fallback | `013..014`, `022..030` | every cross-object/missing negative, especially `057`, `060..063`, `070..073`, `094`, `096`, `098`, `105` | Core |
| `028` | non-empty Scene identity tuple | `015`, `020..030` | terminal/release/Scene gates | Core |

## 5. Scene closure

| Scene | Required acceptance chain | State |
|---|---|---|
| `SCENE-01` | Object/prepare/confirm -> Run/SSE -> release -> metric/Claim/Review/CER -> A/B/C -> HTML/PDF -> reopen | `PHASE4_CORE_REQUIRED` |
| `SCENE-02` | immutable planned graph -> real replan/atomic actual graph -> added Task -> replay/reconcile -> release identity tuple | `PHASE4_CORE_REQUIRED` |
| `SCENE-03` | same-Task correction -> corrected Calculation/Evidence -> Review/check -> release-negative and positive semantics -> A/B/C | `PHASE4_CORE_REQUIRED` |
| `SCENE-04` | Report metric -> Claim -> Review -> Task -> Calculation/Evidence -> Proof when applicable -> CER -> original anchor | `PHASE4_CORE_REQUIRED` |
| `SCENE-05` | immutable applied Object versions and explicit comparison pair | `DEFINED_NOT_ACTIVATED` |
| `SCENE-06` | authoritative incremental seed and Reuse/Refresh/Revalidate/Prevent decisions | `DEFINED_NOT_ACTIVATED` |

## 6. Interaction history mapping

| Interaction ledger | E2E gate | State |
|---|---|---|
| `001..014` | `P4-E2E-001..014` | active |
| `015` | `P4-E2E-015` | retired tombstone; no execution result |
| `016..064` | `P4-E2E-016..064` | active |
| `065` clear-search | `P4-E2E-101` | active Core |
| `066` Full Research | `P4-E2E-102` | active Core |
| `067` Incremental Research | `P4-E2E-103` | active UX regression; real integrated gate Phase 5 |
| `068` incremental Task node | `P4-E2E-104` | active UX regression; real integrated gate Phase 5 |
| `069` alert retry | `P4-E2E-105` | active Core |
| `070` alert dismiss | `P4-E2E-106` | active Core |

```text
P4_E2E_GATES_REFERENCED=106/106
P4_SSE_GATES_REFERENCED=20/20
P4_ID_ASSERTIONS_REFERENCED=28/28
SCENE_01_04_COVERAGE=4/4
INTERACTION_CURRENT_COVERAGE=69/69
HISTORICAL_INTERACTION_UNION=70/70
```
