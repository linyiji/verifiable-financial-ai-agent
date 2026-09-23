"""Confirm resolution and fresh lookup within the existing node/graph authority."""

import hashlib
import inspect
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
from pathlib import Path

from src.application.evidence_collection import evidence_request_plans
from src.application.evidence_routing import EvidenceTaskRouter
from src.data.capability_policy import FUNDAMENTALS_DATA_SCOPES_V1, data_policy
from src.domain.execution_profile import (
    AcceptedRequestProof,
    DataPermission,
    ExecutionSnapshot,
    NodeExecutionProfile,
    NodeProfileBinding,
    ScenarioProfile,
)
from src.domain.model_selection import selected_model
from src.domain.node_binding import BindingDenied, canonical_value, digest
from src.domain.owner_policy import TASK_POLICIES

# Invocation-local only. The value is read from freshly admitted durable state.
execution_profile_context = ContextVar("confirmed_node_execution_profile", default=None)


def provider_configuration(provider):
    if provider is None:
        return None
    policy = getattr(provider, "execution_policy", None)
    settings = getattr(provider, "_settings", None)
    return {
        "provider": provider.provider_name,
        "model": provider.model_name,
        "routes": getattr(provider, "route_ids", {}),
        "execution_policy": asdict(policy) if is_dataclass(policy) else None,
        "fallback_model": getattr(settings, "fallback_model", None),
        "endpoint_digest": digest(getattr(settings, "base_url", None), "endpoint/v1"),
    }


def configured_agent(service, task, selection):
    from src.agentic.composition import selected_research_agent
    from src.agentic.registry import RegistrationNotFoundError

    if service is None:
        return None
    try:
        return selected_research_agent(
            service.agent_registry, task, selection, service.selected_provider_factory
        )
    except RegistrationNotFoundError:
        if selection is not None:
            raise
        return None


def recovery_for(agent):
    from src.agentic.recovery import AdaptiveRecovery

    recovery = getattr(agent, "_recovery", None)
    if recovery is not None and not isinstance(recovery, AdaptiveRecovery):
        raise BindingDenied("PROFILE_COMPOSITION_UNSUPPORTED", "recovery")
    return recovery


