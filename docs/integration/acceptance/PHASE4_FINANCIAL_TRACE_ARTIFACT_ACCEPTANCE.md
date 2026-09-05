# Phase 4 Financial, A/B/C, Trace, and Artifact Acceptance

Status: `AUTHORITATIVE_SUITE_DESIGN — NOT EXECUTED`

Activation scope: `PHASE4_CORE_REQUIRED`

Implementation authority: `NO`

Contract dependency: `WAITING_FOR_PHASE4_BACKEND_FINAL_CONTRACT_FREEZE`

This document defines the future executable acceptance oracles for released financial semantics,
Calculation lineage, Review, Proof, A/B/C, Claim Trace, and `ReportArtifact`. It does not create
routes, schemas, migrations, application code, test code, or new gate IDs.

The coordinator-owned namespaces remain authoritative:

- `P4-BE-020..027` and the supporting `P4-BE-015..017`, `030`;
- the existing `P4-E2E`, `P4-SSE`, and `P4-ID` catalogues;
- `SCENE-01..06` and the approved interaction ledger.

This suite may supply evidence to mapped gates, but it cannot rename, split, merge, weaken, or
declare those gates passed. `P4-E2E-015` remains `RETIRED_TOMBSTONE`. Real `SCENE-05/06` and their
Phase 5 gates remain `DEFINED_NOT_ACTIVATED` with `result=null`.

## 1. Authority boundary and acceptance rule

The authority chain is:

```text
durable Backend records
  -> independently checked release closure
  -> versioned Backend projection
  -> frontend adapter preserving values and IDs
  -> browser-visible semantic value and exact navigation target
  -> independently fetched artifact bytes
```

The browser DOM is an observation, not its own oracle. A fixture, Demo projection, frontend store,
component-to-component copy, filename, title, ticker, or HTTP 200 alone cannot prove any result in
this suite. Final Core evidence is `INTEGRATED`; restart evidence remains `INTEGRATED`; SSE-assisted
reopen/navigation evidence may additionally be `CHAOS_SSE`. `DEMO_UX_ONLY`, `PUBLIC_REAL`,
`LIMITED_REAL`, and `OFFLINE_INTEGRATED` results remain separately labelled and never substitute for
an `INTEGRATED` gate.

After activation, every required mapped gate is exactly `PASS` or `FAIL`. Missing evidence,
unfrozen comparator semantics, an unavailable required record, or an unexplained deterministic
fail-then-pass is `FAIL`, not a qualified pass.

## 2. Preconditions for an executable run

Do not implement or execute this suite as Phase 4 acceptance until all of the following are bound in
the evidence manifest:

1. independently accepted immutable Phase 3 Backend parent and clean Phase 4 Backend Candidate;
2. approved V8.1 parent, approved V17 Change Request, clean V17 Candidate, and served-asset hashes;
3. database revision, API/route schema version and hash, event contract version and hash;
4. final `ReleasedFinancialMetricProjectionV1`, `ClaimDetailV1`,
   `FinancialReviewProjectionV1`, `ExecutionProjectionV1`, `TraceBundleV1`,
   `ReportArtifactGroupV1`, error, availability, Review, and Proof schemas;
5. a frozen release validator version covering Review, Proof, material-output, canonical, result,
   and artifact requirements;
6. a frozen artifact authorization and byte-delivery policy;
7. the coordinator catalogue and crosswalk hashes.

No test may fill a contract gap with a locally invented field, inferred status, unversioned JSON
lookup, or frontend calculation.

## 3. Deterministic acceptance corpus

### 3.1 Two-object identity corpus

Create two authorized test Objects with deliberately colliding presentation labels and distinct
opaque IDs. The principal used for identity-substitution tests must be allowed to read both Objects,
so a 404 proves scope enforcement rather than lack of credentials. A separate principal must be
authorized for A only, and a third principal must be authorized for neither.

| Symbolic record | Object A | Object B | Required collision/difference |
|---|---|---|---|
| Object | `O-A` | `O-B` | same display name/symbol where the identity contract permits; distinct IDs |
| released Run | `R-A` | `R-B` | same status and overlapping timestamps; distinct IDs and owners |
| Task | `T-A` | `T-B` | same title/type; distinct IDs |
| Evidence | `E-A-*` | `E-B-*` | same provider/field labels; distinct owner IDs and sentinel values |
| Calculation | `K-A` | `K-B` | same formula/capability names; distinct Run/Task/Evidence/value |
| metric | `M-A` | `M-B` | same metric name; distinct IDs and sentinel value |
| Claim | `C-A` | `C-B` | same claim type/title-like text; distinct IDs and Runs |
| Review/check | `V-A/Q-A` | `V-B/Q-B` | same code/status; distinct IDs and subject refs |
| Proof/verification | `P-A/Y-A` | `P-B/Y-B` | same backend/program label; distinct K/Run binding |
| canonical/result | `X-A/L-A` | `X-B/L-B` | distinct identities and complete same-Run closure |
| HTML/PDF artifacts | `A-A-H/A-A-P` | `A-B-H/A-B-P` | separate IDs, bytes, hashes, and owner closure |

