"""Independent receipt binding and exact proven-context reconciliation, no provider probes."""

import inspect
from copy import deepcopy

from src.agentic.research_agent import _messages
from src.agentic.specialist import SpecialistExecutionContext
from src.application.execution import IntegratedTaskExecutor
from src.application.execution_profiles import adopted_request_matches
from src.application.risk_follow_up import build_risk_follow_up_context
from src.application.risk_replan_profile import (
    FINAL_CONTEXT_DIGEST,
    PROBED_CONTEXT_DIGEST,
    child_proof,
    source_digest,
)
from src.domain.agent_output import StandardResearchAgentStructuredOutput
from src.domain.node_binding import digest
from src.domain.recovery import Candidate, Scope
from src.phase4_product.hashing import canonical_json_sha256
from tests.risk_replan.fixtures.probed_risk_follow_up import (
    build_risk_follow_up_context as probed_builder,
)
from tests.risk_replan.test_controls import act, pending


async def test_exact_child_proofs_and_candidate_message_equivalence(tmp_path):
    service, value, calls, _ = await pending(tmp_path)
    repo = service.repository
    await act(repo, value, "APPROVE", "A")
    await repo.apply_replan(value.run.run_id)
    value = await repo.get_run_fresh(value.run.run_id)
    task = value.runtime.task(value.run.run_id + ":risk-follow-up")
    from src.application.execution_profiles import frozen_profile

    profile = frozen_profile(value, task)
    evidence = IntegratedTaskExecutor(service, value)._normalized_evidence_for_task(task)
    inputs = build_risk_follow_up_context(value, task, evidence)
    baseline = probed_builder(value, task, evidence)
    assert inputs == baseline
    assert source_digest(probed_builder) == PROBED_CONTEXT_DIGEST
    assert source_digest(build_risk_follow_up_context) == FINAL_CONTEXT_DIGEST
    context = SpecialistExecutionContext(task=task, inputs=inputs)
    assert _messages(context) == _messages(context.model_copy(update={"inputs": baseline}))
    scope = Scope(
        run_id=task.run_id,
        task_id=task.task_id,
        object_id=value.run.research_object_id,
        scheme_id=value.scheme.scheme_id,
        task_profile="risk_follow_up",
        agent_id="risk_analyst",
        context_hash=canonical_json_sha256(context.model_dump(mode="json")),
        contract_hash=canonical_json_sha256(
            StandardResearchAgentStructuredOutput.model_json_schema()
        ),
    )
    request = dict(
        messages=_messages(context),
        response_model=StandardResearchAgentStructuredOutput,
        schema_name="risk_follow_up_research_output_v1",
        workload_type="RESEARCH_AGENT_EXECUTION",
    )
    for route, model in [
        ("teamorouter-sol", "gpt-5.6-sol"),
        ("teamorouter-terra", "gpt-5.6-terra"),
    ]:
        candidate = Candidate(
            route=route, provider="teamorouter", model=model, authority_exists=True
        )
        assert adopted_request_matches(profile, context, scope, candidate, request)
        assert child_proof(route).acceptance_digest == child_proof(route).content_digest()
        for field in type(child_proof(route)).model_fields:
            bad = deepcopy(profile)
            key = "primary" if route == "teamorouter-sol" else "fallback"
            proof = bad.runtime_configuration["risk_follow_up_request"][key]
            proof[field] = "WRONG"
            bad = bad.model_copy(
                update={
                    "runtime_configuration_digest": digest(
                        bad.runtime_configuration, "execution-composition/v1"
                    )
                }
            )
            assert not adopted_request_matches(bad, context, scope, candidate, request), field
        assert not adopted_request_matches(
            profile,
            context,
            scope,
            candidate.model_copy(update={"authority_exists": False}),
            request,
        )
        assert not adopted_request_matches(
            profile, context, scope, candidate.model_copy(update={"model": "gpt-5.6-luna"}), request
        )
        assert not adopted_request_matches(
            profile,
            context,
            scope,
            candidate,
            {**request, "schema_name": "risk_analysis_research_output_v1"},
        )
        assert not adopted_request_matches(
            profile, context, scope, candidate, {**request, "messages": []}
        )
        assert not adopted_request_matches(
            profile, context, scope, candidate, {**request, "reasoning_effort": "high"}
        )
        bad = profile.model_copy(update={"accepted_request_proof": None})
        assert not adopted_request_matches(bad, context, scope, candidate, request)
        from src.application.execution_profiles import accepted_terra_proof

        bad = profile.model_copy(
            update={"accepted_request_proof": accepted_terra_proof("risk_analysis")}
        )
        assert not adopted_request_matches(bad, context, scope, candidate, request)
    assert profile.allowed_model_routes == ("teamorouter-sol", "teamorouter-terra")
    assert profile.owner_policy.recovery_budget.max_capability_checks == 3
    assert profile.recovery_budget.max_capability_checks == 0
    assert profile.recovery_budget.max_total_attempts_per_task == 2
    assert profile.recovery_budget.max_same_route_attempts == 1
    assert profile.recovery_budget.max_model_fallbacks == 1
    assert profile.recovery_budget.max_runtime_replans == 0
    assert profile.allowed_tool_ids == ("evidence_router",) and not profile.data_permissions
    assert "build-state" not in inspect.getsource(
        __import__("src.application.risk_replan_profile", fromlist=["child_proof"])
    )
