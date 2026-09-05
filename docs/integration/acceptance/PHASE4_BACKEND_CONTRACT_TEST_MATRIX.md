# Phase 4 Backend Contract Test Matrix

Status: `PROVISIONAL_EXECUTABLE_TEST_DESIGN — NOT IMPLEMENTED — NOT EXECUTED`  
Companion authority: `PHASE4_BACKEND_ACCEPTANCE_GATE_CATALOG.md`  
Gate range: `P4-BE-001..030`

This matrix makes the positive and negative contract variants mandatory for every backend gate.
It is a future harness specification, not test code. No row may be reported `PASS` until its
unresolved `UAC-*` decisions are frozen, the candidate is immutable, and all seven variant classes
applicable to the contract have executed. “Not applicable” is not a shortcut: where a route is
read-only, the persistence/restart oracle proves no mutation and durable reproducibility; where a
body has no version request field, the unknown-version oracle exercises the frozen content-
negotiation mechanism and consumer rejection of an incompatible response.

The matrix also consumes the newly available provisional V17 preparation artifacts:
`V17_FRONTEND_CONTRACT_PREPARATION.md` (`13/13` named normalized contracts prepared) and
`V17_FRONTEND_BACKEND_DEPENDENCY_MATRIX.md` (`BD-001..012` all open). Their camelCase shapes define
frontend decoder/normalization requirements, not a final backend wire freeze. Backend responses
remain private snake_case DTOs until the approved Phase 4 contract fixes exact schemas; every
backend-to-V17 mismatch identified below remains governed by `UAC-002`, `008`, `013`, `016..018`.

## 1. Harness and corpus contract

The future harness should extend the repository's proven patterns without treating them as current
Phase 4 evidence:

- FastAPI `TestClient` contract/error testing from `tests/integration/test_application_flow.py`;
- async service and replay tests with complete event-envelope checks;
- the target PostgreSQL composition, restart, contiguous-sequence trigger, record repositories,
  and checkpoint restoration used by `tests/postgresql/*` and
  `scripts/run_real_infrastructure_acceptance.py`;
- independent artifact byte/hash verification patterns used by Phase 3 reporting acceptance;
- sanitized Langfuse/reference hooks only as observability evidence, never as domain truth;
- real `text/event-stream` parsing. Direct event-store replay is a backend integration oracle but
  cannot alone satisfy a browser/SSE E2E gate.

Each execution provisions two distinct Objects and complete identity tuples:

```text
A = (O-A, R-A, T-A, C-A, V-A, A-HTML-A/A-PDF-A, K-A, E-A, X-A)
B = (O-B, R-B, T-B, C-B, V-B, A-HTML-B/A-PDF-B, K-B, E-B, X-B)
```

Names, symbols, titles, metric names, and selected values deliberately collide so that only IDs
can close a join. The corpus includes live/nonterminal, successful terminal, failed terminal,
missing optional detail, unavailable required material output, invalid Review/Proof closure,
separate HTML/PDF availability, and at least 26 collection rows. Every setup record is created
through an acceptance-owned factory or supported public workflow and is listed in the evidence
manifest; frontend fixtures never seed an integrated gate.

The seven mandatory variant classes are:

| Code | Variant | Universal oracle |
|---|---|---|
| `POS` | Positive | Exact success schema, identity, semantics, headers and cardinality; no unspecified fallback. |
| `IDN` | Identity-negative | Substitute B into A at every accepted ID edge; fail closed before mixed data/bytes. |
| `MIS` | Missing-data | Optional absence uses exact `AvailabilityV1`; required absence fails; never null/empty/zero as fake success. |
| `VER` | Unknown-version | Unsupported request/response/schema/event/policy version returns or causes `SCHEMA_INCOMPATIBLE`; no downgrade/coercion. |
| `RST` | Restart | Recreate API/worker/repositories/browser client against the same PostgreSQL/artifact state; identity and result are durable. |
| `AUT` | Authorization | Denied actor/tenant receives the frozen concealed-not-found or forbidden response, no data/bytes, and no mutation. |
| `INT` | Integrity | Tampered hashes, refs, sequences, cardinalities, media, or transaction tears are rejected; server does not repair on read. |