def native_tool_configuration(service, task):
    if task.task_type != "fundamental_analysis":
        return ()
    from src.capabilities.financial.growth import RevenueGrowthCapability
    from src.capabilities.financial.profitability import EbitdaMarginCapability

    registry = getattr(service, "capability_registry", None)
    defaults = {
        "revenue_growth": RevenueGrowthCapability(),
        "ebitda_margin": EbitdaMarginCapability(),
    }
    values = []
    for name in defaults:
        if name == "revenue_growth" and task.wp04_method_requirement is not None:
            # The existing exact WP04 descriptor/load gate owns this pinned method,
            # including its diagnostics; never re-resolve it to registry latest.
            values.append({"pinned_method": task.wp04_method_requirement.descriptor})
            continue
        capability = registry.get(name) if registry else defaults[name]
        source = inspect.getsourcefile(type(capability))
        if source is None:
            raise BindingDenied("CAPABILITY_UNAVAILABLE", capability.definition.capability_id)
        values.append(
            {
                "definition": capability.definition,
                "implementation_sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            }
        )
    return tuple(values)


def recovery_configuration(recovery):
    if recovery is None:
        return None
    return {
        "budget": recovery.budget if recovery.explicit_budget else None,
        "routes": {
            key: (value.provider, value.model) for key, value in recovery.detector.routes.items()
        },
        "clients": {key: provider_configuration(value) for key, value in recovery.clients.items()},
        "grants": sorted((str(key), value) for key, value in (recovery.model_grants or {}).items()),
    }


def runtime_configuration(service, task, selection):
    agent = (
        configured_agent(service, task, selection)
        if task.task_type != "evidence_collection"
        else None
    )
    recovery = recovery_for(agent)
    collector = getattr(service, "evidence_collector", None)
    provider = getattr(collector, "_provider", None)
    return {
        "agent": provider_configuration(getattr(agent, "_provider", None)),
        "recovery": recovery_configuration(recovery),
        "data": {
            "fuse_news": getattr(collector, "_fuse_news", False),
            "discovery": getattr(collector, "_discovery", None) is not None,
            "source_authorities_digest": digest(
                getattr(getattr(collector, "_discovery", None), "domains", None), "data-sources/v1"
            ),
            "transient_retry_delays": getattr(provider, "_transient_retry_delays", None),
        },
        "native_tools": native_tool_configuration(service, task),
        "valuation_context": getattr(service, "valuation_context_enabled", False),
    }


def resolve_execution_snapshot(
    scheme, goal, tasks, service=None, *, scenario=None, node_profiles=None
):
    """Initial Confirm only. V5 §2E adopts these exact request sets as permission.

    The Run's object/as-of feed request construction but are deliberately discarded
    from the permission values. They remain existing Goal/Run inputs.
    """
    prospective_defaults = scenario is None and node_profiles is None
    selection = selected_model(goal.preferences)
    from src.domain.execution_profile import report_metric_value

    report_contract = report_metric_value(
        scheme.report_requirements, scheme.assurance_requirements.get("report_metric_requirements")
    )
    if report_contract is not None and report_contract.request_digest != digest(
        goal.preferences.get("report_metric_requirements"), "report-metric-request/v1"
    ):
        raise BindingDenied("CONTRACT_REJECTED", "draft report request mismatch")
    if report_contract is not None:
        validate_report_draft_correspondence(report_contract, goal)
    scenario = scenario or ScenarioProfile(
        task_categories=tuple(sorted({t.task_type for t in tasks})),
        report_requirements=tuple(scheme.report_requirements),
        report_metric_requirements=report_contract,
    )
    if scenario.report_metric_requirements != report_contract:
        raise BindingDenied("CONTRACT_REJECTED", "report snapshot mismatch")
    selected_risk = goal.preferences.get("risk_semantic_profile")
    if selected_risk is not None:
        from src.domain.risk_admission import PROFILE, freeze_contract

        if selected_risk != PROFILE:
            raise BindingDenied("RISK_CONTRACT_VERSION_REJECTED")
        if any(task.task_type == "risk_analysis" for task in tasks):
            scenario = scenario.model_copy(update={
                "risk_semantic_contract": freeze_contract(tasks),
            })
        elif prospective_defaults:
            raise BindingDenied("RISK_REQUIREMENTS_REQUIRED")
    nodes = []
    for task in tasks:
        owner = TASK_POLICIES.get(task.task_type)
        if owner is None:
            raise BindingDenied("PROFILE_TASK_UNSUPPORTED", task.task_type)
        choice = selection if owner.candidates else None
        if choice and choice.route_id not in owner.candidates:
            raise BindingDenied("MODEL_NOT_AUTHORIZED", task.task_type)
        scope = EvidenceTaskRouter._acquisition_scope(EvidenceTaskRouter, task)
        permissions = []
        plans = (
            evidence_request_plans(symbol=goal.research_object_id, as_of=goal.as_of, scope=scope)
            if scope
            else ()
        )
        if scope and (
            tuple(plan.request.dataset for plan in plans)
            != FUNDAMENTALS_DATA_SCOPES_V1[scope.value]
        ):
            raise BindingDenied("DATA_PERMISSION_ADOPTION_REQUIRED", scope.value)
        for plan in plans:
            capability = {"news": "company_news", "transcript": "earnings_transcript"}.get(
                plan.request.dataset
            )
            policy = (
                data_policy(
                    capability,
                    fuse=bool(
                        getattr(getattr(service, "evidence_collector", None), "_fuse_news", False)
                        and capability == "company_news"
                    ),
                )
                if capability
                else None
            )
            permissions.append(
                DataPermission(
                    data_scope_id=scope.value,
                    capability_id=plan.request.dataset,
                    fields=plan.request.fields,
                    observation_limit=plan.request.limit,
                    expected_period=plan.request.expected_period,
                    category=plan.category.value,
                    purpose=plan.purpose,
                    providers=policy.candidates if policy else ("fmp",),
                    max_requests=policy.max_requests if policy else 6,
                    discovery_policy=policy,
                )
            )
        agent = configured_agent(service, task, choice) if owner.candidates else None
        recovery = recovery_for(agent)
        if recovery is not None and recovery.model_grants is not None:
            adopted_grants = {g.requested_route: g.actual_routes for g in owner.dynamic_grants}
            for (task_profile, route), targets in recovery.model_grants.items():
                if task_profile == task.task_type and not set(targets) <= set(
                    adopted_grants.get(route, ())
                ):
                    raise BindingDenied("MODEL_GRANT_NOT_AUTHORIZED", task.task_type)
        explicit = recovery is not None and recovery.explicit_budget
        budget = recovery.budget if explicit else owner.recovery_budget
        configuration = canonical_value(runtime_configuration(service, task, choice))
        methods = (task.skill_id,)
        tools = ["evidence_router"]
        if task.task_type == "fundamental_analysis":
            methods += ("revenue_growth_v1", "ebitda_margin_v1")
            tools += ["revenue_growth", "ebitda_margin"]
        tools += [p.capability_id for p in permissions]
        nodes.append(
            NodeProfileBinding(
                task_id=task.task_id,
                output_contract_digest=digest(task.output_requirements, "output-contract/v1"),
                profile=NodeExecutionProfile(
                    profile_id=f"{scenario.execution_family}/{task.task_type}",
                    profile_version=scenario.execution_family_version,
                    task_type=task.task_type,
                    execution_class="BOUNDED_ADAPTIVE" if owner.candidates else "DETERMINISTIC",
                    allowed_method_ids=methods,
                    allowed_tool_ids=tuple(tools),
                    data_scope_ids=(scope.value,) if scope else (),
                    data_permissions=tuple(permissions),
                    owner_policy=owner,
                    allowed_model_routes=owner.candidates,
                    requested_route=choice.route_id if choice else None,
                    resolved_route=provider_route(agent._provider, owner.candidates)
                    if getattr(agent, "_provider", None)
                    else None,
                    selection_origin=(
                        "USER_EXPLICIT"
                        if choice
                        else "PROFILE_DEFAULT"
                        if getattr(getattr(agent, "_provider", None), "task_profile", None)
                        == task.task_type
                        else "SYSTEM_DEFAULT"
                    ),
                    profile_default_route=owner.preferred_route,
                    recovery_fallback_routes=owner.candidates if recovery else (),
                    recovery_budget=budget,
                    envelope_source="EXPLICIT_CONFIGURATION" if explicit else "PROFILE_DEFAULT",
                    runtime_configuration=configuration,
                    runtime_configuration_digest=digest(configuration, "execution-composition/v1"),
                    stop_conditions=scenario.stop_conditions,
                ),
            )
        )
    if prospective_defaults:
        tightened = [
            default_recovery_profile(node.profile, risk_contract=scenario.risk_semantic_contract)
            if scenario.risk_semantic_contract is not None
            else default_recovery_profile(node.profile)
            for node in nodes
        ]
        if any(a != b.profile for a, b in zip(tightened, nodes, strict=True)):
            scenario = scenario.model_copy(update={"execution_family_version": "2"})
            nodes = [
                node.model_copy(update={"profile": narrow_profile(
                    node.profile,
                    selected.model_copy(update={"profile_version": "2"}),
                    scenario,
                )})
                for node, selected in zip(nodes, tightened, strict=True)
            ]
    if node_profiles:
        # A versioned, explicitly supplied product profile can tighten this family.
        # New grants require a separately adopted product contract, not registry growth.
        nodes = [
            node.model_copy(
                update={
                    "profile": narrow_profile(
                        node.profile, node_profiles[node.profile.task_type], scenario
                    )
                }
            )
            if node.profile.task_type in node_profiles
            else node
            for node in nodes
        ]
    if prospective_defaults and scenario.execution_family_version == "2":
        risks = [t for t in tasks if t.task_type == "risk_analysis"]
        consumers = ([t for t in tasks if risks[0].task_id in t.dependencies]
                     if len(risks) == 1 else [])
        if len(consumers) == 1 and consumers[0].task_type == "report_synthesis":
            from src.application.risk_replan_profile import freeze_child_template

            child = freeze_child_template(service, scheme, goal, risks[0])
            scenario = scenario.model_copy(update={
                "scenario_version": "2", "graph_mutation": "RISK_ADD_CHILD_TASK_HUMAN_V1",
                "risk_follow_up_policy": {
                    "policy_version": "RISK_ADD_CHILD_TASK_HUMAN_V1",
                    "max_approved_expansions_per_run": 1, "max_per_source_node": 1,
                    "max_child_expansions": 0,
                    "decline_policy": "DURABLE_DECLINED_INCOMPLETE_PAUSE/v1",
                    "child_template": child.model_dump(mode="json"),
                    "child_template_digest": digest(child, "node-execution-profile/v1"),
                },
            })
    return ExecutionSnapshot.freeze(scenario, nodes)


def narrow_profile(current, selected, scenario):
    selected = NodeExecutionProfile.model_validate(selected.model_dump())
    if (
        selected.task_type != current.task_type
        or selected.profile_version != scenario.execution_family_version
        or selected.owner_policy != current.owner_policy
    ):
        raise BindingDenied("PROFILE_VERSION_INCOMPATIBLE", selected.profile_id)
    if selected.accepted_request_proof is not None:
        if (
            selected.accepted_request_proof != accepted_terra_proof(
                selected.task_type,
                request_profile=(scenario.risk_semantic_contract["policy"]["profile"]
                                 if scenario.risk_semantic_contract is not None
                                 and selected.task_type == "risk_analysis" else None),
            )
            or selected.profile_version != "2"
            or current.resolved_route != "teamorouter-sol"
            or (selected.task_type == "valuation_analysis"
                and current.runtime_configuration.get("valuation_context") is not False)
        ):
            raise BindingDenied("PROFILE_PROOF_ADOPTION_DENIED", selected.task_type)
    for field in (
        "allowed_method_ids",
        "allowed_tool_ids",
        "allowed_model_routes",
        "data_scope_ids",
        "recovery_fallback_routes",
    ):
        if not set(getattr(selected, field)) <= set(getattr(current, field)):
            raise BindingDenied("PROFILE_PERMISSION_EXPANSION", field)
    for permission in selected.data_permissions:
        adopted = current.data_permission(permission.capability_id, scope=permission.data_scope_id)
        if (
            not set(permission.providers) <= set(adopted.providers)
            or not set(permission.fields) <= set(adopted.fields)
            or permission.observation_limit > adopted.observation_limit
            or permission.max_requests > adopted.max_requests
            or permission.discovery_policy != adopted.discovery_policy
        ):
            raise BindingDenied("PROFILE_PERMISSION_EXPANSION", permission.capability_id)
    if selected.recovery_budget is not None:
        if current.recovery_budget is None:
            raise BindingDenied("PROFILE_PERMISSION_EXPANSION", "model budget")
        for field, limit in selected.recovery_budget.model_dump().items():
            maximum = getattr(current.recovery_budget, field)
            if field == "max_total_recovery_cost":
                # None means not enforced in this profile version. A prospective
                # finite ceiling tightens it; removing a finite ceiling expands it.
                if maximum is not None and (limit is None or limit > maximum):
                    raise BindingDenied("PROFILE_PERMISSION_EXPANSION", field)
                continue
            if limit is not None and (maximum is None or limit > maximum):
                raise BindingDenied("PROFILE_PERMISSION_EXPANSION", field)
    # Selection and configured provider identity are Run resolution, never inherited
    # from a template or another Run. Other values remain owned by the new version.
    return selected.model_copy(
        update={
            key: getattr(current, key)
            for key in (
                "requested_route",
                "resolved_route",
                "selection_origin",
                "profile_default_route",
                "runtime_configuration",
                "runtime_configuration_digest",
                "envelope_source",
            )
        }
    )


def frozen_profile(aggregate, task):
    raw = aggregate.node_binding.execution_snapshot if aggregate.node_binding else None
    if raw is None:
        raise BindingDenied("PROFILE_BINDING_MISSING", task.task_id)
    snapshot = ExecutionSnapshot.model_validate(raw)
    profile = snapshot.for_task(task)
    bound = next(n for n in snapshot.nodes if n.task_id == task.task_id)
    if bound.output_contract_digest != digest(task.output_requirements, "output-contract/v1"):
        raise BindingDenied("PROFILE_OUTPUT_CONTRACT_CHANGED", task.task_id)
    return profile


def validate_runtime_profile(service, aggregate, task):
    profile = frozen_profile(aggregate, task)
    # The existing policy engine may be used only while compatible. No fallback to
    # newer policy: drift explicitly requires re-admission / authorized Replan.
    if profile.owner_policy != TASK_POLICIES.get(task.task_type):
        raise BindingDenied("PROFILE_POLICY_INCOMPATIBLE", task.task_type)
    selection = (
        selected_model(aggregate.goal.preferences) if profile.owner_policy.candidates else None
    )
    if profile.requested_route != (selection.route_id if selection else None):
        raise BindingDenied("PROFILE_SELECTION_CHANGED", task.task_id)
    current = canonical_value(runtime_configuration(service, task, selection))
    from src.application.risk_replan_profile import CHILD_POLICY, validate_child_profile

    if profile.policy_evidence_source == CHILD_POLICY:
        from src.application.risk_follow_up import build_risk_follow_up_context
        from src.application.risk_replan_profile import child_configuration, source_digest

        validate_child_profile(profile)
        current = child_configuration(current, source_digest(build_risk_follow_up_context))

    def executable_configuration(configuration):
        # CapabilityDefinition inherits audit timestamps initialized at module import.
        # They are not executable authority. Keep the exact frozen snapshot/digest;
        # compare every semantic definition field and implementation hash on restart.
        return {**configuration, "native_tools": [
            {**tool, "definition": {
                key: value for key, value in tool["definition"].items()
                if key not in {"created_at", "updated_at"}
            }} if "definition" in tool else tool
            for tool in configuration["native_tools"]
        ]}

    if (
        profile.runtime_configuration_digest is None
        or executable_configuration(current)
        != executable_configuration(profile.runtime_configuration)
    ):
        raise BindingDenied("PROFILE_COMPOSITION_INCOMPATIBLE", task.task_id)
    profile.require_method(task.skill_id)
    profile.require_tool("evidence_router")
    return profile


def active_profile():
    context = execution_profile_context.get()
    return context[2] if context else None


def authorize_data_request(request, provider):
    """At the provider boundary, before probing or discovering any registered data."""
    context = execution_profile_context.get()
    if context is None:
        return  # Independent unbound data consumers retain their separate authority.
    _, _, profile, counts = context
    permission = profile.data_permission(request.dataset, provider=provider)
    profile.require_tool(request.dataset)
    if (
        request.limit > permission.observation_limit
        or not set(request.fields) <= set(permission.fields)
        or request.expected_period != permission.expected_period
    ):
        raise BindingDenied("DATA_REQUEST_OUTSIDE_ENVELOPE", request.dataset)
    key = request.dataset
    counts[key] = counts.get(key, 0) + 1
    if counts[key] > permission.max_requests:
        raise BindingDenied("DATA_REQUEST_ENVELOPE_EXHAUSTED", request.dataset)
    return permission


def profile_request_plans(*, symbol, as_of, scope):
    """Consume the frozen plan; new ambient request members cannot leak into a Run."""
    from src.application.evidence_collection import EvidenceAcquisitionScope, EvidenceRequestPlan
    from src.data.provider import ProviderRequest
    from src.domain.enums import EvidenceCategory

    profile = active_profile()
    if profile is None:
        return evidence_request_plans(symbol=symbol, as_of=as_of, scope=scope)
    if scope.value not in profile.data_scope_ids:
        raise BindingDenied("DATA_SCOPE_NOT_AUTHORIZED", scope.value)
    return tuple(
        EvidenceRequestPlan(
            scope=EvidenceAcquisitionScope(p.data_scope_id),
            request=ProviderRequest(
                symbol=symbol,
                as_of=as_of,
                dataset=p.capability_id,
                fields=p.fields,
                limit=p.observation_limit,
                expected_period=p.expected_period,
            ),
            category=EvidenceCategory(p.category),
            purpose=p.purpose,
        )
        for p in profile.data_permissions
        if p.data_scope_id == scope.value
    )


def validate_recovery_profile(recovery, scope):
    profile = active_profile()
    if profile is None:
        return None
    context = execution_profile_context.get()
    if (scope.run_id, scope.task_id, scope.task_profile) != (
        context[0],
        context[1],
        profile.task_type,
    ):
        raise BindingDenied("PROFILE_INVOCATION_MISMATCH", scope.task_id)
    if profile.owner_policy != TASK_POLICIES.get(scope.task_profile):
        raise BindingDenied("PROFILE_POLICY_INCOMPATIBLE", scope.task_profile)
    effective = (
        recovery.budget if recovery.explicit_budget else profile.owner_policy.recovery_budget
    )
    if canonical_value(recovery_configuration(recovery)) != profile.runtime_configuration.get(
        "recovery"
    ):
        raise BindingDenied("PROFILE_COMPOSITION_INCOMPATIBLE", "recovery")
    if recovery.explicit_budget and effective != profile.recovery_budget:
        raise BindingDenied("PROFILE_BUDGET_INCOMPATIBLE", scope.task_profile)
    return profile


def provider_route(provider, candidates):
    from src.domain.recovery import Candidate

    route = getattr(provider, "route_ids", {}).get(provider.model_name)
    for candidate in (route,) if route else candidates:
        try:
            Candidate(
                route=candidate,
                provider=provider.provider_name,
                model=provider.model_name,
                authority_exists=True,
            )
            if candidate in candidates:
                return candidate
        except ValueError:
            continue
    return None


def authorize_model_provider(provider):
    profile = active_profile()
    if profile is None:
        return
    route = provider_route(provider, profile.allowed_model_routes)
    if route is None:
        raise BindingDenied("MODEL_NOT_AUTHORIZED", "unresolved provider identity")
    profile.require_route(route)
    if canonical_value(provider_configuration(provider)) != profile.runtime_configuration.get(
        "agent"
    ):
        raise BindingDenied("PROFILE_COMPOSITION_INCOMPATIBLE", "model provider")
    if profile.requested_route is not None and route != profile.requested_route:
        raise BindingDenied("MODEL_SELECTION_CHANGED", route)


BOUNDED_TERRA_POLICY = "OWNER_ADOPTED_BOUNDED_TERRA_RECOVERY_V1"


def accepted_terra_proof(task_type, *, request_profile=None):
    """Reviewed exact families, not runtime receipt discovery or certification storage.

    Receipt content digests identify the retained RUN.json and safe request receipt.
    Their output_hash is absent: these are compatibility proofs, never fake Run outputs.
    """
    if request_profile is not None:
        from src.domain.risk_admission import PROFILE

        if task_type != "risk_analysis" or request_profile != PROFILE:
            return None
        identity = {
            "context_digest": (
                "sha256:194d179250754449f281075cdc3e10641a41e501864c64223177f0c8213d0513"
            ),
            "contract_digest": (
                "sha256:15e8772e52044aa424174939d2bac8bb6a575aece2096e40492a49ec6ad98d95"
            ),
            "family": {
                "agent_id": "risk_analyst",
                "builder_digest": (
                    "sha256:12f89727e41d5d0da4f55e0810c2325624d1065e6959f36c10a944f853510671"
                ),
                "execution_profile_version": "2",
                "model": "gpt-5.6-terra",
                "policy_digest": (
                    "sha256:8050f812b83079c689f55b85a0d25a60a8b92b5803c780f7e94542e0edfb30df"
                ),
                "profile": "risk_semantic_outcome_minimal_v1",
                "provider": "teamorouter",
                "response_format_digest": (
                    "sha256:cade1f49fddf9244657aeff2489573863a478fb57989290ee017cdf1477cf65d"
                ),
                "route": "teamorouter-terra",
                "schema_digest": (
                    "sha256:5bbe54a27f6207c4ca1a856e1d3bf739a0141f1c9d8b4be3d209378e19dcbc6c"
                ),
                "schema_identity": "RiskResearchAgentStructuredOutputMinimalV1",
                "schema_name": "risk_analysis_research_output_minimal_v1",
                "skill_id": "risk_analysis_v1",
                "system_prompt_digest": (
                    "sha256:ce20f83b2af7d8b8098a72dd26ff434789c56636a960a478a8a982f3871c23bd"
                ),
                "task_type": "risk_analysis",
                "template_digest": (
                    "sha256:089e28db045eb0214d4278dd2f98863299d3b0f8255dcf6da97da66c51d099cb"
                ),
                "workload": "RESEARCH_AGENT_EXECUTION",
            },
            "family_digest": (
                "sha256:33da4d390e0ebe305a7c752b12ea776bfcf7df57a24312035bd05058be83537e"
            ),
            "messages_digest": (
                "sha256:500b6f21f26be2266549383400f1df63629f58da62d22524e3a79ddf72a7156c"
            ),
            "response_format_digest": (
                "sha256:cade1f49fddf9244657aeff2489573863a478fb57989290ee017cdf1477cf65d"
            ),
            "user_message_digest": (
                "sha256:c72e5357ceef4197a129ac29de214fa04c710cb5949d9b7ef744e5ff8aed4e5c"
            ),
            "wire_digest": (
                "sha256:4e927789b5918839776e9fc18cae8874e6fad1adb72a9213ecf4fb2108577d44"
            ),
            "wire_size": 3739,
        }
        evidence = {
            "proof_id": "D01-TERRA-6dd4f49c-1c49-4162-9421-4c0408e5c4f4",
            "transport_attempt_id": "5e56934c3a4040809a3c6f0bcfe25980",
            "live_digest": (
                "sha256:2a0faba69c1351bfab6095fbd5b74171ef054a2f0edf7b4ee5fcf7570b52f6df"
            ),
            "request_digest": (
                "sha256:4163118d1f9fd9f361692846004f160fe2ff4f32cbecf54b87caf774e27515f0"
            ),
        }
        family = identity["family"]
        proof = AcceptedRequestProof(
            adoption_version="bounded-terra-request-proof/v1", profile_version="2",
            task_type=task_type, skill_id=family["skill_id"], agent_id=family["agent_id"],
            provider=family["provider"], route=family["route"], model=family["model"],
            schema_name=family["schema_name"], schema_identity=family["schema_identity"],
            schema_digest=family["schema_digest"],
            request_builder="src.agentic.research_agent._messages/v1",
            builder_digest=family["builder_digest"], template_digest=family["template_digest"],
            valuation_context_enabled=None, workload_type=family["workload"],
            status="ACCEPTED_BOUNDED_REQUEST_FAMILY",
            receipt_id="REC-c97f2b81-d8e5-402f-a67c-1d6af81b693d",
            attempt_id="ATT-7043e7d1-735d-4abe-9ab2-efadf9150708",
            receipt_content_digest="sha256:dd268b98c1fba43da28fd6ff5de35eac921dc37447183d61eb4f136d1d6a7435",
            request_receipt_digest=evidence["request_digest"],
            d01_identity=identity, d01_evidence=evidence, acceptance_digest="",
        )
        return AcceptedRequestProof.model_validate({
            **proof.model_dump(), "acceptance_digest": proof.content_digest(),
        })
    if task_type == "risk_analysis":
        values = dict(
            agent_id="risk_analyst", schema_identity="RiskResearchAgentStructuredOutput",
            schema_digest="sha256:d896db2e712e14b9a8d9bfc03351a1f384a66529758722204c6c09cd8f4e28ee",
            receipt_id="REC-d1169af9-1065-4506-bf67-e3fbdc1dd8d8",
            attempt_id="ATT-e76b9ff9-a69d-47df-bbcd-6a4599d644f1",
            receipt_content_digest="sha256:828bf51d4cbf08304b4ae17913a16626848b51645d4adb46c820b7062780e7c0",
            request_receipt_digest="sha256:e117d8c608461b791ee0dec21b55bad0ec9b02a8d3ceefdf69fc491be87b90b5",
        )
    elif task_type == "valuation_analysis":
        values = dict(
            agent_id="valuation_analyst", schema_identity="StandardResearchAgentStructuredOutput",
            schema_digest="sha256:171e6d6a310ab660f0aa9075b6b9bc0fe84863f4a27ab5f94a63131aa76a91ab",
            receipt_id="REC-3e6680cf-2b72-4b52-a65f-249d77e76cef",
            attempt_id="ATT-1304bf4c-3742-4b14-83a8-0a7dfdd33c9b",
            receipt_content_digest="sha256:b01b74d12d55d255c16a7b0a419a31e552a6cc7cf698c92cc7be3cf768bea41b",
            request_receipt_digest="sha256:f6465e4e1487d474b52659563f8944153d6ba8e74de3f32fc752042cc681aff6",
        )
    else:
        return None
    proof = AcceptedRequestProof(
        adoption_version="bounded-terra-request-proof/v1", profile_version="2",
        task_type=task_type, skill_id=f"{task_type}_v1",
        provider="teamorouter", route="teamorouter-terra", model="gpt-5.6-terra",
        schema_name=f"{task_type}_research_output_v1",
        request_builder="src.agentic.research_agent._messages/v1",
        builder_digest="sha256:12f89727e41d5d0da4f55e0810c2325624d1065e6959f36c10a944f853510671",
        template_digest="sha256:089e28db045eb0214d4278dd2f98863299d3b0f8255dcf6da97da66c51d099cb",
        valuation_context_enabled=False if task_type == "valuation_analysis" else None,
        workload_type="RESEARCH_AGENT_EXECUTION",
        status="ACCEPTED_BOUNDED_REQUEST_FAMILY", acceptance_digest="", **values,
    )
    return proof.model_copy(update={"acceptance_digest": proof.content_digest()})


def default_recovery_profile(profile, *, risk_contract=None):
    # Explicit selection/configuration and context interaction keep their own authority.
    if (
        profile.task_type not in {"risk_analysis", "valuation_analysis"}
        or profile.resolved_route != "teamorouter-sol"
        or profile.requested_route not in {None, "teamorouter-sol"}
        or (profile.task_type == "valuation_analysis"
            and profile.runtime_configuration.get("valuation_context") is not False)
        or profile.runtime_configuration.get("recovery") is None
        or profile.envelope_source != "PROFILE_DEFAULT"
    ):
        return profile
    return profile.model_copy(update={
        "profile_version": "2",
        "policy_evidence_source": BOUNDED_TERRA_POLICY,
        "allowed_model_routes": ("teamorouter-sol", "teamorouter-terra"),
        "recovery_fallback_routes": ("teamorouter-terra",),
        "recovery_budget": profile.recovery_budget.model_copy(update={"max_capability_checks": 0}),
        "accepted_request_proof": accepted_terra_proof(
            profile.task_type,
            request_profile=(risk_contract["policy"]["profile"]
                             if risk_contract is not None
                             and profile.task_type == "risk_analysis" else None),
        ),
    })


def adopted_request_matches(profile, context, scope, candidate, request):
    """Use frozen acceptance only; exact current builder/schema/route, no ambient proof lookup."""
    from src.application.risk_replan_profile import CHILD_POLICY, adopted_child_matches

    if profile.policy_evidence_source == CHILD_POLICY:
        return adopted_child_matches(profile, context, scope, candidate, request)
    from src.adapters.llm.teamorouter import _structured_request_template
    from src.agentic.research_agent import _messages
    from src.phase4_product.hashing import canonical_json_sha256

    proof = profile.accepted_request_proof
    if proof is None or candidate is None:
        return False
    try:
        builder_digest = "sha256:" + hashlib.sha256(
            inspect.getsource(_messages).encode()
        ).hexdigest()
        template_digest = "sha256:" + hashlib.sha256(
            inspect.getsource(_structured_request_template).encode()
        ).hexdigest()
        return (
            proof.status == "ACCEPTED_BOUNDED_REQUEST_FAMILY"
            and proof.adoption_version == "bounded-terra-request-proof/v1"
            and proof.acceptance_digest == proof.content_digest()
            and proof.profile_version == profile.profile_version
            and proof.task_type == profile.task_type
            == scope.task_profile == context.task.task_type
            and proof.skill_id == context.task.skill_id
            and proof.skill_id in profile.allowed_method_ids
            and proof.agent_id == scope.agent_id == context.task.assigned_agent
            and (proof.route, proof.provider, proof.model)
            == (candidate.route, candidate.provider, candidate.model)
            and candidate.authority_exists
            and proof.route in profile.recovery_fallback_routes
            and proof.schema_digest == scope.contract_hash
            == canonical_json_sha256(request["response_model"].model_json_schema())
            and proof.schema_identity == request["response_model"].__name__
            and proof.schema_name == request["schema_name"]
            and proof.workload_type == request["workload_type"]
            and proof.request_builder == "src.agentic.research_agent._messages/v1"
            and proof.builder_digest == builder_digest
            and proof.template_digest == template_digest
            and (
                (proof.task_type == "risk_analysis" and proof.valuation_context_enabled is None)
                or (proof.task_type == "valuation_analysis"
                    and proof.valuation_context_enabled is False
                    and profile.runtime_configuration.get("valuation_context") is False)
            )
            and _d01_request_matches(proof, profile, context, candidate, request)
            and _adopted_operation_matches(scope)
            and request["messages"] == _messages(context)
            and set(request) == {"messages", "response_model", "schema_name", "workload_type"}
        )
    except (KeyError, TypeError, AttributeError, OSError, IndexError, ValueError):
        return False


def _d01_request_matches(proof, profile, context, candidate, request):
    """Reconstruct the exact proven family; witness inputs are evidence, not Run constants."""
    from src.adapters.llm.teamorouter import _structured_request_template
    from src.domain.risk_admission import active_contract
    from src.phase4_product.hashing import canonical_json_sha256

    contract = active_contract() if context.task.task_type == "risk_analysis" else None
    if proof.d01_identity is None:
        return contract is None
    if contract is None:
        return False
    template = _structured_request_template(
        messages=request["messages"], response_model=request["response_model"],
        schema_name=request["schema_name"],
    )
    family = {
        "profile": contract["policy"]["profile"],
        "execution_profile_version": profile.profile_version,
        "task_type": context.task.task_type, "skill_id": context.task.skill_id,
        "agent_id": context.task.assigned_agent,
        "provider": candidate.provider, "route": candidate.route, "model": candidate.model,
        "schema_name": request["schema_name"],
        "schema_identity": request["response_model"].__name__,
        "schema_digest": canonical_json_sha256(request["response_model"].model_json_schema()),
        "builder_digest": proof.builder_digest, "template_digest": proof.template_digest,
        "system_prompt_digest": "sha256:" + hashlib.sha256(
            request["messages"][0].content.encode()
        ).hexdigest(),
        "response_format_digest": canonical_json_sha256(template["response_format"]),
        "workload": request["workload_type"],
        "policy_digest": canonical_json_sha256(contract["policy"]),
    }
    return (family == proof.d01_identity["family"]
            and canonical_json_sha256(family) == proof.d01_identity["family_digest"])


def _adopted_operation_matches(scope):
    if scope.operation_id == "specialist":
        return True
    from src.application.repository import node_invocation

    admission = node_invocation.get()
    # Resume changes the ledger operation identity, not the frozen request family.
    # Repository admission and provider-entry fences separately revalidate authority.
    return bool(
        admission is not None and scope.task_profile == "risk_analysis"
        and (scope.run_id, scope.task_id) == (admission.run_id, admission.task_id)
        and admission.policy_refs.get("external_resume_cycle")
        and scope.operation_id == "risk-resume:" + admission.policy_refs["external_resume_cycle"]
    )


def resolve_report_metric_draft(scheme, goal, service):
    """Server resolution at draft creation only; conditions never resolve at runtime."""
    from src.domain.execution_profile import (
        REPORT_METRIC_MARKER,
        REPORT_METRIC_SCHEMA,
        ConditionalReportMetric,
        FrozenReportMetricRequirementsV1,
        ReportMetricExpectation,
        report_metric_value,
    )

    request = goal.preferences.get("report_metric_requirements")
    if request is None:
        if report_metric_value(scheme.report_requirements,
                               scheme.assurance_requirements.get("report_metric_requirements")):
            raise BindingDenied("CONTRACT_REJECTED", "unsolicited report opt-in")
        return scheme
    allowed = {"schema_version", "report_mode", "required_metric_ids", "optional_metric_ids",
               "conditional_requirements", "enabled_condition_refs", "period"}
    if (not isinstance(request, dict) or set(request) - allowed
            or request.get("schema_version") != REPORT_METRIC_SCHEMA
            or request.get("report_mode") != "METRIC_FOCUSED"):
        raise BindingDenied("CONTRACT_REJECTED", "report request version/mode")
    supported = {"revenue_growth_v1": "revenue_growth", "ebitda_margin_v1": "ebitda_margin"}

    def ids(key):
        values = request.get(key, [])
        if (not isinstance(values, list) or any(not isinstance(v, str) for v in values)
                or len(values) != len(set(values))):
            raise BindingDenied("CONTRACT_REJECTED", key)
        return set(values)

    required, optional = ids("required_metric_ids"), ids("optional_metric_ids")
    enabled = ids("enabled_condition_refs")
    known_conditions = {f"section:{name}" for name in supported.values()}
    if not enabled <= known_conditions:
        raise BindingDenied("CONTRACT_REJECTED", "unknown report condition")
    provenance = []
    seen = set()
    for item in request.get("conditional_requirements", []):
        if (not isinstance(item, dict)
                or set(item) != {"condition_ref", "metric_id", "requirement_ref"}
                or item["condition_ref"] not in known_conditions
                or not isinstance(item["requirement_ref"], str) or not item["requirement_ref"]):
            raise BindingDenied("CONTRACT_REJECTED", "conditional report requirement")
        pair = (item["condition_ref"], item["metric_id"])
        if pair in seen:
            raise BindingDenied("CONTRACT_REJECTED", "duplicate conditional requirement")
        seen.add(pair)
        active = item["condition_ref"] in enabled
        provenance.append(ConditionalReportMetric(**item, resolved_enabled=active))
        if active:
            required.add(item["metric_id"])
    selected = required | optional | {p.metric_id for p in provenance}
    if not selected <= supported.keys() or not required or required & optional:
        raise BindingDenied("CONTRACT_REJECTED", "unsupported/conflicting report metric selection")
    period = request.get("period")
    if not isinstance(period, str) or len(period) != 6 or not period.startswith("FY"):
        raise BindingDenied("CONTRACT_REJECTED", "explicit annual report period required")
    try:
        year = int(period[2:])
    except ValueError as exc:
        raise BindingDenied("CONTRACT_REJECTED", "report period") from exc
    expectations = []
    for formula in sorted(selected):
        capability = service.capability_registry.get(supported[formula])
        source = inspect.getsourcefile(type(capability))
        expectations.append(ReportMetricExpectation(
            metric_id=formula, capability_id=capability.definition.capability_id,
            capability_version=capability.definition.version,
            implementation_hash="sha256:" + hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            object_id=goal.research_object_id, period=period,
            prior_period=f"FY{year - 1}" if formula == "revenue_growth_v1" else None,
            as_of=goal.as_of,
        ))
    data = dict(schema_version=REPORT_METRIC_SCHEMA, report_mode="METRIC_FOCUSED",
                request_digest=digest(request, "report-metric-request/v1"),
                resolved_required_metric_ids=tuple(sorted(required)),
                optional_metric_ids=tuple(sorted(optional)),
                conditional_requirement_provenance=tuple(sorted(
                    provenance, key=lambda p: (p.condition_ref, p.metric_id))),
                metric_expectations=tuple(expectations))
    contract = FrozenReportMetricRequirementsV1(
        **data, contract_digest=digest(data, REPORT_METRIC_SCHEMA)
    )
    return scheme.model_copy(update={
        "report_requirements": [*scheme.report_requirements, REPORT_METRIC_MARKER],
        "assurance_requirements": {**scheme.assurance_requirements,
                                   "report_metric_requirements": contract.model_dump(mode="json")},
    })


def frozen_report_metrics(aggregate):
    """Read the marker and both copies; never rebuild from runtime preferences."""
    from src.domain.execution_profile import report_metric_value

    contract = report_metric_value(aggregate.scheme.report_requirements,
                                  aggregate.scheme.assurance_requirements.get("report_metric_requirements"))
    if contract is not None and aggregate.aggregate_schema_version != 2:
        raise BindingDenied("CONTRACT_REJECTED", "report requires confirmed v2 authority")
    root = aggregate.node_binding
    if root is None or root.execution_snapshot is None:
        if contract is not None:
            raise BindingDenied("CONTRACT_REJECTED", "missing frozen report authority")
        return None
    raw_scenario = root.execution_snapshot.get("scenario", {})
    snapshot_contract = report_metric_value(
        raw_scenario.get("report_requirements", ()), raw_scenario.get("report_metric_requirements")
    )
    if contract is None and snapshot_contract is None:
        return None
    snapshot = ExecutionSnapshot.model_validate(root.execution_snapshot)
    if snapshot.scenario.report_metric_requirements != contract:
        raise BindingDenied("CONTRACT_REJECTED", "Scheme/scenario report contract mismatch")
    if contract is not None and any(
        e.object_id != aggregate.run.research_object_id or e.as_of != aggregate.run.as_of
        for e in contract.metric_expectations
    ):
        raise BindingDenied("CONTRACT_REJECTED", "report Run identity")
    return contract


def validate_report_draft_correspondence(contract, goal):
    """Validate the resolved draft without choosing or replacing business requirements."""
    request = goal.preferences.get("report_metric_requirements", {})
    required = set(request.get("required_metric_ids", ()))
    enabled = set(request.get("enabled_condition_refs", ()))
    requested_conditions = sorted(
        (c["condition_ref"], c["metric_id"], c["requirement_ref"])
        for c in request.get("conditional_requirements", ())
    )
    retained_conditions = sorted(
        (c.condition_ref, c.metric_id, c.requirement_ref)
        for c in contract.conditional_requirement_provenance
    )
    required.update(c.metric_id for c in contract.conditional_requirement_provenance
                    if c.resolved_enabled)
    if (requested_conditions != retained_conditions
            or any(c.resolved_enabled != (c.condition_ref in enabled)
                   for c in contract.conditional_requirement_provenance)
            or required != set(contract.resolved_required_metric_ids)
            or set(request.get("optional_metric_ids", ())) != set(contract.optional_metric_ids)
            or any(e.object_id != goal.research_object_id or e.as_of != goal.as_of
                   or e.period != request.get("period") for e in contract.metric_expectations)):
        raise BindingDenied("CONTRACT_REJECTED", "resolved report draft differs from request")
