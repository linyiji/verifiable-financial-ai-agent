# Results Workspace semantic contract — W1

[简体中文](RESULTS_WORKSPACE_CONTRACT.zh-CN.md)

## Freeze and gate

W1 contract frozen against authorized clean baseline `a1019f5be8b51597055775cca4e446523e3e0a75`
(tree `d73ece10766d1db9a53a5ce9b81e9027c7eb1209`). W2 is not implemented by this document.
W3, local live, publication and fresh-download live remain separately gated.
Phase 6B is out of scope. Historical records and report files must not be rewritten.

The two authorized Bocha smoke requests were consumed: Web HTTP 200/schema PASS;
AI HTTP 403/FAIL. The response alone does not establish whether credentials,
entitlement, quota or another access rule caused the refusal. No retry is authorized.
Do not advertise both capabilities as healthy or publish before this gate is resolved.

## One canonical truth

A (Report), B (Financial Review) and C (Execution) are read-only projections of the
same Run, Scheme, ReleasedResult, Claim, Review, Calculation, Evidence, AgentOutput,
event, Proof and recovery records. Names and shared actor labels are not joins.
Every joined record must have exact identity and type, with no ambiguous candidates.
Missing relationships remain unavailable; counts and display text cannot create them.

No new terminal Run enum is necessary. `RELEASED` means release policy passed, not
that every branch succeeded. Publication validity, research limitations, trace
coverage and artifact availability are independent dimensions.

## A — reviewed report content

- Material numbers and financial claims come only from the reviewed typed release
  package. Deterministic rendering may organize them; no extra model is required.
- Current unreviewed specialist/synthesis prose must not become material report
  claims merely because its AgentOutput succeeded. It remains observable output in C.
- Any future material narrative requires a pre-Review claim representation and
  reviewed input binding. Post-Review content mutation must fail release/publication.
- New reports use one canonical block projection for browser and HTML/PDF. Each block
  binds its exact Claim, Calculation or AgentOutput, Review selector and execution
  event when those relationships are recorded. No hardcoded Revenue Growth-only joins.
- Historical exports retain original bytes/hashes. Do not retrofit new contributions
  or claim historical unreviewed prose was reviewed. Identify legacy export limitations.
- Material block trace exposes INPUT, observable PROCESS and OUTPUT under the polished
  report. Never render hidden reasoning or generate a missing Risk/News/Target conclusion.

## B — financial-language projection

Use real ReviewChecks and their exact selector `(review_id, check_code, subject_refs)`.
Empty subject lists are valid for aggregate-level checks; duplicate selectors are not.
Preserve status and precision. Allowlist financial `expected`/`actual` fields and
explanations; never expose arbitrary internal payloads. Expanded checks show INPUT,
PROCESS, OUTPUT and VERDICT, not merely a count of referenced records.

Groups are presentation metadata over actual checks. Cover branch/scheme availability
codes and `EVD-` identities; retain an unknown-code fallback. The reference Review has
62 PASS checks, including one empty-subject cardinality check. No synthetic replacement
dataset is permitted. Review→Execution requires an exact unique typed target; common
actor or canonical membership alone does not establish check-specific causality.

## C — technical execution organization

| Category | Authoritative inputs |
| --- | --- |
| 01 Research Lead | Retained planning/lead tasks and outputs |
| 02 Specialist Agents | Fundamental, Peer, Research & News, Valuation, Risk, Synthesis |
| 03 Data Providers | Actual evidence/provider provenance, including FMP and Bocha |
| 04 Deterministic Code | Calculation records and validated generated capabilities |
| 05 Runtime & Recovery | Attempts, policy/budget decisions and owner Run recovery |
| 06 Financial Review | Exact Review and checks |
| 07 Proof | Policy, commitment, Proof and verification records |
| 08 Release / Report / Memory | Persisted release, artifact and memory version identities |

Include tasks without successful outputs and preserve failures. Never infer FMP from
the generic evidence event type or force supporting actors to COMPLETED. I/P/O detail
must come from retained records. “Used by Report” requires an explicit validated
contribution, supports multiple targets and native Calculation+event targets without
inventing AgentOutputs. Other records are execution-only/supporting, not failed reports.

## Recovery and limitations

Reuse `closure_recovery_records` and migration `20260909_0015`; no naming-only migration.
Expose a bounded RunRecoveryAttempt projection containing original terminal state,
failure stage, attempt ID, owner/policy authority, resume node, reused artifact refs,
executed stages, new model/calculation/Proof counters and final state. Validate its
attempt joins, original terminal event, audit hashes and current artifact identities.
Never expose the full failed snapshot publicly.

For reference `RUN-75daae15-9f35-4233-83ff-6d24f2e151ba`, display original FAILED,
owner-authorized resume at Release, retained Review/Proof/calculations/valid outputs,
zero new calls/calculations/Proofs, then RELEASED and persisted Memory. Do not label
the internal REVIEW status marker as a newly executed Review. A Memory failure after
release remains an incomplete writeback, not a retroactively failed release.

Use “已发布 · 存在研究限制” for a valid release with retained research limitations.
Explain the original Risk failure and source gaps. Unavailable PDF or incomplete
trace coverage has its own label and does not change Run publication state.

## W2 implementation and W3 acceptance

Parent serializes shared DTO/projection/frontend changes. Extend contracts with typed,
bounded fields and strict exact-identity decoders. No production values from V17.1.
Use V17.1 only for visual information architecture. No automatic provider/Run retry.

Required tests: real 62-check projection and empty selector; exact comparison values;
all material metric/claim traces; native calculation/event and multiple contributions;
wrong-Run/ambiguous relations; reviewed report/browser/export consistency for new Runs;
eight execution groups; no-output failures; immutable historical recovery; no raw audit
snapshot leakage; release-with-limitations versus missing artifacts; Memory provenance.

W3 uses the retained real database read-only and proves all A/B/C identities, trace
edges, recovery history, original failure, final release, limitations, Review counts,
Proof and Memory state without model/data/Proof calls. Capture real S01–S10 screenshots
and index their route, Run ID, status, evidence and known limitation. Then broad offline
regression, TypeScript/build, Docker, bilingual links and secret scan must pass before
the one authorized fresh local live Run. Publication precedes the separately authorized
single fresh-download Mac live Run. Neither live allowance has been consumed at W1.
