"""Explicit route composition. No ranking, auto switching, or secrets in descriptors."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.mimo import MimoClient
from src.adapters.llm.teamorouter import TeamoRouterClient
from src.infrastructure.config.settings import LLMSettings, Settings


@dataclass(frozen=True)
class ProviderRoute:
    provider_route_id: str
    provider_id: str
    model_id: str
    endpoint_authority_ref: str
    structured_output_capability: str
    timeout_policy: ProviderExecutionPolicyV1


def load_mimo_authority(path=None, *, settings=None):
    """Load evaluator configuration or an explicit private file, never emit values."""
    settings = settings or Settings()
    path = path or settings.mimo_authority_file
    if path is not None:
        path = Path(path)
        if not path.is_file():
            raise ValueError("MiMo authority unavailable")
        values = dotenv_values(path)
    else:
        values = {
            "MIMO_API_KEY": settings.mimo_api_key.get_secret_value()
            if settings.mimo_api_key
            else None,
            "MIMO_BASE_URL": settings.mimo_base_url,
            "MIMO_CHAT_MODEL": settings.mimo_chat_model,
        }
    key, base, model = (values.get(k) for k in ("MIMO_API_KEY", "MIMO_BASE_URL", "MIMO_CHAT_MODEL"))
    if not all(isinstance(v, str) and v.strip() for v in (key, base, model)):
        raise ValueError("MiMo authority incomplete")
    url = urlsplit(base)
    if (
        (url.scheme, url.hostname, url.path.rstrip("/")) != ("https", "api.xiaomimimo.com", "/v1")
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.port not in (None, 443)
    ):
        raise ValueError("MiMo direct endpoint authority invalid")
    if model not in {"mimo-v2.5", "mimo-v2.5-pro"}:
        raise ValueError("MiMo model structured capability not established")
    return LLMSettings(
        provider="mimo", api_key=key, base_url=base, primary_model=model, fallback_model=model
    )


def configured_incremental_provider(settings, *, route_id=None, mimo_authority=None):
    """The only provider-specific choice is in composition, never in the researcher."""
    selected = route_id or settings.incremental_provider_route
    if settings.vfa_credential_mode == "evaluator":
        from src.evaluator.client import EvaluatorGatewayLLM, active_session

        client = EvaluatorGatewayLLM(active_session(), selected)
        client.task_profile = "INCREMENTAL_RESEARCH_PLANNING"
        return client
    if selected == "mimo-direct":
        client = MimoClient(load_mimo_authority(mimo_authority, settings=settings))
        client.route_ids = {client.model_name: selected}
    elif selected in {"teamorouter-sol", "teamorouter-luna"}:
        config = settings.llm
        if selected == "teamorouter-luna":
            config = config.model_copy(update={"primary_model": config.fallback_model})
        client = TeamoRouterClient(config)
        client.route_ids = {
            settings.llm.primary_model: "teamorouter-sol",
            settings.llm.fallback_model: "teamorouter-luna",
        }
    else:
        raise ValueError("Unknown explicit provider route")
    client.task_profile = "INCREMENTAL_RESEARCH_PLANNING"
    return client


def configured_specialist_providers(settings, *, mimo_authority=None):
    """Explicit task-profile overrides; unlisted profiles keep their existing provider."""
    allowed = {
        "fundamental_analysis",
        "peer_analysis",
        "research_news_analysis",
        "valuation_analysis",
        "risk_analysis",
        "risk_follow_up",
        "report_synthesis",
    }
    providers = {}
    for profile, route in settings.specialist_provider_routes.items():
        if profile not in allowed:
            raise ValueError("Unknown Specialist task profile")
        client = configured_incremental_provider(
            settings, route_id=route, mimo_authority=mimo_authority
        )
        client.task_profile = profile
        providers[profile] = client
    return providers


def describe_route(client):
    return ProviderRoute(
        client.route_ids[client.model_name],
        client.provider_name,
        client.model_name,
        "atlasanalyse-mimo-direct" if client.provider_name == "mimo" else "vfas-teamorouter",
        "JSON_MODE_WITH_STRICT_LOCAL_VALIDATION"
        if client.provider_name == "mimo"
        else "NATIVE_SCHEMA_CONSTRAINED",
        client.execution_policy,
    )
