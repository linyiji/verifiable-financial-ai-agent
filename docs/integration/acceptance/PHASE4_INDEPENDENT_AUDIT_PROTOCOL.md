# Phase 4 Independent Acceptance Audit Protocol

Status: **AUTHORITATIVE DESIGN — AUDIT NOT STARTED**

## 1. Decision

The audit answers one question: did the exact manifested Backend Phase 4 and Frontend V17 candidate pair satisfy every activated Phase 4 Core gate with admissible evidence?

The answer is exactly:

```text
PHASE4_INDEPENDENT_AUDIT=PASS | FAIL
```

There is no conditional, partial, warning-qualified or risk-accepted release PASS. A missing required test or evidence item is a `FAIL`, even if implementation self-tests pass.

## 2. Independence

The named audit owner must not be the sole author of either material Candidate and must not report to a process that permits implementation owners to overwrite the decision. The auditor independently:

- obtains and fingerprints both candidates and served build artifacts;
- selects applicable gates from the authoritative activation records;
- verifies source-class admissibility;
- reruns the critical set in an independently provisioned environment;
- inspects raw/sanitized ledgers rather than implementer summaries;
- verifies no Demo, fallback, cross-object or client-authority substitution;
- issues and content-addresses the final binary decision.

Implementation teams may explain behavior, supply reproducible setup and submit evidence. They may not choose a weaker oracle, remove a failed attempt, mark a gate inactive, or self-declare final acceptance.

## 3. Entry criteria

Do not begin a decision audit until all are present:

1. immutable, independently accepted Phase 3 Backend parent;
2. Backend Independent Audit `PASS` and Financial Semantics Audit `PASS` applicable to that parent;
3. approved Phase 4 Backend Final Contract Freeze, including schema/event/route versions and hashes;
4. approved Frontend V8.1 parent manifest;
5. approved V17 Change Request and immutable clean V17 Candidate;
6. clean immutable Phase 4 Backend Candidate;
7. reproducible Backend and Frontend build hashes;
8. exact database revision and runtime environment;
9. content-hashed acceptance catalogue, activation matrix, crosswalk and evidence schema;
10. complete implementer evidence bundle including all failed attempts.

Before a decision audit, an absent item is `NOT_READY_FOR_AUDIT`. Once the release decision begins, an absent mandatory item results in `FAIL`; it never creates a qualified pass.

## 4. Phase A — authenticate exact bits

The auditor verifies full SHAs, Git trees, clean status, dependency locks, build commands, generated assets, migrations, configuration schema, OS/container/runtime/browser versions and timestamps. Then verify:

- served Frontend asset hashes equal the Candidate build;
- the running Backend build identity equals the Backend Candidate;
- API, event and database versions equal the frozen contracts;
- every attempt in the bundle names the same Candidate pair or is explicitly historical;
- no result from Backend A/Frontend B2 is combined with Backend A/Frontend B3;
- all evidence hashes and bundle canonicalization validate.

Any unexplained mismatch is a release `FAIL`.

## 5. Phase B — determine applicability

Build the current denominator from lifecycle metadata, not from which tests happened to run:

| Corpus | Phase 4 Core disposition |
|---|---|
| `P4-BE-*` | every catalogue row marked `PHASE4_CORE_REQUIRED` required |
| `P4-E2E` | 99 unique core IDs required |
| `P4-SSE-001..020` | 20/20 required |
| `P4-ID-001..020`, `023..028` | 26/26 required |
| real Scenes | `SCENE-01..04` required |
| current interaction regression | 69/69 required in its declared admissible suite(s) |
| `P4-E2E-015` | `RETIRED_TOMBSTONE`, result null |
| Phase 5 rows/variants, real Scenes 05/06, `P4-ID-021..022` | `DEFINED_NOT_ACTIVATED`, result null |
| `P4-E2E-099..100` | inactive unless the audited release manifest explicitly activates deployment scope |

The auditor verifies mixed gates `058` and `059` at their Core variants without activating their Phase 5 variants. If a deployment profile is explicitly in scope, its gates form an additional aggregate; their absence does not affect a Phase 4A-only decision.

## 6. Phase C — inspect evidence admissibility

For every result, confirm the declared source class can prove that gate:

- `DEMO_UX_ONLY` proves only UX/interaction regression;
- `INTEGRATED`, `PUBLIC_REAL`, `LIMITED_REAL` or `OFFLINE_INTEGRATED` uses real Backend HTTP/SSE and durable persistence;
- `CHAOS_SSE` uses complete real frames and only drop/delay/duplicate/reorder operations;
- `OFFLINE_INTEGRATED` is labelled fixture/offline and never counted as `LIVE`;
- public/limited runs have no request fulfilment, HAR replay, frontend fixtures, Demo store or silent fixture fallback.

Inspect HTTP ledgers, SSE pre/post frame hashes, projections, artifact bytes, browser traces, console output and failed-attempt history. Screenshots support but never replace structured identity, wire or persistence evidence.

## 7. Phase D — mandatory independent reruns

The auditor reruns the full release aggregate when practical. At minimum, the following critical gates and variants are never accepted only from implementation-team output:

