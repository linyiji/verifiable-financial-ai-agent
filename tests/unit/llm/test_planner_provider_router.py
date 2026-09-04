from __future__ import annotations

import json
from types import MappingProxyType

import httpx
import pytest
from pydantic import BaseModel

from src.adapters.llm import (
    MIMO_PRIMARY_TEAMOROUTER_SECONDARY,
    MIMO_PRIMARY_TEAMOROUTER_SECONDARY_V2,
    LLMMessage,
    LLMProviderUnavailableError,
    LLMStructuredResponse,
    MimoClient,
    PlannerProviderHealth,
    PlannerProviderLockError,
    PlannerProviderRouter,
    PlannerProviderUnavailableError,
    PlannerWorkload,
    TeamoRouterClient,
    WorkloadProviderRouter,
    WorkloadProviderUnavailableError,
)
from src.infrastructure.config.settings import LLMSettings


class Answer(BaseModel):
    value: str


def provider_settings(provider: str) -> LLMSettings:
    return LLMSettings(
        provider=provider,
        api_key=f"{provider}-credential-sentinel",
        base_url=f"https://{provider}.example.test/v1",
        primary_model="mimo-v2.5" if provider == "mimo" else "gpt-5.6-sol",
        fallback_model="mimo-v2.5" if provider == "mimo" else "gpt-5.6-luna",
    )


def response(model: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": model,
            "choices": [{"message": {"content": json.dumps({"value": "ok"})}}],
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client_type", "provider", "model"),
    (
        (MimoClient, "mimo", "mimo-v2.5"),
        (TeamoRouterClient, "teamorouter", "gpt-5.6-sol"),
    ),
)
async def test_supported_clients_return_the_same_owned_result_contract(
    client_type: type[MimoClient] | type[TeamoRouterClient],
    provider: str,
    model: str,
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: response(model))
    ) as http:
        result = await client_type(provider_settings(provider), client=http).complete_structured(
            messages=[LLMMessage(role="user", content="return an answer")],
            response_model=Answer,
            schema_name="answer_v1",
        )

    assert isinstance(result, LLMStructuredResponse)
    assert result.provider == provider
    assert result.actual_model == model
    assert result.output == Answer(value="ok")


def test_mimo_rejects_non_payg_tp_credential_without_exposing_it() -> None:
    payload = provider_settings("mimo").model_dump()
    payload["api_key"] = "tp-rejected-sentinel"
    settings = LLMSettings.model_validate(payload)

    with pytest.raises(ValueError, match="PAYG") as caught:
        MimoClient(settings)

    assert "tp-rejected-sentinel" not in str(caught.value)


@pytest.mark.asyncio
async def test_mimo_maps_unavailable_responses_to_safe_owned_error() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503))
    ) as http:
        with pytest.raises(LLMProviderUnavailableError) as caught:
            await MimoClient(provider_settings("mimo"), client=http).complete_structured(
                messages=[LLMMessage(role="user", content="return an answer")],
                response_model=Answer,
                schema_name="answer_v1",
            )

    assert caught.value.attempted_models == ("mimo-v2.5",)
    assert "mimo" in str(caught.value)
    assert "mimo-credential-sentinel" not in str(caught.value)


class FakeProvider:
    def __init__(self, name: str, model: str) -> None:
        self.provider_name = name
        self.model_name = model
        self.calls = 0

    def lock_to_model(self, model_name: str) -> FakeProvider:
        assert model_name == self.model_name
        return self

    async def complete_structured(self, **kwargs: object) -> LLMStructuredResponse:
        self.calls += 1
        model = kwargs["response_model"]
        assert isinstance(model, type)
        return LLMStructuredResponse(
            output=model(value="ok"),
            provider=self.provider_name,
            requested_model=self.model_name,
            actual_model=self.model_name,
            attempted_models=(self.model_name,),
        )


def health(provider: FakeProvider, passed: bool) -> PlannerProviderHealth:
    return PlannerProviderHealth(
        provider=provider.provider_name,
        model=provider.model_name if passed else None,
        passed=passed,
        failure_classification=None if passed else "retryable_http_failure",
    )


