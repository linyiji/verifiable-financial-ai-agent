# Phase 4A Backend Contract Acceptance Mapping

Status: `PROVISIONAL_CONTRACT_DRAFT`  
Version: `phase4-backend-acceptance/v1`  
Freeze state: `NOT_FINAL`  
Inspected backend: `codex/phase3-contracts@11fe8173a25ff7ac08bae42340ba7c6fae591be5`

This is the executable closure map for the provisional contracts. It changes no existing test or
gate. `P4-BC-*` labels name proposed backend contract cases; they become pass/fail gates only after
the approved Phase 3 SHA is reconciled and implementation is authorized.

## 1. Universal evidence and pass rule

Every applicable case retains:

- immutable backend commit and tree SHA, database migration revision, service composition, and
  exact contract/schema tokens;
- sanitized authenticated HTTP request/response ledger, including headers, status, content type,
  request ID, resource identity, and response hash;
- exact source rows and before/after cardinalities for Object, Run, Goal, Scheme, graphs, Tasks,
  events, Evidence, Calculations, Claims, Review/checks, proof, canonical, result, artifacts,
  idempotency, and scheduler admission as applicable;
- projection revision/sequence/graph-version snapshots from one committed view;
- raw and parsed SSE frames with connection index, order, event ID, sequence, and content hash;
- pre/post process restart record hashes for all persistence cases;
- independently measured artifact content type, byte length, SHA-256, and zero-byte negative
  responses; and
- authorization principal/tenant decision without credentials, tokens, provider bodies, internal
  paths, prompts, or hidden reasoning.

A case passes only when all required facts agree. HTTP 2xx, UI text, a fixture, mock call count, or
one repository record alone is not sufficient. All Core cases must pass on the same immutable
backend SHA and approved migrations. Current state for every `P4-BC-*` case is
`DEFINED_NOT_EXECUTED`.

## 2. Proposed acceptance cases

