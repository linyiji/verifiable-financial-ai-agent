# Controlled User Alpha readiness — 2026-09-08

## Parent contract freeze

**CONTROLLED_ALPHA_READY = YES**, limited to 3–5 invited design partners in
facilitated, read-only sessions using existing NVDA evidence. This is readiness
to conduct user research, **not proof that users already understand the product**.
No human sessions were conducted in this preparation task. First-time human
comprehension remains unmeasured; the 30-second readiness assessment is PARTIAL.

Baseline: branch `phase4`, SHA `85962ecb9148c5a93bfd855ee6bffe554967db9b`, tree
`a8f4bf4887104aa7b26c1580f8027eb6e948c71f`, tag
`phase5b-incremental-research-2026-09-08`. Phase 5 remains frozen.
Companion authorities: [session guide](USER_ALPHA_SESSION_GUIDE.md),
[Evaluation contract](PHASE6_EVALUATION_DATA_CONTRACT_V1.md),
[R5 acceptance](PHASE5B_R5_ADAPTIVE_ACCEPTANCE.md).

## Scope and operational gate

Target 3–5 sessions, 20–30 minutes each, with analysts/researchers, financially
literate non-specialists, and product/technical reviewers. Broad categories only;
no collection of account, portfolio or personal financial data. Facilitated
screen sharing/operator navigation on the existing local product is sufficient.
No public URL, unrestricted remote access, onboarding, billing, tenanting, or
Auth/RBAC development is implied. This is not production SaaS or enterprise
security readiness, complete provenance coverage, or investment suitability.

Before each session the facilitator must confirm the expected release/memory
identities, scheduler disabled, no active research, and mutation-blocking access.
Use the existing controlled acceptance environment, never an ordinary production
launcher that resumes work. The prior R5 guard permits only already-materialized
exact-R5 idempotent memory replay; it is **not a universal read-only backend**.
For this read-only journey stay on Object/history/Results surfaces, not released
Run lifecycle pages (which automatically request memory materialization).
Do not offer unrestricted clicks on `新建研究`, `创建研究对象`, `开始新研究`,
prepare, confirm, authorize, or re-execute. These are real mutation workflows,
not pretend demo buttons; executing them requires a separately authorized task.
If this controlled environment/supervision is unavailable, the session is blocked.

No need to erase or hide engineering history. Start directly at `OBJ-NVDA` and
explain that R1–R5 is a selected research lineage, not the whole database. The
Object has 40 historical Runs; additional released/unmaterialized and legacy
entries remain visible. The separately labelled QA Object is not real research.

## Exact reference lineage

| Alias | ID | Role/status |
| --- | --- | --- |
| R1 | `RUN-57aed683-75d6-4b47-acc6-a73053ea492e` | RELEASED; retained knowledge baseline v1 |
| R2 | `RUN-e1b27d55-a58f-428d-b98b-0dc519577bc0` | FAILED; historical Agent identity defect |
| R3 | `RUN-bd02e630-69e9-468c-a3c8-6819e8facd30` | FAILED; provider transport/availability |
| R4 | `RUN-2bf2ef98-dc79-4b5f-aeb7-fb0ea151948a` | FAILED; Fundamental transport/availability |
| R5 | `RUN-ab806291-8cbf-4c9b-8852-b6a54f10768d` | RELEASED; current research v2 |

Object `OBJ-NVDA`; same confirmed intent
`SCHEME-b7a81dfc-7863-59e2-afd2-0371e796a1b6`. R5's `base_run_id` is R1;
`reexecution_of_run_id` is R4. Never interchange knowledge and execution lineage.
Base view `RVV-05bec42f-ab9b-55c5-b502-c439b8abe948`; current view
`RVV-0f7f4dfc-3dfa-538c-b59f-a8e22607007b`, object version
`ROV-13d9d21a-661e-5df6-92cd-779ad1f944b0`. Latest released pointer is R5.

## Severity and launch gate

