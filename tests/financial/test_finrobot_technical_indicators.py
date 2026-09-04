from __future__ import annotations

import ast
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from src.adapters.finrobot.audit import FINROBOT_PINNED_COMMIT
from src.adapters.finrobot.technical import (
    UPSTREAM_TECHNICAL_SOURCE,
    HistoricalPriceEvidenceError,
    InsufficientHistoryError,
    MACD12269Capability,
    RSI14Capability,
    SMA50Capability,
    SMA200Capability,
    TechnicalIndicatorJudgmentService,
    VolumeRatio20Capability,
    ZeroAverageVolumeError,
    exponential_moving_average,
    latest_volume_ratio,
    moving_average_convergence_divergence,
    ordered_accepted_price_points,
    relative_strength_index,
    simple_moving_average,
)
from src.domain.calculation import CalculationRecord
from src.domain.capability import CapabilityContext
from src.domain.enums import CalculationStatus, EvidenceCategory, EvidenceStatus
from src.domain.evidence import EvidenceRecord


def history(*, count: int = 220, run_id: str = "RUN-1") -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    started = date(2026, 1, 1)
    retrieved = datetime(2026, 9, 4, tzinfo=UTC)
    for index in range(count):
        observed = started + timedelta(days=index)
        common = {
            "run_id": run_id,
            "object_id": "OBJ-NVDA",
            "provider": "fmp",
            "source_locator": "/stable/historical-price-eod/full",
            "source_endpoint": "/stable/historical-price-eod/full",
            "evidence_purpose": "historical_market_context",
            "evidence_category": EvidenceCategory.MARKET,
            "retrieved_at": retrieved,
            "period": "DAILY",
            "as_of": observed,
            "raw_artifact_ref": "artifact://historical",
            "snapshot_hash": "sha256:fixture",
            "status": EvidenceStatus.ACCEPTED,
        }
        records.extend(
            (
                EvidenceRecord(
                    evidence_id=f"EVD-CLOSE-{index:03d}",
                    normalized_field="close",
                    normalized_value=str(index + 1),
                    unit="CURRENCY",
                    currency="USD",
                    **common,
                ),
                EvidenceRecord(
                    evidence_id=f"EVD-VOLUME-{index:03d}",
                    normalized_field="volume",
                    normalized_value=str(100 + index),
                    unit="COUNT",
                    **common,
                ),
            )
        )
    return records


def context(records: list[EvidenceRecord]) -> CapabilityContext:
    return CapabilityContext(
        run_id="RUN-1",
        task_id="TASK-TECHNICAL",
        accepted_evidence_ids=[record.evidence_id for record in records],
    )


def test_pure_math_formulas_are_deterministic_and_version_choices_are_explicit() -> None:
    values = [Decimal(index) for index in range(1, 221)]

    assert simple_moving_average(values, window=50) == Decimal("195.5")
    assert simple_moving_average(values, window=200) == Decimal("120.5")
    assert relative_strength_index(values, period=14) == Decimal(100)
    assert exponential_moving_average([Decimal(1), Decimal(2), Decimal(3)], span=3) == (
        Decimal(1),
        Decimal("1.5"),
        Decimal("2.25"),
    )
    constant_macd = moving_average_convergence_divergence([Decimal(9)] * 34)
    assert constant_macd.line == constant_macd.signal == constant_macd.histogram == 0
    with localcontext() as decimal_context:
        decimal_context.prec = 50
        assert latest_volume_ratio([Decimal(index) for index in range(1, 21)]) == Decimal(
            20
        ) / Decimal("10.5")


def test_evidence_gate_requires_ordered_accepted_paired_market_history() -> None:
    records = history(count=20)
    points = ordered_accepted_price_points(records)
    assert len(points) == 20
    assert points[0].as_of < points[-1].as_of

    rejected = list(records)
    rejected[0] = rejected[0].model_copy(update={"status": EvidenceStatus.REJECTED})
    with pytest.raises(HistoricalPriceEvidenceError, match="not ACCEPTED"):
        ordered_accepted_price_points(rejected)

    unordered = [*records[2:4], *records[0:2], *records[4:]]
    with pytest.raises(HistoricalPriceEvidenceError, match="oldest-to-newest"):
        ordered_accepted_price_points(unordered)

    with pytest.raises(HistoricalPriceEvidenceError, match="both required"):
        ordered_accepted_price_points(records[:-1])

    quote = list(records)
    quote[0] = quote[0].model_copy(update={"evidence_purpose": "market_context"})
    with pytest.raises(HistoricalPriceEvidenceError, match="not historical price evidence"):
        ordered_accepted_price_points(quote)


