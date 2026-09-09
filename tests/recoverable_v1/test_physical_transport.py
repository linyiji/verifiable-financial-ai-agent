import httpx
import pytest

from src.adapters.llm.ledger_transport import LedgerHTTPTransport
from src.domain.execution_contract import ContractDenied
from tests.recoverable_v1.test_ledger import initialized, ledger  # noqa: F401


@pytest.mark.parametrize(
    "purpose", ["CAPABILITY_CHECK", "TASK_EXECUTION", "PLANNING", "DATA_REQUEST"]
)
async def test_all_purposes_count_actual_retries_and_never_store_key(ledger, purpose):  # noqa: F811
    c, token = await initialized(ledger)
    seen = []

    async def fake(request):
        seen.append(request)
        return httpx.Response(503 if len(seen) == 1 else 200, json={"value": 1})

    transport = LedgerHTTPTransport(
        ledger=ledger,
        token=token,
        purpose=purpose,
        route="mimo-direct",
        clock=lambda: 101,
        timeout=50,
        transport=httpx.MockTransport(fake),
        allowed_origins=(("https", "offline.invalid", None),),
    )
    async with httpx.AsyncClient(transport=transport) as client:
        for _ in range(2):
            await client.get(
                "https://offline.invalid/data?apikey=fixture-secret",
                headers={"Authorization": "Bearer fixture-secret"},
            )
    doc = await ledger.view(c.intent_id)
    assert len(seen) == len(doc["calls"]) == 2
    assert all(call["state"] == "SETTLED" for call in doc["calls"].values())
    assert "fixture-secret" not in str(doc)


async def test_unknown_prevents_retry_and_origin_denied_without_send(ledger):  # noqa: F811
    c, token = await initialized(ledger)
    calls = []

    async def fake(request):
        calls.append(request)
        raise httpx.ReadTimeout("fixture")

    transport = LedgerHTTPTransport(
        ledger=ledger,
        token=token,
        purpose="TASK_EXECUTION",
        route="mimo-direct",
        clock=lambda: 101,
        timeout=50,
        transport=httpx.MockTransport(fake),
        allowed_origins=(("https", "offline.invalid", None),),
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ContractDenied, match="ORIGIN_NOT_AUTHORIZED"):
            await client.get("https://foreign.invalid")
        with pytest.raises(httpx.ReadTimeout):
            await client.get("https://offline.invalid")
        with pytest.raises(ContractDenied, match="RESULT_UNKNOWN"):
            await client.get("https://offline.invalid")
    assert len(calls) == 1
    assert len((await ledger.view(c.intent_id))["calls"]) == 1


async def test_check_consume_exactly_once(ledger):  # noqa: F811
    c, token = await initialized(ledger)
    await ledger.reserve(token, "check", "CAPABILITY_CHECK", "mimo-direct", 101, 50)
    await ledger.dispatch(token, "check", 102)
    saved = await ledger.save_result(
        token,
        "check",
        {
            "validated": True,
            "schema_hash": c.schema_hash,
            "actual_route": "mimo-direct",
            "actual_provider": "mimo",
            "actual_model": "mimo-v2.5",
            "contract_hash": c.contract_hash,
            "task_id": c.task_id,
            "operation_id": c.operation_id,
            "input_hashes": c.input_hashes,
            "answer": 7,
        },
        103,
    )
    await ledger.settle(token, "check", 104)
    await ledger.consume_check(token, "check", saved["result_hash"], "mimo-direct", 105)
    replay = await ledger.consume_check(token, "check", saved["result_hash"], "mimo-direct", 106)
    assert replay["answer"] == 7
    doc = await ledger.view(c.intent_id)
    assert len(doc["calls"]) == 1
    assert len(doc["operations"][c.operation_id]["published"]) == 1


async def test_incomplete_check_binding_is_not_reused(ledger):  # noqa: F811
    c, token = await initialized(ledger)
    await ledger.reserve(token, "check", "CAPABILITY_CHECK", "mimo-direct", 101, 50)
    await ledger.dispatch(token, "check", 102)
    saved = await ledger.save_result(
        token,
        "check",
        {
            "validated": True,
            "schema_hash": c.schema_hash,
            "actual_route": "mimo-direct",
        },
        103,
    )
    with pytest.raises(ContractDenied, match="CHECK_NOT_EXACT_VALIDATED"):
        await ledger.consume_check(token, "check", saved["result_hash"], "mimo-direct", 104)