@pytest.mark.asyncio
async def test_router_selects_mimo_first_stops_probing_and_locks_identity() -> None:
    mimo = FakeProvider("mimo", "mimo-v2.5")
    teamorouter = FakeProvider("teamorouter", "gpt-5.6-sol")
    probed: list[str] = []

    async def preflight(provider: FakeProvider) -> PlannerProviderHealth:
        probed.append(provider.provider_name)
        return health(provider, True)

    router = PlannerProviderRouter((mimo, teamorouter))
    selection = await router.select(preflight)

    assert probed == ["mimo"]
    assert selection.provider_name == "mimo"
    assert selection.model_name == "mimo-v2.5"
    assert selection.policy_id == MIMO_PRIMARY_TEAMOROUTER_SECONDARY
    assert selection.fallback_used is False
    assert selection.safe_evidence()["provider_model_locked"] is True
    with pytest.raises(PlannerProviderLockError, match="immutable"):
        await router.select(preflight)


@pytest.mark.asyncio
async def test_router_selects_teamorouter_only_after_mimo_is_unavailable() -> None:
    mimo = FakeProvider("mimo", "mimo-v2.5")
    teamorouter = FakeProvider("teamorouter", "gpt-5.6-sol")
    probed: list[str] = []

    async def preflight(provider: FakeProvider) -> PlannerProviderHealth:
        probed.append(provider.provider_name)
        return health(provider, provider.provider_name == "teamorouter")

    selection = await PlannerProviderRouter((mimo, teamorouter)).select(preflight)

    assert probed == ["mimo", "teamorouter"]
    assert selection.provider_name == "teamorouter"
    assert selection.fallback_used is True


@pytest.mark.asyncio
async def test_router_fails_closed_when_all_registered_providers_are_unavailable() -> None:
    mimo = FakeProvider("mimo", "mimo-v2.5")
    teamorouter = FakeProvider("teamorouter", "gpt-5.6-sol")

    async def preflight(provider: FakeProvider) -> PlannerProviderHealth:
        return health(provider, False)

    with pytest.raises(PlannerProviderUnavailableError) as caught:
        await PlannerProviderRouter((mimo, teamorouter)).select(preflight)

    assert [item.provider for item in caught.value.health_checks] == ["mimo", "teamorouter"]


def test_router_rejects_unknown_provider_identity() -> None:
    with pytest.raises(ValueError, match="unknown"):
        PlannerProviderRouter((FakeProvider("unknown", "model"),))


@pytest.mark.asyncio
async def test_locked_provider_rejects_a_mid_run_model_change() -> None:
    mimo = FakeProvider("mimo", "mimo-v2.5")

    async def preflight(provider: FakeProvider) -> PlannerProviderHealth:
        return health(provider, True)

    selection = await PlannerProviderRouter((mimo,)).select(preflight)
    mimo.model_name = "changed-mid-run"

    with pytest.raises(PlannerProviderLockError, match="lock"):
        await selection.provider.complete_structured(
            messages=[LLMMessage(role="user", content="answer")],
            response_model=Answer,
            schema_name="answer_v1",
        )


def workload_health(
    provider: FakeProvider,
    workload: PlannerWorkload,
    passed: bool,
) -> PlannerProviderHealth:
    return PlannerProviderHealth(
        provider=provider.provider_name,
        model=provider.model_name if passed else None,
        passed=passed,
        failure_classification=None if passed else "provider_unavailable",
        workload_type=workload,
        attempt=2,
        elapsed_seconds=0.2,
        retryable=not passed,
    )


