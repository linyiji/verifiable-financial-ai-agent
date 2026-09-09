"""Existing adapters + durable ledger + mock HTTP; zero business network requests.

The fixture runs both isolated SQLite and the dedicated PostgreSQL gate. These
tests exercise the adapters' real inner attempts, not a test-owned retry loop.
"""

# pytest resolves the explicitly imported fixture by its parameter name.
# ruff: noqa: F811

import json

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, SecretStr

from src.adapters.fmp.models import FMPAccessStatus, FMPEndpoint
from src.adapters.fmp.provider import HttpxFMPTransport
from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.ledger_transport import LedgerHTTPTransport
from src.adapters.llm.provider import LLMMessage
from src.adapters.llm.teamorouter import TeamoRouterClient
from src.domain.execution_contract import ContractDenied
from src.infrastructure.config.settings import FMPSettings, LLMSettings
from tests.recoverable_v1.test_ledger import budget, initialized, ledger  # noqa: F401

ORIGIN = ("https", "adapter.offline.invalid", None)


def tracked_transport(store, token, handler, *, route, purpose):
    return LedgerHTTPTransport(
        ledger=store,
        token=token,
        route=route,
        purpose=purpose,
        clock=lambda: 101,
        timeout=50,
        transport=httpx.MockTransport(handler),
        allowed_origins=(ORIGIN,),
    )


async def fmp_setup(store, handler, *, physical=4):
    limits = budget(physical=physical, execution=0, check=0)
    contract, token = await initialized(
        store,
        candidates=("fmp",),
        task_profile="evidence_collection",
        budget=limits,
        task_budget=limits,
    )
    tracked = tracked_transport(store, token, handler, route="fmp", purpose="DATA_REQUEST")
    adapter = HttpxFMPTransport(
        FMPSettings(
            api_keys=(SecretStr("fake-fmp-first"), SecretStr("fake-fmp-second")),
            base_url="https://adapter.offline.invalid",
        ),
        http_transport=tracked,
    )
    return contract, adapter


async def fmp_request(adapter, endpoint):
    return await adapter.request(
        endpoint=endpoint, path=f"/stable/{endpoint.value}", params={"symbol": "NVDA"}
    )


def assert_safe_calls(doc, expected_statuses, *, purpose, routes):
    calls = list(doc["calls"].values())
    assert [call["result"]["http_status"] for call in calls] == expected_statuses
    assert [call["route"] for call in calls] == routes
    assert all(call["purpose"] == purpose and call["state"] == "SETTLED" for call in calls)
    assert all(call["result"]["task_output_validated"] is False for call in calls)
    assert len({call["call_id"] for call in calls}) == len(calls)
    retained = json.dumps(doc)
    assert "fake-fmp-first" not in retained
    assert "fake-fmp-second" not in retained
    assert "fake-model-key" not in retained
    assert "apikey" not in retained
    assert "Authorization" not in retained


@pytest.mark.parametrize("first_status", [401, 429])
async def test_actual_fmp_adapter_ledgers_every_pool_attempt_and_retains_exclusion(
    ledger, first_status
):  # noqa: F811
    seen = []

    def fake(req):
        slot = req.url.params["apikey"]
        seen.append((req.url.path, slot))
        return httpx.Response(
            first_status if slot == "fake-fmp-first" else 200,
            json=[{"symbol": "NVDA", "price": 123}],
        )

    contract, adapter = await fmp_setup(ledger, fake)
    assert (await fmp_request(adapter, FMPEndpoint.QUOTE)).status is FMPAccessStatus.AVAILABLE
    assert (await fmp_request(adapter, FMPEndpoint.INCOME)).status is FMPAccessStatus.AVAILABLE
    assert [key for _, key in seen] == ["fake-fmp-first", "fake-fmp-second", "fake-fmp-second"]
    assert adapter.invalid_key_count == (1 if first_status == 401 else 0)
    assert adapter.rate_limited_key_count == (1 if first_status == 429 else 0)
    assert_safe_calls(
        await ledger.view(contract.intent_id),
        [first_status, 200, 200],
        purpose="DATA_REQUEST",
        routes=["fmp"] * 3,
    )


async def test_actual_fmp_endpoint_denial_is_one_call_and_same_key_quote_survives(
    ledger,
):  # noqa: F811
    seen = []

    def fake(req):
        seen.append((req.url.path, req.url.params["apikey"]))
        return httpx.Response(
            403 if req.url.path.endswith("transcript") else 200,
            json={"error": "subscription denied"}
            if req.url.path.endswith("transcript")
            else [{"symbol": "NVDA"}],
        )

    contract, adapter = await fmp_setup(ledger, fake)
    denied = await fmp_request(adapter, FMPEndpoint.TRANSCRIPT)
    assert denied.status is FMPAccessStatus.ENTITLEMENT_DENIED
    assert denied.error_scope == "ENDPOINT"
    assert (await fmp_request(adapter, FMPEndpoint.QUOTE)).status is FMPAccessStatus.AVAILABLE
    assert [key for _, key in seen] == ["fake-fmp-first", "fake-fmp-first"]
    assert adapter.invalid_key_count == adapter.rate_limited_key_count == 0
    assert_safe_calls(
        await ledger.view(contract.intent_id),
        [403, 200],
        purpose="DATA_REQUEST",
        routes=["fmp"] * 2,
    )


