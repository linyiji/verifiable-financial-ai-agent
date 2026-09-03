"""Machine-readable audit decisions for the pinned FinRobot capability source.

This module deliberately contains no FinRobot imports.  The upstream checkout is
optional and stays outside the application repository; integration is permitted
only through explicitly audited operations.
"""

from dataclasses import dataclass
from enum import StrEnum

FINROBOT_REPOSITORY = "https://github.com/AI4Finance-Foundation/FinRobot.git"
FINROBOT_PINNED_COMMIT = "d221910096de87579b02f8f0674652bf1a175f51"


class AuditCategory(StrEnum):
    FINANCIAL_DATA_PROCESSOR = "financial_data_processor"
    FMP_CONNECTOR = "fmp_connector"
    PEER_LOGIC = "peer_logic"
    CALCULATIONS = "calculations"
    TECHNICAL_INDICATORS = "technical_indicators"
    CHARTS_REPORT_RENDERER = "charts_report_renderer"


class ReuseDecision(StrEnum):
    DIRECT_REUSE = "DIRECT_REUSE"
    ADAPTER_REUSE = "ADAPTER_REUSE"
    PORT_REQUIRED = "PORT_REQUIRED"
    REJECT_FOR_MVP = "REJECT_FOR_MVP"


@dataclass(frozen=True, slots=True)
class FinRobotAuditEntry:
    category: AuditCategory
    source_module: str
    symbols: tuple[str, ...]
    decision: ReuseDecision
    python_311: str
    inputs: str
    outputs: str
    dependencies: tuple[str, ...]
    action: str
    operation_id: str | None = None


