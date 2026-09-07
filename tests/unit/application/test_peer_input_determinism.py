from copy import deepcopy

from src.application.execution import _peer_model_support
from src.domain.peer import PeerCandidate, PeerSelectionDecision


def test_peer_projection_is_clock_independent_and_preserves_business_fields():
    def build(timestamp):
        candidate = PeerCandidate(candidate_symbol="AMD", created_at=timestamp)
        decision = PeerSelectionDecision(
            candidate_symbol="AMD",
            selected=False,
            reason_summary="Missing enrichment",
            selection_source="test",
            created_at=timestamp,
        )
        return {
            "candidates": [candidate.model_dump(mode="json")],
            "selection_decisions": [decision.model_dump(mode="json")],
            "selected_comparables": [candidate.model_dump(mode="json")],
            "status": "selected",
            "evidence": {"created_at": "authoritative-date"},
        }

    first = build("2026-01-01T00:00:00Z")
    saved = deepcopy(first)
    later = build("2026-09-07T00:00:00Z")
    projected = _peer_model_support(first)
    assert projected == _peer_model_support(later)
    assert first == saved
    assert projected["evidence"] == first["evidence"]
    for key in ("candidates", "selection_decisions", "selected_comparables"):
        assert projected[key] == [{k: v for k, v in first[key][0].items() if k != "created_at"}]
