"""Child-specific accepted request values within existing frozen profile authority."""

import hashlib
import inspect

from src.domain.execution_profile import AcceptedRequestProof
from src.domain.node_binding import BindingDenied, digest
from src.domain.recovery import RecoveryBudget

CHILD_POLICY = "OWNER_ADOPTED_RISK_FOLLOW_UP_REQUEST_V1"
CHILD_ADOPTION = "risk-follow-up-request-proof/v1"
FINAL_CONTEXT_DIGEST = "sha256:dee0a9f10528420b41465fefb7d700367bdf7e52a0ac1f00461d26ada5079050"
PROBED_CONTEXT_DIGEST = "sha256:db98d54ebfff4e86ed9c48845c2aeb7b8c96d10c71fe5e97829d7a5e37719735"
DIAGNOSTIC_ENDPOINT_DIGEST = (
    "sha256:46385290faa1c84f8bdd6e2628d570b6c532c6e3ac17bcfdb986bc6051bbb52b"
)

# Individually reviewed independent PD-2 values, not discovered at runtime.
_PROOFS = {
    "SOL": {
        "acceptance_digest": (
            "sha256:513bd183fa8c2d0659ab0f3b02105bae730748c8341b4690ee797404b5c6fdc2"
        ),
        "adoption_version": "risk-follow-up-request-proof/v1",
        "agent_id": "risk_analyst",
        "attempt_id": "ATT-d2bdeb51101a46ca874154bc0b09da39",
        "builder_digest": "sha256:12f89727e41d5d0da4f55e0810c2325624d1065e6959f36c10a944f853510671",
        "model": "gpt-5.6-sol",
        "profile_version": "1",
        "provider": "teamorouter",
        "receipt_content_digest": (
            "sha256:aa4a41874db2032420e72df79bd986975080101893e978d522c7ad83539ad1e5"
        ),
        "receipt_id": "PD2-SOL-1ab1dbcba4134093ac1ffafec2b0eab3",
        "request_builder": "src.agentic.research_agent._messages/v1",
        "request_receipt_digest": (
            "sha256:5510305c09cac37aa43b07af8d502f79ab3273d58cda45774cf64f41f0641182"
        ),
        "route": "teamorouter-sol",
        "schema_digest": "sha256:171e6d6a310ab660f0aa9075b6b9bc0fe84863f4a27ab5f94a63131aa76a91ab",
        "schema_identity": "StandardResearchAgentStructuredOutput",
        "schema_name": "risk_follow_up_research_output_v1",
        "skill_id": "risk_analysis_v1",
        "status": "ACCEPTED_BOUNDED_REQUEST_FAMILY",
        "task_type": "risk_follow_up",
        "template_digest": (
            "sha256:089e28db045eb0214d4278dd2f98863299d3b0f8255dcf6da97da66c51d099cb"
        ),
        "valuation_context_enabled": None,
        "workload_type": "RESEARCH_AGENT_EXECUTION",
    },
    "TERRA": {
        "acceptance_digest": (
            "sha256:6f2720b4c5b67d6e0af243908e3db4e00decf0b97f5be6b3aa7bc55d9ac77860"
        ),
        "adoption_version": "risk-follow-up-request-proof/v1",
        "agent_id": "risk_analyst",
        "attempt_id": "ATT-45ccd579801e428a8a597ad1ec0a7f76",
        "builder_digest": "sha256:12f89727e41d5d0da4f55e0810c2325624d1065e6959f36c10a944f853510671",
        "model": "gpt-5.6-terra",
        "profile_version": "1",
        "provider": "teamorouter",
        "receipt_content_digest": (
            "sha256:88fa272161dbd00d2ec11af55b492580679d8c6782065fe0ef4da89ead13d242"
        ),
        "receipt_id": "PD2-TERRA-f6721427d08a478ea108c71330e104d7",
        "request_builder": "src.agentic.research_agent._messages/v1",
        "request_receipt_digest": (
            "sha256:17f10da130d5eeea31d5519f54e5b1fa56d0b85978cd9a1df7331fdfe56a87bf"
        ),
        "route": "teamorouter-terra",
        "schema_digest": "sha256:171e6d6a310ab660f0aa9075b6b9bc0fe84863f4a27ab5f94a63131aa76a91ab",
        "schema_identity": "StandardResearchAgentStructuredOutput",
        "schema_name": "risk_follow_up_research_output_v1",
        "skill_id": "risk_analysis_v1",
        "status": "ACCEPTED_BOUNDED_REQUEST_FAMILY",
        "task_type": "risk_follow_up",
        "template_digest": (
            "sha256:089e28db045eb0214d4278dd2f98863299d3b0f8255dcf6da97da66c51d099cb"
        ),
        "valuation_context_enabled": None,
        "workload_type": "RESEARCH_AGENT_EXECUTION",
    },
}


