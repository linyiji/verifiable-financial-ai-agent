from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.adapters.finrobot.audit import FINROBOT_PINNED_COMMIT
from src.adapters.finrobot.peer_port import (
    PeerAggregateMethod,
    PeerMetricAggregationCapability,
    PeerMetricInputError,
    PeerPeriodAlignmentError,
    SelectedComparableMetric,
    align_peer_periods,
    build_peer_metric_matrix,
    pivot_peer_metrics,
)
from src.domain.capability import CapabilityContext
from src.domain.enums import EvidenceCategory, EvidenceStatus
from src.domain.evidence import EvidenceRecord
from src.domain.peer import PeerSelectionDecision


def _evidence(
    *,
    evidence_id: str,
    symbol: str,
    metric: str = "ebitda",
    period: str = "FY2025",
    value: str = "100",
    as_of: date = date(2025, 12, 31),
    status: EvidenceStatus = EvidenceStatus.ACCEPTED,
    category: EvidenceCategory = EvidenceCategory.PEER,
    unit: str = "USD_MILLION",
    currency: str | None = "USD",
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id="RUN-PEER",
        object_id=f"OBJ-{symbol}",
        provider="canonical-test",
        source_endpoint="canonical-peer-metric",
        evidence_category=category,
        retrieved_at=datetime(2026, 9, 4, tzinfo=UTC),
        period=period,
        as_of=as_of,
        raw_artifact_ref=f"raw://{evidence_id}",
        normalized_field=metric,
        normalized_value=value,
        unit=unit,
        currency=currency,
        snapshot_hash=f"sha256:{evidence_id.lower()}",
        status=status,
    )


def _decision(symbol: str, *, selected: bool) -> PeerSelectionDecision:
    return PeerSelectionDecision(
        candidate_symbol=symbol,
        selected=selected,
        reason_summary="selected by existing policy" if selected else "rejected by existing policy",
        selection_source="fmp.stock_peers+deterministic_comparable_policy_v1",
        source_evidence_ids=(f"E-CANDIDATE-{symbol}",),
    )


def _metric(
    *,
    evidence_id: str,
    symbol: str,
    metric: str,
    period: str,
    value: str,
    as_of: date,
) -> SelectedComparableMetric:
    return SelectedComparableMetric.from_accepted_evidence(
        symbol=symbol,
        evidence=_evidence(
            evidence_id=evidence_id,
            symbol=symbol,
            metric=metric,
            period=period,
            value=value,
            as_of=as_of,
            unit="RATIO" if metric == "ev_to_ebitda" else "USD_MILLION",
            currency=None if metric == "ev_to_ebitda" else "USD",
        ),
        selection=_decision(symbol, selected=True),
    )


def _complete_observations() -> tuple[SelectedComparableMetric, ...]:
    observations: list[SelectedComparableMetric] = []
    values = {
        ("AMD", "ebitda", "FY2024"): "90",
        ("AMD", "ev_to_ebitda", "FY2024"): "20",
        ("AVGO", "ebitda", "FY2024"): "110",
        ("AVGO", "ev_to_ebitda", "FY2024"): "24",
        ("AMD", "ebitda", "FY2025"): "120",
        ("AMD", "ev_to_ebitda", "FY2025"): "22",
        ("AVGO", "ebitda", "FY2025"): "160",
        ("AVGO", "ev_to_ebitda", "FY2025"): "26",
        # FY2023 is intentionally incomplete and must be excluded, never filled.
        ("AMD", "ebitda", "FY2023"): "70",
    }
    for index, ((symbol, metric, period), value) in enumerate(values.items(), start=1):
        year = int(period.removeprefix("FY"))
        observations.append(
            _metric(
                evidence_id=f"E-METRIC-{index}",
                symbol=symbol,
                metric=metric,
                period=period,
                value=value,
                as_of=date(year, 12, 31),
            )
        )
    return tuple(observations)


def test_accepted_evidence_constructor_cannot_promote_rejected_peer() -> None:
    evidence = _evidence(evidence_id="E-AMD", symbol="AMD")
    rejected = _decision("AMD", selected=False)
    before = rejected.model_dump()

    with pytest.raises(PeerMetricInputError, match="was not selected"):
        SelectedComparableMetric.from_accepted_evidence(
            symbol="AMD", evidence=evidence, selection=rejected
        )

    assert rejected.model_dump() == before
    assert rejected.selected is False
    with pytest.raises(ValidationError):
        SelectedComparableMetric(
            run_id="RUN-PEER",
            symbol="AMD",
            metric="ebitda",
            period="FY2025",
            as_of=date(2025, 12, 31),
            value=Decimal("100"),
            unit="USD_MILLION",
            currency="USD",
            source_evidence_ids=("E-AMD",),
            selected=False,
            selection_source="test",
        )


@pytest.mark.parametrize(
    ("status", "category", "message"),
    [
        (EvidenceStatus.PARTIAL, EvidenceCategory.PEER, "must be ACCEPTED"),
        (EvidenceStatus.ACCEPTED, EvidenceCategory.FINANCIAL_STATEMENT, "PEER category"),
    ],
)
def test_evidence_constructor_enforces_accepted_peer_gate(
    status: EvidenceStatus,
    category: EvidenceCategory,
    message: str,
) -> None:
    evidence = _evidence(evidence_id="E-INVALID", symbol="AMD", status=status, category=category)
    with pytest.raises(PeerMetricInputError, match=message):
        SelectedComparableMetric.from_accepted_evidence(
            symbol="AMD", evidence=evidence, selection=_decision("AMD", selected=True)
        )


