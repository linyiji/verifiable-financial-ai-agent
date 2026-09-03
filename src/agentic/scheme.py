"""Research Scheme generation boundary and deterministic fallback."""

from typing import Protocol, runtime_checkable
from uuid import NAMESPACE_URL, uuid5

from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.domain.research_scheme import ResearchSchemeSnapshot


@runtime_checkable
class SchemeGenerator(Protocol):
    """Generate a run-scoped scheme candidate for later user confirmation."""

    async def generate(
        self,
        *,
        research_object: ResearchObject,
        goal: ResearchGoal,
    ) -> ResearchSchemeSnapshot: ...


class DeterministicSchemeGenerator:
    """Conservative non-LLM fallback with stable content and identifiers.

    This fallback describes required research work. It deliberately does not
    calculate, estimate, or emit financial values.
    """

    generator_id = "deterministic-scheme-generator-v1"

    async def generate(
        self,
        *,
        research_object: ResearchObject,
        goal: ResearchGoal,
    ) -> ResearchSchemeSnapshot:
        if goal.research_object_id != research_object.object_id:
            raise ValueError("goal and research object must reference the same object")

        scheme_key = f"{research_object.object_id}:{goal.goal_id}:{goal.as_of.isoformat()}"
        return ResearchSchemeSnapshot(
            scheme_id=f"SCHEME-{uuid5(NAMESPACE_URL, scheme_key)}",
            research_object_id=research_object.object_id,
            goal_id=goal.goal_id,
            research_scope=[
                "verified_financial_evidence",
                "fundamental_analysis",
                "peer_analysis",
                "research_and_news_analysis",
                "valuation_analysis",
                "risk_analysis",
                "report_synthesis",
            ],
            data_requirements=[
                "accepted_company_financial_evidence",
                "accepted_peer_evidence",
                "accepted_research_and_news_evidence",
            ],
            agent_requirements=[
                "fundamental_analyst",
                "peer_analyst",
                "research_news_analyst",
                "valuation_analyst",
                "risk_analyst",
                "research_lead",
            ],
            skill_requirements=[
                "evidence_collection_v1",
                "fundamental_analysis_v1",
                "peer_analysis_v1",
                "research_news_analysis_v1",
                "valuation_analysis_v1",
                "risk_analysis_v1",
                "report_synthesis_v1",
            ],
            calculation_requirements=[
                "deterministic_financial_calculations_only",
                "calculation_records_for_reported_values",
            ],
            assurance_requirements={
                "accepted_evidence_only": True,
                "deterministic_financial_values": True,
                "review_required": True,
            },
            report_requirements=[
                "financial_report",
                "financial_review_projection",
                "execution_details_projection",
            ],
            limitations=[
                "Fallback scheme is conservative and does not infer custom goal-specific methods."
            ],
            generated_by=self.generator_id,
            generated_model=None,
        )