Every substitution test records response status, safe error code, response-body digest, before/after
row counts, and an A/B sentinel scan. The Backend and browser must not choose by symbol, title,
metric name, formula name, list position, `first`, or `latest`.

### 3.2 Mandatory financial witness

The A corpus contains one released metric whose authoritative values are exactly:

```json
{
  "metric_id": "M-A",
  "canonical_value": "0.6547",
  "canonical_unit": "RATIO",
  "display_value": "65.47",
  "display_unit": "%"
}
```

The corresponding deterministic Calculation uses Decimal-compatible inputs that independently
evaluate to `0.6547` under the frozen formula/version, for example accepted EBITDA `65.47` and
revenue `100.00` for `ebitda_margin_v1`. The exact Evidence IDs, periods, basis, actuality, as-of,
currency, input snapshot, formula/capability versions, and implementation hash are recorded before
the release is built.

The B corpus uses the same metric/formula labels but a different canonical/display sentinel. A
second A metric has an explicit `MUST_PROVE` decision and a verified Proof chain. A third negative
Run contains a required Proof that is missing or invalid. This prevents the optional Proof branch
from going untested.

### 3.3 Artifact corpora

At least three immutable corpora are required:

- a valid release with both HTML and PDF `AVAILABLE`;
- a valid policy case with HTML `AVAILABLE` and PDF explicitly `NOT_GENERATED` or otherwise
  non-available, if the final release policy permits this;
- quarantined copies with independently introduced byte, declared hash, declared size, MIME,
  owner, canonical/result, and HTML/PDF substitution defects.

Tampered records are created only in an isolated acceptance database/storage namespace. A GET must
never repair them.

## 4. Common executable oracle protocol

For every positive, negative, restart, authorization, and integrity case below, the harness uses the
same protocol:

1. Capture the durable source rows and storage-object digest before the request. Use allow-listed
   projections; do not retain licensed raw provider bodies, secrets, prompts, or hidden reasoning.
2. Capture the Backend release decision and its policy/version. Verify the Run is `RELEASED`, X is
   terminal for R/O, L references X, Review is valid, required Proof is satisfied, and material
   M/C/K/E closure is complete.
3. Fetch result, exact Claim, Review, Execution, Trace, artifact metadata, and artifact bytes through
   the public Candidate. Record the unsynthesized HTTP ledger and served Backend identity.
4. Compare opaque IDs as exact strings. Compare decimal and unit wire fields as exact strings/enums,
   not floating-point equality. Compare arrays in frozen contract order; a set-normalized field may
   be normalized only when the final schema explicitly declares it set-like.
5. Open the same Run in the manifested V17 browser, passively capture responses, and compare
   accessible visible values and navigation targets with the captured Backend records.
6. For restart cases, stop the Backend, dispose of process memory, restart against the same
   PostgreSQL and artifact storage, create a new browser context with cleared browser storage, and
   repeat the same requests and comparisons.
7. Record zero mutation for every GET, rejected identity tuple, denied request, corrupt-artifact
   request, unavailable action, Back/Forward operation, and refresh.

An expected failure passes its negative test only when the request fails in the specified way and
no protected value or artifact byte is disclosed. It does not turn the corresponding positive gate
into a pass when the positive corpus is absent.

## 5. ReleasedFinancialMetric and fixed ratio oracle

### 5.1 Positive oracle

The stored metric, released result, result projection, Claim detail, Trace bundle, released Object
projection where applicable, frontend adapter value, and browser region must preserve:

```text
canonical_value = "0.6547"       exact string
canonical_unit  = "RATIO"        exact enum
display_value   = "65.47"        exact string authored by Backend release
display_unit    = "%"            exact string authored by Backend release
browser visible = "65.47%"       display_value + display_unit only
```

The same joined record must preserve `run_id`, `metric_id`, name, period, period basis, actuality,
as-of, currency/null, formula ID, capability ID, `calculation_id`, Evidence refs, Claim refs, Proof
requirement/status/refs, method metadata, technical price basis, corporate-action state/guards, and
limitations whenever those fields apply in the frozen contract.

The browser metric's accessible region must expose value, unit, period, actuality, and as-of
together. Hidden metadata or a screenshot without the captured Backend tuple is insufficient.

### 5.2 Frontend non-computation oracle

All of the following are required:

- a response-to-adapter-to-DOM data-flow trace keyed by `(run_id, metric_id)` shows visible numeric
  text sourced from `display_value` and `display_unit`;
- AST/module-graph inspection of the served production sources and bundle finds no reachable
  financial formula, formula-ID switch, ratio-to-percent conversion, arithmetic path from
  `canonical_value` to visible financial text, or reuse of Demo financial fixtures;
- an adapter/component contract canary preserves a Backend-supplied display string byte-for-byte
  without deriving it from the canonical value; this is supporting frontend evidence only and does
  not substitute for the integrated witness;
