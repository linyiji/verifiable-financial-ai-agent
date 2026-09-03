# FinRobot Exact Audit & Reuse Report — WS-H

Status: **COMPLETE — MODULE GATE PASS**

Audit date: 2026-09-04

Project baseline: Python `>=3.11,<3.12`

Foundation base: `0a5838624776e0854a6d42f5b1ef9d8ba159173e`

## 1. Audit identity and pin

| Field | Audited value |
|---|---|
| Upstream | `https://github.com/AI4Finance-Foundation/FinRobot.git` |
| Exact commit | `d221910096de87579b02f8f0674652bf1a175f51` |
| Commit timestamp | `2026-08-23T20:06:08+08:00` |
| Commit subject | `Update README.md` |
| Checkout mode | detached, temporary directory outside this repository |
| Vendor tree committed | no |
| Runtime pin | `src.adapters.finrobot.audit.FINROBOT_PINNED_COMMIT` |

The audit used the exact commit already identified by the architecture review. The upstream tree
was not modified. No FinRobot source, generated artifact, configuration file, or credential was
copied into this repository.

Source integrity evidence:

| Upstream file | SHA-256 at audited commit |
|---|---|
| `LICENSE` | `bbcb4226500b503737713f0c9a9da17efce56fa6989b9f0538071dcb60826af5` |
| `NOTICE` | `d1da20e9e1e8a0f3189665c4f21cf35f0eba1a8a1432f95a734db0640e289346` |
| `setup.py` | `16c90b1727b04f8326c11c534800fdb9cfb5085b2ac327e1a6aa580f95c347f0` |
| `requirements.txt` | `685ca02bb04d09f4019f582ec28e41143eff055654fd706e751dd7aa59caae02` |

## 2. Compatibility method and result

The compatibility verdict intentionally distinguishes Python syntax, isolated optional-dependency
imports, and compatibility with the main project's installed baseline.

1. `setup.py` declares Python `>=3.10,<3.12`, so Python 3.11 is inside upstream metadata.
2. Python `3.11.16` compiled all `.py` files below `finrobot/` and the equity `modules/` directory.
3. An isolated temporary Python 3.11 environment installed the audited equity dependency set:
   `numpy 1.26.4`, `pandas 2.0.3`, `Requests 2.31.0`, `matplotlib 3.11.1`,
   `reportlab 5.0.1`, and `yfinance 0.2.66`.
4. The ten audited equity modules imported successfully in that isolated environment:
   financial processor, market API, valuation, sensitivity, base/enhanced charts, base/professional
   HTML, and base/professional PDF.
5. Offline smoke checks passed for historical metric extraction, peer EBITDA projection, and
   technical-indicator chart generation.
6. The main project virtual environment does **not** contain those optional libraries. No project
   dependency was changed during this workstream.

An import pass is not an architecture acceptance. Decisions below also account for the Evidence
Gate, CalculationRecord, Forecast/Fact distinction, assurance ownership, secret handling, and
existing Phase-1 implementations.

## 3. Existing Logic Reuse Matrix

