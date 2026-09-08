"""Production recovery composition, real PostgreSQL and clients; fake HTTP only."""

import json
import os
import subprocess

import httpx
import pytest

from src.agentic.research_agent import LLMResearchAgent
from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
from src.agentic.specialist import SpecialistExecutionContext
from src.capabilities.generated.contract import GeneratedCapabilityRequestV1
from src.capabilities.generated.governed_builder import GovernedCodeBuilder
from src.capabilities.generated.spec import expected_spec
from src.domain.model_execution import resolve_model_execution
from src.domain.recovery import Capability, RecoveryBudget, Scope
from src.infrastructure.database.recovery import capability_provenance
from src.observability import performance
from tests.phase4.backend_product.test_governed_builder_composition import composition
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="PostgreSQL required"
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile",
    ["fundamental_analysis", "valuation_analysis", "GENERATED_CAPABILITY:free_cash_flow_margin"],
)
async def test_real_dynamic_composition(database, tmp_path, profile):  # noqa: F811
    sessions, recovery, repository, request = await composition(database, tmp_path)
    if profile.startswith("GENERATED"):
        from tests.unit.generated.test_contract import build_request

        request = request.model_copy(
            update={
                "gap": request.gap.model_copy(
                    update={"requirement": build_request().gap.requirement}
                )
            }
        )
    aggregate = await repository.get_run(request.gap.run_id)
    calls = []
    owned = GeneratedCapabilityRequestV1.from_build_request(request)
    payload = (
        expected_spec(owned).model_dump_json()
        if profile.startswith("GENERATED")
        else json.dumps(
            {
                "summary": "Offline exact evidence",
                "key_findings": ["Observed inputs"],
                "risks": [],
                "limitations": [],
                "requires_follow_up": False,
            }
        )
    )

    def respond(http):
        model = json.loads(http.content)["model"]
        calls.append(model)
        if model == "gpt-5.6-sol":
            raise httpx.ReadTimeout("offline")
        return httpx.Response(
            200,
            json={
                "model": "gpt-5.6-terra",
                "choices": [{"message": {"content": payload}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 9},
            },
        )

    recorder = performance.Recorder()
    performance.configure(recorder)
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            for client in recovery.clients.values():
                client._client = http
            if profile.startswith("GENERATED"):
                result = await GovernedCodeBuilder(recovery, repository).generate(request)
                assert result.actual_model == "gpt-5.6-terra"
                assert result.requested_model == "gpt-5.6-luna"
            else:
                task = next(
                    t for t in aggregate.runtime.actual_graph.tasks if t.task_type == profile
                )
                result = await LLMResearchAgent(
                    agent_id=task.assigned_agent,
                    supported_task_types=frozenset({profile}),
                    provider=recovery.clients["teamorouter-sol"],
                    recovery=recovery,
                    artifacts=ResearchAgentOutputArtifactStore(tmp_path / "phase4-agent-outputs"),
                ).execute(
                    SpecialistExecutionContext(
                        task=task,
                        inputs={
                            "research_object_id": aggregate.run.research_object_id,
                            "scheme_id": aggregate.scheme.scheme_id,
                            "input_refs": [],
                        },
                    )
                )
                assert result.agent_output.actual_model == "gpt-5.6-terra"
                assert result.agent_output.execution_policy["preferred_model"] == "gpt-5.6-luna"
                aggregate.artifacts.agent_outputs.append(result.agent_output)
                await repository.save_run(aggregate)
                from src.agentic.recovery_composition import build_adaptive_recovery
                from src.infrastructure.config.settings import Settings

                restarted = await build_adaptive_recovery(
                    Settings(
                        _env_file=None,
                        teamorouter_api_key="OFFLINE_SENTINEL",
                        mimo_api_key=None,
                        mimo_authority_file=None,
                        artifact_root=str(tmp_path),
                        vfa_credential_mode="byok",
                    ),
                    sessions,
                )
                assert not restarted.certifications
                assert restarted.initial_health["teamorouter-terra"].value == "HEALTHY"
            records = await recovery.store.records(request.gap.run_id)
            passed = next(r for r in records if r.outcome == "PASS")
            assert passed.execution_outcome == "MODEL_EXECUTION_SUBSTITUTED"
            assert passed.actual_model == "gpt-5.6-terra"
            assert passed.requested_model == "gpt-5.6-luna"
            assert passed.policy_gate_result == "ALLOW"
            assert passed.execution_policy["authorized_actual_models"] == [
                "gpt-5.6-luna",
                "gpt-5.6-terra",
            ]
            assert calls == ["gpt-5.6-sol", "gpt-5.6-luna"]
            assert not capability_provenance(records, passed.scope, recovery.detector.routes)
            start = next(
                r
                for r in records
                if r.attempt_id == passed.attempt_id and r.kind == "ATTEMPT_STARTED"
            )
            assert start.execution_policy == passed.execution_policy
            # The actual public recovery DTO round-trips through the real TS decoder.
            script = (
                "import {decodeRecoveryEvidence} from './apps/web/src/types/recovery.ts';"
                "let s=''; for await (const c of process.stdin) s+=c; const x=JSON.parse(s);"
                "const r=decodeRecoveryEvidence(x.rows,x.run,x.object);"
                "if (!r.some(v=>v.actualModel==='gpt-5.6-terra' && "
                "v.routing==='MODEL_EXECUTION_SUBSTITUTED')) process.exit(1);"
            )
            proc = subprocess.run(  # noqa: ASYNC221 - bounded offline decoder subprocess
                ["node", "--experimental-strip-types", "--input-type=module", "-e", script],
                input=json.dumps(
                    {
                        "rows": [r.model_dump(mode="json") for r in records],
                        "run": passed.scope.run_id,
                        "object": passed.scope.object_id,
                    }
                ),
                text=True,
                capture_output=True,
            )
            assert proc.returncode == 0, proc.stderr
            transport = [
                r
                for r in recorder.records
                if r["operation"] == "model.attempt" and r.get("actual_model") == "gpt-5.6-terra"
            ]
            assert transport and transport[0]["preferred_model"] == "gpt-5.6-luna"
    finally:
        performance.configure(None)


@pytest.mark.asyncio
async def test_policy_matrix_and_mimo_authority(database, tmp_path):  # noqa: F811
    _, recovery, _, _ = await composition(database, tmp_path)
    routes = dict(recovery.detector.routes)
    routes["mimo-direct"] = routes["mimo-direct"].model_copy(
        update={"authority_exists": True, "model": "mimo-v2.5"}
    )
    scope = Scope(
        run_id="RUN-local",
        task_id="RUN-local:fundamentals",
        object_id="OBJ-local",
        scheme_id="SCHEME-local",
        task_profile="fundamental_analysis",
        agent_id="fundamental_analyst",
        context_hash="sha256:" + "0" * 64,
        contract_hash="sha256:" + "1" * 64,
    )
    states = {r: Capability.UNKNOWN for r in routes}
    policy = resolve_model_execution(
        scope, "teamorouter-luna", routes, states, RecoveryBudget(), check=True
    )
    assert policy.outcome("teamorouter", "gpt-5.6-luna", "gpt-5.6-luna") == "MODEL_EXECUTION_DIRECT"
    assert (
        policy.outcome("teamorouter", "gpt-5.6-luna", "gpt-5.6-terra")
        == "MODEL_EXECUTION_SUBSTITUTED"
    )
    assert policy.outcome("mimo", "gpt-5.6-luna", "mimo-v2.5") == "PROVIDER_IDENTITY_OUT_OF_POLICY"
    assert (
        policy.outcome("teamorouter", "gpt-5.6-luna", "unknown-x") == "MODEL_IDENTITY_OUT_OF_POLICY"
    )
    assert (
        policy.model_copy(update={"dynamic_substitution_allowed": False}).outcome(
            "teamorouter", "gpt-5.6-luna", "gpt-5.6-terra"
        )
        == "MODEL_IDENTITY_OUT_OF_POLICY"
    )
    exact = resolve_model_execution(
        scope, "teamorouter-luna", routes, states, RecoveryBudget(), grants={}
    )
    assert (
        exact.outcome("teamorouter", "gpt-5.6-luna", "gpt-5.6-terra")
        == "MODEL_IDENTITY_OUT_OF_POLICY"
    )
    mimo = resolve_model_execution(scope, "mimo-direct", routes, states, RecoveryBudget())
    assert mimo.authorized_actual_models == ("mimo-v2.5",)
    assert mimo.outcome("mimo", "mimo-v2.5", "mimo-v2.5") == "MODEL_EXECUTION_DIRECT"
    assert mimo.outcome("mimo", "mimo-v2.5", "mimo-v2.5-pro") == "MODEL_IDENTITY_OUT_OF_POLICY"


@pytest.mark.asyncio
async def test_real_mimo_client_shared_policy(database, tmp_path, monkeypatch):  # noqa: F811
    from pydantic import SecretStr

    from src.agentic import recovery_composition
    from src.infrastructure.config.settings import LLMSettings

    monkeypatch.setattr(
        recovery_composition,
        "load_mimo_authority",
        lambda **kwargs: LLMSettings(
            provider="mimo",
            api_key=SecretStr("OFFLINE_MIMO"),
            primary_model="mimo-v2.5",
            fallback_model="mimo-v2.5",
            base_url="https://offline.invalid/v1",
        ),
    )
    _, recovery, repository, request = await composition(database, tmp_path)
    aggregate = await repository.get_run(request.gap.run_id)
    task = next(t for t in aggregate.runtime.actual_graph.tasks if t.task_type == "peer_analysis")
    calls = []

    def respond(http):
        body = json.loads(http.content)
        calls.append(body["model"])
        return httpx.Response(
            200,
            json={
                "model": "mimo-v2.5",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Offline",
                                    "key_findings": ["Bound evidence"],
                                    "risks": [],
                                    "limitations": [],
                                    "requires_follow_up": False,
                                }
                            )
                        }
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        recovery.clients["mimo-direct"]._client = http
        result = await LLMResearchAgent(
            agent_id=task.assigned_agent,
            supported_task_types=frozenset({task.task_type}),
            provider=recovery.clients["mimo-direct"],
            recovery=recovery,
            artifacts=ResearchAgentOutputArtifactStore(tmp_path / "mimo"),
        ).execute(
            SpecialistExecutionContext(
                task=task,
                inputs={
                    "research_object_id": aggregate.run.research_object_id,
                    "scheme_id": aggregate.scheme.scheme_id,
                    "input_refs": [],
                },
            )
        )
    assert calls == ["mimo-v2.5"]
    assert result.agent_output.actual_model == "mimo-v2.5"
    assert result.agent_output.execution_policy["authorized_actual_models"] == ["mimo-v2.5"]
    assert result.agent_output.execution_outcome == "MODEL_EXECUTION_DIRECT"
