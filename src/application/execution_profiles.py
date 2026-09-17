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
    selection = selected_model(goal.preferences)
    scenario = scenario or ScenarioProfile(
        task_categories=tuple(sorted({t.task_type for t in tasks})),
        report_requirements=tuple(scheme.report_requirements),
    )
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
    return ExecutionSnapshot.freeze(scenario, nodes)


def narrow_profile(current, selected, scenario):
    selected = NodeExecutionProfile.model_validate(selected.model_dump())
    if (
        selected.task_type != current.task_type
        or selected.profile_version != scenario.execution_family_version
        or selected.owner_policy != current.owner_policy
    ):
        raise BindingDenied("PROFILE_VERSION_INCOMPATIBLE", selected.profile_id)
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
    current = digest(runtime_configuration(service, task, selection), "execution-composition/v1")
    if (
        profile.runtime_configuration_digest is None
        or current != profile.runtime_configuration_digest
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