| Case | Contract and positive oracle | Negative / missing / restart / version / authorization oracle | Existing acceptance mapping |
|---|---|---|---|
| `P4-BC-001` | Global Run collection returns stable filtered pages ordered `(updated_at DESC,run_id DESC)` with exact Object/Run identities, activity, graph, progress, times, revision/sequence, and result availability | malformed, expired, tampered, or filter-reused cursor -> `INVALID_CURSOR`; unauthorized Object -> `FORBIDDEN`; same suffix and order after restart; unknown schema -> `SCHEMA_INCOMPATIBLE` | Blocker 01; `P4-E2E-002,005..007,067,070,076,098,105`; `P4-ID-006,023,025..027` |
| `P4-BC-002` | Object search and creation: normalized identity search is deterministic; same create key/request returns one Object | same key/different request -> `CONFLICT`; provider miss is explicit and never cross-company fallback; durable replay after restart; unauthorized search/detail discloses no Object | Cross-cutting Core dependency; `P4-E2E-012..016,067,098,105`; `P4-BRIDGE-003`; `P4-ID-001,023,025..027` |
| `P4-BC-003` | Prepare creates one immutable FULL, `SCHEME_ONLY` draft with Goal, Scheme, version, hashes, expiry, expected Object, and no Run/Task/graph | missing Object -> `NOT_FOUND`; same prepare key/request replays; changed request conflicts; new key regenerates a new draft; restart retains outcome; Incremental/unknown schema rejected | Blocker 04; `P4-E2E-017..024,074,102`; `P4-ID-001..003,023,025..027` |
| `P4-BC-004` | Confirm consumes the draft and atomically creates exactly one Run, plan/Tasks, initial events, and `PENDING` admission; runtime auto-starts without another click | double click/concurrency/response loss/redelivery/restart still yield one Run, one `run.created`, one effective `run.started`; changed body/key, consumed/expired/version-mismatched draft conflict; unauthorized actor cannot consume | Blocker 04; `P4-E2E-025,075,098`; `P4-SSE-002,004`; `P4-ID-004..005,007..009,023,025..027` |
| `P4-BC-005` | Atomic projection returns Object, Run, immutable plan, actual graph/version, Tasks, lifecycle, component availability, proof policy, terminal, revision and matching event watermark from one view | injected cross-Run child or aggregate/event tear yields no mixed 200; missing optional detail is typed unavailable; restart reproduces committed projection; unknown nested schema/status fails closed; foreign principal gets no body | Blocker 02; `P4-E2E-026..036,040,047,071..073,077,087..091,095,098`; `P4-SSE-012..013,020`; `P4-ID-004,006..020,023,025..027` |
| `P4-BC-006` | Numeric and same-Run opaque SSE cursor replay the identical `sequence > N` suffix; heartbeat changes no domain state; disconnect/reconnect converges | negative, signed, whitespace, leading-zero, malformed, blank, oversized, unknown/cross-Run opaque -> pre-header 400 `INVALID_CURSOR`; numeric ahead -> pre-header 409 `CURSOR_AHEAD`; restart suffix identical; incompatible payload quarantined | Blocker 03; `P4-E2E-068,078..084,087,098`; `P4-SSE-001..014,017..018`; `P4-ID-009,023,025..027` |
| `P4-BC-007` | Duplicate identical frame is a no-op; gap/out-of-order/conflicting duplicate quarantines reduction and an atomic snapshot restores exact state | no cardinality increase, regression, invented Task, or foreign event; sparse graph event forces refresh; restart preserves one graph mutation/version | Blockers 02,03,08; `P4-E2E-077,082..084,088..091`; `P4-SSE-009..013,019..020`; `P4-ID-007..010,023,025..027` |
| `P4-BC-008` | Success commits release, available HTML, `release.completed`, then exactly one `run.completed`; terminal-equal stream closes immediately with zero business frames | scheduler, post-scheduler Review/Proof/release/render/artifact/persistence and cancellation paths emit exactly one safe `run.failed` terminal and no later event; restart does not duplicate terminal; PDF may be explicitly unavailable | Blocker 03 and 06; `P4-E2E-085..087,095..098`; `P4-SSE-015..018`; `P4-ID-009,013..020,023,025..027` |
| `P4-BC-009` | Every supported raw Run/Task/Review/proof/availability/event value maps exactly once; Task progress remains ratio and aggregate exposes fraction plus percent | unknown status, event, payload version, or policy cannot cast/default or mutate the last valid projection; recovery is required; no synthetic frontend event enters ledger | Blocker 08; `P4-E2E-026,032,040..041,077,084,088..091`; `P4-SSE-002,010..011,015..016,019..020`; `P4-ID-008..010,015..016` |
| `P4-BC-010` | Lossless metric fixture preserves all semantic fields and renders canonical `0.6547 RATIO` as display `65.47 %` from backend authority | missing/mismatched material Evidence, Calculation, Claim, proof or semantic field blocks release; restart returns identical decimal strings and lineage; incompatible schema fails closed; unauthorized result returns no metric | Blocker 05 and 07; `P4-E2E-040..044,069..073,092..095,098`; `P4-ID-011..018,023,025..028` |
| `P4-BC-011` | Claim/Review/Trace round trip proves Report -> Claim -> stable Review check -> exact Task -> Calculation/Evidence -> proof -> canonical execution -> same Report anchor | substitute Claim/Task/Evidence/Calculation/Review/proof/anchor from another Run/Object -> fail closed; retained ID with missing nonmaterial body -> typed unavailable; restart preserves IDs/anchors; unknown check/proof schema fails; unauthorized actor gets no detail | Blocker 05; `P4-E2E-040..054,069,072..073,092..095,098`; `P4-ID-011..020,023,025..028` |
| `P4-BC-012` | Execution view returns same-Run canonical C data and stable sequence-ordered filtered pages without hidden reasoning | cursor/filter mismatch invalid; unknown event quarantined; safe missing retained detail explicit; restart page suffix identical; authorization prevents foreign events and text query searches only allowlisted summaries | Blockers 03,05,08; `P4-E2E-054,068,073,079..084,094..095,098`; `P4-SSE-002..013,018`; `P4-ID-009,017..018,023,025..027` |
| `P4-BC-013` | Artifact group has fixed HTML/PDF slots, exact O/R/X/L/report binding, available mandatory HTML, separate IDs, and honest PDF availability | missing optional PDF is explicit; swapped/wrong-Run/wrong-Object ID, bad media/hash/size, denied path, or tampered bytes returns no bytes; restart preserves metadata/bytes; unknown renderer/schema fails; no raw locator crosses boundary | Blocker 06; `P4-E2E-045..049,067,072..073,095..096,098`; `P4-ID-018..020,023,025..027` |
| `P4-BC-014` | Released Object Core chooses newest fully valid same-Object release by `(released_at DESC,run_id DESC)` and exact historical Run links reopen it | newer draft/running/failed/cancelled or another Object's release never supersedes; no-release returns null plus typed `NOT_RELEASED`; restart selection identical; corrupt/unknown closure withheld; unauthorized Object not disclosed | Blocker 07; `P4-E2E-003,057,059(core),060..061,063,070,072..073,076,092,094,096,098`; `P4-ID-001,006,013..020,023,025..027` |
| `P4-BC-015` | Error table exercises each code with exact HTTP, retryable, recovery, request/resource identity and allowlisted details | redaction corpus proves no paths, raw provider bodies, SQL, credentials, stack traces, prompts, or hidden reasoning; retry preserves entity/route identity; unknown contract version returns `SCHEMA_INCOMPATIBLE` | Cross-cutting; `P4-E2E-023,073,086,105..106`; `P4-SSE-018`; `P4-ID-025..027` |
| `P4-BC-016` | Availability transition table exercises `PENDING`, `AVAILABLE`, `NOT_GENERATED`, `NOT_RELEASED`, `UNAVAILABLE`, and `FAILED` with stable reasons | terminal Run cannot remain pending; unavailable mandatory release child blocks release; optional retained-detail loss keeps ID; transient error retains stale state without advancing; unauthorized data is never encoded as availability | Cross-cutting; `P4-E2E-023,046,051..054,086,092,095..096,105`; `P4-ID-013..020,025..027` |
| `P4-BC-017` | Schema negotiation: absent or exact `phase4-core/v1` request selects exact reviewed V1; every DTO/event exposes its frozen token/version | malformed or other major/minor token, absent required response token, and unsupported payload version return/quarantine as specified with no coercion; behavior persists across restart and respects authorization | Cross-cutting; `P4-E2E-032,077,084,088,105`; `P4-SSE-011..013,018`; `P4-ID-023,025..027` |
| `P4-BC-018` | Full persistence witness restarts API and worker against PostgreSQL and artifact storage and reproduces O/R/T/C/V/A/K/E/X, events, unavailable reasons, admissions, and artifact bytes | no process-memory-only acceptance substitution; kill between transaction, lease, render, terminal and response boundaries; redelivery remains idempotent and foreign principal remains unauthorized | Blockers 02–06; `P4-E2E-075,079..081,087,098`; `P4-SSE-007..009,013,017`; `P4-ID-005,009,011..020,023,025..027` |

