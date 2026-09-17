"""Prospective profile tightening must constrain actual data dispatch."""

from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from src.adapters.bocha import BochaDiscovery
from src.adapters.fmp import FMPProvider
from src.application import execution_profiles as ep
from src.application.evidence_collection import EvidenceAcquisitionScope
from src.domain.node_binding import BindingDenied
from tests.execution_profiles.test_confirmed_profiles import (
    confirmed,
    invocation,
    profile,
    snapshot,
    task,
)


class ReachedTransport(Exception):
    pass


class FakeTransport:
    def __init__(self):
        self.calls = []

    async def request(self, **kwargs):
        self.calls.append(kwargs)
        raise ReachedTransport


@pytest.mark.parametrize(
    "kind,scope",
    [
        ("evidence_collection", "COMPANY"),
        ("peer_analysis", "PEER"),
        ("research_news_analysis", "RESEARCH_NEWS"),
    ],
)
@pytest.mark.parametrize("tool,data", [(True, True), (False, True), (True, False), (False, False)])
async def test_p1_dispatch_intersection(kind, scope, tool, data):
    service, value = await confirmed()
    transport = FakeTransport()
    provider = FMPProvider(transport)
    bocha_calls = []

    def respond(request):
        bocha_calls.append(request)
        return httpx.Response(200, json={"data": {"webPages": {"value": []}}})

    discovery = BochaDiscovery(
        SecretStr("local-fake"),
        transport=httpx.MockTransport(respond),
        official_domains={"ALPHA": ("example.test",)},
    )
    service.evidence_collector = SimpleNamespace(_provider=provider, _discovery=discovery)
    current = ep.resolve_execution_snapshot(
        value.scheme, value.goal, value.runtime.actual_graph.tasks, service
    ).for_task(task(value, kind))
    with invocation(value, kind):
        plans = ep.profile_request_plans(
            symbol="ALPHA", as_of=value.run.as_of, scope=EvidenceAcquisitionScope(scope)
        )
    request = plans[0].request
    selected = current.model_copy(
        update={
            "profile_version": "2",
            "allowed_tool_ids": tuple(
                t for t in current.allowed_tool_ids if tool or t != request.dataset
            ),
            "data_permissions": tuple(
                p for p in current.data_permissions if data or p.capability_id != request.dataset
            ),
        }
    )
    selected = ep.narrow_profile(
        current,
        selected,
        snapshot(value).scenario.model_copy(update={"execution_family_version": "2"}),
    )
    with invocation(value, kind, selected):
        denial = (
            None
            if tool and data
            else ("DATA_CAPABILITY_NOT_AUTHORIZED" if not data else "TOOL_NOT_AUTHORIZED")
        )
        with pytest.raises(ReachedTransport if tool and data else BindingDenied, match=denial):
            await provider.probe(request)
    assert len(transport.calls) == int(tool and data)
    if not tool or not data:
        assert transport.calls == []
    if scope == "RESEARCH_NEWS":
        capability = current.data_permission(request.dataset).discovery_policy.capability_id
        with invocation(value, kind, selected):
            if tool and data:
                await discovery.acquire(request, capability)
            else:
                with pytest.raises(BindingDenied):
                    await discovery.acquire(request, capability)
        assert len(bocha_calls) == int(tool and data)
    if scope == "COMPANY":
        other = plans[1].request
        with invocation(value, kind, selected), pytest.raises(ReachedTransport):
            await provider.probe(other)


@pytest.mark.parametrize(
    "before,after,allowed",
    [
        (None, 1.0, True),
        (2.0, 1.0, True),
        (1.0, 1.0, True),
        (1.0, 2.0, False),
        (1.0, None, False),
        (None, None, True),
    ],
)
async def test_p2_cost_order_and_snapshot_immutability(before, after, allowed):
    service, value = await confirmed()
    frozen = value.node_binding.model_dump_json()
    current = profile(value, "fundamental_analysis")
    current = current.model_copy(
        update={
            "recovery_budget": current.recovery_budget.model_copy(
                update={"max_total_recovery_cost": before}
            )
        }
    )
    selected = current.model_copy(
        update={
            "profile_version": "2",
            "recovery_budget": current.recovery_budget.model_copy(
                update={"max_total_recovery_cost": after}
            ),
        }
    )
    scenario = snapshot(value).scenario.model_copy(update={"execution_family_version": "2"})
    if allowed:
        result = ep.narrow_profile(current, selected, scenario)
        assert result.recovery_budget.max_total_recovery_cost == after
    else:
        with pytest.raises(BindingDenied, match="PROFILE_PERMISSION_EXPANSION"):
            ep.narrow_profile(current, selected, scenario)
    reloaded = await service.repository.get_run_fresh(value.run.run_id)
    assert reloaded.node_binding.model_dump_json() == frozen
    assert profile(reloaded, "fundamental_analysis").recovery_budget.max_total_recovery_cost is None


async def test_p2_absent_budget_does_not_acquire_cost_field_ordering():
    _, value = await confirmed()
    current = profile(value, "fundamental_analysis")
    selected = current.model_copy(update={"profile_version": "2"})
    with pytest.raises(BindingDenied, match="PROFILE_PERMISSION_EXPANSION"):
        ep.narrow_profile(
            current.model_copy(update={"recovery_budget": None}),
            selected,
            snapshot(value).scenario.model_copy(update={"execution_family_version": "2"}),
        )


async def test_p2_other_numeric_fields_keep_their_existing_types():
    _, value = await confirmed()
    budget = profile(value, "fundamental_analysis").recovery_budget
    for field in type(budget).model_fields:
        if field != "max_total_recovery_cost":
            with pytest.raises(ValidationError):
                type(budget).model_validate({**budget.model_dump(), field: None})