| Existing module / symbols | Category | Decision | Python 3.11 | Inputs | Outputs | Dependencies | Action |
|---|---|---|---|---|---|---|---|
| `financial_data_processor.py`: `clean_financial_number`, API/PDF extractors | financial data processor | `PORT_REQUIRED` | isolated import pass | scalars or raw provider/PDF DataFrames | float/NaN or mixed DataFrame | numpy, pandas | Port only useful non-overlapping normalization after Evidence acceptance. |
| `financial_data_processor.py`: `calculate_growth_and_forecasts` | financial calculations | `PORT_REQUIRED` | isolated import pass | historical DataFrame, unversioned forecast config | mixed actual/forecast DataFrame | numpy, pandas | Keep Phase-1 native growth/margin; future port must emit CalculationRecord and link AssumptionSet. |
| `finrobot/data_source/fmp_utils.py`: `FMPUtils` | FMP connector | `REJECT_FOR_MVP` | syntax pass; full package stack not installed | ticker/date/year and global environment key | strings, dicts, DataFrames | numpy, pandas, requests plus package imports | Keep Phase-1 async `FMPProvider`. |
| `market_data_api.py`: FMP statement/ratio fetch functions | FMP connector | `REJECT_FOR_MVP` | isolated import pass | ticker, plaintext key, period, limit | raw DataFrames | pandas, requests, yfinance | Do not bypass RawProviderSnapshot and Evidence ingestion. |
| `market_data_api.py`: `combine_peer_financial_data` | peer logic | `PORT_REQUIRED` | isolated import pass | tickers, key, years | EBITDA and EV/EBITDA pivots | pandas, requests | Split fetch from pure aggregation; consume canonical peer values. |
| `market_data_api.py`: `project_ebitda_for_peers` | peer logic | `PORT_REQUIRED` | isolated import/smoke pass | historical peer EBITDA, horizon | historical + forecast DataFrame | pandas | Require assumption/version/run lineage and preserve `FORECAST`. |
| `valuation_engine.py`: `ValuationEngine` | calculations | `REJECT_FOR_MVP` | isolated import pass | loose financial/peer dicts | target-price objects and synthesis dict | numpy, pandas | Defaults are not financially certifiable without an explicit model contract. |
| `sensitivity_analyzer.py`: `SensitivityAnalyzer` | calculations | `REJECT_FOR_MVP` | isolated import pass | mixed forecast DataFrame, scenario ranges | tables, intervals, narrative | numpy, pandas | Fixed-volatility “confidence interval” must not be released as statistical assurance. |
| `market_data_api.py`: `get_technical_indicators` | technical indicators | `PORT_REQUIRED` | isolated import pass | ticker + key; internally fetches price series | SMA/RSI/MACD and heuristic labels | numpy, pandas, requests | Split acquisition from pure formulas; accepted evidence in, CalculationRecord out. |
| `chart_generator.py`: reviewed chart functions | charts | `ADAPTER_REUSE` | isolated import/smoke pass | reviewed DataFrames/dicts, ticker, controlled path | base64 PNG + file | matplotlib, numpy, pandas | Reuse through pinned no-network renderer operation `charts.render`. |
| `html_renderer.py`: HTML report functions | report renderer | `PORT_REQUIRED` | isolated import pass | fixed-schema dict + template | HTML string | pandas | Add escaping/sanitization and canonical FinancialReport mapping. |
| `pdf_generator.py`: `EquityReportPDF`, `generate_equity_report_pdf` | report renderer | `ADAPTER_REUSE` | isolated import pass | reviewed report dict, controlled path | PDF asset | pandas, reportlab | Optional post-release renderer via `report.render_pdf`; do not replace report JSON. |
| `finrobot/functional/reportlab.py`: `build_annual_report` | report renderer | `REJECT_FOR_MVP` | syntax pass; full package stack not installed | narrative, ticker, chart paths | PDF path/error text | reportlab, FMPUtils, YFinanceUtils | Reject report-time data refetch and mixed provider/render responsibility. |

Matrix totals:

- `DIRECT_REUSE`: 0
- `ADAPTER_REUSE`: 2
- `PORT_REQUIRED`: 6
- `REJECT_FOR_MVP`: 5

Zero `DIRECT_REUSE` decisions are deliberate: even pure-looking renderer functions perform file I/O
and require controlled output paths, so the adapter boundary remains mandatory.

## 4. Category findings

### 4.1 Financial data processor

Useful source logic exists, but it cannot be passed raw FMP DataFrames in this system. The API
extractor mixes normalization and calculations and emits ratios as percentage strings. It uses
truth-value checks that drop valid zero values. The forecast function mixes actual and forecast
columns and includes implicit EPS growth and P/E compression assumptions without an AssumptionSet
or calculation lineage.

Decision: port selected, non-overlapping transforms only. The accepted native Revenue Growth and
EBITDA Margin capabilities remain authoritative.

### 4.2 FMP connectors

Both upstream connector variants conflict with the project boundary:

- synchronous network requests in calculation/report flows;
- raw provider DataFrames returned directly to downstream code;
- credentials placed in query-string URLs;
- many requests have no explicit timeout;
- broad exception handling converts failures to `None`/text;
- the equity example prints a key prefix and `common_utils.py` prints a loaded key value;
- the older class relies on a process-global environment value;
- repeated endpoint calls and provider access during report generation.

Decision: reject both upstream FMP connectors for MVP. Phase-1 `HttpxFMPTransport`, `FMPProvider`,
and `EvidenceIngestionService` are retained. Upstream endpoint coverage may be used as reference
only.

### 4.3 Peer logic

The pivot construction is reusable in concept but is coupled to provider calls. The EBITDA
projection uses mean historical YoY growth, which is a forecast assumption rather than a fact.

Decision: port later as two boundaries: canonical peer aggregation, then an explicit forecast
capability with assumption, run, version, and output-type lineage.

### 4.4 Calculations and valuation

The valuation engine hard-codes material defaults, including 10% net debt, 60% EBITDA-to-FCF,
default valuation multiples, growth/WACC values, and confidence weights. The DCF sensitivity range
changes discounting without consistently recalculating terminal value. The sensitivity analyzer's
confidence interval assumes a fixed 15% standard deviation and is not an empirical confidence
interval.

