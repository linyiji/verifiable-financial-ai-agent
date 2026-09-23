"""Bounded same-Task Specialist invocation recovery; no scheduler or Graph mutation."""

import asyncio
import inspect
from dataclasses import replace
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from pydantic import ValidationError

from src.adapters.llm.provider import LLMFailureClassification as Code
from src.adapters.llm.provider import LLMProviderError
from src.agentic.recovery_policy import (
    ProviderDetector,
    ResearchLeadRecoverySupervisor,
    classify,
    policy_allows,
)
from src.domain.model_execution import TASK_CANDIDATES, resolve_model_execution
from src.domain.owner_policy import TASK_POLICIES
from src.domain.recovery import (
    Action,
    Capability,
    FailureClass,
    Health,
    RecoveryBudget,
    RecoveryContext,
    RecoveryDecision,
    RecoveryEvidence,
    SafeFailureEvidence,
    Scope,
    attempt_failure_facts,
    recovery_decision_is_current,
)
from src.evaluator.contracts import EvaluationAuthorizationError
from src.infrastructure.database.recovery import capability_provenance
from src.phase4_product.hashing import canonical_json_sha256 as digest


class RecoveryStopped(LLMProviderError):
    def __init__(self, reason, candidate, attempted, failure_code=Code.PREFLIGHT_FAILURE):
        super().__init__(
            reason,
            failure_classification=failure_code,
            provider=candidate.provider,
            model=candidate.model,
            requested_model=attempted[0] if attempted else candidate.model,
            attempted_models=tuple(attempted),
            retryable=False,
        )


