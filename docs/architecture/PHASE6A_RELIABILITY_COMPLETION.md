# Phase 6A reliability and completion

[简体中文](PHASE6A_RELIABILITY_COMPLETION.zh-CN.md)

## Gate and scope

Completion → Trust → Performance. This is an offline-tested Phase 6A foundation,
not Phase 6B implementation or a new live acceptance claim. No paid provider call,
production Run, historical retry, publication, or historical database migration was
performed for this repair. A fresh, explicitly authorized single NVDA Run remains
the gate before Phase 6B. Previous authorization was already consumed.

The starting revision was `e5fed7dd3cc5512d4b5aa78827149116ac04b57b` on `phase4`.
Historical FAILED Runs stay FAILED. Replay releases described below exist only in
isolated test schemas, which were subsequently removed.

## Proven incident and repaired contract

The latest incident reached PASS Review and VERIFIED Proof, then
`ResearchApplicationService._assure_and_release` rejected every non-null
`partial_research` with `INCOMPLETE_RESEARCH_NOT_RELEASED`. The enclosing handler
reported `POST_SCHEDULER_FAILED`, hiding that policy guard. Report and writeback
were never reached. This was not evidence of a failed proof or an unstarted Run.

Closure now evaluates exact output dependencies and required calculations. A known
qualitative Task may fail only where its narrative is frozen as supporting output;
unknown Tasks, required output gaps, integrity errors and failed correctness checks
remain blocking. Optional absence does not manufacture an Agent success or number.
Policy blocks retain typed causal diagnostics; unexpected closure errors stay fatal.

Success-only canonical contributions and complete execution history are different:
FAILED outputs remain visible with their real, uniquely bound TASK_FAILED events.
Native Revenue Growth can contribute through its exact Calculation, Evidence,
calculation.completed event, Review and Proof, with no model, tokens or AgentOutput
invented. Report and Research Memory preserve that distinction.

## Candidate eligibility

Model registration, configuration, authorization, capability evidence and bounded
recovery remain separate. Task candidate lists are prospective; responses cannot
grant authority. Fundamental, Valuation and Risk admit the configured Sol, Luna,
Terra and MiMo routes, subject to existing eligibility checks. Authorized Luna to
Terra substitution now includes Risk. Peer/News admit MiMo, Sol and Luna; Synthesis
admits Sol, Luna and MiMo. Generated FCF remains Sol/Luna/Terra only.
MiMo uses its independent authority and `mimo-v2.5`; it is not a TeamoRouter alias.
Latency or token counts do not authorize candidates or override correctness.

## Data capability policy

| Capability | Registered candidates | Current execution |
| --- | --- | --- |
| Financial statements / market history | FMP | SELECT_ONE, structured inputs |
| Company news | FMP, Bocha | FALLBACK; explicit collector FUSE option |
| Earnings transcript | FMP, Bocha | FMP transcript; Bocha discovery only |
| Official document search / web research | Bocha | Registry entries; not separate default Tasks |
| Management guidance / company events | FMP, Bocha | Registry entries; not dedicated extraction or certified guidance |

Per-source outcomes are AVAILABLE, PARTIAL, UNAVAILABLE_ENTITLEMENT,
UNAVAILABLE_PROVIDER, INSUFFICIENT_DATA or FAILED. FMP news/transcript 402 cannot
disable successful structured financial data. Preferred/actual provider, source
outcomes and fallback reason persist on the owned Task and survive public decoding.

Bocha is optional BYOK configuration through `BOCHA_API_KEY`; credentials are not
embedded or exposed in public DTOs. The evaluator gateway has not been extended to
proxy Bocha. Without a key the source is unavailable, not a global research failure.
Only explicitly configured official publishers are eligible (NVDA is configured
in this foundation). One search and at most five bounded original-document reads
are permitted, without retries, redirects or forwarding search credentials.