Decision: reject these valuation/sensitivity calculations for MVP. They may inform future contract
design but must not become certified financial capabilities as written.

### 4.5 Technical indicators

The SMA, RSI and MACD formulas are recognizable and ran under Python 3.11, but the function fetches
FMP data itself, catches all exceptions, returns partial `None` values, and mixes numeric results
with non-deterministic heuristic labels.

Decision: port required. A future port should accept an ordered accepted price/volume snapshot,
version formula choices (including EMA adjustment), emit numeric CalculationRecords, and classify
labels as Judgment where appropriate.

### 4.6 Charts and report renderers

The chart and base PDF modules are the best reuse candidates because they can operate on supplied
reviewed data. They are approved only through a controlled adapter: no network, fixed audited
revision, controlled output directory, no credentials, and post-release data.

HTML is not approved yet because report values flow into large templates without an explicit
sanitization contract. The older ReportLab utility is rejected because it refetches FMP/YFinance
data while rendering.

## 5. Implemented adapter boundary

New owned code:

- `src/adapters/finrobot/audit.py`
  - exact upstream repository and commit pin;
  - machine-readable six-category audit matrix;
  - operation lookup that permits only `DIRECT_REUSE`/`ADAPTER_REUSE` rows.
- `src/adapters/finrobot/pinned.py`
  - dependency-injected backend; importing the main app does not import FinRobot;
  - exact revision enforcement;
  - operation allowlist (`charts.render`, `report.render_pdf`);
  - deep-copied inputs;
  - recursive rejection of credential-bearing input keys;
  - result type enforcement for report asset paths.

This boundary does not claim FinRobot is installed and does not execute an upstream function by
itself. A later optional backend may bind the approved module symbols only after dependency,
license, sandbox, and asset-path gates are accepted.

## 6. Security and secret review

- No live provider call was made.
- No credential or local environment value was read, printed, persisted, or committed.
- The adapter rejects credential-bearing report/chart inputs before backend invocation.
- Error messages do not include input values.
- The upstream clone stayed outside the repository.
- Upstream examples that log key material are explicitly not reused.

## 7. License and attribution

At the audited commit:

- root `LICENSE` is Apache License 2.0;
- `NOTICE` requires retention and contains trademark/disclaimer text;
- `TRADEMARK_POLICY.md` restricts product-name/logo usage;
- `setup.py` still declares MIT metadata/classifiers.

The root LICENSE/NOTICE are treated as authoritative and the metadata conflict remains a release
review item. Any future distribution of adapted upstream source/assets must preserve Apache-2.0
notices, document the exact commit, avoid product-brand confusion, and separately verify FMP API
commercial/display rights.

## 8. Contract and dependency requests

### CONTRACT_CHANGE_REQUEST-FR-001 — optional renderer dependencies

Status: **DEFERRED / NOT APPLIED**

If the integration owner activates `charts.render` or `report.render_pdf`, add an isolated optional
dependency group rather than main-runtime dependencies:

```text
numpy>=1.24,<2
pandas>=2,<3
matplotlib>=3.6,<4       # charts only
reportlab>=3.6           # PDF only
```

The versions must be locked and retested on Python 3.11. This workstream did not edit
`pyproject.toml`.

No domain, enum, API, Settings, or application contract change is requested.

## 9. Module gate evidence

```text
Python 3.11 upstream compileall: PASS
Isolated equity module imports: 10/10 PASS
Offline upstream smoke checks: PASS
WS-H adapter tests: 9 PASS
Full project tests: 86 PASS (2 dependency deprecation warnings)
Ruff lint: PASS
Owned Python format check: PASS (5 files)
Contract boundary diff: PASS; frozen files unchanged
Secret scan: PASS; no credential-shaped values in changed files
FinRobot import boundary: PASS; no FinRobot import outside adapter package
```

## 10. Known gaps

- No FinRobot vendor/submodule is added; deployment cannot activate the backend yet.
- Approved renderer operations still require a sandboxed backend and controlled artifact path.
- HTML sanitization is not implemented.
- FMP endpoint expansion belongs to the existing FMP/Evidence workstream, not this adapter.
- Peer, forecast, technical-indicator, and valuation contract ports remain future work.
- Upstream dependency files are not fully locked; exact production resolution requires a lockfile.

## 11. Contract deviations

**NONE.** FinRobot remains a third-party capability source and does not become the main runtime,
provider boundary, orchestrator, calculation authority, or report source of truth.
