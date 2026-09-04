from typing import Protocol

from src.domain.base import JsonObject


class SemanticReviewAdapter(Protocol):
    async def review_claims(
        self,
        claims: list[JsonObject],
        *,
        evidence_refs: list[str],
        calculation_refs: list[str],
    ) -> list[JsonObject]: ...
