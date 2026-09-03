from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from src.data.peers import PeerCompanyFacts, PeerSelectionService
from src.domain.enums import EvidenceStatus
from src.domain.evidence import EvidenceRecord


def _peer_evidence(index: int, symbol: str) -> EvidenceRecord:
    observed_at = datetime(2026, 9, 4, 12, index, tzinfo=UTC)
    return EvidenceRecord(
        evidence_id=f"EVD-PEER-{index}",
        run_id="RUN-PEERS",
        object_id="OBJ-NVDA",
        provider="fmp",
        source_locator="fmp://stock-peers?symbol=NVDA",
        source_endpoint="peers",
        retrieved_at=datetime(2026, 9, 4, 12, 30, tzinfo=UTC),
        observed_at=observed_at,
        period="CURRENT",
        as_of=date(2026, 9, 4),
        raw_artifact_ref="artifact://stock-peers",
        normalized_field=f"peer_symbol_{index}",
        normalized_value=symbol,
        unit="SYMBOL",
        snapshot_hash="peer-snapshot",
        status=EvidenceStatus.ACCEPTED,
    )


def test_candidate_evidence_policy_and_selected_universe_remain_separate() -> None:
    metrics = frozenset({"revenue", "ebitda", "pe"})
    result = PeerSelectionService().select(
        subject=PeerCompanyFacts(
            symbol="NVDA",
            industry="Semiconductors",
            sector="Technology",
            market_cap=Decimal("1000000000000"),
        ),
        stock_peer_evidence=[
            _peer_evidence(0, "AMD"),
            _peer_evidence(1, "MSFT"),
        ],
        facts_by_symbol={
            "AMD": PeerCompanyFacts(
                symbol="AMD",
                industry="Semiconductors",
                sector="Technology",
                market_cap=Decimal("500000000000"),
                available_metrics=metrics,
                source_evidence_ids=("EVD-AMD-PROFILE", "EVD-AMD-METRICS"),
            ),
            "MSFT": PeerCompanyFacts(
                symbol="MSFT",
                industry="Software",
                sector="Technology",
                market_cap=Decimal("3000000000000"),
                available_metrics=metrics,
                source_evidence_ids=("EVD-MSFT-PROFILE", "EVD-MSFT-METRICS"),
            ),
        },
        business_relevance={"AMD": True, "MSFT": False},
        required_metrics=metrics,
    )

    assert [candidate.candidate_symbol for candidate in result.candidates] == ["AMD", "MSFT"]
    assert [decision.selected for decision in result.decisions] == [True, False]
    assert [candidate.candidate_symbol for candidate in result.selected_comparables] == ["AMD"]
    assert result.decisions[0].source_evidence_ids == [
        "EVD-PEER-0",
        "EVD-AMD-PROFILE",
        "EVD-AMD-METRICS",
    ]
