# Controlled User Alpha session guide

[简体中文](USER_ALPHA_SESSION_GUIDE.zh-CN.md)

Authority: [readiness/scope/severity gate](USER_ALPHA_READINESS.md).
Plan for 3–5 invited users, 20–30 minutes each. This is product research, not a
technical benchmark, sales presentation, or investment recommendation.

## Before the participant arrives

Check the controlled environment gate in the readiness document. Start at
`http://127.0.0.1:4173/objects/OBJ-NVDA`. Use supervised read-only navigation;
do not execute new research, prepare, confirmation, re-execution or memory writes.
Do not launch a production scheduler. R1/v1 and R5/v2 must already be present.
Use Object and Results routes; avoid released Run lifecycle routes' automatic
memory replay. No unrestricted participant credentials or public deployment.

Obtain consent to sanitized notes. No recording/screenshots by default; these
require separate explicit consent. Assign a pseudonymous `ALPHA-###` session ID.
Choose a deletion date before recruiting: suggested raw-note retention is 30 days;
retain only de-identified findings afterward if consent permits. Restrict notes
to the research team. Do not commit participant notes to the repository.

## Neutral journey (do not show answer key first)

1. Ask what company/question they would want to research. Capture only optional,
   non-sensitive intent; explain that today they inspect existing NVDA research,
   not submit that question or create a new Run.
2. Give approximately 30 seconds on the Object page without teaching. Ask A1.
3. Ask them to find current research, its retained material and its origin (A2/A3).
4. Ask them to inspect history and distinguish the knowledge baseline from failed
   attempts (A5). R1–R5 are selected aliases, not the entire 40-Run history.
5. Ask what changed between earlier and current research (A4). Use Base vs Current
   and its exact historical/current Results links. Explain only if needed.
6. Open R5 A (report), B (review), C (execution). Ask what adds—or fails to add—to
   trust (A7). Preserve PARTIAL source/contribution mapping and financial caveats.
7. In C ask them to describe one real recovery sequence in their own words (A6).
8. Ask whether they would want another update for this Object, and why (A8).
   Record intent only; do not click `开始新研究`.

| Question | Neutral prompt | What to observe (not a script to teach) |
| --- | --- | --- |
| A1 | What do you think this product does? | Their own explanation after ~30 seconds |
| A2 | Show the current NVDA research and where it came from | Object → current v2 → R5 journey |
| A3 | Is this different from a folder of reports? How? | Accumulating governed material and provenance |
| A4 | What changed from earlier research? | Uses comparison; unchanged metric can be independently revalidated |
| A5 | Which work is the baseline? What are these failed entries? | R1 released baseline versus R2/R3/R4 execution history |
| A6 | What happened when a provider/model failed? | Same Run/Task recovery versus new-Run re-execution |
| A7 | What do Report, Review and Execution add to trust? | Concrete evidence and acknowledged limits, not blanket correctness |
| A8 | Would you want another update for this Object? Why? | YES/MAYBE/NO and explanation |

Record `UNASSISTED / ASSISTED / NOT_DEMONSTRATED / NOT_OBSERVED` separately for
each A1–A8. `NOT_DEMONSTRATED` means attempted but not shown; `NOT_OBSERVED` means
not asked/seen. Log hints and when they were given. Never count assisted answers
as unassisted or infer human understanding from a working browser link.

## Facilitator explanation, only after observation

- Object = the company/research asset. Run = one execution attempt. Memory =
  retained, released-source research materials, not every previous output.
- “上次研究” here means the previous **released knowledge baseline R1/v1**, not
  the most recent failed attempt. R5 re-executes S1 from failed R4 using R1 as base.
- Peer: MiMo timed out; a permitted switch to Sol succeeded in the same R5 Task.
- Fundamental: Sol timed out; Luna passed a separate capability check and then
  the production attempt succeeded. This is a model switch, not provider switch.
  Fundamental MiMo remains UNKNOWN and was not tested.
- Main Agent proposes; Policy authorizes. Only registered providers, capability
  gates and fixed recovery budgets apply. This is not unlimited provider search.
- Review and calculation Proof provide scoped evidence, not investment suitability
  or universal model correctness. Failed attempts do not inherit later PASS results.

## Compact feedback template (blank, no synthetic participants)

```text
session_id: ALPHA-###
date:
participant_category: optional broad category
first_time: YES / NO
consent_to_notes: YES / NO
delete_raw_notes_after:
task_context: existing OBJ-NVDA R1–R5, read-only
desired_research_question: optional sanitized text

A1 through A8, each:
  outcome: UNASSISTED / ASSISTED / NOT_DEMONSTRATED / NOT_OBSERVED
  participant_answer:
  observed_action_or_evidence:
  hint_given_and_when:
  elapsed_seconds: optional / NOT_OBSERVED

PRODUCT_COMPREHENSION: 1–5 / NOT_ANSWERED
MEMORY_VALUE: 1–5 / NOT_ANSWERED
INCREMENTAL_VALUE: 1–5 / NOT_ANSWERED
REPORT_TRUST: 1–5 / NOT_ANSWERED
REVIEW_VALUE: 1–5 / NOT_ANSWERED
EXECUTION_TRACE_VALUE: 1–5 / NOT_ANSWERED
BASE_VS_CURRENT_VALUE: 1–5 / NOT_ANSWERED
RECOVERY_COMPREHENSION: 1–5 / NOT_ANSWERED
WOULD_USE_AGAIN: YES / MAYBE / NO / NOT_ANSWERED
PRIMARY_CONFUSION:
MOST_VALUABLE_FEATURE:
BLOCKED_ACTION:
severity: P0 / P1 / P2 / P3 / NONE
safe_reproduction_steps:
expected_vs_observed:
facilitator_intervention:
qualitative_feedback:
```

Ratings are self-reported Alpha research evidence. Do not average them into a
provider/model/product score or use them to mutate routes. Preserve non-response.

## Minimum product telemetry and stop conditions

Manual event notes suffice: `session_id`, elapsed time if observed, allowed screen,
intended action, outcome, assistance level, issue ID and severity. No analytics
platform, tracking script or network-log collection. Prefer R1–R5 aliases to IDs.
Do not collect names, contact details, holdings, credentials, raw prompts, private
CoT, provider output dumps or private research goals. If someone supplies sensitive
information, stop capture and redact it from the retained notes.

Stop on any cross-identity/data exposure, misleading primary workflow, accidental
mutation or provider activity, or new P0/P1. Classify and report before continuing.
P2/P3 remain documented. After 3–5 sessions, summarize question-by-question
observations, assisted versus unassisted patterns, repeat-use intent and severity;
do not claim statistical validation or start route selection/POT.
