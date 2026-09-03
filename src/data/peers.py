from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, runtime_checkable

from src.domain.enums import EvidenceStatus
from src.domain.evidence import EvidenceRecord
from src.domain.peer import PeerCandidate, PeerSelectionDecision


@dataclass(frozen=True, slots=True)
class PeerCompanyFacts:
    """Evidence-backed facts used to enrich a raw provider candidate symbol."""

    symbol: str
    industry: str | None = None
    sector: str | None = None
    market_cap: Decimal | None = None
    available_metrics: frozenset[str] = field(default_factory=frozenset)
    source_evidence_ids: tuple[str, ...] = ()


@runtime_checkable
class PeerCandidateSource(Protocol):
    source_name: str

    def candidates(
        self,
        *,
        subject_symbol: str,
        stock_peer_evidence: Sequence[EvidenceRecord],
        facts_by_symbol: Mapping[str, PeerCompanyFacts],
        required_metrics: frozenset[str],
    ) -> tuple[PeerCandidate, ...]: ...


class StockPeersCandidateSource:
    """Treat accepted FMP Stock Peers symbols as candidates, never selections."""

    source_name = "fmp.stock_peers"

    def candidates(
        self,
        *,
        subject_symbol: str,
        stock_peer_evidence: Sequence[EvidenceRecord],
        facts_by_symbol: Mapping[str, PeerCompanyFacts],
        required_metrics: frozenset[str],
    ) -> tuple[PeerCandidate, ...]:
        subject = subject_symbol.strip().upper()
        canonical_facts = {symbol.upper(): facts for symbol, facts in facts_by_symbol.items()}
        candidates: list[PeerCandidate] = []
        seen: set[str] = set()
        for evidence in stock_peer_evidence:
            if not _is_stock_peer_candidate_evidence(evidence):
                continue
            symbol = str(evidence.normalized_value).strip().upper()
            if not symbol or symbol == subject or symbol in seen:
                continue
            seen.add(symbol)
            facts = canonical_facts.get(symbol)
            fact_evidence = facts.source_evidence_ids if facts is not None else ()
            available_metrics = facts.available_metrics if facts is not None else frozenset()
            candidates.append(
                PeerCandidate(
                    candidate_symbol=symbol,
                    source_evidence_ids=list(dict.fromkeys((evidence.evidence_id, *fact_evidence))),
                    industry=facts.industry if facts is not None else None,
                    sector=facts.sector if facts is not None else None,
                    market_cap=facts.market_cap if facts is not None else None,
                    data_available=bool(fact_evidence),
                    metric_comparable=required_metrics.issubset(available_metrics),
                )
            )
        return tuple(candidates)