@pytest.mark.asyncio
async def test_capabilities_emit_only_numeric_calculation_records_with_full_provenance() -> None:
    records = history()
    capability_context = context(records)
    capabilities = (
        SMA50Capability(),
        SMA200Capability(),
        RSI14Capability(),
        MACD12269Capability(),
        VolumeRatio20Capability(),
    )
    outputs: list[CalculationRecord] = []
    for index, capability in enumerate(capabilities):
        result = await capability.execute(
            {"history": records, "calculation_id": f"CALC-{index}"},
            capability_context,
        )
        outputs.extend(result if isinstance(result, tuple) else (result,))

    assert len(outputs) == 7
    assert outputs[0].output_value == Decimal("195.5")
    assert outputs[1].output_value == Decimal("120.5")
    assert outputs[2].output_value == Decimal(100)
    with localcontext() as decimal_context:
        decimal_context.prec = 50
        assert outputs[-1].output_value == Decimal(319) / Decimal("309.5")
    assert all(isinstance(output.output_value, Decimal) for output in outputs)
    assert all(output.status is CalculationStatus.PASS for output in outputs)
    assert all(output.implementation_hash.startswith("sha256:") for output in outputs)
    assert all(output.implementation_hash == output.code_hash for output in outputs)
    assert all(output.runtime_version.startswith("Python 3.11.") for output in outputs)
    assert all(FINROBOT_PINNED_COMMIT in output.source_ref for output in outputs)
    assert all("license=Apache-2.0" in output.source_ref for output in outputs)
    assert all(output.input_evidence_ids for output in outputs)
    assert UPSTREAM_TECHNICAL_SOURCE.endswith("#get_technical_indicators")

    forbidden_labels = {"overbought", "oversold", "bullish", "bearish"}
    serialized_calculations = str([output.model_dump(mode="json") for output in outputs]).lower()
    assert all(label not in serialized_calculations for label in forbidden_labels)


@pytest.mark.asyncio
async def test_evidence_must_be_listed_in_capability_context_allowlist() -> None:
    records = history(count=50)
    incomplete_context = CapabilityContext(
        run_id="RUN-1",
        task_id="TASK-TECHNICAL",
        accepted_evidence_ids=[record.evidence_id for record in records[:-1]],
    )

    with pytest.raises(HistoricalPriceEvidenceError, match="accepted_evidence_ids"):
        await SMA50Capability().execute(
            {"history": records, "calculation_id": "CALC-SMA50"},
            incomplete_context,
        )


@pytest.mark.asyncio
async def test_indicator_labels_are_versioned_judgments_not_calculation_values() -> None:
    records = history()
    rsi = await RSI14Capability().execute(
        {"history": records, "calculation_id": "CALC-RSI"},
        context(records),
    )
    macd_line, macd_signal, _ = await MACD12269Capability().execute(
        {"history": records, "calculation_id": "CALC-MACD"},
        context(records),
    )
    policy = TechnicalIndicatorJudgmentService()

    rsi_judgment = policy.rsi(rsi, skill_version="technical_analysis_v1")
    macd_judgment = policy.macd(
        macd_line,
        macd_signal,
        skill_version="technical_analysis_v1",
    )

    assert rsi_judgment.value == "OVERBOUGHT"
    assert macd_judgment.value == "BULLISH"
    assert rsi_judgment.requires_review is True
    assert macd_judgment.requires_review is True
    assert rsi_judgment.calculation_ids == [rsi.calculation_id]
    assert isinstance(rsi.output_value, Decimal)
    assert "OVERBOUGHT" not in str(rsi.model_dump(mode="json"))


def test_owned_port_has_no_provider_or_network_library_imports() -> None:
    source_path = Path(__file__).parents[2] / "src/adapters/finrobot/technical.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_roots = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert {"requests", "httpx", "yfinance", "pandas", "numpy", "socket", "subprocess"}.isdisjoint(
        imported_roots
    )


def test_formula_edge_cases_fail_explicitly() -> None:
    with pytest.raises(InsufficientHistoryError, match="SMA50"):
        simple_moving_average([Decimal(1)] * 49, window=50)
    with pytest.raises(InsufficientHistoryError, match="15 closing prices"):
        relative_strength_index([Decimal(1)] * 14)
    with pytest.raises(ZeroAverageVolumeError, match="must not be zero"):
        latest_volume_ratio([Decimal(0)] * 20)
    assert relative_strength_index([Decimal(5)] * 15) == Decimal(50)