Search snippets/AI answers are not evidence. Accepted originals carry publisher,
URL, date, content digest and retained HTML; scripts/styles are excluded from text.
Unknown publication dates, stale/future material and untrusted hosts are rejected.
Evidence identity uses the original snapshot and exact Run. Transcript discovery
is PARTIAL and explicitly not period-verified or a complete transcript. It cannot
supply structured financial calculation values.

FUSE is opt-in: original URLs are deduplicated within discovery, authority/freshness
filters apply and originals are ranked by authority then recency. FMP normalized
news remains separately attributed. Cross-provider semantic article deduplication
is not claimed; the offline contract checks unique Evidence identities. No learned
ranking, provider benchmarking or performance-based routing was added.

The adapter follows the [official Bocha integration example](https://github.com/bocha-ai/dsh-web-search-bocha/blob/main/README.md).

## Correctness, sufficiency and Review

The existing `OutputRequirements`/`evidence_sufficiency` policy retains HARD_REQUIRED,
ANY_OF, SUPPORTING and ENRICHMENT semantics. Wrong financial periods require
correction, not an insufficient-data label. All accepted period-aligned candidates
are searched; if none exists the branch remains failed/correction-required. A
RESOLVED correction is recorded only after a successful corrected calculation.
Insufficient technical history creates no number, Claim or fake resolution, and
does not stop independent branches. Explicit Scheme requirements still block release.

Review and Release independently bind the exact Scheme fingerprint and branch
outcomes in `financial-requirements/v1`. Formula/cardinality checks use the required
set and accounted supporting absence. Judgment requirements follow available
formulas: a valid RSI Judgment must not fail solely because unavailable MACD has no
Judgment. Every present Judgment still requires exact same-Run Calculation/Evidence.
Historical Review hashes remain unchanged; legacy Evidence omits absent document
authority when serialized. Read-only GETs never rerun Review or rewrite history.

Review/Proof existence is independent of release availability. Failed Runs may
show retained PASS/BLOCK Review and VERIFIED Proof without gaining Report or
released-result availability. Public identity validation remains fail-closed.

## Offline acceptance and remaining live gate

Final regression: **1310 passed**, no deselections; frontend **119/119**. Typecheck
and web build passed. The existing large-bundle warning is not a release failure.
The installer Docker image was built; bilingual and credential scans accompany
the local freeze receipt. No provider health or live success is inferred from mocks.

| Required scenario | Evidence |
| --- | --- |
| 1 FMP mixed availability; 2 Bocha fallback; 3 FUSE | `test_phase6a_data_completion.py`: real collector, HTTP transports, PostgreSQL and Task DTO |
| 4 wrong period; 5 short history | `test_phase6a_review_completion.py`: actual financial branch execution |
| 6 exhausted narrative | `test_output_dependencies.py` plus exact incident replay |
| 7 authorized Risk alternate; 8 unauthorized actual model | `test_dynamic_model_routing.py` and model-policy regression |
| 9 optional formula absent; 10 required formula absent | `test_phase6a_review_completion.py`: PASS versus BLOCK |
| 11 retained assurance; 12 post-scheduler closure | Two immutable incident snapshots, real retained proof records and isolated durable replay |

Replay covered both incident states: actual retained proof/commitment/verification
records, pre-closure events, independent Review, native report contribution, release,
SQLAlchemy persistence, six production GET surfaces and six real TypeScript
decoders per Run, HTML, materialize_memory, Object detail and Memory GET. Failed
Agent records remained FAILED. New RVVs existed only in disposable test schemas.

Migration `20260908_0014` adds nullable document authority to Evidence; apply it
before starting this revision against a new authorized runtime. Existing local
historical API processes were not restarted. This source freeze does not claim
the currently open browser is already served by the repaired backend.

**READY_FOR_PHASE6B = NO.** Next: explicit authorization for one fresh isolated NVDA
live revalidation after offline PASS. Do not retry historical Runs or silently
reuse consumed authorization. Performance/POT work remains gated.
