from datetime import datetime

from pydantic import Field, model_validator

from src.domain.base import DomainModel, JsonObject, utc_now
from src.domain.enums import MaterialCalculationDispositionStatus
from src.domain.financial_semantics import (
    MaterialCalculationDisposition,
    MaterialFinancialClaim,
    ReleasedFinancialMetric,
    ResearchSourceCoverage,
)


class ReleasedResearchResult(DomainModel):
    result_id: str
    run_id: str
    canonical_record_id: str | None = None
    structured_financial_results: JsonObject = Field(default_factory=dict)
    released_claims: list[JsonObject] = Field(default_factory=list)
    released_metrics: tuple[ReleasedFinancialMetric, ...] = ()
    material_claims: tuple[MaterialFinancialClaim, ...] = ()
    material_calculation_dispositions: tuple[MaterialCalculationDisposition, ...] = Field(
        default_factory=tuple
    )
    research_source_coverage: ResearchSourceCoverage | None = None
    judgments: list[JsonObject] = Field(default_factory=list)
    assumption_refs: list[str] = Field(default_factory=list)
    risk_output: JsonObject = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    released_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_typed_release_closure(self) -> "ReleasedResearchResult":
        if not self.released_metrics and not self.material_claims:
            return self
        if not self.canonical_record_id:
            raise ValueError("typed financial release requires canonical_record_id")
        if self.released_claims:
            raise ValueError("legacy released_claims cannot coexist with typed material_claims")
        metric_by_id = {metric.metric_id: metric for metric in self.released_metrics}
        if len(metric_by_id) != len(self.released_metrics):
            raise ValueError("released metric ids must be unique")
        if len({metric.calculation_id for metric in self.released_metrics}) != len(
            self.released_metrics
        ):
            raise ValueError("released metric calculation ids must be unique")
        dispositions = {
            disposition.calculation_id: disposition
            for disposition in self.material_calculation_dispositions
        }
        if len(dispositions) != len(self.material_calculation_dispositions):
            raise ValueError("material calculation dispositions must be unique")
        reportable = {
            calculation_id: disposition
            for calculation_id, disposition in dispositions.items()
            if disposition.status is MaterialCalculationDispositionStatus.REPORTABLE
        }
        if set(reportable) != {metric.calculation_id for metric in self.released_metrics}:
            raise ValueError("every typed released metric requires one reportable disposition")
        if any(disposition.metric_id not in metric_by_id for disposition in reportable.values()):
            raise ValueError("reportable disposition references an unknown metric")
        claims_by_metric: dict[str, MaterialFinancialClaim] = {}
        for claim in self.material_claims:
            if claim.run_id != self.run_id or claim.metric_id in claims_by_metric:
                raise ValueError("typed claims must be unique per metric and belong to the run")
            claims_by_metric[claim.metric_id] = claim
        if set(claims_by_metric) != set(metric_by_id):
            raise ValueError("every released metric requires exactly one typed material claim")
        for metric_id, metric in metric_by_id.items():
            claim = claims_by_metric[metric_id]
            if (
                claim.value != metric.canonical_value
                or claim.unit is not metric.canonical_unit
                or claim.period != metric.period
                or claim.period_basis is not metric.period_basis
                or claim.actuality is not metric.actuality
                or claim.as_of != metric.as_of
                or claim.currency != metric.currency
                or claim.calculation_refs != (metric.calculation_id,)
                or claim.evidence_refs != metric.evidence_ids
            ):
                raise ValueError("typed material claim does not match its released metric")
        return self
