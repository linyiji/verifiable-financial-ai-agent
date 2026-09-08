"""Prospective, task-scoped model authority. Provider responses never grant authority."""

from typing import Literal

from pydantic import Field, model_validator

from src.domain.recovery import Capability, Frozen, ModelId, RecoveryBudget, RouteId


class ModelExecutionPolicy(Frozen):
    version: Literal["bounded-model-execution/v1"] = "bounded-model-execution/v1"
    task_profile: str
    provider_route: RouteId
    provider: Literal["teamorouter", "mimo"]
    preferred_model: ModelId
    authorized_actual_models: tuple[ModelId, ...] = Field(min_length=1, max_length=4)
    dynamic_substitution_allowed: bool = False
    capability_states: dict[str, Capability]
    recovery_budget: RecoveryBudget
    capability_check: bool = False

    @model_validator(mode="after")
    def provider_boundary(self):
        if self.preferred_model not in self.authorized_actual_models:
            raise ValueError("Preferred model must be authorized")
        prefix = "mimo-" if self.provider == "mimo" else "gpt-"
        if any(not model.startswith(prefix) for model in self.authorized_actual_models):
            raise ValueError("Model authorization cannot cross provider authority")
        return self

    def outcome(self, provider, wire_model, actual_model):
        if provider != self.provider:
            return "PROVIDER_IDENTITY_OUT_OF_POLICY"
        if wire_model != self.preferred_model or actual_model not in self.authorized_actual_models:
            return "MODEL_IDENTITY_OUT_OF_POLICY"
        if actual_model != self.preferred_model:
            return (
                "MODEL_EXECUTION_SUBSTITUTED"
                if self.dynamic_substitution_allowed
                else "MODEL_IDENTITY_OUT_OF_POLICY"
            )
        return "MODEL_EXECUTION_DIRECT"


# Explicit grants, not ALL_SUPPORTED_MODELS. Other profiles remain exact-route.
# MiMo v2.5 participates in the same resolver through its independent authority.
DYNAMIC_GRANTS = {
    ("fundamental_analysis", "teamorouter-luna"): ("teamorouter-terra",),
    ("valuation_analysis", "teamorouter-luna"): ("teamorouter-terra",),
    ("risk_analysis", "teamorouter-luna"): ("teamorouter-terra",),
    ("GENERATED_CAPABILITY:free_cash_flow_margin", "teamorouter-luna"): ("teamorouter-terra",),
}

# Prospective task authorization, separate from registration and capability evidence.
TASK_CANDIDATES = {
    "GENERATED_CAPABILITY:gross_margin": (
        "teamorouter-sol",
        "teamorouter-luna",
        "teamorouter-terra",
    ),
    "fundamental_analysis": (
        "teamorouter-sol",
        "teamorouter-luna",
        "teamorouter-terra",
        "mimo-direct",
    ),
    "valuation_analysis": (
        "teamorouter-sol",
        "teamorouter-luna",
        "teamorouter-terra",
        "mimo-direct",
    ),
    "risk_analysis": ("teamorouter-sol", "teamorouter-luna", "teamorouter-terra", "mimo-direct"),
    "peer_analysis": ("mimo-direct", "teamorouter-sol", "teamorouter-luna"),
    "research_news_analysis": ("mimo-direct", "teamorouter-sol", "teamorouter-luna"),
    "report_synthesis": ("teamorouter-sol", "teamorouter-luna", "mimo-direct"),
    "GENERATED_CAPABILITY:free_cash_flow_margin": (
        "teamorouter-sol",
        "teamorouter-luna",
        "teamorouter-terra",
    ),
}


def resolve_model_execution(
    scope, route, routes, capabilities, budget, *, check=False, grants=None
):
    candidate = routes[route]
    if not candidate.authority_exists:
        raise ValueError("Provider authority is absent")
    allowed = [candidate.model]
    states = {candidate.model: capabilities[route]}
    for target in (DYNAMIC_GRANTS if grants is None else grants).get(
        (scope.task_profile, route), ()
    ):
        other = routes.get(target)
        if (
            other is not None
            and other.authority_exists
            and other.provider == candidate.provider
            and capabilities[target] not in {Capability.QUARANTINED, Capability.UNSUPPORTED}
            and (capabilities[target] == Capability.VERIFIED or check)
        ):
            allowed.append(other.model)
            states[other.model] = capabilities[target]
    return ModelExecutionPolicy(
        task_profile=scope.task_profile,
        provider_route=route,
        provider=candidate.provider,
        preferred_model=candidate.model,
        authorized_actual_models=tuple(allowed),
        dynamic_substitution_allowed=len(allowed) > 1,
        capability_states=states,
        recovery_budget=budget,
        capability_check=check,
    )
