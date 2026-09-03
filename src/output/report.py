from pydantic import Field

from src.domain.base import DomainModel, JsonObject
from src.domain.released_research_result import ReleasedResearchResult
from src.output._snapshot import snapshot


class FinancialReport(DomainModel):
    """Minimum Phase-1 report JSON contract."""

    research_object: str
    financial_summary: JsonObject = Field(default_factory=dict)
    fundamental_result: JsonObject = Field(default_factory=dict)
    peer_result: JsonObject = Field(default_factory=dict)
    valuation_result: JsonObject = Field(default_factory=dict)
    risk_result: JsonObject = Field(default_factory=dict)
    investment_thesis: JsonObject = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class FinancialReportRenderer:
    """Map released data into the report model without recalculation."""

    _SECTION_NAMES = (
        "financial_summary",
        "fundamental_result",
        "peer_result",
        "valuation_result",
        "investment_thesis",
    )

    @classmethod
    def render(
        cls,
        result: ReleasedResearchResult,
        *,
        research_object: str | None = None,
    ) -> FinancialReport:
        financial_results = result.structured_financial_results
        resolved_object = research_object or financial_results.get("research_object")
        if not isinstance(resolved_object, str) or not resolved_object.strip():
            raise ValueError("research_object is required to render a financial report")

        sections: dict[str, JsonObject] = {}
        for section_name in cls._SECTION_NAMES:
            section = financial_results.get(section_name, {})
            if not isinstance(section, dict):
                raise ValueError(f"{section_name} must be a JSON object")
            sections[section_name] = snapshot(section)

        risk_result = result.risk_output or financial_results.get("risk_result", {})
        if not isinstance(risk_result, dict):
            raise ValueError("risk_result must be a JSON object")

        return FinancialReport(
            research_object=resolved_object.strip(),
            risk_result=snapshot(risk_result),
            limitations=snapshot(result.limitations),
            **sections,
        )