AUDIT_MATRIX: tuple[FinRobotAuditEntry, ...] = (
    FinRobotAuditEntry(
        category=AuditCategory.FINANCIAL_DATA_PROCESSOR,
        source_module="finrobot_equity/core/src/modules/financial_data_processor.py",
        symbols=(
            "clean_financial_number",
            "extract_historical_metrics_from_api_data",
            "extract_historical_metrics_from_pdf_data",
        ),
        decision=ReuseDecision.PORT_REQUIRED,
        python_311="ISOLATED_IMPORT_PASS; optional deps absent from project baseline",
        inputs="scalar values or provider/PDF pandas.DataFrame collections",
        outputs="float/NaN or mixed-type pandas.DataFrame",
        dependencies=("numpy", "pandas"),
        action="Port only non-overlapping normalization after EvidenceRecord acceptance.",
    ),
    FinRobotAuditEntry(
        category=AuditCategory.FINANCIAL_DATA_PROCESSOR,
        source_module="finrobot_equity/core/src/modules/financial_data_processor.py",
        symbols=("calculate_growth_and_forecasts",),
        decision=ReuseDecision.PORT_REQUIRED,
        python_311="ISOLATED_IMPORT_PASS; optional deps absent from project baseline",
        inputs="mixed historical DataFrame and unversioned forecast_config",
        outputs="mixed actual/forecast DataFrame with percentage strings",
        dependencies=("numpy", "pandas"),
        action=(
            "Keep accepted native growth/margin capabilities; port only new forecast logic "
            "behind assumptions, evidence, and CalculationRecord contracts."
        ),
    ),
    FinRobotAuditEntry(
        category=AuditCategory.FMP_CONNECTOR,
        source_module="finrobot/data_source/fmp_utils.py",
        symbols=("FMPUtils",),
        decision=ReuseDecision.REJECT_FOR_MVP,
        python_311="SYNTAX_PASS; full upstream dependency stack not installed",
        inputs="ticker/date/year plus process-global FMP_API_KEY",
        outputs="strings, dicts, and pandas.DataFrame values",
        dependencies=("numpy", "pandas", "requests"),
        action="Retain Phase-1 async FMPProvider and Evidence ingestion boundary.",
    ),
    FinRobotAuditEntry(
        category=AuditCategory.FMP_CONNECTOR,
        source_module="finrobot_equity/core/src/modules/market_data_api.py",
        symbols=(
            "get_comprehensive_financial_data",
            "get_fmp_income_statement",
            "get_fmp_balance_sheet",
            "get_fmp_cash_flow_statement",
            "get_fmp_ratios_and_key_metrics",
        ),
        decision=ReuseDecision.REJECT_FOR_MVP,
        python_311="ISOLATED_IMPORT_PASS; optional deps absent from project baseline",
        inputs="ticker, plaintext api_key, period, limit",
        outputs="raw pandas.DataFrame values",
        dependencies=("pandas", "requests", "yfinance"),
        action="Do not bypass RawProviderSnapshot, validation, normalization, or Evidence Gate.",
    ),
    FinRobotAuditEntry(
        category=AuditCategory.PEER_LOGIC,
        source_module="finrobot_equity/core/src/modules/market_data_api.py",
        symbols=("combine_peer_financial_data",),
        decision=ReuseDecision.PORT_REQUIRED,
        python_311="ISOLATED_IMPORT_PASS; optional deps absent from project baseline",
        inputs="ticker list, api_key, years_limit",
        outputs="EBITDA and EV/EBITDA pivot DataFrames",
        dependencies=("pandas", "requests"),
        action=(
            "Separate provider fetch from aggregation; accept canonical peer metric values only."
        ),
    ),
    FinRobotAuditEntry(
        category=AuditCategory.PEER_LOGIC,
        source_module="finrobot_equity/core/src/modules/market_data_api.py",
        symbols=("project_ebitda_for_peers",),
        decision=ReuseDecision.PORT_REQUIRED,
        python_311="ISOLATED_IMPORT_PASS; optional deps absent from project baseline",
        inputs="historical peer EBITDA DataFrame and projection horizon",
        outputs="DataFrame containing historical and projected values",
        dependencies=("pandas",),
        action="Require an AssumptionSet and preserve FORECAST classification before reuse.",
    ),
    FinRobotAuditEntry(
        category=AuditCategory.CALCULATIONS,
        source_module="finrobot_equity/core/src/modules/valuation_engine.py",
        symbols=("ValuationEngine", "ValuationResult"),
        decision=ReuseDecision.REJECT_FOR_MVP,
        python_311="ISOLATED_IMPORT_PASS; optional deps absent from project baseline",
        inputs="loosely typed financial_data and peer_data dicts",
        outputs="target-price dataclasses and synthesis dicts",
        dependencies=("numpy", "pandas"),
        action=(
            "Do not certify implicit 10% net-debt, 60% EBITDA-to-FCF, default-multiple, "
            "or confidence-weight assumptions."
        ),
    ),
    FinRobotAuditEntry(
        category=AuditCategory.CALCULATIONS,
        source_module="finrobot_equity/core/src/modules/sensitivity_analyzer.py",
        symbols=("SensitivityAnalyzer", "SensitivityResult"),
        decision=ReuseDecision.REJECT_FOR_MVP,
        python_311="ISOLATED_IMPORT_PASS; optional deps absent from project baseline",
        inputs="mixed forecast DataFrame and scenario ranges",
        outputs="scenario DataFrames, tuples, and narrative strings",
        dependencies=("numpy", "pandas"),
        action="Do not present fixed 15% standard-deviation assumptions as confidence intervals.",
    ),
    FinRobotAuditEntry(
        category=AuditCategory.TECHNICAL_INDICATORS,
        source_module="finrobot_equity/core/src/modules/market_data_api.py",
        symbols=("get_technical_indicators",),
        decision=ReuseDecision.PORT_REQUIRED,
        python_311="ISOLATED_IMPORT_PASS; optional deps absent from project baseline",
        inputs="ticker and api_key; function fetches 250 price/volume records",
        outputs="SMA/RSI/MACD values plus heuristic labels",
        dependencies=("numpy", "pandas", "requests"),
        action=(
            "Split data acquisition from deterministic SMA/RSI/MACD code; consume accepted "
            "price evidence and emit CalculationRecord values."
        ),
    ),
    FinRobotAuditEntry(
        category=AuditCategory.CHARTS_REPORT_RENDERER,
        source_module="finrobot_equity/core/src/modules/chart_generator.py",
        symbols=(
            "generate_revenue_ebitda_chart",
            "generate_ev_ebitda_peer_chart",
            "generate_technical_indicators_chart",
            "generate_sensitivity_heatmap",
        ),
        decision=ReuseDecision.ADAPTER_REUSE,
        python_311="ISOLATED_IMPORT_PASS; optional renderer deps required",
        inputs="reviewed pandas.DataFrame/dict data, ticker, controlled output path",
        outputs="base64 PNG string and a file in the controlled render directory",
        dependencies=("matplotlib", "numpy", "pandas"),
        action="Allow only behind a no-network controlled renderer adapter.",
        operation_id="charts.render",
    ),
    FinRobotAuditEntry(
        category=AuditCategory.CHARTS_REPORT_RENDERER,
        source_module="finrobot_equity/core/src/modules/html_renderer.py",
        symbols=("render_html_report", "render_combined_html_report"),
        decision=ReuseDecision.PORT_REQUIRED,
        python_311="ISOLATED_IMPORT_PASS; optional pandas dependency required",
        inputs="large fixed-schema report dict and template string",
        outputs="HTML string",
        dependencies=("pandas",),
        action="Add escaping/sanitization and map from the canonical FinancialReport contract.",
    ),
    FinRobotAuditEntry(
        category=AuditCategory.CHARTS_REPORT_RENDERER,
        source_module="finrobot_equity/core/src/modules/pdf_generator.py",
        symbols=("generate_equity_report_pdf", "EquityReportPDF"),
        decision=ReuseDecision.ADAPTER_REUSE,
        python_311="ISOLATED_IMPORT_PASS; optional renderer deps required",
        inputs="controlled output path and reviewed report_data dict",
        outputs="PDF asset at the requested path",
        dependencies=("pandas", "reportlab"),
        action="Use as optional post-release renderer; do not replace Phase-1 report JSON.",
        operation_id="report.render_pdf",
    ),
    FinRobotAuditEntry(
        category=AuditCategory.CHARTS_REPORT_RENDERER,
        source_module="finrobot/functional/reportlab.py",
        symbols=("ReportLabUtils.build_annual_report",),
        decision=ReuseDecision.REJECT_FOR_MVP,
        python_311="SYNTAX_PASS; full dependency stack not installed",
        inputs="ticker, generated narrative, chart paths, filing date",
        outputs="PDF path or error text",
        dependencies=("reportlab", "FMPUtils", "YFinanceUtils"),
        action="Reject report-time provider refetch and mixed data/render responsibilities.",
    ),
)


def audit_entry_for_operation(operation_id: str) -> FinRobotAuditEntry:
    matches = [entry for entry in AUDIT_MATRIX if entry.operation_id == operation_id]
    if not matches:
        raise KeyError(f"FinRobot operation is not audited for execution: {operation_id}")
    entry = matches[0]
    if entry.decision not in {ReuseDecision.DIRECT_REUSE, ReuseDecision.ADAPTER_REUSE}:
        raise PermissionError(f"FinRobot operation is not approved for reuse: {operation_id}")
    return entry
