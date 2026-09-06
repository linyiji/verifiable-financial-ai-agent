# Phase 4.5 M3 — V17 HTML ↔ Current Visual Delta

## Comparison basis

- Reference: `/Users/mac/Downloads/financial_agent_workspace_v17_1_minimal_c_execution_fanin.html`
- Reference SHA-256: `1be45091827c6485b624f6a44bf2e0f48bc650836b1a15024a3f7c395718762e`
- The requested `(3)` filename was not present. The canonical file above is byte-identical to the available `(1)` copy and the prior handoff copy, so it is the same reference asset.
- Current: exact accepted Run `RUN-57aed683-75d6-4b47-acc6-a73053ea492e` at `/results/report`.
- Desktop captures: Chromium, 1440 × 900 CSS pixels, 100% zoom, matched semantic report regions.
- Responsive check: 760 × 900 CSS pixels; neither reference nor current reported horizontal document overflow.

## Screenshot sets

Reference:

- `reference/REF-A1-report-top.png`
- `reference/REF-A2-source-map.png`
- `reference/REF-A3-financial-section.png`
- `reference/REF-A4-interaction.png`
- `reference/REF-A5-responsive.png`

Current:

- `current/CUR-A1-report-top.png`
- `current/CUR-A2-source-map.png`
- `current/CUR-A3-financial-section.png`
- `current/CUR-A4-execution-focus.png`
- `current/CUR-A5-responsive.png`

## Visual delta matrix

| Area | Reference | Current | Match | Gap | Action |
|---|---|---|---|---|---|
| Shell | Dark research navigation, fixed top context, centered content | Preserved by the M2 production shell | MATCH | None | None |
| Results Header | Company/run context, status, actions before tabs | Exact object/run/as-of identity and release status remain above tabs | MATCH | Real identity replaces demo identity | Retain production identity |
| A/B/C Tabs | Three evenly weighted views with active A | Same hierarchy, active A, per-surface availability badges | MATCH | Truthful availability labels differ | Retain backend labels |
| Report Paper | Narrow, centered white report paper | 940 px paper with 42/46 px desktop padding and print-like shadow | MATCH | None | None |
| Report Header | Research eyebrow, company title, metadata, strong rule | Matching hierarchy and typography with exact release metadata | MATCH | Rating/target block omitted | Keep omitted; not authoritative |
| Key Metrics | Prominent horizontal metric strip | Exact typed Revenue Growth, EBITDA Margin, and FCF Margin | INTENTIONAL_REAL_DATA_DIFFERENCE | Real metrics replace demo investment-view metrics | Keep exact DTO values |
| Source Map | Specialist → synthesis/claim → report flow inside paper | One exact Fundamental Analyst contribution → Released Claim → Final Report | INTENTIONAL_REAL_DATA_DIFFERENCE | Demo-only source cards removed | Keep visibly PARTIAL |
| Financial Section | Vertical section, table-like financial rows, review action | Revenue/profitability/cash rows, proof status, exact review action | MATCH | Multi-period forecast table unavailable | Keep exact released-period rows |
| Report Interaction | Content link opens related execution context | Source card/Revenue Growth open exact C actor/output/event; Back restores anchor | MATCH | C is deliberately M3-minimal | Expand only in M5 |
| Responsive / Overflow | Report remains readable at narrow viewport | Reflows metrics, source flow, rows, and tabs; no overflow at 760 px | MATCH | None | None |

## Material drift decision

`MATERIAL_VISUAL_DRIFT=NONE`

The current surface retains the V17 report-paper hierarchy, density, typography contrast, in-report Source Map, vertical report flow, and content-level interactions. Differences are required by the frozen product authority: the accepted run has no rating, target price, market-cap/valuation projections, peer/valuation report contributions, or generated PDF in its structured projections. Those demo-only values and source cards are therefore not rendered.

## Intentional real-data differences

- Run identity is the accepted UUID-backed Run, not `RUN-DEMO-FULL`.
- As-of is `2026-09-06`; metric-level dates remain their typed source dates.
- Hero metric is the exact `65.47%`, not the reference's rounded `65.5%`.
- Source Map is visibly `PARTIAL` and contains one authoritative contribution.
- The report has no Buy/target/upside/peer scenario claims because M1 does not project them.
- HTML is an available secondary export; PDF is disabled as `PDF_DEFERRED_MINIMUM_DEMO`.
- C focus is a safe exact summary, not the reference's full future-M5 execution workspace.
