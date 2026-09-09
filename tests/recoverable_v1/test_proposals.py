import httpx
import pytest
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.recovery_v1 import create_recovery_router
from src.agentic.recovery_proposals import (
    OptionalModelProposer,
    ProposalAuthority,
    ProposalGate,
    RecoveryProposal,
)
from src.domain.execution_contract import (
    ContractDenied,
    ExecutionBudget,
    ExecutionContract,
    fingerprint,
)
from src.infrastructure.database.execution_ledger import ExecutionIntentRow, SQLExecutionLedger


def contract(**updates):
    digest = fingerprint({"fixture": "offline"})
    budget = ExecutionBudget(physical_calls=4, execution_calls=2, check_calls=1, decision_calls=1)
    base = dict(
        intent_id="I",
        run_id="R",
        task_id="R:T",
        operation_id="O",
        scheme_id="S",
        scheme_hash=digest,
        object_id="OBJ",
        as_of="2026-09-09",
        graph_version=1,
        graph_hash=digest,
        required_outputs=("report",),
        dependencies=(),
        input_hashes={"E": digest},
        schema_hash=digest,
        formula_hash=digest,
        code_hash=digest,
        policy_version="owner-v1",
        policy_hash=digest,
        source_identity="offline-source",
        task_profile="report_synthesis",
        candidates=("sol", "terra", "mimo"),
        dynamic_grants={},
        budget=budget,
        task_budget=budget,
        deadline=500,
        task_deadline=500,
        per_call_timeout=10,
        compatibility="v1",
        check_consumption="EXACT_VALIDATED_ONCE",
    )
    return ExecutionContract(**{**base, **updates})


@pytest.fixture
async def fixture():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ExecutionIntentRow.__table__.create)
    store = SQLExecutionLedger(async_sessionmaker(engine, expire_on_commit=False))
    c = contract()
    await store.create_intent("I", c.budget, 500)
    await store.admit_run("I", "R")
    await store.freeze(c)
    token = await store.claim("I", "O", "first", 10, 10)
    await store.fail(token, {"code": "READ_TIMEOUT"}, 11)
    failed = (await store.view("I"))["operations"]["O"]["failures"][-1]
    authority = ProposalAuthority(
        contract_hash=c.contract_hash,
        route_providers={"sol": "team", "terra": "team", "mimo": "mi"},
        verified_route_evidence={"terra": ("E",), "mimo": ("E",)},
        approved_cross_provider_routes=("mimo",),
    )
    proposal = RecoveryProposal(
        intent_id="I",
        task_id="R:T",
        operation_id="O",
        contract_hash=c.contract_hash,
        graph_hash=c.graph_hash,
        graph_version=1,
        failure_hash=fingerprint(failed),
        evidence_refs=("E",),
        action="SWITCH_MODEL",
        current_route="sol",
        target_route="terra",
        expires_at=100,
    )
    yield store, c, authority, proposal
    await engine.dispose()


async def recover(store, c):
    await store.authorize_recovery("I", "O", "AUTH", c.contract_hash)
    return await store.claim("I", "O", "second", 30, 60)


async def test_allowed_proposal_reserves_once_before_send(fixture):
    store, c, authority, proposal = fixture
    token = await recover(store, c)
    sent = []

    async def send(route, deadline_seconds):
        state = (await store.view("I"))["calls"]["proposal:" + fingerprint(proposal)[7:]]
        assert state["state"] == "DISPATCHED"
        sent.append(route)
        return {"report": "validated"}

    gate = ProposalGate(store, authority, lambda: 31)
    assert await gate.execute(token, proposal, send_one=send, validate_output=lambda x: x) == {
        "report": "validated"
    }
    with pytest.raises(ContractDenied, match="CALL_ID_ALREADY_RESERVED"):
        await gate.execute(token, proposal, send_one=send, validate_output=lambda x: x)
    assert sent == ["terra"]


@pytest.mark.parametrize(
    "mutation,code",
    [
        ({"target_route": "unauthorized"}, "CANDIDATE_NOT_AUTHORIZED"),
        ({"expires_at": 30}, "PROPOSAL_EXPIRED"),
        ({"graph_version": 2}, "PROPOSAL_IDENTITY_MISMATCH"),
        ({"contract_hash": "stale"}, "PROPOSAL_IDENTITY_MISMATCH"),
        ({"failure_hash": "stale"}, "PROPOSAL_FAILURE_MISMATCH"),
        ({"evidence_refs": ("fabricated",)}, "PROPOSAL_EVIDENCE_MISMATCH"),
        ({"action": "REPLAN"}, "UNSUPPORTED_ACTION"),
        ({"action": "PAUSE"}, "UNSUPPORTED_ACTION"),
        ({"action": "WAIT"}, "UNSUPPORTED_ACTION"),
        ({"action": "SWITCH_PROVIDER", "target_route": "terra"}, "CROSS_PROVIDER_NOT_AUTHORIZED"),
    ],
)
async def test_invalid_proposal_has_zero_execution_effects(fixture, mutation, code):
    store, c, authority, proposal = fixture
    token = await recover(store, c)
    gate = ProposalGate(store, authority, lambda: 31)
    with pytest.raises(ContractDenied, match=code):
        await gate.execute(
            token, proposal.model_copy(update=mutation), send_one=None, validate_output=None
        )
    assert (await store.view("I"))["calls"] == {}