P0 = data/security/cross-identity or catastrophic truth failure.
P1 = primary in-scope workflow unusable or misleading.
P2 = meaningful friction; P3 = wording/polish/low-impact issue.
Launch requires P0=0 and P1=0; do not chase zero P2/P3. A new P0/P1 suspends
the session and controlled Alpha pending classification/repair/reacceptance.

Operator/source/browser audit: **P0=0, P1=0, P2=5, P3=2** within this narrow scope.
These are seven deduplicated readiness findings, not participant-reported defects.

| ID | Severity | Observed friction / retained limitation | Disposition |
| --- | --- | --- | --- |
| A-01 | P2 | Object/Run/Memory/View English terminology competes on a dense first page | Observe unassisted first; glossary only after answer |
| A-02 | P2 | `上次研究` can sound like most recent failed attempt rather than released baseline R1 | Clarify only when needed; verify teach-back |
| A-03 | P2 | Recovery timeline includes UUIDs, codes and separate start/completion rows | Ask for plain-language story, not ID recall |
| A-04 | P2 | 40-Run history, legacy disabled entries and other non-memory releases obscure chosen lineage | Start at current v2; use exact comparison links; do not hide history |
| A-05 | P2 | A `REPORT_SOURCE_MAP_PARTIAL`, C `REPORT_CONTRIBUTIONS_PARTIAL` limit traceability | Keep PARTIAL visible; ask whether missing mapping reduces trust |
| A-06 | P3 | Deferred PDF; current exercise relies on HTML | No export promise; out of session scope |
| A-07 | P3 | Missing industry metadata and labelled test Object add visual noise | Start at NVDA; do not manufacture metadata |

No product source repair is justified by these findings. Primary read actions
reach exact targets; unavailable legacy actions are disabled, not fake working
links. New-run action implementation is not exercised or re-certified here.

## Product questions and evidence level

The frozen questions A1–A8 and observation rubric are in the session guide.
Operator readiness judgments below do not substitute for actual user answers.

| Gate | Readiness | Basis |
| --- | --- | --- |
| 30_SECOND_PRODUCT_COMPREHENSION | PARTIAL | Dense mixed terminology; no timed participant test yet |
| RESEARCH_OBJECT_COMPREHENSION | PASS | Company identity and persistent current-view entry exist |
| RESEARCH_MEMORY_COMPREHENSION | PASS | Verified material, exact provenance and missing categories visible |
| INCREMENTAL_RESEARCH_COMPREHENSION | PASS | Refresh/revalidate/prevent and independent current evidence explained |
| FAILED_EXECUTION_HISTORY_COMPREHENSION | PASS | R2/R3/R4 explicitly failed, separate from released R1/v1 |
| RECOVERY_COMPREHENSION | PARTIAL | Correct same-Run timeline, but engineering-heavy presentation |
| A_B_C_COMPREHENSION | PASS | Separate report/review/execution roles and honest availability |
| BASE_VS_CURRENT_COMPREHENSION | PASS | v1/v2 comparison explains unchanged value independently verified |
| PRIMARY_ACTION_INTEGRITY | PASS | In-scope Object/history/exact Results navigation works |

Real browser readiness = PASS for the guided read-only journey, with the above
comprehension caveats. Actual human comprehension for **every** gate is
NOT_OBSERVED until sessions; do not translate operator PASS into user success rates.

## Audit and next actions

Preparation used parallel read-only diagnosis, parent-owned documentation freeze,
then independent evidence/terminology verification and real-browser navigation.
No feature development or new extractor was necessary. Existing exact-run APIs,
typed recovery ledger, and safe retained telemetry cover Evaluation preparation.
Production snapshots use read-only repeatable-read SQL, row counts and hashes;
no raw payload export. Before/after identity/memory/history checks are retained
in the local preparation receipt. No provider/model calls or new Runs authorized.

Next exact action: `CONTROLLED_USER_ALPHA`. Owner may separately choose
`PHASE_6A_EVALUATION_PLANE` in parallel; neither starts in this task.
