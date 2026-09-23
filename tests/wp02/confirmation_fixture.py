"""Lawful Confirm for legacy synthetic planner templates; never mint receipts."""

from contextlib import nullcontext
from functools import partial
from unittest.mock import patch

from src.domain.research_object import ResearchObject
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.task import PlannedTaskGraph


async def confirm_template(
    service, template, *, symbol="SYNTHETIC", scenario=None, node_profiles=None,
):
    class Scheme:
        async def generate(self, *, research_object, goal):
            raw = template.scheme.model_dump(mode="json")
            raw.update(goal_id=goal.goal_id, research_object_id=research_object.object_id,
                       confirmed_at=None)
            return ResearchSchemeSnapshot.model_validate(raw)

    class Planner:
        def plan(self, *, run_id, goal, scheme):
            raw = template.runtime.planned_graph.model_dump(mode="json")
            assert raw["run_id"] == run_id
            return PlannedTaskGraph.model_validate(raw)

    # Only the existing object port is seeded; Run/snapshot/receipt creation is
    # entirely performed by prepare_run -> confirm_run and its persistence owner.
    if await service.repository.get_object(template.run.research_object_id) is None:
        await service.repository.add_object(ResearchObject(
            object_id=template.run.research_object_id, symbol=symbol,
            company_name="Synthetic", exchange="LOCAL",
        ))
    previous = (service.scheme_generator, service.planner, service._run_id_factory)
    service.scheme_generator, service.planner = Scheme(), Planner()
    service._run_id_factory = lambda: template.run.run_id
    try:
        draft = await service.prepare_run(
            research_object_id=template.run.research_object_id,
            research_goal=template.goal.goal_text, as_of=template.goal.as_of,
            preferences=template.goal.preferences,
        )
        from src.application.execution_profiles import resolve_execution_snapshot

        # Existing explicit server profile arguments select the old/narrow
        # policy under test. The real resolver and all validators still run.
        selection = (patch(
            "src.application.execution_profiles.resolve_execution_snapshot",
            partial(resolve_execution_snapshot, scenario=scenario, node_profiles=node_profiles),
        ) if scenario is not None else nullcontext())
        with selection:
            return await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    finally:
        service.scheme_generator, service.planner, service._run_id_factory = previous


async def persist_template(repository, template):
    """Replace a never-persisted test template with the actual Confirm return."""
    from src.application.service import ResearchApplicationService

    assert template.confirmed_risk_semantic_binding is None
    service = ResearchApplicationService(repository=repository)
    confirmed = await confirm_template(service, template)
    template.__dict__.update(confirmed.__dict__)
    return template