- browser response fulfilment/interception is absent in the integrated run.

Generic progress conversion is not a failure by name alone; the data-flow check must distinguish
Run/Task progress from financial values. Any financial use of `canonical_value * 100`,
`Number(canonicalValue)`, formula recomputation, or a separately constructed percent is a failure.

### 5.3 Negative, restart, authorization, and integrity oracles

| Dimension | Action | Required result |
|---|---|---|
| semantic negative | attempt release/projection with `0.6547%`, unlabelled `0.6547`, `65.47` with `RATIO`, float drift, missing unit, or inconsistent period/as-of | release/projection is unavailable or fails with the frozen safe error; no frontend repair and no `AVAILABLE` metric |
| lineage negative | substitute `M-B`, `K-B`, `C-B`, or B Evidence under R-A despite colliding names | fail closed; no B sentinel in JSON, DOM, or accessible tree |
| missing data | remove required Calculation, Evidence, Claim, Review, or Proof closure | release cannot be `AVAILABLE`; an ID-retained optional-detail `UNAVAILABLE` must not be confused with a missing required child |
| unknown version/value | inject unknown metric schema, unit, actuality, period basis, proof status, or projection version | `SCHEMA_INCOMPATIBLE`/frozen equivalent; withhold metric and stop reduction, never coerce |
| restart | restart Backend and new browser; reopen exact R-A | the four authoritative strings, all IDs, metadata, and visible `65.47%` are byte-equivalent |
| authorization | exact R-A/metric request by A-denied principal | `FORBIDDEN` or the final concealed policy; no metric semantics, IDs beyond safe resource context, or existence side channel |
| integrity | mutate any stored semantic field after release or make M/C/K/E disagree | immutable/hash/closure check fails; no released result, report, or artifact is served as valid |

## 6. Calculation lineage oracle

### 6.1 Positive oracle

For every accepted material metric M and Claim C, resolve exactly one named K from M and every K
named by C. The future test asserts:

```text
K.calculation_id == M.calculation_id
K.run_id == C.run_id == R
K.task_id resolves to T and T.run_id == R
K.formula_id == M.formula_id
K.capability_id == M.capability_id
canonical_decimal(K.output_value) == M.canonical_value == C.value
K.output_unit == M.canonical_unit == C.unit
K.input_evidence_ids closes exactly to M.evidence_refs/evidence_ids and C.evidence_refs
every E.run_id == R and E.object_id == O
C.metric_id == M.metric_id
```

The harness independently evaluates the frozen deterministic formula from captured accepted
Evidence and parameters using Decimal arithmetic. This verifies Backend truth; the browser never
receives or runs that calculation. It also verifies implementation/capability version and hash,
runtime version, input snapshot, parameters, status, and the exact Proof commitment inputs where
applicable. Calculation detail is a read of K, not a recomputation by the route.

### 6.2 Negative, restart, authorization, and integrity oracles

| Dimension | Action | Required result |
|---|---|---|
| negative ownership | put `K-B` in C-A/M-A or point K-A at T-B/E-B | `IDENTITY_MISMATCH` or persisted-closure `INTEGRITY_FAILURE`; zero B values/provider data |
| negative heuristic | remove K-A and leave K-B with the same formula/capability/metric name | no lookup by name and no “closest” Calculation; exact unavailable/failure |
| stale correction | point M/C to the pre-correction K while Review/X names the corrected K | release and Trace fail; no mixed old/new lineage |
| missing data | retain K ID but remove optional detail versus remove required K row | first yields ID-retained typed unavailable only if final policy permits; second blocks release as integrity failure |
| restart | reopen K/E/T and Proof commitment after Backend restart | IDs, input order, values, hashes, versions, and output strings match the pre-restart ledger |
| authorization | request K/E detail without O/R authorization | safe denial before value, provider field, raw locator, or existence disclosure |
| integrity | alter input snapshot, accepted Evidence digest/order, output, formula version, or implementation hash | independent recomputation/commitment/closure mismatch fails; GET does not repair K |

## 7. Review oracle

### 7.1 Positive oracle

Fetch `FinancialReviewProjectionV1` independently of A/C. It must preserve one exact V, not mint a
per-Claim Review. The released B view must bind O/R/X/L and include C and K through
`reviewed_claim_refs`, `reviewed_calculation_refs`, or the final typed Check subject contract.

For a PASS Review:

- V owns R; reviewer and `input_snapshot_hash` are present when required by the review policy;
- every stable Check ID is unique and durable;
- all Check statuses and aggregate verdict obey the frozen total map;
- reviewed Evidence/Calculation/metric/Claim refs and required-Proof Calculation refs match the
  released tuple;
- `OPEN`/`RESOLVED`, correction refs, created/resolved times, expected/actual, and detail come from
  durable Backend facts rather than array position or event text;
- `review.resolved` is never interpreted as one exception's resolution without an explicit
  Check-to-correction relation.