@dataclass(frozen=True, slots=True)
class PeerSelectionPolicy:
    """Deterministic, auditable comparable-company selection policy."""

    minimum_market_cap_ratio: Decimal = Decimal("0.20")
    maximum_market_cap_ratio: Decimal = Decimal("5.00")
    policy_name: str = "deterministic_comparable_policy_v1"

    def decide(
        self,
        *,
        subject: PeerCompanyFacts,
        candidates: Sequence[PeerCandidate],
        business_relevance: Mapping[str, bool],
        candidate_source: str,
    ) -> tuple[PeerSelectionDecision, ...]:
        relevance = {symbol.upper(): value for symbol, value in business_relevance.items()}
        return tuple(
            self._decide_one(
                subject=subject,
                candidate=candidate,
                business_relevant=relevance.get(candidate.candidate_symbol.upper(), False),
                candidate_source=candidate_source,
            )
            for candidate in candidates
        )

    def _decide_one(
        self,
        *,
        subject: PeerCompanyFacts,
        candidate: PeerCandidate,
        business_relevant: bool,
        candidate_source: str,
    ) -> PeerSelectionDecision:
        same_industry = _same_nonempty(subject.industry, candidate.industry)
        same_sector = _same_nonempty(subject.sector, candidate.sector)
        classification_relevant = same_industry or same_sector
        market_cap_ratio = _market_cap_ratio(candidate.market_cap, subject.market_cap)
        size_comparable = market_cap_ratio is not None and (
            self.minimum_market_cap_ratio <= market_cap_ratio <= self.maximum_market_cap_ratio
        )
        checks = {
            "classification": classification_relevant,
            "business": business_relevant,
            "market_cap": size_comparable,
            "data": candidate.data_available,
            "metrics": candidate.metric_comparable,
        }
        selected = all(checks.values())
        classification = (
            "industry_match"
            if same_industry
            else ("sector_match" if same_sector else "classification_mismatch")
        )
        ratio_summary = "unavailable" if market_cap_ratio is None else f"{market_cap_ratio:.2f}x"
        failed = ",".join(name for name, passed in checks.items() if not passed) or "none"
        reason_summary = (
            f"{'selected' if selected else 'rejected'}; classification={classification}; "
            f"business_relevant={str(business_relevant).lower()}; "
            f"market_cap_ratio={ratio_summary}; data_available="
            f"{str(candidate.data_available).lower()}; metric_comparable="
            f"{str(candidate.metric_comparable).lower()}; failed_checks={failed}"
        )
        return PeerSelectionDecision(
            candidate_symbol=candidate.candidate_symbol,
            selected=selected,
            reason_summary=reason_summary,
            selection_source=f"{candidate_source}+{self.policy_name}",
            source_evidence_ids=list(candidate.source_evidence_ids),
        )


@dataclass(frozen=True, slots=True)
class PeerSelectionResult:
    candidates: tuple[PeerCandidate, ...]
    decisions: tuple[PeerSelectionDecision, ...]
    selected_comparables: tuple[PeerCandidate, ...]


class PeerSelectionService:
    def __init__(
        self,
        *,
        candidate_source: PeerCandidateSource | None = None,
        policy: PeerSelectionPolicy | None = None,
    ) -> None:
        self._candidate_source = candidate_source or StockPeersCandidateSource()
        self._policy = policy or PeerSelectionPolicy()

    def select(
        self,
        *,
        subject: PeerCompanyFacts,
        stock_peer_evidence: Sequence[EvidenceRecord],
        facts_by_symbol: Mapping[str, PeerCompanyFacts],
        business_relevance: Mapping[str, bool],
        required_metrics: frozenset[str],
    ) -> PeerSelectionResult:
        candidates = self._candidate_source.candidates(
            subject_symbol=subject.symbol,
            stock_peer_evidence=stock_peer_evidence,
            facts_by_symbol=facts_by_symbol,
            required_metrics=required_metrics,
        )
        decisions = self._policy.decide(
            subject=subject,
            candidates=candidates,
            business_relevance=business_relevance,
            candidate_source=self._candidate_source.source_name,
        )
        selected_symbols = {
            decision.candidate_symbol for decision in decisions if decision.selected
        }
        return PeerSelectionResult(
            candidates=candidates,
            decisions=decisions,
            selected_comparables=tuple(
                candidate
                for candidate in candidates
                if candidate.candidate_symbol in selected_symbols
            ),
        )


def _is_stock_peer_candidate_evidence(evidence: EvidenceRecord) -> bool:
    return (
        evidence.status is EvidenceStatus.ACCEPTED
        and evidence.provider.lower() == "fmp"
        and evidence.source_endpoint == "peers"
        and evidence.normalized_field.startswith("peer_symbol_")
        and evidence.unit == "SYMBOL"
    )


def _same_nonempty(left: str | None, right: str | None) -> bool:
    return bool(left and right and left.strip().casefold() == right.strip().casefold())


def _market_cap_ratio(candidate: Decimal | None, subject: Decimal | None) -> Decimal | None:
    if candidate is None or subject is None or subject <= 0 or candidate <= 0:
        return None
    return candidate / subject
