# Phase 4.5 M5 — V17.1 Execution collaboration visual delta

[简体中文](visual-delta.zh-CN.md)

Viewport for every captured artifact: **1440 × 900**, device scale factor **1**, browser zoom **100%**.

Reference authority: `financial_agent_workspace_v17_1_minimal_c_execution_fanin.html` from the accepted V17.1 handoff (SHA-256 `1be45091827c6485b624f6a44bf2e0f48bc650836b1a15024a3f7c395718762e`). The requested `(3)` filename is not present; this is the byte-identical canonical asset already accepted for M3/M4. Current authority: exact released Run `RUN-57aed683-75d6-4b47-acc6-a73053ea492e` served by the real Phase 4 backend.

## Matched evidence

| State | Reference | Current |
| --- | --- | --- |
| C1 · Execution top | `reference/REF-C1-execution-top.png` | `current/CUR-C1-execution-top.png` |
| C2 · Actor collaboration | `reference/REF-C2-actor-collaboration.png` | `current/CUR-C2-real-actor-rail.png` |
| C3 · Fundamental Analyst | `reference/REF-C3-fundamental-analyst.png` | `current/CUR-C3-real-fundamental-analyst.png` |
| C4 · Input / Process / Output | `reference/REF-C4-input-process-output.png` | `current/CUR-C4-real-input-process-output.png` |
| C5 · Report Contribution | `reference/REF-C5-report-contribution.png` | `current/CUR-C5-hero-report-contribution.png` |
| C6 · Secondary record mode | `reference/REF-C6-timeline.png` | `current/CUR-C6-observable-records.png` |

## Visual delta matrix

| Area | Classification | Evidence / decision |
| --- | --- | --- |
| Shell | MATCH | Navy research navigation, white workspace header, centered surface and compact card language preserve the governed product shell. |
| Results Header | MINOR_DRIFT | Current header is denser and includes exact Run, Object and As-of identity established in M2. |
| A/B/C Tabs | MATCH | Three equal-width tabs, active white state and per-surface availability retain the reference navigation model. |
| Execution Header | MATCH | C is an explicit business surface with a short actor-centered description and visible PARTIAL state. |
| Toolbar | MATCH | Collaboration is primary; a secondary record mode plus actor search replaces the reference's demo-only raw/full filters. |
| Actor Rail | MATCH | A sticky left rail drives the selected Actor detail on the right and persists actor-only selection in the URL. |
| Actor Groups | INTENTIONAL_REAL_DATA_DIFFERENCE | Current renders exactly 1 Research Lead, 5 Specialists and 6 Supporting Execution actors observed for this Run; it does not reproduce the reference demo roster. |
| Selected Actor Header | MATCH | Actor type, display role, stable actor ID, status and observable summary counts are visually distinct. |
| Execution Cards | MATCH | Each public Actor detail is task-centered and reads Input → Observable Process → Output → Report Contribution. |
| Input Column | INTENTIONAL_REAL_DATA_DIFFERENCE | Current uses typed public reference IDs only. It neither expands provider payloads nor assigns actor-level refs to an invented hidden sequence. |
| Process Column | INTENTIONAL_REAL_DATA_DIFFERENCE | Current has 7 public `task.completed` detail events. It shows only event type/status/ID because timestamp, sequence, duration and private reasoning are not in the public contract. |
| Output Column | MATCH | AgentOutput ID, status, safe summary and opt-in structured findings/risks/limitations follow the reference hierarchy using real DTO fields. |
| Report Contribution | INTENTIONAL_REAL_DATA_DIFFERENCE | Exactly one authoritative relation is shown, on `fundamental_analyst`, to `metric-revenue-growth`; all other Actors explicitly show no observed relation. |
| Secondary Timeline | INTENTIONAL_REAL_DATA_DIFFERENCE | Current intentionally uses a 7-row observable-record table. A chronological timeline would fabricate ordering because the public surface exposes no timestamp or sequence. |
| Responsive / Overflow | MATCH | At ≤900px I/P/O collapses vertically; at ≤760px rail, headers and controls become single-column and long IDs wrap or remain in bounded overflow containers. |

## Acceptance

- Structural material drift: **0**
- Minor visual drift: **1** (governed exact-run header density)
- Intentional real-data differences: **5** (real actor roster, reference-only inputs, safe process projection, one authoritative contribution, non-chronological secondary table)
- V17.1 Execution alignment: **HIGH** — actor-centered collaboration, I/P/O reading order and report fan-in are restored without exposing hidden chain-of-thought or manufacturing unavailable Execution/Review relations.
