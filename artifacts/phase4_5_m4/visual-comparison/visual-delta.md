# Phase 4.5 M4 — V17 Financial Review visual delta

Viewport for every captured artifact: **1440 × 900**, device scale factor **1**, browser zoom **100%**.

Reference authority: `financial_agent_workspace_v17_1_minimal_c_execution_fanin.html` from the accepted V17.1 handoff (SHA-256 `1be45091827c6485b624f6a44bf2e0f48bc650836b1a15024a3f7c395718762e`). The requested `(3)` filename is not present; this is the byte-identical canonical asset already accepted for M3. Current authority: exact released Run `RUN-57aed683-75d6-4b47-acc6-a73053ea492e` served by the real Phase 4 backend.

## Matched evidence

| State | Reference | Current |
| --- | --- | --- |
| B1 · Results B top | `reference/REF-B1-results-review-top.png` | `current/CUR-B1-results-review-top.png` |
| B2 · Complete Review item | `reference/REF-B2-complete-review-item.png` | `current/CUR-B2-real-review-item.png` |
| B3 · Exception mode | `reference/REF-B3-exception-filter.png` | `current/CUR-B3-exception-filter.png` |
| B4 · Review / machine relation | `reference/REF-B4-review-machine-interaction.png` | `current/CUR-B4-review-machine-relation-not-observed.png` |
| B5 · Run Stage 03 | `reference/REF-B5-run-stage-03-review.png` | `current/CUR-B5-run-stage-03-review.png` |

## Visual delta matrix

| Area | Classification | Evidence / decision |
| --- | --- | --- |
| Shell | MATCH | Navy research navigation, white workspace header, centered content column and card system retain the reference hierarchy. |
| Results Header | MINOR_DRIFT | Current header is more compact and exposes exact Run/Object/As-of identity as governed by M2. |
| A/B/C Tabs | MATCH | Three equal-width tabs, active white surface and availability state match the reference interaction model. |
| Review Header | MATCH | Chinese-first B label, overall readiness and a distinct Review surface header are preserved. |
| Review Toolbar | MATCH | `完整复核` and `异常筛选` are direct, two-state segmented controls. |
| Summary | INTENTIONAL_REAL_DATA_DIFFERENCE | Reference shows demo pass/open/resolved counts; current shows authoritative verdict, 54 checks, 4 real groups and 0 actionable exceptions. |
| Full Review Layout | MATCH | Summary → mode toolbar → deterministic groups → expandable checks follows the same review reading order without copying demo steps. |
| Input / Process / Result | MATCH | Each expanded real check exposes Input, observable Review Logic / Process, Result and Verdict in a compact 2×2 evidence grid. |
| Verdict | MATCH | Status is visually distinct at package, group and check levels; accepted truth remains PASS. |
| Exception Mode | INTENTIONAL_REAL_DATA_DIFFERENCE | Reference has two resolved demo exceptions. The accepted Review has 54 PASS checks and no check-linked correction/replan relation, so current truthfully renders an empty actionable state. |
| Stage 03 Review | MATCH | Current Stage 03 directly embeds the shared full Review component and adds the authoritative Review Gate state. |
| Review → C Interaction | INTENTIONAL_REAL_DATA_DIFFERENCE | Reference demo supplies event IDs. Current Results workspace explicitly reports `EXACT_REVIEW_EXECUTION_RELATION_NOT_OBSERVED`; current shows the non-navigable observed state and does not invent an event. |
| Responsive / Overflow | MATCH | Review grids collapse to one column below 760px; long scoped subject identities wrap without horizontal page overflow. |

## Acceptance

- Structural material drift: **0**
- Minor visual drift: **1** (governed exact-run header density)
- Intentional real-data differences: **3** (54/4/0 summary, zero linked exceptions, no exact Review→C relation)
- V17 Review alignment: **HIGH** — both B and Stage 03 render the same business-readable Review truth; the only unavailable interaction is represented explicitly rather than fabricated.
