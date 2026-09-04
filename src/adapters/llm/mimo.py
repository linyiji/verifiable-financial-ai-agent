from __future__ import annotations

import httpx

from src.adapters.llm.teamorouter import OpenAICompatiblePlannerClient
from src.infrastructure.config.settings import LLMSettings


class MimoClient(OpenAICompatiblePlannerClient):
    """Xiaomi MiMo specialization with truthful identity and PAYG-only credentials."""

    provider_name = "mimo"

    def __init__(
        self,
        settings: LLMSettings,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        credential = settings.api_key.get_secret_value() if settings.api_key is not None else ""
        if credential.startswith("tp-"):
            raise ValueError("mimo credential is not in the governed PAYG form")
        super().__init__(settings, client=client, timeout_seconds=timeout_seconds)
