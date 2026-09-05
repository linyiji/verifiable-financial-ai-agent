# Phase 4 Frontend Browser E2E Master Plan

Status: `AUTHORITATIVE_DESIGN - NOT_IMPLEMENTED - NOT_EXECUTED`  
Frontend parent: `FRONTEND_BASELINE_V8.1@d854c97789c98cca14fee3f4b3d7f00e0d5d137a`  
Approved V17 R2: `fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19`  
Backend contract set: `0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741`

Production-counting execution is pinned browser -> content-addressed production Frontend -> versioned decoder -> private DTO -> normalized adapter -> immutable store/reducer -> real HTTP/fetch-stream SSE -> exact Backend -> PostgreSQL/runtime -> Backend projection -> browser. An independent recorder captures Backend truth. Harness route fulfilment, fake events, direct store setters, browser business state, Demo fixtures and Presenter state are prohibited.

## Browser invariants

- Pages never consume raw Backend JSON; only the shared decoder/adapter sees wire DTOs.
- The Frontend never calculates, rounds, infers units, repairs, promotes, or merges financial truth.
- URL/request/response/projection/event/DOM/accessibility/store identities agree; no cross-Object, cross-Run, title, symbol, metric, latest or first fallback.
- Unknown schema/enum/event/payload/identity/cursor/conflicting duplicate fails closed with zero business or cursor mutation.
- Stale state is visibly stale. Connection failure changes transport presentation, never Run truth.
- Sparse graph events trigger projection refresh; they do not create Tasks or dependencies.
- HTML is required for release; PDF has independent optional Availability.
- Retry repeats the same failed read and entity; dismiss mutates alert presentation only.
- Demo/Presenter evidence contributes zero to production acceptance.

## Namespace and interaction custody

Current production interactions are `001..014` plus `016..070` = 69. `015` is an immutable retired tombstone with `result=null`, never reused. The historical union is 70/70.

The current authoritative `P4-E2E-001..106` contains 99 unique Phase 4 Core IDs. `015` is tombstoned; Phase 5-only `062/097/103/104` and the Incremental `058` and versioned `059` variants are inactive; deployment `099..100` is inactive in Phase 4A; `101..106` is the approved append-only delta.

| Reservation | Intent | State |
|---|---|---|
| `071` / `P4-E2E-107` | Execution actor filter | `RESERVED_NOT_ACTIVE`, proposed Core |
| `072` / `P4-E2E-108` | Safe Execution search | `RESERVED_NOT_ACTIVE`, proposed Core |
| `073..076` / `P4-E2E-109..112` | Presenter select/reset/previous/next | `RESERVED_NOT_ACTIVE`, Demo-only |

These IDs are outside the current result matrix until a governed append-only activation. Presenter gates can never enter real Phase 4 acceptance.

## FE-E2E-1 - Object and New Research

Cover `/new`, `/objects`, Object detail and collections: create/select/search/clear/cancel/retry/dismiss, Goal and FULL choice. Assert exact Object/return-route identity, request-bound creation, zero mutation for close/cancel/clear/dismiss, loading/empty/error/unavailable, and safe missing/foreign Object handling. No default NVDA/Demo or latest fallback. Gate: `IG-01`.

## FE-E2E-2 - Scheme Preview and Confirm

Goal validation -> real prepare -> Scheme-only preview/regenerate -> exactly-once confirm -> admitted Run. Use `PreparedResearchDraft` and `ConfirmRunResponseV1`; no local Scheme/Task/graph. Expired/mismatched/consumed draft and changed request under one key fail. Lost response and double activation return the same Run. Gate: `IG-01`.

## FE-E2E-3 - Run Workspace

Cover Run list/detail, lifecycle, planned/actual/compare, Tasks/drawer and terminal reopen. DOM status/graph/Task IDs equal `RunProjection`; direct-load, mixed identity, refresh and clean-browser variants are mandatory. Stage tabs are presentational. Gate: `IG-01` and dynamic completion at `IG-03`.

## FE-E2E-4 - SSE Live Progression

Use actual fetch-stream `text/event-stream`, not native `onmessage` assumptions or polling. Cover split UTF-8, LF/CRLF, comments, named events, numeric/opaque resume, invalid/ahead pre-header errors, heartbeat, duplicate, delay, reorder, gap, unknown and terminal close. Exact duplicates are no-ops; other conflicts trigger one snapshot recovery and zero rejected mutation. Gate: `IG-01`; all `P4-SSE-001..020`.

## FE-E2E-5 - Dynamic Path

Planned graph -> Backend-approved Replan -> actual Task/edge/version -> same-Run continuation. Only approved Phase 4 change types. Planned graph remains immutable; one Backend mutation creates one version/history change. Open trigger/added/affected Tasks by ID. Reject cycles, duplicates, cross-Run refs, unknown/deferred kind, local Task construction and Demo label substitution. Gate: `IG-03`.

## FE-E2E-6 - Financial Results

Released Run -> Results -> exact Backend metric/Claim -> A/B/C closure. Visible value/unit/period/actuality/as-of equals `ReleasedFinancialMetric`; mandatory witness uses Backend `0.6547 RATIO` and `65.47 %`. Reject parse/multiply/round, missing lineage, unknown unit, blocked Review or Demo/latest result. Gate: `IG-02`.

