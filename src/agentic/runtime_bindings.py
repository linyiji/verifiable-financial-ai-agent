"""Executable skill/profile authority shared by planning and admission."""

# Extracted from the existing graph semantic validator; not an Agent identity list.
SKILL_TASK_TYPES = {
    "evidence_collection_v1": frozenset({"evidence_collection"}),
    "fundamental_analysis_v1": frozenset({"fundamental_analysis"}),
    "peer_analysis_v1": frozenset({"peer_analysis"}),
    "research_news_analysis_v1": frozenset({"research_news_analysis"}),
    "valuation_analysis_v1": frozenset({"valuation_analysis"}),
    "risk_analysis_v1": frozenset({"risk_analysis"}),
    "report_synthesis_v1": frozenset({"report_synthesis", "quality_review"}),
}

# The application evidence handler executes acquisition, not SpecialistAgent.execute.
# A registered Agent owns the task; its LLM supported_task_types are not expanded.
NATIVE_PLANNING_TASK_TYPES = SKILL_TASK_TYPES["evidence_collection_v1"]


class GraphRuntimeBindingError(ValueError):
    def __init__(self):
        super().__init__("GRAPH_RUNTIME_BINDING_INVALID")


def validate_graph_runtime_bindings(graph, registry, *, scheme=None):
    """No aliases, normalization, model repair, dispatch, or persistence."""
    from src.agentic.registry import RegistrationNotFoundError

    known_tasks = {task.task_id for task in graph.tasks}
    if not known_tasks or len(known_tasks) != len(graph.tasks):
        raise GraphRuntimeBindingError()
    for task in graph.tasks:
        try:
            agent = registry.get(task.assigned_agent)
        except RegistrationNotFoundError:
            raise GraphRuntimeBindingError() from None
        if (
            task.task_type not in agent.supported_task_types | NATIVE_PLANNING_TASK_TYPES
            or task.task_type not in SKILL_TASK_TYPES.get(task.skill_id, frozenset())
            or task.run_id != graph.run_id
            or not task.task_id.startswith(graph.run_id + ":")
            or not set(task.dependencies) <= known_tasks
        ):
            raise GraphRuntimeBindingError()
    dependencies = {task.task_id: set(task.dependencies) for task in graph.tasks}
    resolved = set()
    while len(resolved) < len(dependencies):
        ready = {
            key for key, deps in dependencies.items() if key not in resolved and deps <= resolved
        }
        if not ready:
            raise GraphRuntimeBindingError()
        resolved.update(ready)
    if scheme and not set(scheme.skill_requirements) <= {task.skill_id for task in graph.tasks}:
        raise GraphRuntimeBindingError()