## 3. Source-of-truth ownership

| Contract family | Authoritative records | Projection may do | Projection must not do |
|---|---|---|---|
| Object / collection | `ResearchObject`, exact object-owned `ResearchRun` records | filter, sort, count, select validated latest release | provider/company fallback, infer Object from ticker text |
| Prepare / confirm | durable draft, Goal, Scheme, idempotency outcome, Run, graphs/Tasks, admission/outbox | hash canonical request, expose replay metadata | invent preview Tasks, schedule twice, rely on process cache |
| Run projection | Run aggregate, actual graph, Tasks, durable event ledger and assurance/output records | normalize, redact, assemble one snapshot | mix read times, use elapsed progress, infer missing relations |
| Runtime / SSE | per-Run durable RuntimeEvent rows and checkpoint/event watermark | version/redact payload, map status, signal refresh | rename raw event, fabricate Task, treat heartbeat as event |
| Finance / trace | accepted Evidence, deterministic Calculation, Claim, Review, proof policy/verification, canonical, result | exact joins and availability wrappers | arithmetic, text/first/latest joins, expose provider payload or CoT |
| Artifacts | immutable artifact metadata and stored bytes bound to O/R/X/L | group HTML/PDF, authorize path, verify bytes | expose internal locator, treat metadata possession as authorization |

## 4. Required catalogue reconciliation before activation

The provisional contract resolves two stale catalogue statements; the later final delta must update
their expectations rather than weaken this contract:

- `P4-BE-001`: expected collection order becomes `(updated_at DESC,run_id DESC)` and requires a
  truthful durable `updated_at`.
- `P4-BE-014`: numeric ahead-of-tail is specifically HTTP 409 `CURSOR_AHEAD`; it is not
  `INVALID_CURSOR` or an implementation-chosen equivalent.

The shared catalog currently lacks dedicated rows for exhaustive error-envelope/redaction,
availability transitions, schema negotiation, noncanonical/ahead/terminal-equal cursors, Object
search/create idempotency, and execution filtering/pagination. `P4-BC-002`, `006`, `008`, `012`,
and `015..017` are the exact proposed closure rows. This is acceptance ownership, not a ninth V17
blocker and not test modification.

`P4-BE-002` must map prepare identity only to `P4-ID-002..003`; Run identity begins at confirm and
maps to `P4-ID-004..005`.

## 5. Phase boundary and activation

`P4-E2E-101` and `106` remain frontend-only Core behavior. `P4-E2E-102` is covered by FULL
Scheme-only prepare. `P4-E2E-103..104`, `062`, `097`, `P4-ID-021..022`, real Scenes 05/06,
Object/View versions, comparison, memory, incremental, freshness/reuse/refresh/revalidate/prevent,
writeback, POT, and capability certification/global registry remain Phase 5 or later.
`P4-E2E-099..100` remain deployment-activated; `P4-E2E-015` remains a tombstone.

Activation requires the immutable Phase 3 candidate, independent Backend audit PASS, Financial
Semantics audit PASS, final contract delta reconciliation, authorized implementation, and then
execution of this map. Nothing in this draft activates production work.