The harness recomputes the Review input-snapshot digest with the frozen canonicalization/version and
compares it exactly. If no algorithm/version is present, the integrity oracle cannot pass.

### 7.2 Negative, restart, authorization, and integrity oracles

| Dimension | Action | Required result |
|---|---|---|
| negative ownership | request V-B/check B under R-A or inject C-B/K-B/T-B subjects | public nested lookup fails closed; no B status, counts, or expected/actual data |
| semantic negative | aggregate PASS with BLOCK/REVIEW check; duplicate/missing Check ID; inferred resolved state; synthetic per-Claim Review | schema/closure failure; released B and Results unavailable |
| missing data | no Review before review, terminal Run without Review, or retained Review body unavailable | respectively typed `PENDING`, `NOT_GENERATED`, or `UNAVAILABLE` as frozen; never PASS/empty-success |
| unknown version/value | unknown Review/check status or schema | withhold Review with schema error/recovery; never map to PASS |
| restart | reopen V/check/correction history in new process/browser | exact IDs, order/history, verdict, subjects, timestamps, and digest persist |
| authorization | A-denied principal reads Review/check | safe denial with no count/status/subject leakage |
| integrity | mutate reviewed refs or snapshot input while retaining prior digest/PASS | digest or closure failure blocks release and A/B/C |

## 8. Proof visibility and verification oracle

### 8.1 Positive oracle

Exercise both branches; one cannot substitute for the other.

For `MUST_PROVE`, capture one explicit policy decision for `(R,K)`, input commitment, Proof record,
receipt artifact metadata, and verification record. Assert exact R/K/formula/capability/
implementation-hash/Evidence commitments, Proof ID, verifier ID, image/program identity, receipt and
journal hashes, `verified=true`, and final `VERIFIED` status. The Trace and metric projection expose
only safe Proof status/IDs and never the internal receipt path or proof internals not approved for
the public schema.

For `NOT_REQUIRED`, an explicit same-R/K policy decision is mandatory. Absence of a Proof row alone
does not mean `NOT_REQUIRED`.

### 8.2 Negative, restart, authorization, and integrity oracles

| Dimension | Action | Required result |
|---|---|---|
| negative ownership | associate P-B/Y-B to K-A by formula/program/name or inject P-A under R-B | fail closed; no proof-valid indicator |
| policy negative | required Proof missing, pending, errored, generated but unverified, or verification false | release and Results/artifacts blocked; never coerce to verified |
| missing policy | omit policy decision and Proof | `UNAVAILABLE/PROOF_POLICY_UNKNOWN` or frozen equivalent, not `NOT_REQUIRED` |
| unknown version/value | unknown policy/status/backend/schema | schema/unavailable failure; no success fallback |
| restart | reopen decision/commitment/Proof/receipt metadata/verification | exact identities, commitments, statuses, and hashes persist; no reproving is used to hide loss |
| authorization | unauthorized Trace/Proof read | no status, receipt reference, commitment, or existence leakage |
| integrity | mutate receipt bytes/hash/size, commitment input/order, image ID, journal hash, or verifier result | independent byte check or verification closure fails and release remains unavailable |

## 9. A/B/C single-canonical-record oracle

`A` is the Professional Report/result, `B` is Financial Review, and `C` is the Execution Record
view. For a released Run the test requires:

```text
A.object_id == B.object_id == C.object_id == O
A.run_id == B.run_id == C.run_id == R
A.canonical_record_id == B.canonical_record_id == C.canonical_record_id == X
A.released_result_id == B.released_result_id == C.released_result_id == L
A.report_id == L                         # Phase 4 v1 draft; final freeze required
```

In addition, A's M/C/K/E refs, B's V/check subjects and required-Proof refs, and C/X's Task,
Evidence, Calculation, metric, Claim, Review, Proof, correction, and safe event refs must close to
the same release. `X.object_snapshot_ref == O` and `X.runtime_outcome` is terminal-success under the
frozen release policy.

| Dimension | Action | Required result |
|---|---|---|
| positive | capture A/B/C responses separately, then use the browser tablist and deep links | exact identity tuple and ref closure; keyboard/tab presentation does not alter Backend truth |
| negative | substitute B-B or C-B, stale historical X/L, latest same-symbol Run, or structurally present but unreleased report | fail closed or wholly navigate to B context; never mixed headers/body or ready Results |
| missing data | omit X, L, successful Review, required Proof, material output, or mandatory artifact state | A/B/C released aggregate unavailable; a live Review may remain independently visible with explicit nonreleased IDs/state |
| unknown version/value | unknown A/B/C projection or execution/review status | no partial mixed tabs; schema-incompatible recovery |
| restart | Backend restart and clean browser reopen of R | all four common IDs, ref sets, tab selection, and immutable released content are identical |
| authorization | deny any one of O/R/X/L/A/B/C | withhold the whole protected view; no partial cross-view leakage |
| integrity | make any one view claim another X/L or omit a required reciprocal ref | A/B/C consistency gate fails even if each view renders successfully alone |