def test_period_alignment_excludes_incomplete_period_without_fill_or_projection() -> None:
    aligned = align_peer_periods(
        _complete_observations(), required_metrics=("ebitda", "ev_to_ebitda")
    )

    assert aligned.symbols == ("AMD", "AVGO")
    assert aligned.included_periods == ("FY2024", "FY2025")
    assert aligned.excluded_periods == ("FY2023",)
    assert len(aligned.observations) == 8
    assert all(item.period != "FY2023" for item in aligned.observations)


def test_alignment_fails_closed_when_no_complete_period_exists() -> None:
    observations = (
        _metric(
            evidence_id="E-AMD-EBITDA",
            symbol="AMD",
            metric="ebitda",
            period="FY2025",
            value="100",
            as_of=date(2025, 12, 31),
        ),
        _metric(
            evidence_id="E-AVGO-MULTIPLE",
            symbol="AVGO",
            metric="ev_to_ebitda",
            period="FY2025",
            value="25",
            as_of=date(2025, 12, 31),
        ),
    )
    with pytest.raises(PeerPeriodAlignmentError, match="not filled or projected"):
        align_peer_periods(observations, required_metrics=("ebitda", "ev_to_ebitda"))


def test_pivot_and_metric_matrix_are_deterministic() -> None:
    observations = _complete_observations()
    first = build_peer_metric_matrix(observations)
    second = pivot_peer_metrics(align_peer_periods(tuple(reversed(observations))))

    assert first == second
    assert first.upstream_commit == FINROBOT_PINNED_COMMIT
    assert first.symbols == ("AMD", "AVGO")
    assert first.metrics == ("ebitda", "ev_to_ebitda")
    assert len(first.rows) == 2
    assert len(first.rows[0].cells) == 4
    assert first.cell(symbol="amd", metric="ebitda", period="FY2025").value == Decimal("120")
    with pytest.raises(KeyError):
        first.cell(symbol="NVDA", metric="ebitda", period="FY2025")


@pytest.mark.asyncio
async def test_aggregation_emits_provenance_complete_calculation_records() -> None:
    matrix = build_peer_metric_matrix(_complete_observations())
    capability = PeerMetricAggregationCapability()
    records = await capability.execute(
        {
            "matrix": matrix,
            "methods": [PeerAggregateMethod.MEAN, PeerAggregateMethod.MEDIAN],
            "calculation_id_prefix": "CALC-PEER",
        },
        CapabilityContext(
            run_id="RUN-PEER",
            task_id="TASK-PEER",
            accepted_evidence_ids=list(matrix.source_evidence_ids),
        ),
    )

    assert len(records) == 8
    fy2025_ebitda_mean = next(
        item
        for item in records
        if item.formula_id == "peer_mean_v1"
        and item.parameters["metric"] == "ebitda"
        and item.parameters["period"] == "FY2025"
    )
    assert fy2025_ebitda_mean.output_value == Decimal("140")
    assert fy2025_ebitda_mean.output_unit == "USD_MILLION"
    assert fy2025_ebitda_mean.parameters["currency"] == "USD"
    assert fy2025_ebitda_mean.capability_id == "finrobot_peer_metric_aggregation"
    assert fy2025_ebitda_mean.implementation_hash
    assert fy2025_ebitda_mean.code_hash == fy2025_ebitda_mean.implementation_hash
    assert FINROBOT_PINNED_COMMIT in str(fy2025_ebitda_mean.source_ref)
    assert "Apache-2.0" in str(fy2025_ebitda_mean.source_ref)
    assert fy2025_ebitda_mean.runtime_version.startswith("Python 3.11.")
    assert fy2025_ebitda_mean.parameters["projection_policy"] == "PROHIBITED"
    assert fy2025_ebitda_mean.parameters["missing_value_policy"] == (
        "EXCLUDE_INCOMPLETE_PERIOD_NO_FILL"
    )


@pytest.mark.asyncio
async def test_aggregation_rejects_wrong_run_or_unaccepted_lineage() -> None:
    matrix = build_peer_metric_matrix(_complete_observations())
    capability = PeerMetricAggregationCapability()
    inputs = {
        "matrix": matrix,
        "methods": ["MEAN"],
        "calculation_id_prefix": "CALC-PEER",
    }

    with pytest.raises(PeerMetricInputError, match="does not belong"):
        await capability.execute(
            inputs,
            CapabilityContext(
                run_id="RUN-OTHER",
                task_id="TASK-PEER",
                accepted_evidence_ids=list(matrix.source_evidence_ids),
            ),
        )
    with pytest.raises(PeerMetricInputError, match="outside"):
        await capability.execute(
            inputs,
            CapabilityContext(
                run_id="RUN-PEER",
                task_id="TASK-PEER",
                accepted_evidence_ids=[],
            ),
        )


@pytest.mark.asyncio
async def test_aggregation_rejects_cross_currency_values() -> None:
    usd = _metric(
        evidence_id="E-USD",
        symbol="AMD",
        metric="ebitda",
        period="FY2025",
        value="100",
        as_of=date(2025, 12, 31),
    )
    eur_evidence = _evidence(
        evidence_id="E-EUR",
        symbol="ASML",
        value="120",
        currency="EUR",
    )
    eur = SelectedComparableMetric.from_accepted_evidence(
        symbol="ASML", evidence=eur_evidence, selection=_decision("ASML", selected=True)
    )
    matrix = build_peer_metric_matrix((usd, eur))
    with pytest.raises(PeerMetricInputError, match="one unit and currency"):
        await PeerMetricAggregationCapability().execute(
            {
                "matrix": matrix,
                "methods": ["MEAN"],
                "calculation_id_prefix": "CALC-PEER",
            },
            CapabilityContext(
                run_id="RUN-PEER",
                task_id="TASK-PEER",
                accepted_evidence_ids=list(matrix.source_evidence_ids),
            ),
        )
