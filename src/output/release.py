from datetime import datetime

from pydantic import Field

from src.domain.base import DomainModel, JsonObject
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.enums import ProofStatus, ReviewStatus
from src.domain.released_research_result import ReleasedResearchResult
from src.output._snapshot import snapshot


class ReleaseGateSnapshot(DomainModel):
    """Control-plane decision inputs required before result publication."""

    review_status: ReviewStatus
    has_hard_block: bool = False
    must_prove_statuses: list[ProofStatus] = Field(default_factory=list)

    @property
    def is_satisfied(self) -> bool:
        return (
            self.review_status is ReviewStatus.PASS
            and not self.has_hard_block
            and all(
                status in {ProofStatus.VALID, ProofStatus.VERIFIED}
                for status in self.must_prove_statuses
            )
        )


class ReleasedResearchResultBuilder:
    """Publish a result only when the supplied release-gate snapshot passes."""

    @staticmethod
    def build(
        *,
        result_id: str,
        canonical_record: CanonicalExecutionRecord,
        release_gate: ReleaseGateSnapshot,
        structured_financial_results: JsonObject,
        released_claims: list[JsonObject] | tuple[JsonObject, ...] = (),
        judgments: list[JsonObject] | tuple[JsonObject, ...] = (),
        assumption_refs: list[str] | tuple[str, ...] = (),
        risk_output: JsonObject | None = None,
        limitations: list[str] | tuple[str, ...] = (),
        released_at: datetime | None = None,
    ) -> ReleasedResearchResult:
        if not result_id.strip():
            raise ValueError("result_id must not be blank")
        if not release_gate.is_satisfied:
            raise ValueError("release gate is not satisfied")

        payload: dict[str, object] = {
            "result_id": result_id.strip(),
            "run_id": canonical_record.run_id,
            "structured_financial_results": snapshot(structured_financial_results),
            "released_claims": snapshot(list(released_claims)),
            "judgments": snapshot(list(judgments)),
            "assumption_refs": snapshot(list(assumption_refs)),
            "risk_output": snapshot(risk_output or {}),
            "limitations": snapshot(list(limitations)),
        }
        if released_at is not None:
            payload["released_at"] = released_at
        return ReleasedResearchResult.model_validate(payload)