1. candidate/build/database/contract identity checks;
2. one full real `SCENE-01` release through HTTP, actual SSE, A/B/C and both artifact representations;
3. `SCENE-02` atomic graph mutation and reconciliation;
4. `SCENE-03` correction/review/release-negative behavior;
5. `SCENE-04` full Claim Trace round trip;
6. durable confirm idempotency across lost response and Backend restart;
7. snapshot race, disconnect, numeric resume, opaque resume, duplicate, out-of-order, terminal success/failure and PostgreSQL restart replay;
8. complete Object A/Object B cross-object matrix, including authorized artifact bytes;
9. the `0.6547 RATIO -> 65.47 % -> 65.47%` witness and client-side financial-authority scan;
10. Backend restart plus new browser context reopening terminal Run, Review, A/B/C, artifact metadata/bytes and terminal cursor;
11. current 69-interaction classification/regression, representative focus/scroll/deep-link/overlay checks, all governed widths and console/runtime checks.

Any sampling beyond this critical set must be risk-based and documented. Sampling never removes a required result from the aggregate; it concerns only which already-produced results the auditor independently reruns.

## 8. Phase E — identity and security review

Using two distinct Objects A and B, verify every requested nested record closes through its route Run and Object. Repeat at least Run-B-under-Object-A, Claim-B-under-Run-A, Task-B-under-Run-A, Review-B-under-Run-A, Artifact-B-under-Run-A, Evidence-B-in-Claim-A and Calculation-B-in-Claim-A.

Inspect both response and browser state. A 200 response whose UI hides the leaked object is still a failure. A 404/403 that leaves stale B data in A's shared store is also a failure. Missing historical/latest/symbol/title/metric-name lookups must remain unavailable without repair.

## 9. Phase F — finance, release, trace and artifact review

For a material Report metric, independently join:

```text
ReleasedFinancialMetric
  -> exact Claim
  -> exact Review/check
  -> exact Task
  -> exact Calculation
  -> exact Evidence
  -> Proof/verification when policy requires
  -> Canonical Execution Record
  -> ReleasedResearchResult/report anchor
  -> separate HTML and PDF artifact identities/bytes
```

Verify canonical and display values are distinct fields, browser text equals Backend display fields, and no React/page/reducer formula creates financial truth. Verify A/B/C use the same canonical record and exact released references.

Recompute byte length and SHA-256 after authorized download for both HTML and PDF. Confirm object/run/canonical/result binding, media type and format; verify cross-owned, unauthorized and tampered variants fail. A raw internal path or `artifact://` locator exposed to the browser is a failure.

Verify release does not pass from structural presence alone: Backend release gate, valid Review, terminal CER, required Proof state, ReleasedResearchResult and artifact consistency must all hold.

## 10. Phase G — browser and runtime review

Verify actual `text/event-stream` source, snapshot cursor, replay, duplicate/order defense, final convergence and no reconnection after terminal reconciliation. The final browser oracle is a fresh Backend projection and persisted record ledger, never another DOM component.

Check route restoration, deep links, breadcrumb semantics, Back/Forward, refresh, focus trap/restore, Escape/topmost overlay, scroll restoration, disabled/unavailable states, retry/dismiss behavior, governed responsive widths and all browser console/page/request errors. Presenter remains a separate `DEMO_UX_ONLY` surface and cannot satisfy integrated gates.

## 11. Failure and rerun policy

All attempts remain append-only with timestamp, environment, candidate SHAs, failure, rerun reason, source-change flag and final disposition.

- deterministic failure plus unchanged source remains a failure unless an independently demonstrated environmental cause invalidated the attempt;
- source, schema, lockfile, migration, generated asset, build or oracle change creates a new Candidate;
- a flaky retry-only success does not pass;
- report edits cannot repair missing raw evidence;
- severity labels cannot override a required gate.

The auditor may stop early after a conclusive failure but must retain the failure and list unexecuted required rows as evidence gaps; the decision remains `FAIL`.

## 12. Decision algorithm

The auditor validates that:

```text
all candidate coordinates valid
AND every activated required gate has result PASS
AND every required Scene passes
AND current interaction coverage is 69/69
AND no inactive/tombstone row has a fabricated result
AND no failed attempt is improperly suppressed
AND all required evidence is intact and admissible
AND all critical independent reruns pass
```

If and only if the expression is true, return `PASS`. Otherwise return `FAIL` with exact gate IDs and evidence references. P0/P1 counts are supporting classification only; `P0=0` and `P1=0` do not turn a failed required gate into PASS.

## 13. Required audit record

The signed/content-addressed audit report contains auditor identity and independence statement; exact candidate/build/contract/database coordinates; activation denominator; source-class inventory; evidence-integrity result; independent rerun plan/results; failed-attempt disposition; P4-BE/E2E/SSE/ID/Scene/interaction matrices; identity/finance/release/artifact conclusions; all findings; and final `PASS` or `FAIL`.

The report must explicitly state:

```text
DEMO_SUBSTITUTION_FOUND=YES|NO
CROSS_OBJECT_LEAKAGE_FOUND=YES|NO
FRONTEND_FINANCIAL_AUTHORITY_FOUND=YES|NO
TERMINAL_RELEASE_SEMANTICS_VALID=YES|NO
REQUIRED_EVIDENCE_COMPLETE=YES|NO
PHASE4_INDEPENDENT_AUDIT=PASS|FAIL
```
