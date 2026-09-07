"""Offline route capability checks. No real credentials or provider requests."""

import json
from dataclasses import asdict
from pathlib import Path

import httpx
import pytest

from src.adapters.llm.mimo import MimoClient
from src.adapters.llm.routes import (
    configured_incremental_provider,
    describe_route,
    load_mimo_authority,
)
from src.agentic.llm_integration import PlannerProviderSchemeGenerator
from src.agentic.planning_errors import IncrementalSchemeFailure
from src.infrastructure.config.settings import LLMSettings, Settings
from src.observability.performance import Recorder, configure
from tests.phase4.backend_product.test_incremental_scheme_repair import (
    real_inputs,
    valid_incremental,
)


def config():
    return LLMSettings(
        provider="mimo",
        api_key="fixture-only-secret",
        base_url="https://api.xiaomimimo.com/v1",
        primary_model="mimo-v2.5",
        fallback_model="mimo-v2.5",
    )


@pytest.mark.parametrize(
    "case", ["valid", "bad-json", "extra", "foreign", "reuse", "timeout", "auth"]
)
async def test_json_mode_strict_validation_and_route_telemetry(case):
    _, obj, goal, context = real_inputs()
    requests = []

    def handler(request):
        requests.append(request)
        payload = json.loads(request.content)
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["model"] == "mimo-v2.5" and payload["stream"] is False
        assert '"additionalProperties": false' in payload["messages"][0]["content"]
        assert payload["thinking"] == {"type": "disabled"}
        assert "fixture-only-secret" not in request.content.decode()
        if case == "timeout":
            raise httpx.ReadTimeout("private", request=request)
        if case == "auth":
            return httpx.Response(401, json={"error": {"message": "private"}})
        proposal = valid_incremental(context)
        if case == "extra":
            proposal["unexpected"] = True
        if case == "foreign":
            proposal["incremental_decisions"][0]["source_identity"] = "FOREIGN"
        if case == "reuse":
            proposal["incremental_decisions"][0]["decision"] = "REUSE"
        return httpx.Response(
            200,
            json={
                "model": "mimo-v2.5",
                "choices": [
                    {
                        "message": {
                            "content": "not JSON" if case == "bad-json" else json.dumps(proposal),
                            "reasoning_content": "private",
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )

    recorder = Recorder(forbidden_values=("fixture-only-secret",))
    configure(recorder)
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            provider = MimoClient(config(), client=http)
            provider.route_ids = {"mimo-v2.5": "mimo-direct"}
            provider.task_profile = "INCREMENTAL_RESEARCH_PLANNING"
            generator = PlannerProviderSchemeGenerator(provider, max_validation_attempts=1)
            if case == "valid":
                scheme = await generator.generate(
                    research_object=obj, goal=goal, incremental_context=context
                )
                assert scheme.incremental_context.base_run_id == context.base_run_id
                assert scheme.generated_model == "mimo-v2.5"
            else:
                with pytest.raises(IncrementalSchemeFailure):
                    await generator.generate(
                        research_object=obj, goal=goal, incremental_context=context
                    )
    finally:
        configure(None)
    assert len(requests) == 1
    logical = [r for r in recorder.records if r["operation"] == "model.logical_call"]
    assert len(logical) == 1 and logical[0]["provider_route_id"] == "mimo-direct"
    assert logical[0]["task_profile"] == "INCREMENTAL_RESEARCH_PLANNING"
    assert "private" not in json.dumps(recorder.snapshot())
    assert "fixture-only-secret" not in json.dumps(asdict(describe_route(provider)))


def test_authority_absent_fails_before_route_or_call(tmp_path):
    with pytest.raises(ValueError, match="unavailable"):
        load_mimo_authority(tmp_path / "missing")


def test_exact_route_selection_keeps_teamorouter_policy():
    settings = Settings(_env_file=None, teamorouter_api_key="fixture-only-secret")
    sol = configured_incremental_provider(settings)
    luna = configured_incremental_provider(settings, route_id="teamorouter-luna")
    assert sol.execution_policy.read_timeout_seconds == 60
    assert sol.execution_policy.max_attempts == 2
    assert sol._settings.fallback_model == "gpt-5.6-luna"
    assert luna.model_name == "gpt-5.6-luna"
    with pytest.raises(ValueError, match="Unknown"):
        configured_incremental_provider(settings, route_id="automatic")


def test_researcher_has_no_provider_specific_selection():
    source = Path("src/agentic/llm_integration.py").read_text()
    assert "MimoClient(" not in source and "TeamoRouterClient(" not in source
