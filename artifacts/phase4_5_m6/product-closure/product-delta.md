# Phase 4.5 M6 — Product Closure Delta

## Governed comparison

- Reference: `financial_agent_workspace_v17_1_minimal_c_execution_fanin.html`
- Reference SHA-256: `1be45091827c6485b624f6a44bf2e0f48bc650836b1a15024a3f7c395718762e`
- Current acceptance Run: `RUN-57aed683-75d6-4b47-acc6-a73053ea492e`
- Viewport: `1440 × 900`, zoom `100%`, device scale `1`
- Material product drift: `0`

The classification compares product hierarchy, lifecycle semantics, primary actions, and cross-view behavior. Backend-authoritative differences are not treated as visual defects.

| Product area | Classification | Evidence / disposition |
|---|---|---|
| Run Header | MATCH | Same company-first hierarchy, completion state, identity, and Run actions. Current uses the exact accepted Run. |
| Lifecycle 01 | MATCH | Five-stage lifecycle preserves `01 · 研究计划`. |
| Lifecycle 02 | MATCH | `02 · AI研究` remains the research path surface. |
| Lifecycle 03 | INTENTIONAL_REAL_DATA_DIFFERENCE | Current renders the shared authoritative Review: `PASS · READY`, 54 checks, 4 groups, rather than reference demo review cards. |
| Lifecycle 04 | INTENTIONAL_REAL_DATA_DIFFERENCE | Current replaces simulated chapter progress with observable truth: 8/8 outputs, report `PARTIAL`, one contribution, HTML `AVAILABLE`, PDF `NOT_GENERATED`. |
| Lifecycle 05 | MATCH | Released completion summary and results action are preserved; current strengthens it with Review, Proof, Execution, Report, Result, and terminal-event closure. |
| Results Entry | MATCH | Stage 03/04/05 actions enter B/A/A respectively and preserve the exact Run. |
| A Report | INTENTIONAL_REAL_DATA_DIFFERENCE | Reference report structure is preserved while current renders typed Released Result values, one real Source Map contribution, and actual HTML/PDF availability. |
| B Review | INTENTIONAL_REAL_DATA_DIFFERENCE | Current exposes 54 persisted checks and zero exceptions; no demo correction/replan cards are invented. |
| C Execution | INTENTIONAL_REAL_DATA_DIFFERENCE | Current exposes 12 real Actors, seven public detailed records, and one report contribution; intentionally partial public detail remains disclosed. |
| A → B | MATCH | Exact scoped selector (`review_id`, `check_code`, ordered `subject_refs`) and return anchor are URL-addressable. |
| B → A | MATCH | Exact authoritative report anchor returns to A; no text/index fallback. |
| A → C | MATCH | Revenue Growth Hero opens `fundamental_analyst` with the exact AgentOutput and execution event. |
| C → A | MATCH | The authoritative contribution returns to `metric-revenue-growth`. |
| B → C truthful partial state | INTENTIONAL_REAL_DATA_DIFFERENCE | Exact Review→Execution relation is not observed; UI says the machine relation is not observed and provides no fuzzy link. |
| Refresh | MATCH | A, B, C Hero focus and Run lifecycle stage survive real reloads through URL state. |
| Back/Forward | MATCH | Browser Back/Forward restores the exact prior A/B focus and Run stage without selecting a latest Run. |

## Captures

Reference:

- `reference/REF-M6-1-run-stage-03.png`
- `reference/REF-M6-2-run-stage-04.png`
- `reference/REF-M6-3-run-stage-05.png`
- `reference/REF-M6-4-results-a.png`
- `reference/REF-M6-5-results-b.png`
- `reference/REF-M6-6-results-c.png`

Current:

- `current/CUR-M6-1-run-stage-03.png`
- `current/CUR-M6-2-run-stage-04.png`
- `current/CUR-M6-3-run-stage-05.png`
- `current/CUR-M6-4-results-a.png`
- `current/CUR-M6-5-results-b.png`
- `current/CUR-M6-6-results-c.png`

## Real-browser closure receipt

- Stage 03 / Results B: same Run and Review identity; 54 checks, 4 groups, `PASS · READY`.
- Stage 04 / Results A: same `report_id`, `released_result_id`, HTML artifact, projection, and one contribution.
- Stage 05: release closure requires Review, required Proof, Execution, Report, Released Result, `release.completed`, and `run.completed`.
- A ↔ C Hero: exact anchor, Actor, AgentOutput, execution event, and calculation observed.
- B ↔ C: truthful `PARTIAL`; no exact general machine relation observed.
- Secondary C Actor: no report contribution action or Review link is fabricated.
- Refresh and Back/Forward: passed in the real browser for A, B, C, and Run Stage 04.
