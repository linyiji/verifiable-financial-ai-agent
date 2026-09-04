import ast
import inspect
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

import src.adapters.finrobot.peer_port as peer_port
from src.adapters.finrobot.peer_port import (
    PeerMetricAggregationCapability,
    PeerMetricInputError,
    SelectedComparableMetric,
    build_peer_metric_matrix,
)
from src.capabilities.registry import CapabilityRegistry
from src.data.peers import PeerCompanyFacts, PeerSelectionService
from src.domain.capability import CapabilityContext
from src.domain.enums import CapabilityBackend, EvidenceCategory, EvidenceStatus
from src.domain.evidence import EvidenceRecord
from src.tooling.native import NativeToolBackend
from src.tooling.runtime import ToolRuntime


def _peer_evidence(evidence_id: str, symbol: str, position: int) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id="RUN-PEER-INTEGRATION",
        object_id="OBJ-NVDA",
        provider="fmp",
        source_endpoint="peers",
        evidence_category=EvidenceCategory.PEER,
        retrieved_at=datetime(2026, 9, 4, tzinfo=UTC),
        period="CURRENT",
        as_of=date(2026, 9, 4),
        raw_artifact_ref="raw://fmp/peers",
        normalized_field=f"peer_symbol_{position}",
        normalized_value=symbol,
        unit="SYMBOL",
        snapshot_hash=f"sha256:peer-{position}",
        status=EvidenceStatus.ACCEPTED,
    )


def _metric_evidence(evidence_id: str, symbol: str, value: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id="RUN-PEER-INTEGRATION",
        object_id=f"OBJ-{symbol}",
        provider="canonical-evidence-layer",
        source_endpoint="canonical-peer-metric",
        evidence_category=EvidenceCategory.PEER,
        retrieved_at=datetime(2026, 9, 4, tzinfo=UTC),
        period="FY2025",
        as_of=date(2025, 12, 31),
        raw_artifact_ref=f"raw://canonical/{symbol}/ebitda",
        normalized_field="ebitda",
        normalized_value=value,
        unit="USD_MILLION",
        currency="USD",
        snapshot_hash=f"sha256:{evidence_id.lower()}",
        status=EvidenceStatus.ACCEPTED,
    )


@pytest.mark.asyncio
async def test_selected_comparable_runtime_path_has_no_fetch_or_selection() -> None:
    candidate_evidence = (
        _peer_evidence("E-CANDIDATE-AMD", "AMD", 0),
        _peer_evidence("E-CANDIDATE-INTC", "INTC", 1),
    )
    service = PeerSelectionService()
    selection = service.select(
        subject=PeerCompanyFacts(
            symbol="NVDA",
            industry="Semiconductors",
            sector="Technology",
            market_cap=Decimal("1000"),
            available_metrics=frozenset({"ebitda"}),
            source_evidence_ids=("E-SUBJECT",),
        ),
        stock_peer_evidence=candidate_evidence,
        facts_by_symbol={
            "AMD": PeerCompanyFacts(
                symbol="AMD",
                industry="Semiconductors",
                sector="Technology",
                market_cap=Decimal("500"),
                available_metrics=frozenset({"ebitda"}),
                source_evidence_ids=("E-FACTS-AMD",),
            ),
            # Missing enrichment remains a rejection; the port must not force it in.
            "INTC": PeerCompanyFacts(symbol="INTC"),
        },
        business_relevance={"AMD": True, "INTC": True},
        required_metrics=frozenset({"ebitda"}),
    )
    decisions = {item.candidate_symbol: item for item in selection.decisions}
    rejected_before = decisions["INTC"].model_dump()
    assert decisions["AMD"].selected is True
    assert decisions["INTC"].selected is False
    assert tuple(item.candidate_symbol for item in selection.selected_comparables) == ("AMD",)

    amd_metric = _metric_evidence("E-METRIC-AMD", "AMD", "120")
    selected_metric = SelectedComparableMetric.from_accepted_evidence(
        symbol="AMD", evidence=amd_metric, selection=decisions["AMD"]
    )
    with pytest.raises(PeerMetricInputError, match="was not selected"):
        SelectedComparableMetric.from_accepted_evidence(
            symbol="INTC",
            evidence=_metric_evidence("E-METRIC-INTC", "INTC", "80"),
            selection=decisions["INTC"],
        )

    matrix = build_peer_metric_matrix((selected_metric,), required_metrics=("ebitda",))
    registry = CapabilityRegistry()
    registry.register(PeerMetricAggregationCapability())
    runtime = ToolRuntime(
        registry=registry,
        backends={CapabilityBackend.NATIVE: NativeToolBackend(registry)},
    )
    calculations = await runtime.execute(
        "finrobot_peer_metric_aggregation",
        {
            "matrix": matrix,
            "methods": ["MEAN"],
            "calculation_id_prefix": "CALC-PEER-RUNTIME",
        },
        CapabilityContext(
            run_id="RUN-PEER-INTEGRATION",
            task_id="TASK-PEER-AGGREGATION",
            accepted_evidence_ids=list(matrix.source_evidence_ids),
        ),
    )

    assert len(calculations) == 1
    assert calculations[0].output_value == Decimal("120")
    assert calculations[0].parameters["peer_symbols"] == ["AMD"]
    assert decisions["INTC"].model_dump() == rejected_before
    assert decisions["INTC"].selected is False

    # Static dependency assertion complements the runtime path: the owned port
    # has no HTTP client/import through which it could fetch or discover peers.
    tree = ast.parse(inspect.getsource(peer_port))
    imported_roots = {
        node.names[0].name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imported_roots.isdisjoint({"aiohttp", "httpx", "requests", "urllib"})