def child_proof(route):
    key = {"teamorouter-sol": "SOL", "teamorouter-terra": "TERRA"}.get(route)
    if key is None:
        raise BindingDenied("CHILD_PROOF_ADOPTION_DENIED", route)
    proof = AcceptedRequestProof.model_validate(_PROOFS[key])
    if proof.acceptance_digest != proof.content_digest():
        raise BindingDenied("CHILD_PROOF_ADOPTION_DENIED", "receipt digest")
    return proof


def source_digest(function):
    return "sha256:" + hashlib.sha256(inspect.getsource(function).encode()).hexdigest()


def child_budget():
    return RecoveryBudget(
        max_total_attempts_per_task=2,
        max_same_route_attempts=1,
        max_model_fallbacks=1,
        max_cross_provider_switches=0,
        max_capability_checks=0,
        max_recovery_decisions=2,
        max_runtime_replans=0,
        max_total_recovery_time=180.0,
        max_total_recovery_cost=None,
    )


def child_configuration(configuration, context_digest):
    from src.adapters.llm.teamorouter import _structured_request_template
    from src.agentic.research_agent import _messages
    from src.domain.agent_output import StandardResearchAgentStructuredOutput
    from src.phase4_product.hashing import canonical_json_sha256

    if context_digest != FINAL_CONTEXT_DIGEST:
        raise BindingDenied("CHILD_PROOF_ADOPTION_DENIED", "unreviewed candidate adapter")
    primary = child_proof("teamorouter-sol")
    fallback = child_proof("teamorouter-terra")
    if (
        primary.builder_digest != source_digest(_messages)
        or primary.template_digest != source_digest(_structured_request_template)
        or primary.schema_digest
        != canonical_json_sha256(StandardResearchAgentStructuredOutput.model_json_schema())
    ):
        raise BindingDenied("CHILD_PROOF_ADOPTION_DENIED", "request family changed")
    recovery = configuration.get("recovery")
    if recovery is None or configuration.get("agent") is None:
        raise BindingDenied("CHILD_PROOF_ADOPTION_DENIED", "missing composition")
    from src.domain.node_binding import digest

    if configuration["agent"].get("endpoint_digest") != digest(
        "https://api.teamorouter.com/v1", "endpoint/v1"
    ):
        raise BindingDenied("CHILD_PROOF_ADOPTION_DENIED", "unproven endpoint")
    for proof in (primary, fallback):
        client = recovery.get("clients", {}).get(proof.route)
        route = recovery.get("routes", {}).get(proof.route)
        if client is None or list(route or ()) != [proof.provider, proof.model]:
            raise BindingDenied("CHILD_PROOF_ADOPTION_DENIED", "route binding")
        if (client.get("provider"), client.get("model"), client.get("fallback_model")) != (
            proof.provider,
            proof.model,
            proof.model,
        ):
            raise BindingDenied("CHILD_PROOF_ADOPTION_DENIED", "isolated model identity")
        from src.domain.owner_policy import ADAPTIVE_TRANSPORT_POLICY

        if client.get("execution_policy") != ADAPTIVE_TRANSPORT_POLICY:
            # Canonical configuration encodes tuples as lists.
            from src.domain.node_binding import canonical_value

            if client.get("execution_policy") != canonical_value(dict(ADAPTIVE_TRANSPORT_POLICY)):
                raise BindingDenied("CHILD_PROOF_ADOPTION_DENIED", "transport envelope")
        if client.get("endpoint_digest") != configuration["agent"].get("endpoint_digest"):
            raise BindingDenied("CHILD_PROOF_ADOPTION_DENIED", "endpoint composition")
    if (configuration["agent"]["provider"], configuration["agent"]["model"]) != (
        primary.provider,
        primary.model,
    ):
        raise BindingDenied("CHILD_PROOF_ADOPTION_DENIED", "primary identity")
    return {
        **configuration,
        "risk_follow_up_request": {
            "adoption_version": CHILD_ADOPTION,
            "primary": primary.model_dump(mode="json"),
            "fallback": fallback.model_dump(mode="json"),
            "probed_context_builder_digest": PROBED_CONTEXT_DIGEST,
            "context_builder_digest": context_digest,
            "diagnostic_endpoint_digest": DIAGNOSTIC_ENDPOINT_DIGEST,
            "endpoint_digest": configuration["agent"]["endpoint_digest"],
            "adaptation": "APPROVED_CANDIDATE_AUTHORITY_ONLY_V1",
        },
    }


