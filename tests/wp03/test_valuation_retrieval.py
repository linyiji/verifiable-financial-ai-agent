"""Real Service/Scheduler/Executor with owned HTTP MockTransport, no external calls."""

import asyncio
import hashlib
import json
import os
import shutil
import socket
from pathlib import Path

import httpx
import pytest

from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.teamorouter import TeamoRouterClient
from src.domain.node_binding import BindingDenied, canonical_value, digest
from src.infrastructure.config.settings import LLMSettings
from tests.wp02.test_node_binding import wired

FINAL = dict(
    summary="本地定性结果",
    key_findings=["仅使用精确引用"],
    risks=[],
    limitations=["无量化估值"],
    requires_follow_up=False,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("WP03 network forbidden")

    monkeypatch.setattr(socket.socket, "connect", deny)


async def run_case(tmp_path, monkeypatch, mode="final", configure=None):
    from src.agentic.valuation_context import ValuationInteraction

    observed = {}
    original_init = ValuationInteraction.__init__

    def capture(self, *args):
        original_init(self, *args)
        observed["interaction"] = self

    monkeypatch.setattr(ValuationInteraction, "__init__", capture)
    service, value, _, _ = await wired(tmp_path)
    agent = service.agent_registry.get("valuation_analyst")
    config = LLMSettings(
        provider="teamorouter",
        api_key="FAKE_LOCAL_ONLY",
        base_url="https://api.teamorouter.com/v1",
        primary_model="gpt-5.6-sol",
        fallback_model="gpt-5.6-sol",
    )
    client = TeamoRouterClient(
        config,
        execution_policy=ProviderExecutionPolicyV1(
            max_attempts=1, overall_workload_deadline_seconds=90
        ),
    )
    client.route_ids = {"gpt-5.6-sol": "teamorouter-sol"}
    client.task_profile = "valuation_analysis"
    agent._provider = client
    service.valuation_context_enabled = True
    if configure:
        await configure(service, value, agent)
    calls = []
    wire_payloads = []
    original_client = httpx.AsyncClient

    async def fake(request):
        payload = json.loads(request.content)
        context = json.loads(payload["messages"][-1]["content"])
        root = (await service.repository.get_run_fresh(value.run.run_id)).node_binding
        steps = [b for b in root.resolved_inputs.values() if b.step_id.startswith("wp03:")]
        assert steps[-1].step_id == f"wp03:valuation:context:{len(calls) + 1}"
        assert steps[-1].payload_snapshot["request_manifest_digest"] == digest(
            payload, "model-wire-payload/v1"
        )
        assert steps[-1].payload_snapshot["context_package"] == context
        calls.append(context)
        wire_payloads.append(payload)
        if mode == "cancel":
            raise asyncio.CancelledError()
        if mode == "evidence_stale":
            service.evidence_repository._records["EVIDENCE-WP02"].normalized_value = "changed"
        if mode == "memory_stale":
            from tests.wp03.test_context_projection import view

            service.research_memory_reader.current = view(2)
        if mode == "timeout":
            raise httpx.ReadTimeout("local", request=request)
        if mode == "stale":
            raw = service.repository._runs[value.run.run_id]
            raw.runtime.task(context["task_id"]).goal = "changed after dispatch"
        if (
            mode in {"retrieve", "second_retrieve", "foreign", "memory_retrieve"}
            and len(calls) == 1
        ):
            req = dict(
                context_id=context["context_id"],
                context_revision=1,
                consumer_role="valuation_analyst",
                need_type="MEMORY_ITEM" if mode == "memory_retrieve" else "EVIDENCE",
                subject_refs=[
                    "foreign"
                    if mode == "foreign"
                    else (
                        context["claim_metric_refs"]
                        if mode == "memory_retrieve"
                        else context["evidence_refs"]
                    )[0]["source_id"]
                ],
                reason="需要完整支持资料",
            )
            req["request_id"] = digest(req, "retrieval-request/v1")
            output = dict(kind="RETRIEVE", answer=None, request=req)
        elif mode == "second_retrieve":
            output = {"kind": "RETRIEVE", "request": {}}
        else:
            output = dict(kind="FINAL", answer=FINAL, request=None) if len(calls) == 1 else FINAL
        body = {"choices": [{"message": {"content": json.dumps(output)}}]}
        if mode != "missing_model":
            body["model"] = "gpt-5.6-luna" if mode == "substitution" else "gpt-5.6-sol"
        return httpx.Response(200, json=body, headers={"x-request-id": "fake-request"})

    monkeypatch.setattr(
        "src.adapters.llm.teamorouter.httpx.AsyncClient",
        lambda **kw: original_client(transport=httpx.MockTransport(fake), **kw),
    )
    try:
        if mode == "cancel":
            from src.application.execution import IntegratedTaskExecutor
            from src.runtime.scheduler import TaskExecutionContext

            owner = await service.repository.claim_execution(value.run.run_id)
            for task in value.runtime.actual_graph.tasks[:2]:
                executor = IntegratedTaskExecutor(
                    service, await service.repository.validate_execution(owner)
                )
                admission = await service.repository.reserve_node(
                    owner, task, executor.admission_requirements(task)
                )
                await service.repository.dispatch_node(admission)
                await executor.execute(
                    task, TaskExecutionContext(run_id=task.run_id, attempt=1, admission=admission)
                )
            raise AssertionError("expected fake physical cancellation")
        result = await service.execute_run(value.run.run_id)
    except asyncio.CancelledError:
        assert mode == "cancel"
        result = await service.repository.get_run_fresh(value.run.run_id)
    except (ExceptionGroup, BindingDenied):
        if mode in {"final", "retrieve"} and configure is None:
            raise
        result = await service.repository.get_run_fresh(value.run.run_id)
    valuation = value.runtime.actual_graph.tasks[1]
    root = result.node_binding
    receipts = [
        b.payload_snapshot["execution_receipt"]
        for b in root.resolved_inputs.values()
        if b.step_id.startswith("wp03:") and b.step_id.endswith(":receipt")
    ]
    if mode in {"stale", "evidence_stale"}:
        files = await asyncio.to_thread(
            lambda: list((agent._artifacts.root / "blobs" / "sha256").iterdir())
        )
        blobs = [json.loads(await asyncio.to_thread(path.read_bytes)) for path in files]
        assert any(
            b.get("failure_code") == "WP03_UNCOMMITTED_DIAGNOSTIC"
            and "UNCOMMITTED" in b["input_refs"]
            for b in blobs
        )
    destination = os.environ.get("WP03_EVIDENCE_DIR")
    if destination:
        await asyncio.to_thread(Path(destination).mkdir, parents=True, exist_ok=True)
        node = os.environ.get("PYTEST_CURRENT_TEST", mode)
        case = mode + "-" + hashlib.sha256(node.encode()).hexdigest()[:12]
        retained = {}
        records = [m for b in root.resolved_inputs.values() for m in b.material_refs]
        records += [m for r in root.results.values() for m in r.output_records]
        blob_dir = Path(destination) / "blobs"
        await asyncio.to_thread(blob_dir.mkdir, exist_ok=True)
        for record in records:
            if record.kind in {"EVIDENCE", "AGENT_OUTPUT"}:
                content = await asyncio.to_thread(Path(record.location).read_bytes)
                target = blob_dir / hashlib.sha256(content).hexdigest()
                await asyncio.to_thread(shutil.copyfile, record.location, target)
                retained[record.location] = str(target)
        await asyncio.to_thread(
            Path(destination, f"{case}.json").write_text,
            json.dumps(
                {
                    "test_node": node,
                    "observation_scope": "LOCAL_FAKE_VALUATION_INTERACTION_ONLY",
                    "counters": observed["interaction"].summary()
                    if observed
                    else {
                        "logical_turn_count": 0,
                        "provider_logical_call_count": 0,
                        "retrieval_round_count": 0,
                        "client_physical_dispatch_count": 0,
                        "tool_data_read_count": 0,
                        "fallback_count": 0,
                        "retry_count": 0,
                    },
                    "counter_authority": "COMMITTED_RESULT"
                    if valuation.task_id in root.current_results
                    else "TEST_OBSERVATION_NOT_A_COMMITTED_RESULT",
                    "requested_model": agent._provider.model_name,
                    "resolved_model": receipts[-1]["resolved_model"] if receipts else "UNKNOWN",
                    "observed_provider": receipts[-1]["observed_provider"]
                    if receipts
                    else "UNKNOWN",
                    "observed_model": receipts[-1]["observed_model"] if receipts else "UNKNOWN",
                    "retained_source_files": retained,
                    "wire_payloads": wire_payloads,
                    "calls": calls,
                    "receipts": receipts,
                    "root": canonical_value(root),
                    "physical_http_calls": len(calls),
                    "valuation_task": valuation.task_id,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    return result, calls, receipts, valuation


@pytest.mark.parametrize("mode,expected", [("final", 1), ("retrieve", 2)])
async def test_real_flow(tmp_path, monkeypatch, mode, expected):
    result, calls, receipts, task = await run_case(tmp_path, monkeypatch, mode)
    assert len(calls) == expected
    assert len(receipts) == expected
    root = result.node_binding
    assert task.task_id in root.current_results
    r = root.results[root.current_results[task.task_id]]
    summary = r.observed_execution["wp03_context"]
    assert summary["client_physical_dispatch_count"] == expected
    assert summary["logical_turn_count"] == expected
    assert summary["retrieval_round_count"] == expected - 1
    assert len([o for o in result.artifacts.agent_outputs if o.task_id == task.task_id]) == 1
    assert all(
        c["fallback_used"] is False and c["observed_model"] == "gpt-5.6-sol" for c in receipts
    )
    assert all(c["pre_call_B_ref"] in r.resolved_input_binding_ids for c in receipts)
    assert (
        result.run.status.value == "FAILED"
    )  # Original required-calculation closure, not financial PASS.


@pytest.mark.parametrize(
    "mode,count",
    [
        ("foreign", 1),
        ("second_retrieve", 2),
        ("missing_model", 1),
        ("substitution", 1),
        ("timeout", 1),
        ("stale", 1),
    ],
)
async def test_fail_closed(tmp_path, monkeypatch, mode, count):
    result, calls, receipts, task = await run_case(tmp_path, monkeypatch, mode)
    assert len(calls) == count
    assert task.task_id not in result.node_binding.current_results
    if mode != "stale":
        assert sum(r["client_physical_dispatch_count"] for r in receipts) == count
    if mode in {"missing_model", "timeout"}:
        assert receipts[0]["observed_model"] == "UNKNOWN"
    if mode == "timeout":
        assert receipts[0]["phase"] == "RESULT_UNKNOWN"
    if mode == "substitution":
        assert receipts[0]["observed_model"] == "gpt-5.6-luna"


@pytest.mark.parametrize("composition", ["recovery", "fallback", "retry", "route", "opaque"])
async def test_composition_denied(tmp_path, monkeypatch, composition):
    async def configure(service, value, agent):
        if composition == "recovery":
            agent._recovery = object()
        elif composition == "fallback":
            agent._provider._settings = agent._provider._settings.model_copy(
                update={"fallback_model": "gpt-5.6-luna"}
            )
        elif composition == "retry":
            agent._provider._execution_policy = ProviderExecutionPolicyV1()
        elif composition == "route":
            agent._provider.task_profile = "risk_analysis"
        else:
            agent._provider._client = object()

    result, calls, _, task = await run_case(tmp_path, monkeypatch, configure=configure)
    assert not calls
    assert task.task_id not in result.node_binding.current_results


@pytest.mark.parametrize("mode", ["cancel", "evidence_stale"])
async def test_inflight_cancel_or_source_change(tmp_path, monkeypatch, mode):
    result, calls, receipts, task = await run_case(tmp_path, monkeypatch, mode)
    assert len(calls) == 1
    assert task.task_id not in result.node_binding.current_results
    if mode == "cancel":
        assert receipts[0]["phase"] == "RESULT_UNKNOWN"
        assert receipts[0]["client_physical_dispatch_count"] == 1
    else:
        assert not receipts  # stale original is denied; only UNCOMMITTED failure artifact exists.
