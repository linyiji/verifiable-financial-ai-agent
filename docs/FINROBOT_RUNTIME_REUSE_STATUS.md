# FinRobot Runtime Reuse Status — WS-T0

[简体中文](FINROBOT_RUNTIME_REUSE_STATUS.zh-CN.md)

Status: **COMPLETE — ACTIVATION AUDIT**<br>
Audit date: 2026-09-04<br>
Pinned upstream commit: `d221910096de87579b02f8f0674652bf1a175f51`

## Scope and decision rule

This is a targeted activation audit of the current main project, not a repeat of the full
upstream audit. The upstream paths below were checked at the pinned commit. No upstream file was
modified or vendored.

`ACTIVE_REUSE` requires a concrete upstream implementation, an owned adapter, a registered
capability or renderer, an integration test, and a reachable production call path. Merely having
an audit entry, allowlist entry, protocol, or upstream source does not qualify.

## Runtime activation matrix

| Module | Upstream Source | Classification | Adapter | Runtime Active | Tested | Next Action |
|---|---|---|---|---:|---|---|
| Financial Data Processor | `finrobot_equity/core/src/modules/financial_data_processor.py` (`clean_financial_number`, extractors, `calculate_growth_and_forecasts`) | `PORT_PENDING` | None; audit metadata only | No | Python 3.11 isolated import/smoke recorded in `FINROBOT_EXACT_AUDIT.md`; no project runtime test | Port only non-overlapping transforms after Evidence acceptance. Forecasts must use explicit assumptions and emit CalculationRecords. Keep native revenue growth and EBITDA margin authoritative. |
| Peer Aggregation | `finrobot_equity/core/src/modules/market_data_api.py` (`combine_peer_financial_data`, `project_ebitda_for_peers`) | `PORT_PENDING` | None | No | Upstream isolated peer projection smoke only | Separate provider fetch from pure aggregation. Consume canonical peer Evidence; any projection must retain `FORECAST` classification, assumptions, version and CalculationRecord lineage. |
| Technical Indicators | `finrobot_equity/core/src/modules/market_data_api.py` (`get_technical_indicators`) | `PORT_PENDING` | None | No | Python 3.11 isolated import; no owned capability test | Extract deterministic SMA/RSI/MACD formulas from the function. Input must be ordered accepted price Evidence, output numeric CalculationRecords; heuristic labels become Judgments. Do not call upstream FMP fetch code. |
| Chart Generators | `finrobot_equity/core/src/modules/chart_generator.py` (reviewed chart functions); enhanced module remains outside the allowlist | `ADAPTER_READY_NOT_ACTIVE` | `src/adapters/finrobot/pinned.py`, operation `charts.render` | No | `tests/unit/adapters/test_finrobot_audit.py` passes against a stub backend; upstream isolated chart smoke passed | Implement a pinned, no-network backend and post-release chart service consuming canonical report data in a controlled artifact directory. Add real renderer/integration tests before activation. |
| Professional HTML Renderer | `finrobot_equity/core/src/modules/html_renderer.py` (`render_html_report`, `render_combined_html_report`) | `PORT_PENDING` | No executable adapter operation | No | Upstream isolated import only | Add an owned `ReleasedResearchResult`/canonical-report mapper, escaping and sanitization. Renderer must receive data only and must never fetch. |
| Professional PDF Renderer | `finrobot_equity/core/src/modules/professional_pdf_report.py` (`ProfessionalEquityReport`, `generate_professional_report`) | `PORT_PENDING` | No executable adapter operation. Existing `report.render_pdf` allowlist covers the older `pdf_generator.py`, not this professional renderer. | No | Older PDF boundary has stub-adapter tests; professional renderer has no project integration test | Audit and allowlist the exact professional symbols, map canonical report data, constrain output paths, and run real PDF render verification. No provider access during render. |
| News / Catalyst Analyzer | `finrobot_equity/core/src/modules/news_integrator.py`; `finrobot_equity/core/src/modules/catalyst_analyzer.py` | `REFERENCE_ONLY` | None | No | Targeted source identification only; no owned adapter/runtime test | Reuse taxonomy/prompt ideas only after the existing Live FMP Evidence layer supplies accepted News Evidence. Do not reuse connector/key handling or generate catalysts when entitlement is blocked. |
| Sensitivity Analyzer | `finrobot_equity/core/src/modules/sensitivity_analyzer.py` (`SensitivityAnalyzer`) | `REJECTED` | Explicitly not allowlisted; `PinnedFinRobotAdapter.calculate` rejects calculations | No | Isolated import passed; financial semantics rejected by prior audit | Do not activate as written. A future owned deterministic implementation must use explicit scenario assumptions, Evidence and CalculationRecord lineage and must not label a fixed-volatility range as statistical assurance. |
| Valuation Engine | `finrobot_equity/core/src/modules/valuation_engine.py` (`ValuationEngine`) | `REJECTED` | Explicitly not allowlisted; calculation path rejects it | No | Isolated import passed; implicit defaults rejected by prior audit | Do not activate as written. Any future valuation capability must version material assumptions and flow through Financial Code, Evidence, CalculationRecord and Review. |
| LLM Section Generator | `finrobot_equity/core/src/modules/text_generator_agents.py` (`generate_text_section`) and `modules/equity_agents/*` | `REJECTED` | None | No | No project runtime test | Do not bypass TeamoRouter, structured-output validation, Langfuse, Agent/Skill boundaries or Review. Prompt/persona wording may be referenced manually, but the direct client/fallback generator is not a runtime component. |
| Agent Definitions | `finrobot/agents/agent_library.py`; `finrobot_equity/core/src/modules/equity_agents/*.py` | `REFERENCE_ONLY` | None | No | No runtime import or integration test | Reuse role decomposition and prompt concepts only through owned Agent/Skill contracts. Do not import upstream agents into the scheduler. |
| Legacy AutoGen | `finrobot/agents/workflow.py` (`FinRobot`, `SingleAssistant*`, `MultiAssistant*`) plus legacy demos/experiments | `REJECTED` | None | No | No project runtime test | Keep outside the runtime. It would duplicate the owned planner, dependency scheduler, checkpoint, RuntimeEvent, replan and review semantics. |
| FinRobot Web Orchestrator | `finrobot_equity/web_app/main.py` (`execute_analysis_pipeline`, FastAPI routes) and `run_web_app.py` | `REJECTED` | None | No | No project runtime test | Do not activate. Frontend is deferred, and the subprocess/file-log pipeline duplicates the owned API/runtime, performs provider/report orchestration, and does not satisfy current contracts. |

