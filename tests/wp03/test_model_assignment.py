"""Wire-seam budgets and truthful missing identity; pure local fixture adapters."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.agentic.valuation_context import CallReceipt, RetrievalRequest, ValuationInteraction
from src.application.research_context import encoded
from src.domain.node_binding import BindingDenied, digest
from tests.wp03.test_valuation_retrieval import run_case


@pytest.mark.parametrize("mode", ["missing_model", "substitution", "timeout"])
async def test_exact_observed_evidence(tmp_path, monkeypatch, mode):
    _, calls, receipts, _ = await run_case(tmp_path, monkeypatch, mode)
    receipt = receipts[0]
    assert receipt["requested_model"] == receipt["resolved_model"] == "gpt-5.6-sol"
    assert receipt["observed_provider"] == "teamorouter"
    assert receipt["provider_identity_source"] == "CLIENT_DISPATCH"
    assert receipt["observed_model"] == ("gpt-5.6-luna" if mode == "substitution" else "UNKNOWN")
    assert receipt["cost"] == receipt["observed_reasoning"] == "UNKNOWN"
    assert receipt["input_tokens"] is None and receipt["output_tokens"] is None
    assert receipt["fallback_used"] is False
    assert len(calls) == receipt["client_physical_dispatch_count"] == 1


@pytest.mark.parametrize("bad", ["duplicate", "count", "size", "id"])
def test_retrieval_request_rejection(bad):
    values = dict(
        request_id="",
        context_id="ctx",
        context_revision=1,
        consumer_role="valuation_analyst",
        need_type="EVIDENCE",
        subject_refs=["a"],
        reason="required detail",
    )
    if bad == "duplicate":
        values["subject_refs"] = ["a", "a"]
    elif bad == "count":
        values["subject_refs"] = [str(i) for i in range(9)]
    elif bad == "size":
        values["subject_refs"] = ["x" * 2048]
    else:
        values["request_id"] = "forged"
    with pytest.raises(ValidationError):
        RetrievalRequest(**values)


def test_code_derives_request_id():
    request = RetrievalRequest(
        request_id="",
        context_id="ctx",
        context_revision=1,
        consumer_role="valuation_analyst",
        need_type="EVIDENCE",
        subject_refs=("a",),
        reason="read",
    )
    assert request.request_id == digest(
        request.model_dump(exclude={"request_id"}), "retrieval-request/v1"
    )


@pytest.mark.parametrize("size", [65536, 65537])
async def test_wire_boundary_before_B(size, tmp_path, monkeypatch):
    async def configure(service, value, agent):
        original = agent._provider._request_template

        def exact_size(**kwargs):
            template = {**original(**kwargs), "padding": ""}
            base = len(encoded({"model": agent._provider.model_name, **template}))
            template["padding"] = "x" * (size - base)
            return template

        agent._provider._request_template = exact_size

    result, calls, receipts, task = await run_case(
        tmp_path, monkeypatch, f"wire_edge_{size}", configure
    )
    assert len(calls) == (1 if size == 65536 else 0)
    assert (task.task_id in result.node_binding.current_results) == (size == 65536)
    if size == 65537:
        assert receipts[0]["diagnostic_code"] == "CONTEXT_TOO_LARGE"


def test_shared_budget_and_duplicate_dispatch(monkeypatch):
    interaction = object.__new__(ValuationInteraction)
    interaction.limit = lambda: None
    client = SimpleNamespace(provider_name="teamorouter")
    interaction.client, interaction.agent = client, None
    interaction.projector = SimpleNamespace(task=None, route_ref="route")
    monkeypatch.setattr("src.agentic.valuation_context.validate_composition", lambda *args: "route")
    payload = {"model": "m"}
    interaction.wire_digest = digest(payload, "model-wire-payload/v1")

    def receipt(turn):
        return CallReceipt(
            interaction_id="i",
            turn_number=turn,
            call_id=str(turn),
            pre_call_B_ref="committed",
            context_id="c",
            context_revision=turn,
            requested_model="m",
            route_ref="route",
        )

    interaction.calls = 0
    interaction.current = receipt(1)
    interaction.dispatch(client, payload)
    with pytest.raises(BindingDenied):
        interaction.dispatch(client, payload)
    interaction.current = receipt(2)
    interaction.dispatch(client, payload)
    interaction.current = receipt(2)
    with pytest.raises(BindingDenied):
        interaction.dispatch(client, payload)
    assert interaction.calls == 2


async def test_actual_wire_oversize_no_dispatch(tmp_path, monkeypatch):
    async def configure(service, value, agent):
        original = agent._provider._request_template

        def oversized(**kwargs):
            return {**original(**kwargs), "oversize": "x" * 65537}

        agent._provider._request_template = oversized

    result, calls, receipts, task = await run_case(
        tmp_path, monkeypatch, "wire_oversize", configure
    )
    assert not calls and task.task_id not in result.node_binding.current_results
    assert receipts[0]["diagnostic_code"] == "CONTEXT_TOO_LARGE"
    assert receipts[0]["observed_model"] == receipts[0]["fallback_used"] == "UNKNOWN"


async def test_mimo_actual_expanded_wire(tmp_path, monkeypatch):
    from src.adapters.llm.execution import ProviderExecutionPolicyV1
    from src.adapters.llm.mimo import MimoClient
    from src.infrastructure.config.settings import LLMSettings

    async def configure(service, value, agent):
        agent._provider = MimoClient(
            LLMSettings(
                provider="mimo",
                api_key="FAKE_LOCAL_ONLY",
                base_url="https://api.xiaomimimo.com/v1",
                primary_model="mimo-v2.5",
                fallback_model="mimo-v2.5",
            ),
            execution_policy=ProviderExecutionPolicyV1(
                max_attempts=1, overall_workload_deadline_seconds=90
            ),
        )
        agent._provider.task_profile = "valuation_analysis"
        agent._provider.route_ids = {"mimo-v2.5": "mimo-direct"}

    # Fake body reports gpt for MiMo. The expanded pre-call wire is checked.
    result, calls, receipts, task = await run_case(
        tmp_path, monkeypatch, "mimo_mismatch", configure
    )
    assert len(calls) == 1
    assert receipts[0]["requested_model"] == receipts[0]["resolved_model"] == "mimo-v2.5"
    assert receipts[0]["observed_provider"] == "mimo"
    assert receipts[0]["observed_model"] == "gpt-5.6-sol"
    assert task.task_id not in result.node_binding.current_results


def test_turn_schema_is_strict_at_every_object():
    from src.agentic.valuation_context import ValuationTurn

    def visit(schema):
        if isinstance(schema, dict):
            if schema.get("type") == "object":
                assert set(schema["properties"]) == set(schema["required"])
                assert schema["additionalProperties"] is False
            assert "default" not in schema
            for value in schema.values():
                visit(value)
        elif isinstance(schema, list):
            for value in schema:
                visit(value)

    visit(ValuationTurn.model_json_schema())


def test_request_exact_byte_edge():
    values = dict(
        request_id="",
        context_id="c",
        context_revision=1,
        consumer_role="valuation_analyst",
        need_type="EVIDENCE",
        subject_refs=("a",),
        reason="read",
    )
    base = len(encoded(RetrievalRequest(**values)))
    values["subject_refs"] = ("a" * (1 + 2048 - base),)
    assert len(encoded(RetrievalRequest(**values))) == 2048
    values["subject_refs"] = (values["subject_refs"][0] + "a",)
    with pytest.raises(ValidationError):
        RetrievalRequest(**values)


def test_interaction_deadline_denies():
    from time import monotonic

    interaction = object.__new__(ValuationInteraction)
    interaction.started = monotonic() - 181
    with pytest.raises(BindingDenied, match="CONTEXT_BUDGET_EXHAUSTED"):
        interaction.limit()


async def test_unguarded_turn_primitive_rejected(tmp_path):
    from src.domain.agent_output import StandardResearchAgentStructuredOutput
    from tests.wp02.test_node_binding import wired

    service, _, _, provider = await wired(tmp_path)
    with pytest.raises(BindingDenied, match="WP03_CONTEXT_PROTOCOL_REQUIRED"):
        await service.agent_registry.get("valuation_analyst").execute_valuation_turn(
            None, StandardResearchAgentStructuredOutput
        )
    assert not provider.calls
