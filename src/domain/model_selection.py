"""Identity-only product preference, persisted with the ResearchGoal."""

from src.domain.recovery import Frozen, RouteId


class ModelSelection(Frozen):
    route_id: RouteId


def selected_model(preferences):
    if "model_selection" not in preferences:
        return None
    return ModelSelection.model_validate(preferences["model_selection"])
