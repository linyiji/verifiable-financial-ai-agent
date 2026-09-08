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
from src.domain.recovery import (
    Action,
    Capability,
    FailureClass,
    Health,
    RecoveryBudget,
    RecoveryContext,
    RecoveryDecision,
    RecoveryEvidence,
    Scope,
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
    ):
        self.detector = ProviderDetector(routes)
        self.clients = dict(clients)
        self.store = store
        self.certifications = dict(capabilities or {})
        self.certification_refs = dict(certification_refs or {})
        self.initial_health = dict(initial_health or {})
        self.budget = budget or RecoveryBudget()
        self.supervisor = supervisor or ResearchLeadRecoverySupervisor()
        self.forbidden = tuple(value for value in forbidden_values if value)

    async def execute(self, context, initial_provider, **kwargs):
        task = context.task
        scope = Scope(
            run_id=task.run_id,
            task_id=task.task_id,
            object_id=context.inputs["research_object_id"],
            scheme_id=context.inputs["scheme_id"],
            task_profile=task.task_type,
            agent_id=task.assigned_agent,
            context_hash=digest(context.model_dump(mode="json")),
            contract_hash=digest(kwargs["response_model"].model_json_schema()),
        )
        return await self.execute_scope(context, scope, initial_provider, **kwargs)

    async def execute_scope(
        self, context, scope, initial_provider, *, output_validator=None, **kwargs
    ):
        """Shared authority and ledger; generated operations use exact owned scope."""
        generated = scope.operation_id.startswith("generated-capability:")
        if digest(context.model_dump(mode="json")) != scope.context_hash:
            raise ValueError("Recovery scope/context mismatch")
        routes = self.detector.routes
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
        history, health, attempted_models = [], dict(self.initial_health), []
        checks = decisions = model_switches = provider_switches = 0
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
                if observed.outcome == "PASS":
                    health[observed.route] = Health.HEALTHY
                elif observed.failure_class in {
                    FailureClass.READ_TIMEOUT,
                    FailureClass.PROVIDER_UNAVAILABLE,
                    FailureClass.REMOTE_PROTOCOL_ERROR,
                    FailureClass.RATE_LIMIT,
                }:
                    health[observed.route] = Health.DEGRADED
        refs = []
        last_failure = None
        last_failure_route = current

        def remaining():
            return max(0.0, self.budget.max_total_recovery_time - (monotonic() - started))

        async def record(kind, outcome, **fields):
            value = RecoveryEvidence(
                record_id="REC-" + str(uuid4()),
                scope=scope,
                kind=kind,
                outcome=outcome,
                timestamp=datetime.now(UTC).isoformat(),
                **fields,
            )
            await self.store.append(value)
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
        if any(
            r.scope.operation_id == scope.operation_id
            for r in await self.store.records(scope.run_id, scope.task_id)
        ):
            await stop("INTERRUPTED_EXECUTION")
        if not routes[current].authority_exists:
            await stop("POLICY_DENIED")
        if self.budget.max_total_recovery_cost is not None:
            await stop("POLICY_DENIED")  # No cost authority in this repository.
        if capabilities[current] in {Capability.QUARANTINED, Capability.UNSUPPORTED}:
            await stop("POLICY_DENIED")

        frozen_input = digest([message.model_dump() for message in kwargs["messages"]])

        async def invoke(route, check=False):
            nonlocal last_failure, last_failure_route
            candidate = routes[route]
            if (
                digest(context.model_dump(mode="json")) != scope.context_hash
                or digest([m.model_dump() for m in kwargs["messages"]]) != frozen_input
            ):
                await stop("NONRECOVERABLE")
            if remaining() <= 0:
                await stop("RECOVERY_BUDGET_EXHAUSTED")
            attempt_id = "ATT-" + str(uuid4())
            common = dict(
                attempt_id=attempt_id,
                attempt_number=checks if check else len(history),
                route=route,
                provider=candidate.provider,
                model=candidate.model,
                requested_model=candidate.model,
                capability_check=check,
            )
            await record("ATTEMPT_STARTED", "STARTED", **common)
            clock = monotonic()
            actual_model = None
            try:
                async with asyncio.timeout(remaining()):
                    response = await self.clients[route].complete_structured(**kwargs)
                if response.actual_model in {
                    "gpt-5.6-sol",
                    "gpt-5.6-luna",
                    "gpt-5.6-terra",
                    "mimo-v2.5",
                    "mimo-v2.5-pro",
                }:
                    actual_model = response.actual_model
                if (
                    response.provider != candidate.provider
                    or response.actual_model != candidate.model
                    or generated
                    and response.requested_model != candidate.model
                ):
                    raise LLMProviderError(
                        "Provider response route identity mismatch",
                        failure_classification=Code.MODEL_IDENTITY_MISMATCH,
                        provider=candidate.provider,
                        model=candidate.model,
                    )
                output = kwargs["response_model"].model_validate(
                    response.output.model_dump(mode="json")
                )
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
                )
                return response, None
            except asyncio.CancelledError:
                await record(
                    "ATTEMPT_COMPLETED",
                    "CANCELLED",
                    **common,
                    latency_ms=(monotonic() - clock) * 1000,
                )
                raise
            except EvaluationAuthorizationError:
                await record(
                    "ATTEMPT_COMPLETED",
                    "FAIL",
                    **common,
                    latency_ms=(monotonic() - clock) * 1000,
                    failure_class=FailureClass.NON_RECOVERABLE_RUNTIME_FAILURE,
                )
                await record("TERMINAL", "FAIL", route=route, reason_code="NONRECOVERABLE")
                raise
            except Exception as exc:
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
                    actual_model=actual_model,
                )
                last_failure = assessment.failure_class
                last_failure_route = route
                return None, assessment

        history.append(current)
        attempted_models.append(routes[current].model)
        response, failure = await invoke(current)
        while response is None:
            if remaining() <= 0:
                await stop("RECOVERY_BUDGET_EXHAUSTED")
            if not failure.recoverable:
                await stop("NONRECOVERABLE")
            health[current] = Health.DEGRADED
            candidates = self.detector.candidates(
                capabilities, history, self.budget, health, capability_refs
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
                        and model_switches >= self.budget.max_model_fallbacks
                    )
                    or (
                        candidate.provider != routes[current].provider
                        and provider_switches >= self.budget.max_cross_provider_switches
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
                remaining_attempts=self.budget.max_total_attempts_per_task - len(history),
                remaining_checks=self.budget.max_capability_checks - checks,
                remaining_decisions=self.budget.max_recovery_decisions - decisions,
                remaining_seconds=remaining(),
                evidence_refs=tuple(refs[-12:]),
            )
            if (
                recovery_context.remaining_decisions <= 0
                or recovery_context.remaining_attempts <= 0
            ):
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
                self.budget,
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
            target = decision.target_route
            if decision.action == Action.CAPABILITY_CHECK:
                checks += 1
                checked, check_failure = await invoke(target, check=True)
                capabilities[target] = (
                    Capability.VERIFIED if checked is not None else Capability.QUARANTINED
                )
                capability_refs[target] = (refs[-1],)
                if check_failure is not None and not check_failure.recoverable:
                    await stop("NONRECOVERABLE")
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