def validate_child_profile(profile):
    from src.domain.execution_profile import NodeExecutionProfile
    from src.domain.owner_policy import TASK_POLICIES

    profile = NodeExecutionProfile.model_validate(profile.model_dump())
    metadata = profile.runtime_configuration.get("risk_follow_up_request", {})
    from src.application.risk_follow_up import build_risk_follow_up_context

    base = {
        key: value
        for key, value in profile.runtime_configuration.items()
        if key != "risk_follow_up_request"
    }
    if child_configuration(base, source_digest(build_risk_follow_up_context)) != (
        profile.runtime_configuration
    ):
        raise BindingDenied("CHILD_PROOF_ADOPTION_DENIED", "request/context configuration")
    if (
        profile.profile_id != "risk_follow_up_v1"
        or profile.profile_version != "1"
        or profile.task_type != "risk_follow_up"
        or profile.policy_evidence_source != CHILD_POLICY
        or profile.owner_policy != TASK_POLICIES["risk_follow_up"]
        or profile.allowed_model_routes != ("teamorouter-sol", "teamorouter-terra")
        or profile.recovery_fallback_routes != ("teamorouter-terra",)
        or profile.resolved_route != "teamorouter-sol"
        or profile.requested_route not in {None, "teamorouter-sol"}
        or profile.envelope_source != "PROFILE_DEFAULT"
        or profile.selection_origin
        != ("USER_EXPLICIT" if profile.requested_route else "PROFILE_DEFAULT")
        or profile.allowed_method_ids != ("risk_analysis_v1",)
        or profile.allowed_tool_ids != ("evidence_router",)
        or profile.data_scope_ids
        or profile.data_permissions
        or profile.recovery_budget != child_budget()
        or profile.accepted_request_proof != child_proof("teamorouter-terra")
        or metadata.get("primary") != child_proof("teamorouter-sol").model_dump(mode="json")
        or metadata.get("fallback") != child_proof("teamorouter-terra").model_dump(mode="json")
    ):
        raise BindingDenied("CHILD_PROOF_ADOPTION_DENIED", "frozen child profile")
    return profile