Execution actor filtering and free-text search, if approved, operate only on already authorized safe
C rows and cannot change O/R/X/L, ref sets, canonical state, or domain rows. Their proposed V17 IDs
are addressed in the freeze-conflict section; this document does not adopt them as coordinator gates.

## 10. TraceBundle and Claim Trace oracle

### 10.1 Positive round trip

Start from the visible M-A in a specific report representation and follow the user-visible sequence:

```text
Report metric M-A
  -> exact Claim C-A
  -> exact Review V-A and durable Check Q-A
  -> exact Task T-A derived only through C-A -> K-A -> T-A
  -> exact Calculation K-A
  -> exact Evidence E-A-*
  -> exact Proof P-A/Y-A when policy for K-A is MUST_PROVE
  -> exact Execution X-A and safe Task/event anchor
  -> the original report representation and Claim anchor
```

At each hop the test compares route state, network request IDs, response ownership, accessible
target, focus, highlight, and preserved origin. `TraceBundleV1` must carry the exact O/R/C/M,
all Task/Evidence/Calculation/Judgment/Review/Proof refs, X/L, report ID, representation artifact
IDs, and scoped report/review/task/execution anchors. `primary_task_id` is null unless a durable
Backend selection names it; multiple Tasks remain visible as multiple refs.

The returned report anchor is scoped at least to `(O,R,C,L/X,artifact representation)`. Review
anchors name an exact durable Check, Task anchors name an exact T, and execution anchors name exact
safe X/R event rows. An anchor is opaque to the browser; converting it to a DOM identifier must not
change its owner tuple.

No Claim Trace response or UI needs or exposes chain-of-thought, prompt transcripts, model scratch
state, raw provider bodies, `raw_artifact_ref`, Proof receipt storage paths, or report storage paths.

### 10.2 Negative, restart, authorization, and integrity oracles

| Dimension | Action | Required result |
|---|---|---|
| Claim substitution | request `(R-A,C-B)` | public 404 `IDENTITY_MISMATCH`/frozen equivalent; no C-A fallback and no C-B body |
| child substitution | inject E-B, K-B, V-B, P-B, T-B, X-B, L-B, or A-B into A Trace | integrity/identity failure; no partial Trace and no B sentinel |
| historical negative | request historical C-A1 while current/latest is R-A2 | remain on R-A1 or fail exact lookup; never open same-name C-A2 |
| heuristic negative | remove exact target while leaving same symbol/title/metric/formula/check text | typed unavailable/not-found; no search, first, latest, or closest repair |
| missing optional detail | retain authoritative ref but remove allowed retained detail | ref and stable ID remain with typed `UNAVAILABLE`; action disabled |
| missing required child | remove a child required for released closure | `INTEGRITY_FAILURE`; report/Trace cannot remain available |
| anchor negative | use HTML anchor with PDF artifact, another Claim, another Run, or missing anchor metadata | fail/disabled unavailable panel; no document text search fallback |
| unknown version/value | unknown Trace schema, ref type, anchor version, or availability | withhold Trace and recover only from a compatible snapshot |
| restart | reopen exact deep link after Backend restart and clean browser context | same tuple, refs, anchors, route, focus target, and original representation |
| authorization | exact Trace or any child requested by denied principal | fail before nested existence/value disclosure |
| integrity | source graph and Trace disagree on any reciprocal ref/cardinality/watermark | Trace gate fails; a visually complete drawer cannot cure it |

## 11. ReportArtifact metadata, authorization, content, and integrity

### 11.1 Metadata oracle

Fetch `ReportArtifactGroupV1` for R and require group-level exact equality:

```text
object_id == O
run_id == R
report_id == released_result_id == L        # subject to final V1 freeze
canonical_record_id == X
availability reflects actual release/generation state
```

The representation set has one HTML slot and one PDF slot. For each `AVAILABLE` slot require all of
the following non-null facts:

```text
artifact_id
format
content_type
sha256
size_bytes > 0
renderer.renderer_id
renderer.renderer_version
generated_at
authorized_ref
```

HTML and PDF have distinct `artifact_id` values and distinct immutable records. Their bytes and
content hashes are independently verified; neither representation is an alias, redirect, fallback,
or filename variant of the other. A non-available slot carries the frozen availability and safe
failure code and has no fabricated byte-derived identity or authorized reference.

Recursively scan every public JSON value, error detail, header, URL, DOM attribute, and log retained
for the browser. Fail on internal `artifact_ref`, `raw_artifact_ref`, `artifact://`, `file://`, an
absolute filesystem path, parent traversal, storage bucket/key, symlink-resolved path, or any other
raw storage locator. The public `authorized_ref` must be an approved same-origin API reference and
must not be accepted as storage authority.

### 11.2 Authorized-byte oracle

For each available representation:

1. fetch only through its public authorized reference as an authorized principal;
2. prohibit redirects to a raw filesystem/object-store locator unless the final reviewed contract
   explicitly defines an equally authorized delivery boundary and evidence model;