async def test_model_cannot_expand_budget_or_ignore_required(fixture):
    proposal = fixture[3].model_dump()
    for field in ("budget", "required_outputs", "grants"):
        with pytest.raises(ValidationError):
            RecoveryProposal.model_validate({**proposal, field: []})


async def test_fail_task_is_safe_and_no_request(fixture):
    store, c, authority, proposal = fixture
    token = await recover(store, c)
    gate = ProposalGate(store, authority, lambda: 31)
    result = await gate.execute(
        token,
        proposal.model_copy(update={"action": "FAIL_TASK", "target_route": None}),
        send_one=None,
        validate_output=None,
    )
    assert result["status"] == "FAIL_TASK"
    assert (await store.view("I"))["calls"] == {}


async def test_no_decider_authority_borrowed_from_research(fixture):
    store, c, authority, _ = fixture
    token = await recover(store, c)
    proposer = OptionalModelProposer(store, authority, lambda: 31)
    with pytest.raises(ContractDenied, match="MODEL_PROPOSALS_DISABLED"):
        await proposer.propose(token, call_id="D", route="sol", request={}, send_one=None)
    proposer.enabled = True
    with pytest.raises(ContractDenied, match="DECIDER_NOT_AUTHORIZED"):
        await proposer.propose(token, call_id="D", route="sol", request={}, send_one=None)
    assert (await store.view("I"))["calls"] == {}


async def test_decider_timeout_uses_only_preapproved_deterministic_fallback(fixture):
    store, _, authority, proposal = fixture
    dc = contract(
        task_id="R:DECIDER",
        operation_id="D",
        task_profile="DECIDER",
        input_hashes={"decision_request": fingerprint({})},
    )
    await store.freeze(dc)
    token = await store.claim("I", "D", "decider", 30, 60)
    calls = []

    async def timed_out(*args):
        calls.append(1)
        raise TimeoutError

    authority = authority.model_copy(
        update={
            "decider_contract_hash": dc.contract_hash,
            "deterministic_fallback_allowed": True,
        }
    )
    proposer = OptionalModelProposer(store, authority, lambda: 31, enabled=True)
    assert (
        await proposer.propose(
            token,
            call_id="D1",
            route="sol",
            request={},
            send_one=timed_out,
            deterministic_fallback=lambda: proposal,
        )
        == proposal
    )
    assert calls == [1]
    # A timeout is not refunded, and no second decider can be reserved.
    with pytest.raises(ContractDenied, match="RESULT_UNKNOWN_REQUIRES_RECONCILIATION"):
        await proposer.propose(token, call_id="D2", route="sol", request={}, send_one=timed_out)
    assert calls == [1]


async def test_real_api_ledger_read_auth_idempotency_and_no_new_run(fixture):
    store, c, _, _ = fixture
    calls = []

    async def actor(request, run, permission):
        calls.append(permission)
        if request.headers.get("X-Test-Actor") != "owner":
            raise HTTPException(403, "ACCESS_REVOKED")
        return "fixture-owner"

    app = FastAPI()
    app.include_router(
        create_recovery_router(store, resolve_actor=actor, clock=lambda: 31, actions_accepted=True)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = "/api/research-runs/R/recovery/I/O"
        assert (await client.get(path)).status_code == 403
        headers = {"X-Test-Actor": "owner"}
        assert (await client.get(path, headers=headers)).json()[
            "original_failure"
        ] == "READ_TIMEOUT"
        assert not (await store.view("I"))["operations"]["O"]["authorizations"]
        body = {"action": "AUTHORIZE_FAILED_OPERATION", "contract_hash": c.contract_hash}
        assert (await client.post(path, headers=headers, json=body)).status_code == 400
        headers["Idempotency-Key"] = "K"
        first = await client.post(path, headers=headers, json=body)
        second = await client.post(path, headers=headers, json=body)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        await store.claim("I", "O", "new", 32, 50)
        assert (await client.post(path, headers=headers, json=body)).json() == first.json()
        wrong = {**body, "contract_hash": fingerprint("different")}
        assert (await client.post(path, headers=headers, json=wrong)).status_code == 409
        assert first.json()["new_run_created"] is False
        assert first.json()["execution_started"] is False
        assert (
            await client.get(path.replace("/R/", "/other/"), headers=headers)
        ).status_code == 404
    assert len((await store.view("I"))["operations"]["O"]["authorizations"]) == 1
    assert (await store.view("I"))["calls"] == {}


async def test_api_default_does_not_expose_accepted_actions(fixture):
    store, c, _, _ = fixture

    async def actor(*args):
        return "fixture"

    app = FastAPI()
    app.include_router(create_recovery_router(store, resolve_actor=actor, clock=lambda: 31))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = "/api/research-runs/R/recovery/I/O"
        assert (await client.get(path)).json()["accepted_actions"] == []
        assert (
            await client.post(
                path,
                headers={"Idempotency-Key": "K"},
                json={
                    "action": "AUTHORIZE_FAILED_OPERATION",
                    "contract_hash": c.contract_hash,
                },
            )
        ).status_code == 409