All final test records contain `attempt_id`, candidate/backend-parent SHAs, database revision,
schema/event/route versions and hashes, source class, environment, timestamp, result, failure,
rerun reason, whether source changed, and final disposition. A failed attempt is append-only
evidence. Source changes create a new candidate; unchanged-source reruns state the environmental or
nondeterministic cause. No raw licensed provider bodies, credentials, DSNs, local storage paths, or
hidden chain-of-thought are retained.

## 2. Contract-variant matrix

| Gate | `POS` positive case | `IDN` identity-negative | `MIS` missing-data | `VER` unknown-version | `RST` restart case | `AUT` authorization case | `INT` integrity case |
|---|---|---|---|---|---|---|---|
| `P4-BE-001` | Page 25 of 26+ Runs; exact V1 fields/order/filter, ratio+method progress authority and opaque next cursor; GET changes zero rows. Final freeze binds whether percent is wire-carried or normalized once in the adapter. | Filter A and inject B row/cursor; B is absent and filter-mismatched cursor is `INVALID_CURSOR`. | No Runs → `items=[]`, `next_cursor=null`; missing required item field rejects serialization. | Unsupported collection/cursor version → `SCHEMA_INCOMPATIBLE`, never offset fallback. | Same dataset+cursor returns same suffix after API restart. | Actor denied O-B cannot enumerate its Runs or infer counts. | Tampered/filter-rebound cursor, duplicate order tuple, or false `updated_at` fails; no partial page. |
| `P4-BE-002` | FULL prepare with K1 creates one V1 draft/Goal/unconfirmed Scheme and zero Run/Task/graph rows; identical K1 replays it, while new K2 regenerates a distinct draft. | Prepare O-B as A-only actor or mismatched Goal/Scheme O; safe failure, zero partial rows. | Missing/unknown O or goal → validation/not-found; no draft. | Unknown mode/draft schema → `SCHEMA_INCOMPATIBLE`; `INCREMENTAL` is not coerced. | Draft/version/hash/expiry, request-bound K1 outcome, and children reopen unchanged. | Unauthorized O fails before generation and disclosure. | Same K1 with changed request hash, wrong Goal/Scheme join or expiry rejects; replay cannot duplicate, and K2 cannot mutate K1's draft. |
| `P4-BE-003` | `SCHEME_ONLY` contains exact requirements/metadata/limitations and `confirmed_at=null`; regeneration is new identity. | Scheme Goal/Object B under draft A is rejected. | Generator missing/failed output produces typed failure and no empty-success Scheme. | Unknown Scheme/generator contract version fails; no guessed parsing. | Stored Scheme/hash is byte/semantic equivalent after restart. | Authorization checked before Scheme generation/readback. | Mutation of prior Scheme or premature confirmation timestamp fails immutability check. |
| `P4-BE-004` | First K/H → 201 R; retries before/after response loss → 200 same R and immutable admission with replay metadata. | Actor/tenant/draft B changes H and fails; no cross-scope key reuse. | Missing key/draft/version/body → typed validation/conflict, zero Run. | Wrong `draft_version` or admission schema → conflict/`SCHEMA_INCOMPATIBLE`; no downgrade. | Same K/H returns same durable outcome after API/worker restart. | Denied actor cannot consume/replay another actor's draft/key. | Same K/different H, altered canonicalization, or partial outcome fails without changing original. |
| `P4-BE-005` | Concurrent same confirmation yields one R/graph/Task set/initial log/outbox/outcome in one transaction. | Same draft B/Run A substitution cannot create/reparent either aggregate. | Planner/Task/admission data missing causes full rollback. | Unknown draft/admission/graph version rejects before commit. | Counts remain one after restart and admission redelivery. | Unauthorized confirm consumes nothing. | Commit-boundary fault proves all-or-nothing; duplicate Run/event/outbox fails. |
| `P4-BE-006` | Confirmation alone starts R once; one durable start state/timestamp/event. | Forged R-B admission cannot start R-A or vice versa. | Missing durable admission means no start and a visible operational failure, not process-local magic. | Unknown admission/event version is quarantined and emits no start effect. | Pending admission starts once after restart; completed admission does not restart. | Unauthorized execute-like call/admission has no effect. | Duplicate/redelivered admission cannot duplicate `run.started`, tasks, or effects. |
| `P4-BE-007` | One atomic V1 snapshot/ETag matches one DB view across all required aggregates, availability states and the frozen mutation-history/`pathChanges` representation. | Seed nested B Task/Claim/Review/artifact into A; projection fails rather than mixes. | Optional domain absent → typed availability; missing O/R or required release closure → failure. | Unknown projection schema/embedded enum → `SCHEMA_INCOMPATIBLE`, no partial DTO. | Rebuild gives identical terminal IDs and nondecreasing revision/sequence. | Denied actor receives no projection or nested-existence hints. | Torn event/aggregate state, bad ETag, cross-ref, or non-atomic read is rejected. |
| `P4-BE-008` | Snapshot at N includes exactly mutations through N; replay from N starts N+1. | R-B watermark cannot resume/reconcile R-A. | Legitimate no-event aggregate uses 0; missing watermark on live projection fails. | Unknown watermark/event-contract version or noninteger sequence fails. | Same N/suffix survives database/API restart. | Unauthorized cursor cannot disclose whether R/event exists. | Watermark ahead of reflected state or behind an included mutation fails atomicity. |
| `P4-BE-009` | Starts >=1; each frozen projection-affecting transaction increments once; reads/rollbacks do not. | R-B ETag/revision cannot produce A `304`/success. | Missing revision is invalid, never inferred from time/event count. | Unknown revision/schema version fails conditional and normal reads. | Last revision and next monotonic value persist after restart. | Denied conditional request reveals no current revision. | Retry/no-op double increment, regression, collision, or nontransactional value fails. |
| `P4-BE-010` | Same-revision list/detail/projection agree on O/R/status/as-of/timestamps/lifecycle/graph/availability. | Open R-B from A row/history; reject or wholly switch to B, never mixed. | Missing exact R is not-found/unavailable; never latest R. | Mismatched list/detail schema or status-map version fails reconciliation. | Terminal list/detail remain identical after restart. | Collection visibility and detail authorization cannot disagree/leak. | Same-revision semantic mismatch or fabricated progress/activity fails. |
| `P4-BE-011` | Numeric N returns actual SSE suffix N+1..M with exact envelope and no store mutation. | Numeric position from B cannot authorize or satisfy A; every frame remains R-A. | No later event: terminal closes empty; nonterminal only heartbeat, no domain mutation. | Unsupported SSE/event version or wrong media negotiation fails before frames. | Byte/semantic suffix equals pre-restart oracle. | Unauthorized R returns no stream/business frames. | Missing/duplicate/resequenced/wire-vs-data mismatch fails exact range. |
| `P4-BE-012` | Opaque E at N yields exactly the numeric-N suffix. | E-B against R-A is invalid; no global lookup. | Unknown E → invalid cursor; no replay zero. | Unsupported opaque cursor/event schema version fails closed. | E→N mapping and suffix survive restart. | Denied actor cannot test existence of E. | Ambiguous/duplicate E, wrong resolved N, or changed suffix fails. |
| `P4-BE-013` | Each invalid class returns bounded safe non-2xx and zero frames/mutations. | Other-Run E is invalid without leaking owner. | Blank/malformed/unknown/negative cursor follows the frozen error table. | Unknown cursor encoding/version → `SCHEMA_INCOMPATIBLE`/`INVALID_CURSOR` as frozen. | Error class/disclosure stable after restart. | Denied actor is checked before cursor existence disclosure. | Oversized/tampered token cannot crash, scan globally, or replay zero. |
| `P4-BE-014` | Cursor M+1 promptly returns the frozen ahead response and zero frames; V17 proposes `CURSOR_AHEAD`, while final code/status remains unresolved. | Higher valid sequence from B is still ahead/invalid for A. | Empty log: 0 is origin; positive cursor is ahead and rejected. | Unknown numeric-cursor contract version is incompatible, not treated as decimal. | Same max/ahead rejection after restart. | Denied actor receives no maximum-sequence clue. | Huge integer/overflow/tampered value cannot heartbeat forever, wrap, or mutate. |
| `P4-BE-015` | Valid closure yields release.completed < exactly-one run.completed, stream close, RELEASED/AVAILABLE final snapshot. | Terminal/result/canonical/review/proof/artifact ref from B rejects release. | Any required material/review/proof/canonical/result input absent prevents success and follows failure contract. | Unknown release-policy/terminal payload/status version cannot be accepted as success. | Terminal stream/result/history reopen exactly; no reconnect loop. | Unauthorized caller receives no release/result/stream content. | Wrong order, duplicate/missing terminal, invalid closure/hash/ref fails gate. |
| `P4-BE-016` | Each real failure boundary yields exactly one last `run.failed`, FAILED projection, no released Results. | Failure/audit record from B cannot complete A's failure state. | Missing safe reason or terminal event is failure of this gate; missing result remains explicitly unavailable. | Unknown failure-event/status version is quarantined and acceptance fails, never mapped to success. | FAILED state/cursor/reason survive and execution does not resume. | Unauthorized caller gets no exception/detail disclosure. | Duplicate/missing terminal, partial release, unsafe exception, or Demo tail fails. |
| `P4-BE-017` | Pre/post restart aggregate/events/review/result/A/B/C/artifacts and cursor suffixes match exactly. | Restore/replay cannot attach B rows or artifact storage to A. | Any missing durable entity fails closed; no fixture/latest reconstruction. | Unknown DB/schema/event version blocks startup/replay safely until migrated; no silent decode. | Restart is repeated across confirm/start/live/terminal boundaries; exactly-once identities persist. | Recreated service rechecks authorization rather than trusting cache. | Hash/cardinality/sequence/next-value differences or duplicate delivery effects fail. |
| `P4-BE-018` | Every frozen raw event maps once with identity/type/sequence/ratio and exact semantic effect. | Event/Task/capability/replan/correction B in A is rejected/quarantined. | Missing required payload field is incompatible; missing optional field follows exact schema default only. | Unknown type/payload/map version fails or invokes frozen refresh policy; never coercion. | Same raw log maps identically under same mapper hash after restart. | Unauthorized stream/projection exposes no normalized events. | Scale change, semantic conflation, fabricated type/default, or mutation of raw event fails. |
| `P4-BE-019` | Sparse graph frame triggers refresh; one actual-graph version with full Task/edges; plan unchanged. | Sparse B frame/snapshot cannot mutate or reconcile A. | Missing Task definition in event is acceptable only because refresh supplies it; missing in snapshot fails. | Unknown graph/mutation/schema version triggers incompatible/reconcile, not application. | Actual graph/version/history restore exactly. | Denied projection refresh reveals no graph. | Gap/order tear, invalid edge/cycle, double version, fabricated Task, or changed plan fails. |
| `P4-BE-020` | Wire M preserves all canonical/display/period/actuality/as-of/currency/lineage/method/limitation fields exactly. | Same-name M/K/C/E/Proof from B fails exact joins. | Optional nullable fields stay explicit; any required semantic/lineage field missing blocks release. | Unknown metric/unit/period/policy schema fails; no lossy downgrade. | Exact decimal strings/enums/refs remain identical. | Denied result/Claim route exposes no metric. | M↔C value/unit/period/as-of or K/E/Proof mismatch fails release/projection. |
| `P4-BE-021` | Canonical `0.6547` RATIO and display `65.47` `%` are exact in every backend projection. | Colliding B metric cannot replace A's M. | Missing display value/unit or canonical label blocks release; no unlabeled value. | Unknown unit/decimal contract version fails without conversion. | Values are byte-equivalent after restart. | Unauthorized caller receives no value. | `0.6547%`, `65.47 RATIO`, float drift, read-time recalculation, or repaired value fails. |
| `P4-BE-022` | Claim V1 returns exact O/R/C/M/all T/K/E/Proof/V/X/result/anchors and safe bodies. | C-B under R-A, E-B/K-B in C-A, or T by matching title fails. | Missing retained E/K body may be `UNAVAILABLE` with ID/reason; missing required ID/Claim fails. | Unknown Claim/detail/Judgment schema fails; no arbitrary JSON heuristic. | Same Claim/refs/availability reopen. | Denied caller receives no Claim or raw body/path. | M/C/K/E/V/X mismatch, guessed primary Task, duplicate refs, or raw locator fails. |
| `P4-BE-023` | One V1 Review projects exact V/check IDs, subjects, refs, exceptions, corrections and history, plus exact X/result binding for released A/B/C closure under the final field/nullability freeze. | V/C/K/T-B under R-A fails; no synthetic per-Claim V. | Nonterminal absent Review uses PENDING; released Run without valid V fails release. | Unknown Review/Check/status/exception schema is incompatible, not cast. | Stable check/correction IDs and resolution history reopen. | Denied caller sees no Review/check facts. | Array-position IDs, conflicting status, false resolved history, input-hash mismatch, or X/result mismatch fails. |
| `P4-BE-024` | Exact M→C→V→T→K→E→Proof→Execution→originating report anchor closes one tuple. | C/E/K/V/A-B, historical-to-latest, title/symbol/metric fallback all fail. | Missing body may retain typed unavailable ID; missing required identity/anchor fails trace/release as applicable. | Unknown Trace/anchor schema or scope version fails, no partial chain. | Entire tuple/anchor manifest reopens unchanged. | Denied caller receives no partial trace or anchor existence. | Broken/cyclic/mixed refs, nonorigin anchor, mutated manifest, or hidden-reasoning field fails. |
| `P4-BE-025` | Group V1 has O/R/report=result/X, accurate availability, distinct HTML/PDF records and safe refs. | A-B metadata under R-A fails and leaks nothing. | PDF absent → `NOT_GENERATED`+reason and null artifact ID/byte metadata/ref, as both provisional drafts specify; AVAILABLE missing hash/size/ref always fails. | Unknown group/format/renderer schema fails; SVG cannot substitute for HTML/PDF. | IDs/availability/hashes survive storage/process reopen. | Denied actor receives no metadata or usable ref. | Raw path, reused HTML/PDF available identity, wrong MIME/hash/size/renderer, or report binding fails. |
| `P4-BE-026` | Authorized ref returns exact bytes plus type/length/digest/ETag/safe disposition. | A-B under R-A returns denial with zero bytes; no A-A fallback. | Missing/unavailable bytes return typed error/availability and zero bytes. | Unsupported media/schema/digest negotiation fails before body. | Durable bytes still verify; authorization is reevaluated. | Denied/expired/revoked actor/ref receives zero bytes and no locator. | Mismatch/tamper/truncation/swap returns `INTEGRITY_FAILURE`, never partial bytes. |
| `P4-BE-027` | Independently recomputed HTML/PDF hash, size and media match metadata/headers/body. | B bytes behind A metadata are withheld. | Missing content is unavailable/integrity failure, not empty 200. | Unknown digest/media algorithm/version fails closed. | Same verification result after restart/storage reopen. | Integrity diagnostic does not bypass authorization or disclose bytes/path. | Same-size edit, truncation, MIME/charset change, HTML/PDF swap, wrong digest all yield zero-body failure. |
| `P4-BE-028` | Released Object V1 selects newest valid same-O release and returns lossless metrics/Claims/artifacts. | B release/current state never appears under O-A. | No valid release → typed nonavailable/null IDs; never lossy `/financials` fallback. | Unknown object/release-policy schema is incompatible. | Latest/historical immutable state survives restart. | Denied O exposes no Run counts/latest/value. | Invalid Review/Proof/material closure, source/latest mismatch, mutated old release, or Phase5 field fails. |
| `P4-BE-029` | Exact eligible set ordered `(released_at DESC,run_id DESC)` yields one consistent latest R. | Globally newer R-B never wins O-A. | No eligible Run → null/nonavailable; no first/newest-nonterminal fallback. | Unknown release-policy/order schema fails selection. | Same selection after restart. | Denied actor cannot infer latest ID/time/count. | Equal-time tie, invalid closure, changed order, inconsistent surfaces, or historical redirect fails. |
| `P4-BE-030` | Every exact A request succeeds; all A/B substitution cases fail closed with zero mutation. | Run/Claim/Task/Review/Artifact/Evidence/Calculation B under A plus latest/history/shared-state cases all reject. | Unknown/missing ID is not-found/unavailable with no latest/first/title/symbol/metric repair. | Unknown identity/auth/error schema is incompatible, not normalized heuristically. | Rejections and legitimate tuples remain stable; caches are empty/re-authorized. | Differential actors prove tenant/Object authorization before disclosure for every route and byte read. | Reparented row, mixed tuple, cache poisoning, fallback, partial body, or cross-object sentinel fails. |