3. collect the complete response as bytes without browser text normalization;
4. independently compute byte count and `sha256:<64 lowercase hex>`;
5. compare them with metadata and the frozen `Content-Length`, `Digest`, immutable ETag,
   `Content-Type`, and safe `Content-Disposition` encodings;
6. validate content signature: HTML is valid UTF-8 under `text/html; charset=utf-8` and parses as
   the intended document; PDF starts with a valid `%PDF-` signature, has a valid EOF/xref structure,
   and parses under `application/pdf`;
7. extract the allow-listed report semantic tuple from each representation and compare O/R/X/L,
   M/C identifiers, `65.47%`, period/as-of, limitations, and Proof/Calculation references with the
   captured canonical report input. Hash agreement alone cannot bless semantically wrong content.

HTML and PDF may have different presentation and byte hashes, but both must represent the same
canonical released semantics. Any public `semantic_hash` or `metric_semantics_hash` is supporting
evidence only until its canonicalization is frozen; the harness still compares source facts and
authorized bytes independently.

### 11.3 Negative, restart, authorization, and integrity oracles

| Dimension | Action | Required result |
|---|---|---|
| identity negative | call A-B content route under R-A or alter O/R/X/L/report binding | public fail-closed identity response; no artifact bytes and no A-A fallback |
| representation negative | reuse one artifact ID for HTML/PDF, swap slots/bytes, or serve HTML as PDF | metadata/schema or integrity failure; no content accepted |
| unavailable negative | click/fetch non-available PDF or missing HTML under a policy that requires it | action disabled with exact safe Backend reason; direct request fails; required HTML absence blocks release |
| authorization | use the A-only principal for B bytes, or use an expired/revoked, logged-out, or never-authorized principal/reference | authorization is rechecked; no protected artifact bytes, cache hit, redirect, or existence leak |
| byte integrity | alter one byte with same size, truncate/append, change declared hash/size, or change MIME/charset | `INTEGRITY_FAILURE`; no partial/accepted artifact; GET performs no repair |
| semantic integrity | render a validly hashed artifact from another X/L or with wrong metric/Claim content | semantic/source closure fails despite valid file syntax and self-consistent hash |
| header integrity | mismatch metadata and Content-Type/Length/Digest/ETag/Disposition | delivery fails acceptance; browser success/download toast cannot override |
| raw-path negative | request or expose the internal `artifact://`/filesystem locator | safe rejection and disclosure-scan failure; never follow the path from the browser |
| restart | restart Backend/storage handle and use a clean browser | same artifact IDs/metadata/bytes/hashes remain; authorization is freshly evaluated |
| concurrent mutation | replace storage object between metadata read and delivery | final pre-stream binding/hash/size/type check rejects; no partially valid artifact |

## 12. Release, terminal, missing-data, and availability rules

A report or artifact that merely exists must not pass. The positive release corpus requires:

```text
Run.status == RELEASED
Backend release decision == allowed under the manifested policy
L.run_id == R and L.canonical_record_id == X
X.run_id == R and X.object_snapshot_ref == O and X is terminal-success
Review V is successful and covers the exact released C/K tuple
every MUST_PROVE K has exact verified Proof closure
every material M has exact C/K/E closure
artifact state satisfies the frozen release policy
release.completed precedes exactly one run.completed
```

Any missing material Calculation, Evidence, Claim, invalid Review, unknown Proof policy, required
unverified Proof, canonical/result mismatch, or required artifact failure blocks success. A
nonterminal Run may report `PENDING`; a terminal Run with no attempted optional resource may report
`NOT_GENERATED`; an unreleased Run reports `NOT_RELEASED`; retained but inaccessible optional detail
may report `UNAVAILABLE`; an attempted failed generation reports `FAILED`. Empty arrays, nulls,
zeroes, fabricated IDs, or 200 responses cannot replace those states.

The stream terminal is `run.completed`, not `release.completed`. Financial/A/B/C/artifact evidence
must be captured only after authoritative terminal reconciliation. `P4-SSE-015` and `017` support
this proof; an SSE unit test cannot substitute for the Backend release or browser gates.

## 13. Restart and new-browser composite scenario

The composite restart test is mandatory even when each repository has its own unit restart test:

1. complete R-A and record terminal cursor, M/C/K/E/V/P/X/L, Trace, HTML/PDF metadata and bytes;
2. close the browser and Backend process; retain only manifested PostgreSQL and artifact storage;
3. restart the Backend with empty process caches and the same Candidate/build identity;
4. create a fresh browser context with empty local/session storage, IndexedDB, cache, and service
   worker state as governed;
5. open the exact R-A deep link, then A/B/C, Claim Trace, HTML, and PDF;
6. assert every opaque ID, decimal string, unit, Review/Proof state, anchor, content type, size, hash,
   and authorized byte digest equals the pre-restart record;
7. assert terminal SSE reopen closes correctly and causes no duplicate release, Review, Proof,
   artifact, or report generation;
