"""Research Lead initial planning implementation."""

from dataclasses import dataclass

from src.domain.enums import TaskOrigin, TaskStatus
from src.domain.research_goal import ResearchGoal
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.task import PlannedTaskGraph, Task


@dataclass(frozen=True, slots=True)
class _TaskTemplate:
    suffix: str
    task_type: str
    goal: str
    assigned_agent: str
    skill_id: str
    dependency_suffixes: tuple[str, ...] = ()


_INITIAL_PLAN: tuple[_TaskTemplate, ...] = (
    _TaskTemplate(
        suffix="evidence",
        task_type="evidence_collection",
        goal="Collect and validate the evidence required by the confirmed research scheme",
        assigned_agent="research_news_analyst",
        skill_id="evidence_collection_v1",
    ),
    _TaskTemplate(
        suffix="fundamentals",
        task_type="fundamental_analysis",
        goal="Analyze company fundamentals using accepted evidence and deterministic calculations",
        assigned_agent="fundamental_analyst",
        skill_id="fundamental_analysis_v1",
        dependency_suffixes=("evidence",),
    ),
    _TaskTemplate(
        suffix="peers",
        task_type="peer_analysis",
        goal="Analyze comparable companies using accepted evidence",
        assigned_agent="peer_analyst",
        skill_id="peer_analysis_v1",
        dependency_suffixes=("evidence",),
    ),
    _TaskTemplate(
        suffix="research-news",
        task_type="research_news_analysis",
        goal="Analyze relevant research and news using accepted evidence",
        assigned_agent="research_news_analyst",
        skill_id="research_news_analysis_v1",
        dependency_suffixes=("evidence",),
    ),
    _TaskTemplate(
        suffix="valuation",
        task_type="valuation_analysis",
        goal="Interpret deterministic valuation capability outputs",
        assigned_agent="valuation_analyst",
        skill_id="valuation_analysis_v1",
        dependency_suffixes=("evidence", "fundamentals", "peers"),
    ),
    _TaskTemplate(
        suffix="risk",
        task_type="risk_analysis",
        goal="Assess material risks from accepted evidence and completed analyses",
        assigned_agent="risk_analyst",
        skill_id="risk_analysis_v1",
        dependency_suffixes=("evidence", "fundamentals", "research-news"),
    ),
    _TaskTemplate(
        suffix="synthesis",
        task_type="report_synthesis",
        goal="Synthesize completed specialist outputs into a review-ready research result",
        assigned_agent="research_lead",
        skill_id="report_synthesis_v1",
        dependency_suffixes=(
            "fundamentals",
            "peers",
            "research-news",
            "valuation",
            "risk",
        ),
    ),
)


class ResearchLeadPlanner:
    """Create the complete initial graph before runtime execution starts."""

    planner_id = "research-lead-planner-v1"

    def plan(
        self,
        *,
        run_id: str,
        goal: ResearchGoal,
        scheme: ResearchSchemeSnapshot,
    ) -> PlannedTaskGraph:
        if scheme.goal_id != goal.goal_id:
            raise ValueError("scheme and goal identifiers must match")
        if scheme.research_object_id != goal.research_object_id:
            raise ValueError("scheme and goal must reference the same research object")
        if scheme.confirmed_at is None:
            raise ValueError("the research scheme must be confirmed before planning")

        planned_skill_ids = {template.skill_id for template in _INITIAL_PLAN}
        missing_skills = set(scheme.skill_requirements) - planned_skill_ids
        if missing_skills:
            detail = sorted(missing_skills)
            raise ValueError(
                f"confirmed scheme contains unsupported skill requirements: {detail}"
            )

        ids = {template.suffix: f"{run_id}:{template.suffix}" for template in _INITIAL_PLAN}
        tasks = [
            Task(
                task_id=ids[template.suffix],
                run_id=run_id,
                task_type=template.task_type,
                goal=template.goal,
                assigned_agent=template.assigned_agent,
                skill_id=template.skill_id,
                dependencies=[ids[suffix] for suffix in template.dependency_suffixes],
                origin=TaskOrigin.PLAN,
                status=TaskStatus.CREATED,
            )
            for template in _INITIAL_PLAN
        ]
        return PlannedTaskGraph(
            graph_id=f"{run_id}:planned:v1",
            run_id=run_id,
            version=1,
            tasks=tasks,
        )