class AdaptiveRecovery:
    def __init__(
        self,
        routes,
        clients,
        store,
        *,
        capabilities=None,
        certification_refs=None,
        initial_health=None,
        budget=None,
        supervisor=None,
        forbidden_values=(),
        model_grants=None,
    ):
        self.detector = ProviderDetector(routes)
        self.clients = dict(clients)
        self.store = store
        self.certifications = dict(capabilities or {})
        self.certification_refs = dict(certification_refs or {})
        self.initial_health = dict(initial_health or {})
        self._budget = budget or RecoveryBudget()
        self.explicit_budget = budget is not None
        self.supervisor = supervisor or ResearchLeadRecoverySupervisor()
        self.forbidden = tuple(value for value in forbidden_values if value)
        self.model_grants = model_grants

    @property
    def budget(self):
        return self._budget

    @budget.setter
    def budget(self, value):
        # Existing compositions may tighten this public budget after construction.
        # A versioned profile default must never overwrite that explicit limit.
        self._budget = RecoveryBudget.model_validate(value)
        self.explicit_budget = True

    async def execute(self, context, initial_provider, **kwargs):
        task = context.task
        from src.application.repository import node_invocation

        admission = node_invocation.get()
        cycle_id = getattr(admission, "policy_refs", {}).get("external_resume_cycle")
        scope = Scope(
            run_id=task.run_id,
            task_id=task.task_id,
            object_id=context.inputs["research_object_id"],
            scheme_id=context.inputs["scheme_id"],
            task_profile=task.task_type,
            agent_id=task.assigned_agent,
            operation_id="risk-resume:" + cycle_id if cycle_id else "specialist",
            context_hash=digest(context.model_dump(mode="json")),
            contract_hash=digest(kwargs["response_model"].model_json_schema()),
        )
        return await self.execute_scope(context, scope, initial_provider, **kwargs)

    async def execute_scope(
        self, context, scope, initial_provider, *, output_validator=None, **kwargs
    ):
        """Shared authority and ledger; generated operations use exact owned scope."""
        from src.application.execution_profiles import validate_recovery_profile

        frozen_profile = validate_recovery_profile(self, scope)
        from src.application.repository import NodeRecoveryPending, node_recovery

        durable = node_recovery.get()
        resume = durable[2] if durable is not None else None
        cycle = None
        if durable is not None:
            from src.application.resume_runtime import cycle_for

            if getattr(durable[1], "policy_refs", {}).get("external_resume_cycle"):
                current_aggregate = await durable[0].check_invocation(durable[1])
                cycle = cycle_for(current_aggregate, scope.task_id)
            if hasattr(self.store, "admission_lock") and hasattr(durable[0], "_runs"):
                self.store.binding_repository = durable[0]
        generated = scope.operation_id.startswith("generated-capability:")
        owner_policy = TASK_POLICIES.get(scope.task_profile)
        ordered_route_walk = bool(owner_policy and owner_policy.ordered_route_walk)
        budget = (
            owner_policy.effective_budget()
            if owner_policy and owner_policy.recovery_budget and not self.explicit_budget
            else self.budget
        )
        if digest(context.model_dump(mode="json")) != scope.context_hash:
            raise ValueError("Recovery scope/context mismatch")
        if frozen_profile is not None:
            owner_policy = frozen_profile.owner_policy
            budget = frozen_profile.recovery_budget
        if cycle is not None:
            if scope.operation_id != cycle.operation_id:
                raise ValueError("Resume cycle scope changed")
            budget = cycle.budget
        allowed_routes = (
            frozen_profile.allowed_model_routes if frozen_profile is not None
            else TASK_CANDIDATES.get(scope.task_profile, ())
        )
        routes = {
            key: self.detector.routes[key] for key in allowed_routes if key in self.detector.routes
        }
        detector = ProviderDetector(routes)
        current = next(
            (
                key
                for key, c in routes.items()
                if c.provider == initial_provider.provider_name
                and c.model == initial_provider.model_name
            ),
            None,
        )
        if current is None or (not generated and not routes[current].authority_exists):
            raise ValueError("Initial provider is outside governed recovery authority")
        initial_route = current
        history, checked_routes, health, attempted_models = [], [], dict(self.initial_health), []
        checks = decisions = model_switches = provider_switches = provider_calls = 0
        started = monotonic()
        capabilities = {
            key: self.certifications.get(
                (scope.task_profile, key, c.model, scope.contract_hash), Capability.UNKNOWN
            )
            for key, c in routes.items()
        }
        capability_refs = {
            key: self.certification_refs.get(
                (scope.task_profile, key, c.model, scope.contract_hash), ()
            )
            for key, c in routes.items()
        }
        from src.application.execution_profiles import BOUNDED_TERRA_POLICY, adopted_request_matches
        from src.application.risk_replan_profile import CHILD_POLICY

        bounded_proof_policy = (
            frozen_profile is not None
            and frozen_profile.policy_evidence_source in {BOUNDED_TERRA_POLICY, CHILD_POLICY}
        )
        child_proof_policy = (
            frozen_profile is not None and frozen_profile.policy_evidence_source == CHILD_POLICY
        )

        def adopt_bounded_proof():
            if not bounded_proof_policy:
                return
            for key in (frozen_profile.allowed_model_routes if child_proof_policy
                        else frozen_profile.recovery_fallback_routes):
                if key not in routes:
                    continue
                # Schema-only certificates and saved decisions cannot widen this family.
                negative = capabilities.get(key) in {Capability.QUARANTINED, Capability.UNSUPPORTED}
                matched = adopted_request_matches(
                    frozen_profile, context, scope, routes[key], kwargs
                )
                if not negative:
                    capabilities[key] = Capability.VERIFIED if matched else Capability.UNKNOWN
                    capability_refs[key] = (
                        (frozen_profile.runtime_configuration["risk_follow_up_request"][
                            "primary" if key == "teamorouter-sol" else "fallback"
                        ]["receipt_id"],) if matched and child_proof_policy else
                        (frozen_profile.accepted_request_proof.receipt_id,) if matched else ()
                    )

        adopt_bounded_proof()
        observed_records = await self.store.records()
        for key, (status, reference) in capability_provenance(
            observed_records, scope, routes
        ).items():
            capabilities[key] = status
            capability_refs[key] = (reference,)
        for observed in observed_records:
            if (
                observed.kind == "ATTEMPT_COMPLETED"
                and observed.route in routes
                and observed.model == routes[observed.route].model
                and observed.provider == routes[observed.route].provider
                and (datetime.now(UTC) - datetime.fromisoformat(observed.timestamp)).total_seconds()
                < 86400
            ):
                if (
                    observed.outcome == "PASS"
                    and observed.execution_outcome != "MODEL_EXECUTION_SUBSTITUTED"
                ):
                    health[observed.route] = Health.HEALTHY
                elif observed.failure_class in {
                    FailureClass.READ_TIMEOUT,
                    FailureClass.PROVIDER_UNAVAILABLE,
                    FailureClass.REMOTE_PROTOCOL_ERROR,
                    FailureClass.RATE_LIMIT,
                }:
                    health[observed.route] = Health.DEGRADED
        if child_proof_policy:
            # An explicit current outage cannot be healed by an older parent PASS.
            for key, status in self.initial_health.items():
                if status == Health.UNAVAILABLE:
                    health[key] = status
        current_negative_capabilities = {
            key: (status, capability_refs[key])
            for key, status in capabilities.items()
            if status in {Capability.QUARANTINED, Capability.UNSUPPORTED}
        }
        current_unavailable_routes = {
            key for key, status in health.items() if status == Health.UNAVAILABLE
        }
        refs = []
        last_failure = None
        last_failure_route = current
        pending_decision = None
        if resume is not None:
            if resume["context"]["scope"] != scope.model_dump(mode="json"):
                raise ValueError("Durable recovery scope changed")
            history = list(resume["history"])
            checked_routes = list(resume["checked_routes"])
            attempted_models = list(resume["attempted_models"])
            checks, decisions = resume["checks"], resume["decisions"]
            model_switches = resume["model_switches"]
            provider_switches = resume["provider_switches"]
            provider_calls = resume["provider_calls"]
            current = resume["current"]
            last_failure_route = resume["last_failure_route"]
            last_failure = FailureClass(resume["last_failure"])
            refs = list(resume["refs"])
            capabilities = {k: Capability(v) for k, v in resume["capabilities"].items()}
            capability_refs = {k: tuple(v) for k, v in resume["capability_refs"].items()}
            health = {k: Health(v) for k, v in resume["health"].items()}
            started -= resume["elapsed"] + max(0, (
                datetime.now(UTC) - datetime.fromisoformat(resume["saved_at"])
            ).total_seconds())
            pending_decision = RecoveryDecision.model_validate(resume["decision"])

        if bounded_proof_policy:
            # Recheck the current request on resume, then retain fresh negative evidence.
            adopt_bounded_proof()
            for key, (status, references) in current_negative_capabilities.items():
                capabilities[key] = status
                capability_refs[key] = references
            for key in current_unavailable_routes:
                health[key] = Health.UNAVAILABLE

        cycle_monotonic_deadline = (
            monotonic() + max(0.0, (cycle.deadline_at - datetime.now(UTC)).total_seconds())
            if cycle is not None else None
        )

        def remaining():
            seconds = budget.max_total_recovery_time - (monotonic() - started)
            if cycle is not None:
                seconds = min(
                    seconds, cycle_monotonic_deadline - monotonic(),
                    (cycle.deadline_at - datetime.now(UTC)).total_seconds(),
                )
            return max(0.0, seconds)

        async def record(kind, outcome, **fields):
            if kind == "ATTEMPT_COMPLETED":
                facts = attempt_failure_facts.get()
                if facts is not None:
                    fields["transport_evidence"] = facts.get("transport_evidence")
            value = RecoveryEvidence(
                record_id="REC-" + str(uuid4()),
                scope=scope,
                kind=kind,
                outcome=outcome,
                timestamp=datetime.now(UTC).isoformat(),
                node_reservation_id=durable[1].attempt_reservation_id if durable else None,
                **fields,
            )
            await self.store.append(value)
            if kind in {"ATTEMPT_STARTED", "ATTEMPT_COMPLETED", "TERMINAL"}:
                from src.runtime.scheduler import liveness_progress

                liveness_progress(scope.run_id, ("recovery", value.record_id))
            refs.append(value.record_id)
            return value

        async def stop(reason):
            await record(
                "TERMINAL",
                "FAIL",
                route=last_failure_route,
                reason_code=reason,
                failure_class=last_failure,
            )
            codes = {
                FailureClass.MODEL_IDENTITY_MISMATCH: Code.MODEL_IDENTITY_MISMATCH,
                FailureClass.READ_TIMEOUT: Code.READ_TIMEOUT,
                FailureClass.PROVIDER_DEADLINE_EXCEEDED: Code.OVERALL_DEADLINE_EXCEEDED,
                FailureClass.TASK_DEADLINE_EXCEEDED: Code.OVERALL_DEADLINE_EXCEEDED,
                FailureClass.PROVIDER_UNAVAILABLE: Code.PROVIDER_UNAVAILABLE,
                FailureClass.REMOTE_PROTOCOL_ERROR: Code.REMOTE_PROTOCOL_ERROR,
                FailureClass.RATE_LIMIT: Code.QUOTA_OR_RATE_LIMIT,
                FailureClass.OUTPUT_CONTRACT_FAILURE: Code.SEMANTIC_SCHEMA_FAILURE,
            }
            raise RecoveryStopped(
                reason,
                routes[last_failure_route],
                attempted_models,
                codes.get(last_failure, Code.PREFLIGHT_FAILURE),
            )

        # Re-delivery cannot reset budgets after crash or duplicate task scheduling.
        records = await self.store.records(scope.run_id, scope.task_id)
        if resume is None:
            # Initial delivery retains the operation single-entry fence (also
            # enforced by the store). It cannot reset budgets with a new context.
            if any(r.scope.operation_id == scope.operation_id for r in records):
                await stop("INTERRUPTED_EXECUTION")
        else:
            # The immutable saved decision belongs to the failed reservation,
            # not the newly admitted generation's UUID.
            saved_record = next((r for r in records if r.record_id == refs[-1]), None)
            if (saved_record is None or saved_record.node_reservation_id is None
                    or not recovery_decision_is_current(
                        records, scope, saved_record.node_reservation_id, resume,
                    )):
                await stop("INTERRUPTED_EXECUTION")
        if not routes[current].authority_exists:
            await stop("POLICY_DENIED")
        if budget.max_total_recovery_cost is not None:
            await stop("POLICY_DENIED")  # No cost authority in this repository.
        if capabilities[current] in {Capability.QUARANTINED, Capability.UNSUPPORTED}:
            await stop("POLICY_DENIED")

        model_grants = self.model_grants
        if child_proof_policy or cycle is not None:
            model_grants = {}
        if frozen_profile is not None and model_grants is None:
            model_grants = {
                (scope.task_profile, grant.requested_route): grant.actual_routes
                for grant in frozen_profile.owner_policy.dynamic_grants
            }
        frozen_input = digest([message.model_dump() for message in kwargs["messages"]])

        async def invoke(route, check=False):
            if frozen_profile is not None:
                validate_recovery_profile(self, scope)
                frozen_profile.require_route(route)
                if route != initial_route and route not in frozen_profile.recovery_fallback_routes:
                    raise ValueError("Fallback route outside frozen envelope")
            if bounded_proof_policy and (child_proof_policy or route != initial_route) and (
                not adopted_request_matches(frozen_profile, context, scope, routes[route], kwargs)
                or capabilities[route] != Capability.VERIFIED
                or health.get(route) == Health.UNAVAILABLE
            ):
                await stop("POLICY_DENIED")
            nonlocal last_failure, last_failure_route, provider_calls
            candidate = routes[route]
            if (
                digest(context.model_dump(mode="json")) != scope.context_hash
                or digest([m.model_dump() for m in kwargs["messages"]]) != frozen_input
            ):
                await stop("NONRECOVERABLE")
            if remaining() <= 0:
                await stop("RECOVERY_BUDGET_EXHAUSTED")
            attempt_id = "ATT-" + str(uuid4())
            provider_calls += 1
            model_policy = resolve_model_execution(
                scope,
                route,
                routes,
                capabilities,
                budget,
                check=check,
                grants=model_grants,
            )
            common = dict(
                attempt_id=attempt_id,
                attempt_number=(
                    provider_calls if ordered_route_walk else checks if check else len(history)
                ),
                route=route,
                provider=candidate.provider,
                model=candidate.model,
                requested_model=candidate.model,
                capability_check=check,
                execution_policy=model_policy.model_dump(mode="json"),
            )
            await record("ATTEMPT_STARTED", "STARTED", **common)
            clock = monotonic()
            actual_model = None
            execution_outcome = None
            facts = {}
            facts_token = attempt_failure_facts.set(facts)

            def safe_failure(exc, retryable=None):
                values = dict(facts)
                values.pop("transport_evidence", None)
                values.setdefault(
                    "safe_code",
                    "PROVIDER_ERROR"
                    if isinstance(exc, LLMProviderError)
                    else "VALIDATION_ERROR"
                    if type(exc) is ValidationError
                    else "TIMEOUT"
                    if type(exc) is TimeoutError
                    else "EVALUATION_AUTHORIZATION_REJECTED"
                    if type(exc) is EvaluationAuthorizationError
                    else "UNKNOWN_EXCEPTION",
                )
                code = exc.failure_classification if isinstance(exc, LLMProviderError) else None
                values["normalized_failure_class"] = (
                    code.value if isinstance(code, Code) else "UNKNOWN"
                )
                values["provider_retryable"] = (
                    exc.retryable if isinstance(exc, LLMProviderError) else None
                )
                values["retryable"] = retryable
                return SafeFailureEvidence(**values)

            from src.runtime.scheduler import liveness_progress, resume_liveness

            liveness = resume_liveness.get()
            active_key = None
            active_deadline = None
            timeout_seconds = remaining()
            task_timeout = asyncio.timeout(timeout_seconds)
            try:
                if liveness is not None and durable is not None:
                    provider_policy = getattr(self.clients[route], "execution_policy", None)
                    provider_bound = getattr(
                        provider_policy, "overall_workload_deadline_seconds", timeout_seconds,
                    )
                    active_deadline = liveness.clock() + min(timeout_seconds, provider_bound)
                    active_key = liveness.start(
                        durable[1], attempt_id,
                        active_deadline, asyncio.current_task(),
                    )
                try:
                    async with task_timeout:
                        if liveness is None:
                            response = await self.clients[route].complete_structured(**kwargs)
                        else:
                            transport = asyncio.create_task(
                                self.clients[route].complete_structured(**kwargs)
                            )
                            try:
                                # Timeout cancels this wait, not an unbounded
                                # cancellation handshake with a transport.
                                done, _ = await asyncio.wait((transport,))
                                response = done.pop().result()
                            finally:
                                if not transport.done():
                                    transport.cancel()
                                    transport.add_done_callback(
                                        lambda t: None if t.cancelled() else t.exception()
                                    )
                finally:
                    if active_key is not None:
                        liveness.end(active_key)
                        active_key = None
                # A transport may swallow asyncio cancellation and return late.
                # Its response cannot renew the already expired recovery budget.
                if task_timeout.expired() or remaining() <= 0:
                    raise TimeoutError("Recovery response arrived after its deadline")
                if active_deadline is not None and liveness.clock() >= active_deadline:
                    raise LLMProviderError(
                        "Provider response arrived after its owned deadline",
                        failure_classification=Code.OVERALL_DEADLINE_EXCEEDED,
                        provider=candidate.provider, model=candidate.model, retryable=False,
                    )
                if response.actual_model in {
                    "gpt-5.6-sol",
                    "gpt-5.6-luna",
                    "gpt-5.6-terra",
                    "mimo-v2.5",
                    "mimo-v2.5-pro",
                }:
                    actual_model = response.actual_model
                execution_outcome = model_policy.outcome(
                    response.provider, response.requested_model, response.actual_model
                )
                if execution_outcome.endswith("OUT_OF_POLICY"):
                    raise LLMProviderError(
                        "Provider response route identity mismatch",
                        failure_classification=Code.MODEL_IDENTITY_MISMATCH,
                        provider=candidate.provider,
                        model=candidate.model,
                    )
                output = kwargs["response_model"].model_validate(
                    response.output.model_dump(mode="json")
                )
                liveness_progress(scope.run_id, ("typed_return", attempt_id))
                text = output.model_dump_json()
                if any(secret in text for secret in self.forbidden):
                    raise ValueError("Unsafe output")
                candidate_hash = output_validator(output) if output_validator is not None else None
                if (
                    digest(context.model_dump(mode="json")) != scope.context_hash
                    or digest([m.model_dump() for m in kwargs["messages"]]) != frozen_input
                ):
                    raise ValueError("Recovery input mutation")
                await record(
                    "ATTEMPT_COMPLETED",
                    "PASS",
                    **common,
                    latency_ms=(monotonic() - clock) * 1000,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    output_hash=digest(output.model_dump(mode="json")),
                    actual_model=actual_model,
                    candidate_hash=candidate_hash,
                    execution_outcome=execution_outcome,
                    policy_gate_result="ALLOW",
                )
                return replace(
                    response,
                    execution_policy=model_policy.model_dump(mode="json"),
                    execution_outcome=execution_outcome,
                ), None
            except asyncio.CancelledError:
                await record(
                    "ATTEMPT_COMPLETED",
                    "CANCELLED",
                    **common,
                    latency_ms=(monotonic() - clock) * 1000,
                )
                raise
            except EvaluationAuthorizationError as exc:
                await record(
                    "ATTEMPT_COMPLETED",
                    "FAIL",
                    **common,
                    latency_ms=(monotonic() - clock) * 1000,
                    failure_class=FailureClass.NON_RECOVERABLE_RUNTIME_FAILURE,
                    safe_failure=safe_failure(exc, False),
                )
                await record("TERMINAL", "FAIL", route=route, reason_code="NONRECOVERABLE")
                raise
            except Exception as exc:
                if task_timeout.expired() or remaining() <= 0:
                    last_failure = FailureClass.TASK_DEADLINE_EXCEEDED
                    last_failure_route = route
                    await record(
                        "ATTEMPT_COMPLETED",
                        "FAIL",
                        **common,
                        latency_ms=(monotonic() - clock) * 1000,
                        failure_class=last_failure,
                        safe_failure=safe_failure(exc),
                        reason_code="RECOVERY_BUDGET_EXHAUSTED",
                    )
                    await stop("RECOVERY_BUDGET_EXHAUSTED")
                assessment = classify(exc)
                if isinstance(exc, ValidationError):
                    assessment = assessment.model_copy(
                        update={
                            "failure_class": FailureClass.OUTPUT_CONTRACT_FAILURE,
                            "failure_stage": "OUTPUT",
                        }
                    )
                if generated and assessment.failure_class in {
                    FailureClass.MODEL_IDENTITY_MISMATCH,
                    FailureClass.OUTPUT_CONTRACT_FAILURE,
                }:
                    assessment = assessment.model_copy(update={"recoverable": True})
                if generated and assessment.failure_class is FailureClass.MODEL_IDENTITY_MISMATCH:
                    capabilities[route] = Capability.QUARANTINED
                await record(
                    "ATTEMPT_COMPLETED",
                    "FAIL",
                    **common,
                    latency_ms=(monotonic() - clock) * 1000,
                    failure_class=assessment.failure_class,
                    safe_failure=safe_failure(exc, assessment.recoverable),
                    actual_model=actual_model,
                    execution_outcome=execution_outcome,
                    policy_gate_result="DENY"
                    if execution_outcome and execution_outcome.endswith("OUT_OF_POLICY")
                    else None,
                )
                last_failure = assessment.failure_class
                last_failure_route = route
                return None, assessment
            finally:
                attempt_failure_facts.reset(facts_token)

        if resume is None:
            history.append(current)
            attempted_models.append(routes[current].model)
            response, failure = await invoke(current)
        else:
            response = None
            failure = RecoveryContext.model_validate(resume["context"]).failure
        while response is None:
            if pending_decision is not None:
                decision = pending_decision
                pending_decision = None
                if remaining() <= 0:
                    await stop("RECOVERY_BUDGET_EXHAUSTED")
            else:
                if remaining() <= 0:
                    await stop("RECOVERY_BUDGET_EXHAUSTED")
                if not failure.recoverable:
                    await stop("NONRECOVERABLE")
                health[current] = Health.DEGRADED
                discovery_history = history + checked_routes if ordered_route_walk else history
                candidates = detector.candidates(
                    capabilities, discovery_history, budget, health, capability_refs
                )
                # Never spend a capability check on a route that cannot be used under
                # the remaining switch budget. Independent policy still rechecks it.
                candidates = tuple(
                    candidate.model_copy(
                        update={"eligible": False, "next_allowed_action": Action.FAIL_TASK}
                    )
                    if candidate.route != current
                    and (
                        (
                            candidate.provider == routes[current].provider
                            and model_switches >= budget.max_model_fallbacks
                        )
                        or (
                            candidate.provider != routes[current].provider
                            and provider_switches >= budget.max_cross_provider_switches
                        )
                    )
                    else candidate
                    for candidate in candidates
                )
                recovery_context = RecoveryContext(
                    scope=scope,
                    failure=failure,
                    current_route=current,
                    candidates=candidates,
                    attempt_history=tuple(history),
                    remaining_attempts=budget.max_total_attempts_per_task - len(history),
                    remaining_checks=budget.max_capability_checks - checks,
                    remaining_decisions=budget.max_recovery_decisions - decisions,
                    remaining_seconds=remaining(),
                    evidence_refs=tuple(refs[-12:]),
                )
                if ordered_route_walk and not any(
                    candidate.eligible or candidate.next_allowed_action == Action.CAPABILITY_CHECK
                    for candidate in candidates
                ):
                    decision = RecoveryDecision(
                        scope=scope,
                        action=Action.FAIL_TASK,
                        reason_code="NO_ALLOWED_ROUTE",
                        evidence_refs=recovery_context.evidence_refs,
                    )
                    await record(
                        "DECISION",
                        "ALLOW",
                        action=decision.action,
                        decision=decision,
                        recovery_context=recovery_context,
                    )
                    await stop("POLICY_DENIED")
                if (
                    recovery_context.remaining_decisions <= 0
                    or recovery_context.remaining_attempts <= 0
                ):
                    if cycle is not None and recovery_context.remaining_attempts <= 0:
                        decision = RecoveryDecision(
                            scope=scope, action=Action.FAIL_TASK, reason_code="BUDGET_EXHAUSTED",
                            evidence_refs=recovery_context.evidence_refs,
                        )
                        await record("DECISION", "ALLOW", action=decision.action,
                                     decision=decision, recovery_context=recovery_context)
                    await stop("RECOVERY_BUDGET_EXHAUSTED")
                try:
                    decision = self.supervisor.decide(recovery_context)
                    if inspect.isawaitable(decision):
                        async with asyncio.timeout(remaining()):
                            decision = await decision
                    decision = RecoveryDecision.model_validate(decision)
                except TimeoutError:
                    await stop("RECOVERY_BUDGET_EXHAUSTED")
                except EvaluationAuthorizationError:
                    raise
                except Exception:
                    await stop("POLICY_DENIED")
                allowed = policy_allows(
                    decision,
                    recovery_context,
                    budget,
                    model_switches=model_switches,
                    provider_switches=provider_switches,
                )
                decisions += 1
                await record(
                    "DECISION",
                    "ALLOW" if allowed else "DENY",
                    route=decision.target_route,
                    action=decision.action,
                    decision=decision,
                    recovery_context=recovery_context,
                )
                if not allowed:
                    await stop("POLICY_DENIED")
                if decision.action in {Action.FAIL_TASK, Action.FAIL_RUN}:
                    await stop(
                        "RECOVERY_BUDGET_EXHAUSTED"
                        if decision.reason_code == "BUDGET_EXHAUSTED"
                        else "POLICY_DENIED"
                    )
                # Re-entry must consume durable inputs, without reacquisition or
                # replaying a method whose result embeds the prior reservation.
                # Those invocations retain the existing in-call recovery path.
                can_reenter = durable is not None and (
                    not durable[1].authorized_input_requirements.get("acquire", False)
                    and "wp04_candidates" not in durable[1].authorized_input_requirements
                )
                if can_reenter and not generated:
                    owned = await self.store.records(scope.run_id, scope.task_id)
                    completion = next(r for r in reversed(owned)
                                      if r.scope == scope and r.kind == "ATTEMPT_COMPLETED")
                    if (completion.outcome == "FAIL"
                            and completion.failure_class == recovery_context.failure.failure_class):
                        saved = dict(
                            decision=decision.model_dump(mode="json"),
                            context=recovery_context.model_dump(mode="json"),
                            history=history, checked_routes=checked_routes,
                            attempted_models=attempted_models, checks=checks, decisions=decisions,
                            model_switches=model_switches, provider_switches=provider_switches,
                            provider_calls=provider_calls, current=current,
                            last_failure_route=last_failure_route, last_failure=last_failure.value,
                            refs=refs, capabilities=capabilities, capability_refs=capability_refs,
                            health=health, elapsed=monotonic() - started,
                            receipt_id=completion.record_id, saved_at=datetime.now(UTC).isoformat(),
                        )
                        await durable[0].fail_node_for_recovery(durable[1], saved, self.store)
                        raise NodeRecoveryPending(scope.task_id)
            target = decision.target_route
            if decision.action == Action.CAPABILITY_CHECK:
                checks += 1
                if ordered_route_walk:
                    # A check is a real provider request, but it has a separate finite
                    # budget and does not consume an execution-attempt slot.
                    if routes[target].provider == routes[current].provider:
                        model_switches += int(target != current)
                    else:
                        provider_switches += 1
                    current = target
                    checked_routes.append(target)
                    attempted_models.append(routes[target].model)
                checked, check_failure = await invoke(target, check=True)
                if checked is not None and (
                    ordered_route_walk or checked.execution_outcome == "MODEL_EXECUTION_SUBSTITUTED"
                ):
                    # A successful bounded check already executed and validated the exact
                    # task input. Consume that output, not a free duplicate HTTP attempt.
                    # It is observed success, not certification of the preferred route.
                    if not ordered_route_walk:
                        history.append(target)
                        attempted_models.append(routes[target].model)
                    response = checked
                    break
                capabilities[target] = (
                    Capability.VERIFIED
                    if checked is not None
                    else Capability.UNKNOWN
                    if check_failure is not None and check_failure.failure_stage == "PROVIDER"
                    else Capability.QUARANTINED
                )
                capability_refs[target] = (refs[-1],)
                if check_failure is not None and not check_failure.recoverable:
                    await stop("NONRECOVERABLE")
                if ordered_route_walk and check_failure is not None:
                    failure = check_failure
                continue
            if decision.action == Action.SWITCH_MODEL:
                model_switches += 1
            if decision.action == Action.SWITCH_PROVIDER:
                provider_switches += 1
            current = target
            history.append(current)
            attempted_models.append(routes[current].model)
            response, failure = await invoke(current)
        return replace(
            response,
            requested_model=response.requested_model if generated else attempted_models[0],
            attempted_models=tuple(dict.fromkeys(attempted_models)),
        )