## ACTIVE_REUSE evidence

There are **zero** `ACTIVE_REUSE` FinRobot modules on the current main branch.

The reachable financial runtime is:

```text
Research Task
→ IntegratedTaskExecutor
→ ToolRuntime
→ CapabilityRegistry
→ NativeToolBackend
→ RevenueGrowthCapability / EbitdaMarginCapability
```

The registry contains only `revenue_growth` and `ebitda_margin`. No Skill, Task, Capability,
service, API route, or release renderer constructs `PinnedFinRobotAdapter`.

The current FinRobot boundary stops at a non-active protocol path:

```text
prospective caller
→ PinnedFinRobotAdapter.execute(operation)
→ FinRobotBackend.invoke(audited entry, copied inputs)
→ [no concrete backend exists]
```

Consequently there is no truthful FinRobot `capability_id` or actual upstream runtime call path to
list. The two allowlisted operations (`charts.render`, `report.render_pdf`) are safety-ready adapter
contracts, not active reuse.

## Recommended activation order

1. **Charts** — activate the already allowlisted base chart functions behind a concrete pinned,
   no-network backend. Consume canonical post-review data only.
2. **Professional HTML renderer** — port behind a strict canonical report DTO and HTML
   sanitization boundary; never fetch data.
3. **Professional PDF renderer** — separately audit/allowlist the professional implementation,
   map the same canonical DTO, constrain asset paths, and visually verify output.
4. **Technical indicators** — port only pure formulas as deterministic Financial Code over
   accepted historical-price Evidence, producing CalculationRecords.
5. **Peer aggregation helpers** — port pure pivot/aggregation code. Keep peer acquisition in the
   existing Live FMP Evidence layer and keep forecasts behind explicit assumptions.

## Guardrails retained

- The FinRobot FMP connector is not activated; Live FMP Evidence remains the sole provider path.
- Valuation and sensitivity code cannot bypass Financial Code, Evidence, CalculationRecord,
  Review, or CanonicalExecutionRecord.
- Renderers may consume only `ReleasedResearchResult` or canonical report data and may not fetch.
- No FinRobot upstream source is modified, copied into the project, or placed on the main import
  path.
- Frontend remains deferred.

## Verification

- Pinned commit constant equals the required upstream commit: PASS.
- Targeted upstream checkout resolved the exact commit: PASS.
- `tests/unit/adapters/test_finrobot_audit.py`: 9 passed.
- Search for `PinnedFinRobotAdapter`, `charts.render`, and `report.render_pdf` outside the adapter
  package found no runtime construction or call site: PASS.
- Capability registry inspection found only the two owned native financial capabilities: PASS.