8. repeat A/B substitution and denied-byte requests after restart to prove caches do not bypass
   ownership or authorization.

Reconstruction from Demo data, frontend persistence, latest-Run lookup, report filename, or a newly
generated replacement artifact fails `P4-BE-017`, the mapped identity gates, and `P4-E2E-098`.

## 14. Coordinator-owned gate crosswalk

This table references the current coordinator crosswalk; it does not redefine gate semantics. An
em dash means there is no independent gate in that namespace.

| Capability | P4-BE | P4-E2E | P4-SSE | P4-ID | Real Scene | Interaction |
|---|---|---|---|---|---|---|
| terminal release success | `015` | `006`, `085`, `088`, `098` | `015`, `017` | `006`, `017..019`, `023`, `028` | `01..04` | `006`, `044..055`, `060..061` |
| terminal release failure / no Results | `016` | `007`, `086`, `088`, `098` | `016..017` | `006`, `015`, `017..019`, `023` | `01..04` negative variants | `007`, `040..047` |
| lossless `ReleasedFinancialMetric` | `020` | `069`, `092`, `094..095` | — | `011..020`, `028` | `01`, `03`, `04` | `040..055` |
| ratio/percentage witness | `021` | `069`, `092..093` | — | `013..014`, `018`, `020` | `01`, `04` | `047..049` |
| Claim detail and missing detail, including K/E support | `022` | `042`, `048..055`, `092`, `094` | — | `011..014`, `020`, `025..027` | `03`, `04` | `042`, `048..055` |
| Review/check truth | `023` | `040..043`, `053`, `090`, `094..095` | — | `015..016`, `020`, `025..027` | `01`, `03`, `04` | `040..043`, `053` |
| Proof policy/verification visibility | `020`, `024` | `072`, `092`, `094..095` | — | `013..018`, `020` | `01`, `03`, `04` | `047..055` |
| one canonical A/B/C record | `020`, `023..025` | `047`, `092`, `094..095` | — | `013..020`, `028` | `01`, `03`, `04` | `047..055` |
| Claim Trace closure | `024` | `042..055`, `063`, `094` | `013..014` for navigation/reopen | `011..020`, `023..027` | `04` | `042..055` |
| artifact metadata | `025` | `045..046`, `072`, `096`, `098` | — | `019`, `023`, `025..027` | `01`, `04` | `045..046` |
| authorized artifact bytes | `026` | `045..046`, `073`, `096`, `098` | — | `019`, `025..027` | `01`, `04` | `045..046` |
| artifact size/hash/media/content integrity | `027` | `045..046`, `096`, `098` | — | `019`, `023`, `026` | `01`, `04` | `045..046` |
| durable released reopen | `017` | `075`, `087`, `098` | `007..009`, `013`, `017` | `005`, `009`, `023` | `01..04` | `025`, `044..063` |
| cross-object/Run/authorization rejection | `030` | `057`, `060..063`, `070..073`, `094`, `096`, `098` | `003`, `018` | `001..020`, `023..028` as applicable | `01..04` | `057`, `060..063` |
| exact-read retry without substitution | relevant failed-read gate | `105` | mapped stream retry gates when applicable | `023`, `025`, `027` | `01..04` | `069` |

Calculation-lineage evidence is consumed through the coordinator's lossless-metric and Claim-detail
rows; this document creates no separate Calculation gate. Terminal ordering is independently owned
by the existing terminal-success and SSE rows, even when its evidence is a prerequisite for the
released finance scenario. The source coordinator crosswalk remains the final mapping authority if
any row above is changed during package reconciliation.

## 15. Evidence retained by this suite

Each attempt contributes content-addressed, sanitized records to the coordinator evidence bundle:

- durable source-record graph for O/R/T/E/K/M/C/V/Check/Proof/verification/X/L/artifacts;
- release policy/version, decision, reason codes, terminal ordering, and projection watermarks;
- API request/response ledger with schema versions, identities, availability, and semantic hashes;
- fixed financial witness and independent Decimal calculation result;
- frontend adapter data-flow/source scan and served-bundle hash;
- browser route/tab/focus/scroll/highlight/accessibility semantic snapshots;
- Trace response, scoped anchor manifest, and round-trip navigation ledger;
- separate HTML and PDF metadata rows, authorized bytes, parser result, byte count, MIME signature,
  actual SHA-256, headers, authorization decisions, and zero-protected-byte negative evidence;
- pre/post-restart equality diff and negative cache/authorization rerun;
- append-only failed-attempt history with Candidate pair, environment, rerun reason, source-change
  flag, and final disposition.

Sanitization is allow-list based. It preserves required opaque IDs, values, units, hashes, sizes,
statuses, versions, and timestamps, but excludes credentials, cookies, secrets, provider bodies,
private prompts, hidden reasoning, raw artifact locators, and filesystem paths.

## 16. Draft/freeze conflicts and execution holds

The following are explicit holds, not waivers. They reconcile the newly available provisional
Backend/V17 drafts with the current coordinator catalogue.