## 3. Gate-to-suite execution ownership

| Future suite | Gates owned | Required source class | Minimum retained evidence |
|---|---|---|---|
| API schema/negative contract | `001..004`, `007`, `009..010`, `018`, `020..025`, `028..030` | `INTEGRATED`, optionally repeated `PUBLIC_REAL`/`LIMITED_REAL` | HTTP ledger, schema hashes, DB oracle, identity substitutions, safe errors |
| PostgreSQL transactional/restart | `004..009`, `015..017`, `019`, `025..029` | `OFFLINE_INTEGRATED` or manifested integrated environment using target PostgreSQL | DB revision, transaction/cardinality ledger, pre/post snapshots, restart/process manifest |
| SSE backend protocol | `008`, `011..019` | `INTEGRATED`; `CHAOS_SSE` only for allowed delivery faults | Raw frame and parsed envelope ledger, upstream/downstream hashes, cursors, terminal close |
| Financial/release/trace | `015..016`, `020..030` | `INTEGRATED`; source mode separately declared | Released metric/Claim/Review/Proof/CER/result records, lineage graph, release decision |
| Artifact delivery | `025..027`, `030` | `INTEGRATED` | Public metadata, auth ledger, independently computed byte hash/size/type, zero-byte failures |

Unit tests may support diagnosis but do not independently pass any row. Backend contract tests must
be followed by backend integration and mapped browser evidence where the catalog names P4-E2E or
P4-SSE gates. `P4-E2E-015` remains a `RETIRED_TOMBSTONE` and is absent from execution. Real Scene
05/06, `P4-E2E-103/104`, Object Memory, comparison, incremental seed, and writeback are
`DEFINED_NOT_ACTIVATED` for Phase 4 Core.