@pytest.mark.asyncio
async def test_workload_router_selects_each_workload_independently() -> None:
    mimo = FakeProvider("mimo", "mimo-v2.5")
    teamorouter = FakeProvider("teamorouter", "gpt-5.6-sol")
    probes: list[tuple[PlannerWorkload, str]] = []

    def preflight(workload: PlannerWorkload):
        async def run(provider: FakeProvider) -> PlannerProviderHealth:
            probes.append((workload, provider.provider_name))
            passed = not (
                workload is PlannerWorkload.GENERATED_CAPABILITY
                and provider.provider_name == "mimo"
            )
            return workload_health(provider, workload, passed)

        return run

    router = WorkloadProviderRouter((mimo, teamorouter))
    bindings = await router.select({workload: preflight(workload) for workload in PlannerWorkload})

    assert bindings.policy_id == MIMO_PRIMARY_TEAMOROUTER_SECONDARY_V2
    assert bindings.binding_for(PlannerWorkload.SCHEME_PLANNER).provider_name == "mimo"
    assert bindings.binding_for(PlannerWorkload.LEAD_PLANNER).provider_name == "mimo"
    generated = bindings.binding_for(PlannerWorkload.GENERATED_CAPABILITY)
    assert generated.provider_name == "teamorouter"
    assert generated.fallback_used is True
    assert probes == [
        (PlannerWorkload.SCHEME_PLANNER, "mimo"),
        (PlannerWorkload.LEAD_PLANNER, "mimo"),
        (PlannerWorkload.GENERATED_CAPABILITY, "mimo"),
        (PlannerWorkload.GENERATED_CAPABILITY, "teamorouter"),
    ]
    assert isinstance(bindings.bindings, MappingProxyType)
    with pytest.raises(TypeError):
        bindings.bindings[PlannerWorkload.SCHEME_PLANNER] = generated
    with pytest.raises(PlannerProviderLockError, match="immutable"):
        await router.select({workload: preflight(workload) for workload in PlannerWorkload})
    with pytest.raises(PlannerProviderLockError, match="workload provider binding"):
        await generated.provider.complete_structured(
            messages=[LLMMessage(role="user", content="answer")],
            response_model=Answer,
            schema_name="answer_v1",
            workload_type=PlannerWorkload.SCHEME_PLANNER.value,
        )


@pytest.mark.asyncio
async def test_workload_router_uses_mimo_for_all_when_every_exact_probe_passes() -> None:
    mimo = FakeProvider("mimo", "mimo-v2.5")
    teamorouter = FakeProvider("teamorouter", "gpt-5.6-sol")

    def preflight(workload: PlannerWorkload):
        async def run(provider: FakeProvider) -> PlannerProviderHealth:
            return workload_health(provider, workload, True)

        return run

    bindings = await WorkloadProviderRouter((mimo, teamorouter)).select(
        {workload: preflight(workload) for workload in PlannerWorkload}
    )

    assert {binding.provider_name for binding in bindings.bindings.values()} == {"mimo"}


@pytest.mark.asyncio
async def test_workload_router_fails_closed_for_one_unavailable_workload() -> None:
    mimo = FakeProvider("mimo", "mimo-v2.5")
    teamorouter = FakeProvider("teamorouter", "gpt-5.6-sol")

    def preflight(workload: PlannerWorkload):
        async def run(provider: FakeProvider) -> PlannerProviderHealth:
            return workload_health(
                provider,
                workload,
                workload is not PlannerWorkload.GENERATED_CAPABILITY,
            )

        return run

    with pytest.raises(WorkloadProviderUnavailableError) as caught:
        await WorkloadProviderRouter((mimo, teamorouter)).select(
            {workload: preflight(workload) for workload in PlannerWorkload}
        )

    assert caught.value.workload_type is PlannerWorkload.GENERATED_CAPABILITY
    assert [item.provider for item in caught.value.health_checks] == [
        "mimo",
        "teamorouter",
    ]


@pytest.mark.asyncio
async def test_workload_router_rejects_false_workload_health_identity() -> None:
    mimo = FakeProvider("mimo", "mimo-v2.5")

    async def wrong(provider: FakeProvider) -> PlannerProviderHealth:
        return workload_health(provider, PlannerWorkload.LEAD_PLANNER, True)

    with pytest.raises(PlannerProviderLockError, match="workload identity"):
        await WorkloadProviderRouter((mimo,)).select(
            {
                PlannerWorkload.SCHEME_PLANNER: wrong,
                PlannerWorkload.LEAD_PLANNER: wrong,
                PlannerWorkload.GENERATED_CAPABILITY: wrong,
            }
        )