| Existing conflict / hold | Current observed conflict | Required freeze before execution |
|---|---|---|
| `UAC-001` | Backend API/identity/event documents are `PROVISIONAL_CONTRACT_DRAFT`, `NOT_FINAL`; inspected `codex/phase3-contracts@11fe817...` is not the immutable accepted Phase 4 Candidate | exact parent/Candidate, clean tree, database/API/event/route/build hashes |
| `UAC-002` | V17 preparation exists but remains blocked; no final readiness approval or governed V17 Candidate | approved FCR/readiness review, complete Candidate manifest, independent delta audit |
| `UAC-003`, `UAC-010`, `UAC-018` | schema negotiation, total Review/Proof/availability maps, and one total negative/error table are not final | exact version request/response behavior, unknown handling, status/recovery/disclosure semantics |
| `UAC-011`, `UAC-017` | all-path terminal failure and final release validator policy/version are not accepted | exact release/terminal state machine and artifact requirement in release closure |
| `UAC-012` | `ClaimDetailV1` remains prose; typed Judgment and retained-detail schema are incomplete | closed JSON schema, field cardinality/order, availability wrapper, forbidden-field list |
| `UAC-013` | durable Check IDs/correction resolution are absent; Backend Review example omits `canonical_record_id`/`released_result_id` while V17 B requires them | one Review schema carrying released A/B/C identity and durable Check history |
| `UAC-014` | `TraceBundleV1`/anchor schema is provisional and the current renderer has no representation-scoped Claim anchor manifest | exact bundle/anchor schema, scope, production/retention/version rules, HTML and PDF anchor behavior |
| `UAC-015`, `UAC-006` | authorized-reference issuance, expiry/revocation, storage resolution, actor scope, and 403 versus concealed 404 are not frozen | one authorization/disclosure lifecycle applied to metadata, Trace, and every byte request |
| `UAC-016` | public artifact routes/group/failure records are absent from the accepted Candidate; HTML-required/PDF-optional policy is provisional | durable attempt/availability transitions and exact release requirement for each representation |
| `UAC-016` catalogue reconciliation | the current Backend draft example uses `artifact_id=null` for non-generated PDF, while the Backend catalogue conflict text still says V17 null conflicts with a reserved non-null PDF ID | coordinator must select and hash one rule; this suite requires no fabricated unavailable artifact identity |
| artifact wire mapping | internal `artifact_type="text/html"`, combined renderer version and `content_hash="sha256:<hex>"` must map to public format, `text/html; charset=utf-8`, renderer object and `sha256` | allowlisted mapping including exact charset, prefix, renderer split, and unknown-MIME failure |
| artifact header/error encoding | `Digest`, ETag and `Content-Disposition` syntax are not exact; JSON error-envelope language can conflict with “zero bytes” byte-route wording | exact header grammar and whether denial has empty body or safe JSON; in all cases zero protected artifact bytes |
| Proof public identity | current durable Proof records can close R/K, but legacy `ProofResult` alone cannot; safe public Proof/receipt projection is not frozen | exact policy/record/verification joins, status map, receipt-field allowlist and unavailable behavior |
| Evidence comparator | current documents permit set normalization only when declared, while Proof commitments may require ordered inputs | per-field ordered-versus-set declaration and canonical hash algorithm; frontend never sorts to repair |
| canonical Object closure | current `CanonicalExecutionRecord.object_snapshot_ref` is nullable, but Phase 4 released X requires exact O | final validator makes non-null equality mandatory before release |
| V17 interaction/gate reservation | coordinator authority currently freezes 69 active interactions, 70 historical, and `P4-E2E-001..106`; provisional V17 preparation reserves product interactions `071..072` / `P4-E2E-107..108` and Demo `073..076` / `109..112` | coordinator must ratify and update the authoritative crosswalk; this suite neither activates nor silently counts these reservations |

Until these holds close, the test design is ready but implementation and acceptance execution are
not authorized. A provisional draft value may be used to prepare an oracle fixture, but it cannot
produce a release PASS.

## 17. Suite decision

```text
PHASE4_FINANCIAL_TRACE_ARTIFACT_DESIGN_READY=YES
PHASE4_FINANCIAL_TRACE_ARTIFACT_IMPLEMENTATION_AUTHORIZED=NO
PHASE4_FINANCIAL_TRACE_ARTIFACT_EXECUTED=NO
MANDATORY_RATIO_WITNESS_DEFINED=YES
FRONTEND_FINANCIAL_COMPUTATION_ACCEPTED=NO
CLAIM_TRACE_EXACT_ID_ROUND_TRIP_DEFINED=YES
A_B_C_SINGLE_CANONICAL_ORACLE_DEFINED=YES
HTML_PDF_SEPARATE_IDENTITY_ORACLE_DEFINED=YES
RAW_ARTIFACT_PATH_ACCEPTED=NO
REAL_SCENE_05_06=DEFINED_NOT_ACTIVATED
```
