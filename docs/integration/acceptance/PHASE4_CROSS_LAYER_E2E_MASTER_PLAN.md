# Phase 4 Cross-Layer E2E Master Plan

Status: `DESIGN_READY - NOT_IMPLEMENTED - NOT_EXECUTED`  
Required topology: `E2_LOCAL_FULL_STACK_REAL_RUNTIME`

Every family proves the full chain:

```text
Browser -> production Frontend -> decoder -> private DTO -> adapter/store
-> real HTTP or fetch-stream SSE -> API -> PostgreSQL -> runtime
-> Evidence/Calculation/Review/Proof -> atomic Backend projection
-> Frontend reducer -> browser-visible state
```

A page PASS without durable/runtime truth and a Backend PASS without the user-visible outcome are both insufficient. Service workers, intercepted response fulfilment, direct store mutation, local-storage business truth, Demo sources, timer replay and data-URL artifacts are forbidden. Provider/model is selected before Run and locked; pre-lock fallback is recorded, post-lock switch is failure. Frontend financial authority is zero.

## X-E2E-01 - Create Research

Gate/slice: `IG-01 / VS-01 / SCENE-01`; data: controlled real or authoritative acceptance; environment E2.

User creates/selects Object, enters FULL Goal, prepares and inspects Scheme-only preview, confirms, then repeats double-click/lost-response cases. Prepare persists immutable draft identity/hash/version/expiry without Run/Tasks. Confirm atomically consumes it and creates one admission, Run, plan, Tasks, idempotency result, scheduler lease/outbox, one `run.created` and one effective `run.started`. The browser opens the exact R without another start action.

Reject foreign/missing Object, expired/consumed/mismatched draft, changed request under same key, duplicate admission/Run, frontend-only mode, Demo or latest substitution, provider identity drift. Evidence: actions/a11y, HTTP hashes, SQL counts, draft/admission IDs, lease/start and provider-lock ledgers. Maps `P4-BE-002..006`, create `P4-E2E`, Core identity. Manual required.

## X-E2E-02 - Live Run

Gates: `IG-01`, dynamic completion at `IG-03`; Scenes 01-03; E2.

Install atomic projection N and subscribe after N. Projection revision/sequence, Task rows, actual graph/version and event append must be one Run-consistent view. Numeric/opaque cursors yield the same suffix. Frontend fetch-stream parses split UTF-8, CRLF/LF, comments and named events; planned graph stays immutable; sparse graph events force refresh and never create a Task.

Reject direct raw-enum casts, unknown/conflicting/foreign event mutation, synthetic Task/edge, polling presented as SSE and event-only financial values. Evidence: raw frame hashes, projection/watermark, reducer disposition, connection state, DOM cardinality and control/browser equality. Maps `P4-BE-007..019`, `P4-SSE-001..020`, runtime/dynamic browser gates. Manual required.

## X-E2E-03 - Result

Gate: `IG-02`; VS-02/05; Scenes 01/03/04; E2 authoritative financial corpus.

Wait for accepted Evidence, deterministic Calculations, Review/Proof/HTML closure and release, then open Results. SQL/domain witness joins E -> K -> M -> C -> X -> L with one R. `release.completed` follows durable closure and precedes one `run.completed`. Browser values exactly equal Backend display fields, including the `0.6547 RATIO` / `65.47 %` witness.

Reject React arithmetic/rounding, Claim synthesis, missing material relation, cross-Run K/E, unknown unit, blocked Review as released, stale latest or Demo result. Evidence: response, full join, release-validation hash, event order, DOM and source-authority scan. Manual semantic inspection required.

## X-E2E-04 - Review

Gate: `IG-02`; Scenes 01/03/04; E2 with PASS plus REVIEW/BLOCK/correction runs.

Persist one Review with stable Checks, typed subjects, original status, exception/correction refs and resolved times. Run-level review events never resolve a Check by themselves. Browser exact filters and history derive from that projection and never mint per-Claim Reviews. REVIEW/BLOCK remains unreleased.

Reject array/text/timestamp inference, missing Check as PASS, client release computation, wrong Claim association, raw failure or foreign Review. Evidence: response/hash, SQL rows, events, DOM filter/count/status and focus/navigation. Manual history inspection required.

## X-E2E-05 - Trace

Gate: `IG-04`; VS-04/05; SCENE-04; E2 authoritative trace plus foreign identities.

From the originating Report Claim traverse Review Check -> Task -> Calculation -> Evidence -> Execution -> Proof -> original anchor. TraceBundle closes O/R/X/L/C/V/T/K/E/P/A; Task follows Calculation, Review follows typed subjects/reviewed refs. Hash-bound manifest has plural Review/Task/Execution and representation-specific anchors.