@pytest.mark.parametrize("status", [403, 429])
async def test_actual_fmp_account_denial_never_creates_a_second_request(ledger, status):  # noqa: F811
    seen = []

    def fake(req):
        seen.append(req.url.path)
        return httpx.Response(status, json={"error": {"scope": "account"}})

    contract, adapter = await fmp_setup(ledger, fake)
    first = await fmp_request(adapter, FMPEndpoint.TRANSCRIPT)
    second = await fmp_request(adapter, FMPEndpoint.QUOTE)
    assert first.error_scope == second.error_scope == "ACCOUNT"
    assert second.status is first.status
    assert len(seen) == 1
    assert_safe_calls(
        await ledger.view(contract.intent_id),
        [status],
        purpose="DATA_REQUEST",
        routes=["fmp"],
    )


async def test_actual_fmp_pool_retry_cannot_exceed_durable_physical_budget(ledger):  # noqa: F811
    seen = []

    def fake(req):
        seen.append(req.url.params["apikey"])
        return httpx.Response(429, json={"error": "rate limit"})

    contract, adapter = await fmp_setup(ledger, fake, physical=1)
    with pytest.raises(ContractDenied, match="PHYSICAL_BUDGET_EXHAUSTED"):
        await fmp_request(adapter, FMPEndpoint.QUOTE)
    assert seen == ["fake-fmp-first"]
    assert_safe_calls(
        await ledger.view(contract.intent_id),
        [429],
        purpose="DATA_REQUEST",
        routes=["fmp"],
    )


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: int


def model_adapter(client):
    return TeamoRouterClient(
        LLMSettings(
            provider="teamorouter",
            api_key=SecretStr("fake-model-key"),
            base_url="https://adapter.offline.invalid/v1",
            primary_model="gpt-5.6-sol",
            fallback_model="gpt-5.6-luna",
        ),
        client=client,
        execution_policy=ProviderExecutionPolicyV1(
            max_attempts=2,
            bounded_backoff_seconds=(),
            per_attempt_deadline_seconds=5,
            overall_workload_deadline_seconds=10,
        ),
    )


async def complete(adapter):
    return await adapter.complete_structured(
        messages=[LLMMessage(role="user", content="Offline fixture: answer 7.")],
        response_model=Answer,
        schema_name="offline_answer",
    )


def model_handler(seen, first_status):
    def fake(req):
        body = json.loads(req.content)
        seen.append(body["model"])
        assert req.headers["Authorization"] == "Bearer fake-model-key"
        if len(seen) == 1:
            return httpx.Response(first_status, json={"error": "fake unavailable"})
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "choices": [{"message": {"content": '{"answer": 7}'}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )

    return fake


@pytest.mark.parametrize("first_status", [429, 503])
async def test_actual_model_adapter_internal_fallback_is_two_exact_physical_routes(
    ledger, first_status
):  # noqa: F811
    limits = budget(physical=2, execution=2, check=0)
    contract, token = await initialized(
        ledger,
        candidates=("teamorouter-sol", "teamorouter-luna"),
        budget=limits,
        task_budget=limits,
    )
    seen = []
    tracked = tracked_transport(
        ledger,
        token,
        model_handler(seen, first_status),
        route="teamorouter-sol",
        purpose="TASK_EXECUTION",
    )
    async with httpx.AsyncClient(transport=tracked) as client:
        response = await complete(model_adapter(client))
    assert response.output.answer == 7
    assert response.attempted_models == ("gpt-5.6-sol", "gpt-5.6-luna")
    assert response.actual_model == "gpt-5.6-luna"
    assert seen == ["gpt-5.6-sol", "gpt-5.6-luna"]
    assert_safe_calls(
        await ledger.view(contract.intent_id),
        [first_status, 200],
        purpose="TASK_EXECUTION",
        routes=["teamorouter-sol", "teamorouter-luna"],
    )


async def test_actual_model_adapter_cannot_hide_unauthorized_luna_fallback_as_sol(
    ledger,
):  # noqa: F811
    contract, token = await initialized(ledger, candidates=("teamorouter-sol",))
    seen = []
    tracked = tracked_transport(
        ledger,
        token,
        model_handler(seen, 503),
        route="teamorouter-sol",
        purpose="TASK_EXECUTION",
    )
    async with httpx.AsyncClient(transport=tracked) as client:
        with pytest.raises(ContractDenied, match="CANDIDATE_NOT_AUTHORIZED"):
            await complete(model_adapter(client))
    assert seen == ["gpt-5.6-sol"]
    assert_safe_calls(
        await ledger.view(contract.intent_id),
        [503],
        purpose="TASK_EXECUTION",
        routes=["teamorouter-sol"],
    )


async def test_actual_model_adapter_retry_respects_durable_budget_before_second_send(
    ledger,
):  # noqa: F811
    limits = budget(physical=1, execution=1, check=0)
    contract, token = await initialized(
        ledger,
        candidates=("teamorouter-sol", "teamorouter-luna"),
        budget=limits,
        task_budget=limits,
    )
    seen = []
    tracked = tracked_transport(
        ledger,
        token,
        model_handler(seen, 503),
        route="teamorouter-sol",
        purpose="TASK_EXECUTION",
    )
    async with httpx.AsyncClient(transport=tracked) as client:
        with pytest.raises(ContractDenied, match="PHYSICAL_BUDGET_EXHAUSTED"):
            await complete(model_adapter(client))
    assert seen == ["gpt-5.6-sol"]
    assert_safe_calls(
        await ledger.view(contract.intent_id),
        [503],
        purpose="TASK_EXECUTION",
        routes=["teamorouter-sol"],
    )