## 4. Mapping and completeness summary

The catalog references all `P4-SSE-001..020`; `P4-SSE-006` is a delivery-fault action whose
backend replay support is owned by `P4-BE-011`, while its browser/proxy execution remains in the SSE
suite. It references 25 of 28 identity assertions: `P4-ID-021/022` are Phase 5 only, and
`P4-ID-024` is browser Back/Forward ownership rather than an independent backend contract. The
backend gates provide the durable state used by `P4-ID-024`, but do not claim to pass that browser
assertion.

```text
P4_BE_GATES_DEFINED=30
P4_BE_REQUIRED_VARIANT_CLASSES_PER_GATE=7
P4_BE_REQUIRED_VARIANT_CELLS=210
P4_CONTRACT_BLOCKERS_WITH_GATE_OWNERS=12/12
V17_BACKEND_DEPENDENCIES_WITH_P4_BE_OWNERS=12/12
P4_E2E_GATES_DIRECTLY_REFERENCED=74/106
P4_SSE_GATES_REFERENCED=20/20
P4_ID_ASSERTIONS_DIRECTLY_REFERENCED=25/28
P4_ID_PHASE5_NOT_ACTIVE=021,022
P4_ID_BROWSER_OWNED_NOT_CLAIMED_BY_BACKEND=024
UNRESOLVED_BACKEND_ACCEPTANCE_SEMANTIC_CONFLICTS=18
PHASE4_BACKEND_ACCEPTANCE_EXECUTED=NO
PHASE4_BACKEND_TEST_IMPLEMENTATION_AUTHORIZED=NO
```