def freeze_child_template(service, scheme, goal, source):
    from src.application.execution_profiles import (
        configured_agent,
        resolve_execution_snapshot,
    )
    from src.application.risk_follow_up import build_risk_follow_up_context
    from src.domain.execution_profile import ScenarioProfile
    from src.domain.task import Task

    task = Task(
        task_id=f"{source.run_id}:risk-follow-up",
        run_id=source.run_id,
        parent_task_id=source.task_id,
        task_type="risk_follow_up",
        assigned_agent="risk_analyst",
        skill_id="risk_analysis_v1",
        dependencies=[source.task_id],
        origin="REPLAN",
        goal="Validate the material risk signal as a bounded child task",
        reason_code="MATERIAL_RISK_FOLLOW_UP",
    )
    from src.domain.execution_profile import report_metric_value

    report_contract = report_metric_value(
        scheme.report_requirements, scheme.assurance_requirements.get("report_metric_requirements")
    )
    scenario = ScenarioProfile(
        task_categories=("risk_follow_up",),
        **({"report_requirements": tuple(scheme.report_requirements),
            "report_metric_requirements": report_contract} if report_contract is not None else {}),
    )
    current = resolve_execution_snapshot(scheme, goal, [task], service, scenario=scenario).for_task(
        task
    )
    if current.requested_route not in {None, "teamorouter-sol"}:
        raise BindingDenied("CHILD_PROOF_ADOPTION_DENIED", "explicit model selection")
    agent = configured_agent(service, task, None)
    settings = getattr(getattr(agent, "_provider", None), "_settings", None)
    base_url = getattr(settings, "base_url", None)
    if (
        not isinstance(base_url, str)
        or "sha256:"
        + hashlib.sha256((base_url.rstrip("/") + "/chat/completions").encode()).hexdigest()
        != DIAGNOSTIC_ENDPOINT_DIGEST
    ):
        raise BindingDenied("CHILD_PROOF_ADOPTION_DENIED", "unproven endpoint")
    configuration = child_configuration(
        current.runtime_configuration, source_digest(build_risk_follow_up_context)
    )

    profile = current.model_copy(
        update={
            "profile_id": "risk_follow_up_v1",
            "profile_version": "1",
            "policy_evidence_source": CHILD_POLICY,
            "selection_origin": "USER_EXPLICIT" if current.requested_route else "PROFILE_DEFAULT",
            "allowed_model_routes": ("teamorouter-sol", "teamorouter-terra"),
            "recovery_fallback_routes": ("teamorouter-terra",),
            "recovery_budget": child_budget(),
            "accepted_request_proof": child_proof("teamorouter-terra"),
            "runtime_configuration": configuration,
            "runtime_configuration_digest": digest(configuration, "execution-composition/v1"),
        }
    )
    return validate_child_profile(profile)


def adopted_child_matches(profile, context, scope, candidate, request):
    from src.adapters.llm.teamorouter import _structured_request_template
    from src.agentic.research_agent import _messages
    from src.application.risk_follow_up import build_risk_follow_up_context
    from src.domain.agent_output import StandardResearchAgentStructuredOutput
    from src.phase4_product.hashing import canonical_json_sha256

    try:
        validate_child_profile(profile)
        from src.application.risk_follow_up import RiskFollowUpContext

        RiskFollowUpContext.model_validate(context.inputs["risk_follow_up"])
        if set(context.inputs) != {
            "research_object_id",
            "goal_id",
            "scheme_id",
            "as_of",
            "research_goal",
            "normalized_evidence",
            "risk_follow_up",
            "input_refs",
        }:
            return False
        proof = child_proof(candidate.route)
        metadata = profile.runtime_configuration["risk_follow_up_request"]
        return (
            candidate.authority_exists
            and (candidate.provider, candidate.model) == (proof.provider, proof.model)
            and proof.task_type == context.task.task_type == scope.task_profile
            and proof.agent_id == context.task.assigned_agent == scope.agent_id
            and proof.skill_id == context.task.skill_id
            and proof.schema_name == request["schema_name"]
            and request["response_model"] is StandardResearchAgentStructuredOutput
            and proof.schema_digest
            == scope.contract_hash
            == canonical_json_sha256(request["response_model"].model_json_schema())
            and proof.builder_digest == source_digest(_messages)
            and proof.template_digest == source_digest(_structured_request_template)
            and metadata["context_builder_digest"]
            == FINAL_CONTEXT_DIGEST
            == source_digest(build_risk_follow_up_context)
            and metadata["adoption_version"] == CHILD_ADOPTION
            and metadata["diagnostic_endpoint_digest"] == DIAGNOSTIC_ENDPOINT_DIGEST
            and scope.operation_id == "specialist"
            and request["workload_type"] == proof.workload_type
            and request["messages"] == _messages(context)
            and set(request) == {"messages", "response_model", "schema_name", "workload_type"}
        )
    except (BindingDenied, ValueError, KeyError, AttributeError, TypeError, OSError):
        return False
