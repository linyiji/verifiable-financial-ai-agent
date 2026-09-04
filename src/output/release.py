from datetime import datetime

from pydantic import Field

from src.domain.base import DomainModel, JsonObject
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.enums import ProofStatus, ReviewStatus
from src.domain.financial_semantics import (
    MaterialCalculationDisposition,
    MaterialFinancialClaim,
    ReleasedFinancialMetric,
    ResearchSourceCoverage,
)
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
            and all(status is ProofStatus.VERIFIED for status in self.must_prove_statuses)
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
        released_metrics: list[ReleasedFinancialMetric] | tuple[ReleasedFinancialMetric, ...] = (),
        material_claims: list[MaterialFinancialClaim] | tuple[MaterialFinancialClaim, ...] = (),
        material_calculation_dispositions: list[MaterialCalculationDisposition]
        | tuple[MaterialCalculationDisposition, ...] = (),
        research_source_coverage: ResearchSourceCoverage | None = None,
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
        if released_metrics or material_claims:
            metric_ids = {item.metric_id for item in released_metrics}
            claim_ids = {item.claim_id for item in material_claims}
            calculation_ids = {item.calculation_id for item in released_metrics}
            evidence_ids = {
                evidence_id for item in released_metrics for evidence_id in item.evidence_ids
            }
            judgment_ids = {
                str(item["judgment_id"])
                for item in judgments
                if isinstance(item.get("judgment_id"), str)
            }
            if metric_ids != set(canonical_record.metric_refs):
                raise ValueError("canonical metric refs do not match typed release")
            if claim_ids != set(canonical_record.claim_refs):
                raise ValueError("canonical claim refs do not match typed release")
            if calculation_ids - set(canonical_record.calculation_refs):
                raise ValueError("canonical record omits typed release calculations")
            if evidence_ids - set(canonical_record.evidence_refs):
                raise ValueError("canonical record omits typed release evidence")
            if judgment_ids != set(canonical_record.judgment_refs):
                raise ValueError("canonical judgment refs do not match typed release")

        payload: dict[str, object] = {
            "result_id": result_id.strip(),
            "run_id": canonical_record.run_id,
            "canonical_record_id": canonical_record.record_id,
            "structured_financial_results": snapshot(structured_financial_results),
            "released_claims": snapshot(list(released_claims)),
            "released_metrics": [
                ReleasedFinancialMetric.model_validate(item.model_dump(mode="python"))
                for item in released_metrics
            ],
            "material_claims": [
                MaterialFinancialClaim.model_validate(item.model_dump(mode="python"))
                for item in material_claims
            ],
            "material_calculation_dispositions": [
                MaterialCalculationDisposition.model_validate(item.model_dump(mode="python"))
                for item in material_calculation_dispositions
            ],
            "research_source_coverage": (
                ResearchSourceCoverage.model_validate(
                    research_source_coverage.model_dump(mode="python")
                )
                if research_source_coverage is not None
                else None
            ),
            "judgments": snapshot(list(judgments)),
            "assumption_refs": snapshot(list(assumption_refs)),
            "risk_output": snapshot(risk_output or {}),
            "limitations": snapshot(list(limitations)),
        }
        if released_at is not None:
            payload["released_at"] = released_at
        return ReleasedResearchResult.model_validate(payload)
