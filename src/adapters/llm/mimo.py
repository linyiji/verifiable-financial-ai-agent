from __future__ import annotations

import json

import httpx

from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.teamorouter import OpenAICompatiblePlannerClient
from src.infrastructure.config.settings import LLMSettings


class MimoClient(OpenAICompatiblePlannerClient):
    """Xiaomi MiMo specialization with truthful identity and PAYG-only credentials."""

    provider_name = "mimo"

    def _request_template(self, *, messages, response_model, schema_name):
        # MiMo documents JSON mode, not native JSON-schema enforcement.
        # The unchanged shared decoder and exact Pydantic validator remain mandatory.
        template = super()._request_template(
            messages=messages, response_model=response_model, schema_name=schema_name
        )
        schema = template["response_format"]["json_schema"]["schema"]
        template["response_format"] = {"type": "json_object"}
        template["messages"] = [
            {
                "role": "system",
                "content": "Return only one JSON object matching this exact "
                "schema. No Markdown, commentary or reasoning. JSON schema: " + json.dumps(schema),
            },
            *template["messages"],
        ]
        template.update(stream=False, max_completion_tokens=8192, thinking={"type": "disabled"})
        return template

    def __init__(
        self,
        settings: LLMSettings,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 60.0,
        execution_policy: ProviderExecutionPolicyV1 | None = None,
    ) -> None:
        credential = settings.api_key.get_secret_value() if settings.api_key is not None else ""
        if credential.startswith("tp-"):
            raise ValueError("mimo credential is not in the governed PAYG form")
        super().__init__(
            settings,
            client=client,
            timeout_seconds=timeout_seconds,
            execution_policy=execution_policy,
        )