Frontend preserves route, overlay stack, exact IDs, focus, scroll and anchor through close/refresh/history. Reject DOM/title/text/latest/singleton mapping, foreign child, ambiguous Review, raw Execution/CoT or wrong-format return. Evidence: request/ID ledger, trace/manifest hashes, DB join, artifact anchor lookup, focus/scroll/history and sentinel scan. Manual full trace required.

## X-E2E-06 - Artifact

Gate: `IG-05`; VS-05; Scenes 01/04; E2 real stored bytes.

Fixed HTML/PDF group persists append-only attempts, Availability/reason, type/size/SHA, safe non-bearer ref and release validation. Required HTML is valid; PDF independently passes AVAILABLE, NOT_GENERATED and FAILED cases. Browser fetches only the authorized ref and independently verifies bytes/type/size/hash after restart.

Reject internal path/permanent URL/bearer secret/data URL/Demo bytes, wrong type/hash/size, cross-Run artifact, or PDF absence disabling HTML. Failures return zero protected bytes. Evidence: metadata, authorized request, raw bytes/hash, storage record, browser result and restart/tamper/cross-owner cases. Manual HTML/PDF states required.

## X-E2E-07 - Recovery

Gate: `IG-07`; all Core slices/Scenes; E2 with controlled stream fault proxy and restart controls.

Disconnect, resume numeric/opaque, inject duplicate/delay/reorder/gap, refresh/navigate, restart API/worker/PostgreSQL, clear browser storage and reopen. Valid cursors return exact suffix; invalid/foreign fails pre-header `INVALID_CURSOR`, ahead `CURSOR_AHEAD`; heartbeat has zero mutation. Exact duplicate is no-op; other disorder quarantines and triggers one snapshot. Terminal reopens without reconnect.

Reject entity swap, state regression, duplicate rows, continued reduction after quarantine, browser-cache-only recovery, polling or Demo substitution. Evidence: frames/cursors/status, recovery ledger, control/chaos hashes, DB/restart, storage clear and DOM/route/focus state. Automation exhaustive; manual smoke required.

## X-E2E-08 - Failure

Gate: `IG-07/08`; negative Scenes 01-04; E2 fault cuts.

Exercise permanent admission failure, Task/deadlock, locked provider loss/drift, Review BLOCK, Proof failure, required HTML/storage/render failure and terminal persistence retry; optional PDF failure is the nonterminal control. Every unsuccessful admitted R atomically persists terminal state/Availability/revision/watermark and exactly one last `run.failed`, zero `run.completed`, no later event or release/latest promotion. Pre-admission rollback has no terminal R. Optional PDF failure preserves valid HTML release.

Browser stays on exact failed R, shows safe Backend error and unavailable controls, stops terminal reconnect and retries only real reads. Reject success UI, report access, successful latest substitution, raw error/secrets, frontend terminal, Demo fallback, provider switch or endless spinner. Evidence: fault manifest, SQL before/after, terminal order/count, projection/availability, provider lock, HTTP/SSE, browser safe state and no-result requests. Representative manual failure required; false release is P0.

## Shared implementation surfaces

Backend: `apps/api/routes.py`, `apps/api/main.py`, `contracts/api/models.py`, application service/persistence/repository/events, runtime SSE/graph, DB composition/models/events/Phase 3 records, LLM router, financial/release/output and canonical/Review/report domains.

Frontend: `App.tsx`, API client, data/runtime interfaces and transports, domain/status/reducer/history, New/Run/Results/Object pages and path/Review/Claim/Task/artifact components. No browser-E2E path currently exists; future `apps/web/e2e/cross-layer/*` and runner/lockfile decisions are implementation-pending.

## Evidence minimum and pass rule

Every attempt records frontend/backend/build/database/environment identities, activation/data class, HTTP hashes, raw SSE and recovery, SQL transaction/restart, provider/model lock, projections and store hashes, full identity tuple/substitutions, DOM/a11y/route/history/focus/scroll, artifact bytes and append-only result. Secrets, raw providers, prompts, CoT and private paths are excluded.

```text
CROSS_LAYER_E2E_FAMILIES=8/8
CROSS_LAYER_E2E_READY=YES_DESIGN_ONLY
DEMO_AS_REAL_EVIDENCE=0
FRONTEND_FINANCIAL_AUTHORITY=0
CROSS_OBJECT_FALLBACK=0
CROSS_RUN_FALLBACK=0
PHASE5_LEAKAGE_IN_PHASE4_REAL_ACCEPTANCE=0
PHASE4_STARTED=NO
PRODUCTION_SOURCE_MODIFIED=NO
```