## FE-E2E-7 - Financial Review

Open complete/exception and all/open/resolved views and follow exact Check/Claim/Task relations. Counts and stable IDs come from one `FinancialReviewProjection`; filters mutate presentation only. Review `REVIEW/BLOCK` never enables release. Correction history survives refresh/restart. Gate: `IG-02`.

## FE-E2E-8 - Execution

Open typed Execution C for the exact R/X and show only allowlisted structured facts. Prohibit prompts, raw completions/provider bodies, CoT, secrets, internal paths and raw stringify. Proposed `071/107` filter and `072/108` search remain excluded until activated. Gate: `IG-04` support.

## FE-E2E-9 - Claim Trace

Report anchor -> Claim -> Review Check -> Task -> Calculation -> Evidence -> Execution -> Proof -> original representation anchor. Assert all IDs before transitions; test nested drawers, Back/Forward, refresh, focus/scroll/highlight and foreign/missing substitutions. No DOM/text/latest fallback. Gate: `IG-04`.

## FE-E2E-10 - Report, HTML and PDF

Open exact released report and authorized HTML bytes; handle distinct optional PDF. Metadata, type, size, digest, O/R/A and anchor agree. Missing/corrupt/wrong-hash/cross-owned artifact returns no bytes. PDF absence is explicit and never substitutes HTML or Demo. Gate: `IG-05`.

## FE-E2E-11 - Recovery, Refresh and Reconnect

Cover lost confirm response, disconnect, Backend/PostgreSQL restart, hard reload, Back/Forward, clean browser and terminal reopen. Preserve R, install authoritative snapshot, resume one stream after N, prevent duplicate mutations, clear browser storage for restart proof, and stop reconnecting after terminal. Gates: `IG-06/07`.

## FE-E2E-12 - Errors, Unavailable and Blocked

Cover loading/empty/validation/read failure, unavailable Claim/artifact/PDF, blocked release, unknown values, stale state, retry and dismiss. Render exact safe `ErrorEnvelope`/`Availability`; disabled actions make no forbidden request; unknown fails closed. Applies at every Phase 4 gate.

## Routing, keyboard and responsive matrix

Logical routes `/new`, `/runs`, `/objects`, `/objects/{objectId}`, `/runs/{runId}` plus reviewed URL state for tab/Claim/Task/origin/anchor must survive direct load and history. Mixed routes show safe unavailable/not-found and never redirect to latest.

Modals require accessible name, initial focus, Tab trap, inert background, scroll lock, top-overlay Escape and trigger focus restoration. Tabs support selected state and roving keys. Progress, stale/reconnect and empty/error states are announced. Disabled PDF/Incremental/trace actions expose a reason and issue no request.

Pinned visual matrix: Chromium at widths 1024, 1280, 1366, 1440 and 1920; height 900, DPR 1, zoom 100%, `zh-CN`, `Asia/Shanghai`, primary 1366x900. Fail document overflow, clipped actions, lost identity/availability, bad order/focus, unfit overlays or unwrapped long values. Manual review supplements but cannot override automation.

## Environments and data

| Environment | Browser use | Data | Release contribution |
|---|---|---|---|
| E0 | reducer/layout/a11y/Demo compatibility | contract, synthetic, labelled Demo | none for real gates |
| E1 | adapter/API/persistence preparation | contract, synthetic, controlled real | supporting |
| E2 | primary full-stack Core acceptance | authoritative acceptance/controlled real; live provider separately labelled | Phase 4 Core |
| E3 | Preview parity | same manifested corpus | IG-09 |
| E4 | cold-start/release/provider/network | authoritative plus permitted live data | IG-10 |

## Evidence and pass rule

Bind Candidate SHA/tree/build/lock/toolchain, contract/database/browser/environment hashes, attempts, HTTP hashes/IDs, raw SSE frames/cursors/dispositions, projections and browser store/route/DOM/a11y/focus/scroll, artifact metadata/bytes, Backend-to-DOM financial/Review/Execution/Trace joins, logs and screenshots. Exclude secrets, prompts, raw model/provider data, CoT and private paths.

Once activated, a required gate is PASS or FAIL; blocked/skipped/not-run/incomplete evidence fails the release aggregate. Tombstones/inactive gates retain null. Family PASS is conjunctive across positive, negative, identity, availability and recovery cases.

```text
FRONTEND_E2E_FAMILIES=12/12
CURRENT_ACTIVE_INTERACTIONS=69/69
HISTORICAL_INTERACTIONS=70/70
TOMBSTONES=1/1
PHASE4_CORE_P4_E2E_IDS=99
P4_SSE_GATES=20/20
FRONTEND_CONTRACTS=13/13
RESERVED_INTERACTIONS_ACTIVE=0/6
PHASE5_LEAKAGE_IN_PHASE4_REAL_ACCEPTANCE=0
DEMO_AS_REAL_EVIDENCE=0
FRONTEND_FINANCIAL_AUTHORITY=0
CROSS_OBJECT_FALLBACK=0
CROSS_RUN_FALLBACK=0
PRODUCTION_SOURCE_MODIFIED=NO
```
