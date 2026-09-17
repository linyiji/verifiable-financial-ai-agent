from __future__ import annotations

import asyncio
import hashlib
import inspect
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from src.agentic.decisions import ResearchLeadReplanDecider
from src.agentic.registry import RegistrationNotFoundError
from src.agentic.research_agent import ResearchAgentInvocationError
from src.agentic.specialist import SpecialistExecutionContext, SpecialistResult
from src.application.repository import node_invocation, node_recovery
from src.application.research_outputs import (
    availability_map,
    configure_output_contracts,
    publish_output,
)
from src.data.peers import PeerCompanyFacts, PeerSelectionService
from src.domain.agent_output import ResearchAgentOutputRecord
from src.domain.capability import CapabilityContext
from src.domain.correction import CorrectionRecord
from src.domain.decision import StructuredAgentDecision
from src.domain.enums import (
    CorrectionStatus,
    EvidenceAcquisitionStatus,
    EvidenceCategory,
    ReplanDecision,
    TaskOrigin,
)
from src.domain.financial_branch import BranchRequirement
from src.domain.node_binding import (
    BindingDenied,
    GraphIdentity,
    OutputRecord,
    calculation_core,
    canonical_value,
    digest,
    task_semantics,
)
from src.domain.output_dependency import LocalOutputFailure, OutputStatus
from src.domain.runtime_event import RuntimeEventType
from src.domain.task import ReplanRequest, Task
from src.observability.instrumentation import ObservationStage
from src.observability.performance import observe
from src.runtime.graph import (
    GraphMutationActor,
    GraphMutationRole,
    GraphMutationService,
)
from src.runtime.scheduler import TaskExecutionContext, TaskExecutionResult


class IntegratedTaskExecutor:
    """Adapter from runtime Tasks to application capabilities and Agent decisions."""

    def __init__(self, service: object, aggregate: object) -> None:
        self._service = service
        self._aggregate = aggregate
        before = GraphIdentity.of(aggregate.runtime.actual_graph)
        configure_output_contracts(aggregate.runtime)
        if aggregate.node_binding is not None and (
            before != GraphIdentity.of(aggregate.runtime.actual_graph)
            or before != aggregate.node_binding.frozen_graph
        ):
            raise BindingDenied("STATE_REFRESH_REQUIRED", "initial normalization drift")
        self._bound_steps = []
        self._wp04 = {}
        self._has_specialized_collection_tasks = (
            sum(
                task.task_type == "evidence_collection"
                for task in aggregate.runtime.actual_graph.tasks
            )
            > 1
        )
        self._active = 0
        self.parallel_peak = 0
        self._calculation_commit_lock = asyncio.Lock()

    @observe("task.execution", task="task")
    async def execute(
        self,
        task: Task,
        context: TaskExecutionContext,
    ) -> TaskExecutionResult:
        if self._aggregate.node_binding is None:
            raise BindingDenied("STATE_REFRESH_REQUIRED", "legacy Executor is read only")
        if (
            context.admission is None
            or context.run_id != task.run_id
            or context.admission.task_id != task.task_id
        ):
            raise BindingDenied("STATE_REFRESH_REQUIRED", "missing admission context")
        fresh = await self._service.repository.enter_node_execution(context.admission)
        invocation = IntegratedTaskExecutor(self._service, fresh)
        if (
            invocation.admission_requirements(task)
            != context.admission.authorized_input_requirements
        ):
            raise BindingDenied("IDENTITY_MISMATCH", "authorized work changed")
        from src.application.execution_profiles import (
            execution_profile_context,
            validate_runtime_profile,
        )

        profile = validate_runtime_profile(self._service, fresh, task)
        profile_token = execution_profile_context.set((task.run_id, task.task_id, profile, {}))
        token = node_invocation.set(context.admission)
        reservation = fresh.node_binding.attempts[task.task_id]
        recovery_token = node_recovery.set((
            self._service.repository, context.admission, reservation.recovery,
        ))
        self._active += 1
        self.parallel_peak = max(self.parallel_peak, self._active)
        try:
            # Preserve the existing instrumentation owners around the scoped invocation.
            async with self._service.instrumentation.task(
                run_id=task.run_id,
                task_id=task.task_id,
                attributes={"task_type": task.task_type},
            ):
                async with self._service.instrumentation.agent(
                    run_id=task.run_id,
                    task_id=task.task_id,
                    attributes={"agent": task.assigned_agent},
                ):
                    async with self._service.instrumentation.skill(
                        run_id=task.run_id,
                        task_id=task.task_id,
                        attributes={"skill": task.skill_id},
                    ):
                        result = await invocation._execute_instrumented_task(task)
                        return await invocation._commit_bound_result(task, result)
        except BaseException as exc:
            if task.wp04_method_requirement is not None and not invocation._wp04.get('terminal_observed'):
                await invocation._observe_wp04(task,
                    'EXECUTION_FINISHED' if invocation._wp04.get('dispatch_count') else 'DENIED',
                    'SUPPORTED' if invocation._wp04.get('input_binding') else 'UNKNOWN',
                    getattr(exc, 'code', type(exc).__name__),
                    'RESULT_UNKNOWN' if invocation._wp04.get('dispatch_count') else 'NONE')
            raise
        finally:
            self._active -= 1
            node_invocation.reset(token)
            node_recovery.reset(recovery_token)
            execution_profile_context.reset(profile_token)

    async def _execute_instrumented_task(self, task: Task) -> TaskExecutionResult:
        self._require_bound_invocation(task)
        self.admission_requirements(task) if self._aggregate.node_binding is not None else None
        if task.wp04_method_requirement is not None:
            self._wp04['selected_pair'] = await self._prepare_wp04(task)
        await self._service.event_store.emit(
            run_id=task.run_id,
            task_id=task.task_id,
            event_type=RuntimeEventType.TASK_PROGRESS,
            payload={
                "progress": 0.1,
                "stage": "dispatched",
                "message": "Task dispatched to its application execution adapter.",
            },
        )
        acquire = self._should_acquire_evidence(task)
        async with self._service.instrumentation.tool(
            run_id=task.run_id,
            task_id=task.task_id,
            attributes={
                "tool_name": "evidence_router",
                "capability": "live_or_fixture_evidence_collection" if acquire else "evidence_link",
            },
        ):
            routing = await self._service.route_task_evidence(
                self._aggregate,
                task,
                acquire=acquire,
            )
        if routing.acquisition_status is not None:
            produced = set(routing.output_evidence_ids)
            records = [
                record
                for record in self._aggregate.artifacts.evidence
                if record.evidence_id in produced
            ]
            authoritative = self._aggregate.runtime.task(task.task_id)
            for endpoint, coverage in authoritative.evidence_source_coverage.items():
                refs = [
                    record.evidence_id
                    for record in records
                    if record.source_endpoint == endpoint and record.status.value == "ACCEPTED"
                ]
                status = OutputStatus(coverage["outcome"])
                if status is OutputStatus.COMPLETED and not refs:
                    status = OutputStatus.INSUFFICIENT_EVIDENCE
                publish_output(
                    authoritative,
                    "source." + endpoint,
                    status,
                    refs=refs,
                    reason=coverage.get("error_code"),
                )
                await self._service.event_store.emit(
                    run_id=task.run_id,
                    task_id=task.task_id,
                    event_type=RuntimeEventType.TASK_PROGRESS,
                    payload={
                        "progress": authoritative.progress,
                        "message_code": f"SOURCE_OUTCOME:{endpoint}:{status.value}:{len(refs)}",
                    },
                )
            status_counts: dict[str, int] = {}
            for record in records:
                status_counts[record.status.value] = status_counts.get(record.status.value, 0) + 1
            if not records:
                status_counts[routing.acquisition_status.value] = 1
            async with self._service.instrumentation.observe(
                ObservationStage.EVIDENCE,
                run_id=task.run_id,
                task_id=task.task_id,
                attributes={
                    "evidence_count": len(records),
                    "providers": sorted({record.provider for record in records}),
                    "periods": sorted({record.period for record in records}),
                    "normalized_fields": sorted({record.normalized_field for record in records}),
                    "status_counts": status_counts,
                },
            ):
                pass
        for intent in routing.event_intents:
            await self._service.event_store.emit(
                run_id=intent.run_id,
                task_id=intent.task_id,
                event_type=intent.type,
                payload=intent.payload,
            )
        if self._aggregate.node_binding is not None:
            # Acquired originals exist now; no future evidence was invented in Stage A.
            await self._bind_step(
                task,
                "acquisition",
                {
                    "task": canonical_value(self._aggregate.runtime.task(task.task_id)),
                    "availability": availability_map(self._aggregate, task),
                },
            )
        handler = self._handler_for(task)
        return await handler(task)

    async def _execute_evidence_collection(self, task: Task) -> TaskExecutionResult:
        self._require_bound_invocation(task)
        routed = self._aggregate.runtime.task(task.task_id)
        acquisition = routed.evidence_acquisition_status
        status = acquisition.value.lower() if acquisition is not None else "not_requested"
        return TaskExecutionResult(
            result_ref=f"evidence://{task.run_id}/{task.task_id.rsplit(':', 1)[-1]}/{status}",
            output_refs=tuple(routed.task_output_evidence_ids),
        )

    async def _execute_fundamental_analysis(self, task: Task) -> TaskExecutionResult:
        self._require_bound_invocation(task)
        input_ids = set(self._aggregate.runtime.task(task.task_id).task_input_evidence_ids)
        evidence = [
            record
            for record in self._aggregate.artifacts.evidence
            if record.evidence_id in input_ids
        ]
        if task.wp04_method_requirement is not None:
            prior, current = self._wp04['selected_pair']
            # Only companion selection retains the existing legacy behavior.
            _, _, mismatch, ebitda = _select_financial_inputs(evidence)
        else:
            prior, current, mismatch, ebitda = _select_financial_inputs(evidence)
        context = CapabilityContext(
            run_id=task.run_id,
            task_id=task.task_id,
            accepted_evidence_ids=[record.evidence_id for record in evidence],
        )
        await self._service.event_store.emit(
            run_id=task.run_id,
            task_id=task.task_id,
            event_type=RuntimeEventType.CALCULATION_STARTED,
            payload={"capability_id": "revenue_growth"},
        )
        growth = await self._execute_calculation(
            task=task,
            capability_id="revenue_growth",
            inputs={
                "prior": prior,
                "current": current,
                "calculation_id": f"CALC-{task.run_id}-GROWTH",
            },
            context=context,
        )
        await self._commit_calculation(task, growth)

        # The fixture intentionally presents a quarterly revenue candidate first.
        # The real capability rejects its period mismatch and the same task corrects it.
        correction = None
        try:
            await self._execute_calculation(
                task=task,
                capability_id="ebitda_margin",
                inputs={
                    "ebitda": ebitda,
                    "revenue": mismatch,
                    "calculation_id": f"CALC-{task.run_id}-MARGIN-BAD",
                },
                context=context,
            )
        except ValueError as exc:
            from src.capabilities.financial.common import PeriodMismatchError

            if not isinstance(exc, PeriodMismatchError):
                raise
            correction_id = f"CORR-{task.run_id}-PERIOD"
            # Awaited event publication, not presentation dwell, defines the
            # durable correction boundaries. Slow consumers reconstruct by replay.
            async with self._service.instrumentation.self_correction(
                run_id=task.run_id,
                task_id=task.task_id,
                attributes={
                    "correction_id": correction_id,
                    "problem_code": "PERIOD_MISMATCH",
                    "error_type": type(exc).__name__,
                },
            ):
                await self._service.event_store.emit(
                    run_id=task.run_id,
                    task_id=task.task_id,
                    event_type=RuntimeEventType.TASK_SELF_CORRECTING,
                    payload={"problem_code": "PERIOD_MISMATCH", "error": type(exc).__name__},
                )
                correction_timestamp = datetime.now(UTC)
                correction = CorrectionRecord(
                    correction_id=correction_id,
                    run_id=task.run_id,
                    task_id=task.task_id,
                    problem_code="PERIOD_MISMATCH",
                    detected_by="ebitda_margin",
                    attempt=1,
                    action="SELECT_PERIOD_ALIGNED_REVENUE",
                    input_refs=[ebitda.evidence_id, mismatch.evidence_id],
                    output_refs=[current.evidence_id],
                    status=CorrectionStatus.RESOLVED,
                    created_at=correction_timestamp,
                    resolved_at=correction_timestamp,
                )

        margin = await self._execute_calculation(
            task=task,
            capability_id="ebitda_margin",
            inputs={
                "ebitda": ebitda,
                "revenue": current,
                "calculation_id": f"CALC-{task.run_id}-MARGIN",
            },
            context=context,
        )
        await self._commit_calculation(task, margin)
        if correction is not None:
            correction.resolved_at = datetime.now(UTC)
            self._aggregate.artifacts.corrections.append(correction)
            await self._service.event_store.emit(
                run_id=task.run_id,
                task_id=task.task_id,
                event_type=RuntimeEventType.TASK_CORRECTION_RESOLVED,
                payload={"correction_id": correction.correction_id},
            )
        extension_calculations = []
        extension_refs: list[str] = []
        extension_judgments: list[dict[str, object]] = []
        extension_output: dict[str, object] = {}
        for extension in self._service.calculation_extensions:

            async def commit(part):
                async with self._calculation_commit_lock:
                    for calculation in part.calculations:
                        await self._commit_calculation(task, calculation)
                    self._aggregate.artifacts.generated_capability_refs.extend(
                        part.generated_capability_refs
                    )
                    self._aggregate.artifacts.judgments.extend(part.judgments)

            async def publish(outcome):
                async with self._calculation_commit_lock:
                    self._aggregate.artifacts.financial_branches.append(outcome)
                    if outcome.status.value != "NOT_APPLICABLE":
                        publish_output(
                            self._aggregate.runtime.task(task.task_id),
                            outcome.calculation_type,
                            OutputStatus(outcome.status.value),
                            refs=outcome.calculation_ids,
                            reason=outcome.reason_code,
                        )
                    await self._service.repository.save_runtime_events(
                        list(await self._service.event_store.replay(task.run_id))
                    )

            incremental = getattr(extension, "execute_incremental", None)
            if incremental is not None:
                scheme = getattr(self._aggregate, "scheme", None)
                required = getattr(scheme, "calculation_requirements", [])
                result = await incremental(
                    task=task,
                    state=self._aggregate.runtime,
                    evidence=evidence,
                    context=context,
                    commit=commit,
                    publish=publish,
                    requirements={key: BranchRequirement.REQUIRED for key in required},
                )
            else:
                result = await extension.execute(
                    task=task, state=self._aggregate.runtime, evidence=evidence, context=context
                )
                await commit(result)
            for calculation in result.calculations:
                if calculation.run_id != task.run_id or calculation.task_id != task.task_id:
                    raise ValueError("calculation extension returned cross-task lineage")
            extension_calculations.extend(result.calculations)
            extension_refs.extend(result.generated_capability_refs)
            extension_judgments.extend(result.judgments)
            extension_output.update(result.task_output)
        supporting_output = {
            "revenue_growth": str(growth.output_value),
            "ebitda_margin": str(margin.output_value),
            **extension_output,
        }
        calculation_refs = (
            growth.calculation_id,
            margin.calculation_id,
            *(item.calculation_id for item in extension_calculations),
        )
        agent_result = await self._invoke_research_agent(
            task,
            supporting_output=supporting_output,
            additional_input_refs=calculation_refs,
        )
        if agent_result is not None:
            return self._accept_research_agent_output(
                task,
                agent_result,
                supporting_output=supporting_output,
                additional_output_refs=calculation_refs,
            )
        self._aggregate.artifacts.task_outputs[task.task_id] = supporting_output
        return TaskExecutionResult(
            result_ref=f"analysis://{task.task_id}",
            output_refs=calculation_refs,
        )

    async def _observe_wp04(self, task, phase, support, diagnostic, numeric, calculation=None):
        from src.domain.financial_validation import MethodObservation, MethodDenied
        from src.domain.node_binding import task_fingerprint
        admission = node_invocation.get()
        req = task.wp04_method_requirement
        state = getattr(self, '_wp04', {})
        binding = state.get('input_binding')
        b = state.get('B')
        observation = MethodObservation(
            run_id=task.run_id, object_id=req.object_id, task_id=task.task_id,
            owner_id=admission.owner.owner_id, owner_generation=admission.owner.owner_generation,
            task_fingerprint=task_fingerprint(task), requirement_id=req.requirement_id,
            requirement_digest=req.requirement_digest, requirement_state=req.requirement_state,
            descriptor=req.descriptor, descriptor_digest=req.descriptor.descriptor_digest,
            input_binding=binding, input_identity_digest=binding['input_identity_digest'] if binding else None,
            observed_input_refs=[v['evidence_id'] for v in admission.authorized_input_requirements.get('wp04_candidates', [])],
            verification_state='VERIFIED' if binding else 'UNVERIFIED',
            admission_binding_id=admission.admission_binding_id,
            reservation_id=admission.attempt_reservation_id,
            B_ref=b.resolved_input_binding_id if b else None,
            phase=phase, support_status=support, diagnostic_code=diagnostic,
            numeric_outcome=numeric, calculation_ref=calculation.calculation_id if calculation else None,
            source_manifest_digest=req.descriptor.source_manifest_digest,
            semantic_policy_digest=req.descriptor.semantic_policy_digest,
            decimal_policy_digest=req.descriptor.decimal_policy_digest,
            dispatch_count=state.get('dispatch_count', 0), previous_observation_id=state.get('previous'),
            observed_at=datetime.now(UTC),
        ).identified()
        try:
            await self._service.repository.record_method_observation(admission.owner, task.task_id,
                                                                     observation, admission=admission, calculation=calculation)
        except BaseException as exc:
            self._wp04['terminal_observed'] = True
            primary = diagnostic if diagnostic != 'NONE' else getattr(exc, 'code', 'PERSISTENCE_UNAVAILABLE')
            try:
                self._service.wp04_diagnostic_store.retain_method_diagnostic(
                    run_id=task.run_id, task_id=task.task_id, requirement_id=req.requirement_id,
                    diagnostic_code=primary, secondary_diagnostic_code='PERSISTENCE_UNAVAILABLE',
                    observation_id=observation.observation_id)
            except Exception:
                pass
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise MethodDenied(primary, support, 'RESULT_UNKNOWN') from exc
        self._wp04['previous'] = observation.observation_id
        if phase in ('DENIED', 'EXECUTION_FINISHED'):
            self._wp04['terminal_observed'] = True
        return observation

    async def _prepare_wp04(self, task):
        from src.domain.financial_validation import MethodDenied
        self._wp04 = {'dispatch_count': 0}
        req = task.wp04_method_requirement
        try:
            req.verify()
            if req.requirement_state != 'REQUIRED':
                raise MethodDenied('METHOD_SCOPE_UNSUPPORTED', 'UNSUPPORTED')
            capability, receipt = self._service._verify_wp04_load(req.descriptor)
            admission = node_invocation.get()
            prior, current, binding = wp04_bind_inputs(req,
                admission.authorized_input_requirements['wp04_candidates'], self._aggregate.run.as_of)
            self._wp04.update(capability=capability, load_receipt=receipt, input_binding=binding)
            prepared = await self._observe_wp04(task, 'PREPARED', 'SUPPORTED', 'NONE', 'NONE')
            self._wp04['prepared_ref'] = prepared.observation_id
            return prior, current
        except BaseException as exc:
            if getattr(exc, 'code', None) != 'PERSISTENCE_UNAVAILABLE':
                await self._observe_wp04(task, 'DENIED', getattr(exc, 'support', 'UNKNOWN'),
                    getattr(exc, 'code', 'METHOD_PREPARATION_FAILED'), 'NONE')
            raise

    async def _execute_wp04(self, task, inputs, context):
        from decimal import localcontext
        from src.capabilities.financial.growth import capture_revenue_growth_decimal_observation
        from src.domain.financial_validation import (
            MethodDenied, WP04_FLAGS_SCHEMA, WP04_DECIMAL_POLICY,
            wp04_decimal_context, validate_decimal_observation,
        )
        state = self._wp04
        req = task.wp04_method_requirement
        admission = node_invocation.get()
        try:
            capability, receipt = self._service._verify_wp04_load(req.descriptor)
            if capability is not state['capability'] or receipt != state['load_receipt']:
                raise MethodDenied('METHOD_LOAD_IDENTITY_MISMATCH')
            payload = {
                'inputs': canonical_value(inputs), 'context': canonical_value(context),
                'capability': canonical_value(capability.definition), 'formula_id': req.descriptor.formula_id,
                'implementation_hash': next(e['sha256'] for e in req.descriptor.source_manifest
                                            if e['path'] == 'src/capabilities/financial/growth.py'),
                'wp04': {'descriptor': canonical_value(req.descriptor), 'requirement': canonical_value(req),
                    'input_binding': state['input_binding'], 'load_receipt': receipt,
                    'prepared_observation_ref': state['prepared_ref'],
                    'decimal_policy': WP04_DECIMAL_POLICY,
                    'expected_decimal_observation_schema': WP04_FLAGS_SCHEMA, 'expected_capture_count': 1},
            }
            await self._bind_step(task, 'calculation:' + inputs['calculation_id'], payload)
            b = self._bound_steps[-1]
            state['B'] = b
            await self._service.repository.check_invocation(admission)
            if state['dispatch_count']:
                raise MethodDenied('METHOD_REDISPATCH_FORBIDDEN')
            state['dispatch_count'] = 1
            identity = (task.run_id, task.task_id, inputs['calculation_id'],
                        inputs['prior'].evidence_id, inputs['current'].evidence_id,
                        str(inputs['prior'].normalized_value), str(inputs['current'].normalized_value),
                        b.resolved_input_binding_id, admission.attempt_reservation_id)
            with localcontext(wp04_decimal_context()):
                with capture_revenue_growth_decimal_observation(identity) as collector:
                    calculation = await self._service.tool_runtime.execute('revenue_growth', inputs,
                        context, version='1.1.0', wp04_expected=(req.descriptor,
                            self._service.wp04_manifest_sha256, receipt, self._service._wp04_load_expectation))
                    # Original owner/source/result errors precede observation errors.
                    await self._service.repository.check_invocation(admission)
                    self._service._verify_wp04_load(req.descriptor)
                    if (calculation.run_id != task.run_id or calculation.task_id != task.task_id
                            or calculation.calculation_id != inputs['calculation_id']
                            or calculation.input_evidence_ids != state['input_binding']['input_evidence_ids']
                            or calculation.capability_id != 'revenue_growth'
                            or calculation.capability_version != '1.1.0'
                            or calculation.formula_id != 'revenue_growth_v1'
                            or calculation.implementation_hash != payload['implementation_hash']
                            or calculation.code_hash != payload['implementation_hash']
                            or calculation.status.value != 'PASS'
                            or not isinstance(calculation.output_value, Decimal)
                            or not calculation.output_value.is_finite()):
                        raise MethodDenied('METHOD_RESULT_IDENTITY_MISMATCH', 'SUPPORTED', 'FAILED')
                    from src.assurance.independent_financial_review import _snapshot_matches
                    if not _snapshot_matches(calculation, [inputs['prior'], inputs['current']]):
                        raise MethodDenied('METHOD_RESULT_INPUT_MISMATCH', 'SUPPORTED', 'FAILED')
                    actual = collector.seal()
            flags = validate_decimal_observation(actual)
            metadata = {**payload['wp04'], 'A_ref': admission.admission_binding_id,
                        'B_ref': b.resolved_input_binding_id, 'formula_version': '1.0.0',
                        'resulting_decimal_flags': flags, 'decimal_flags_observation': actual,
                        'support_status': 'SUPPORTED', 'dispatch_count': 1}
            return calculation.model_copy(update={'parameters': {**calculation.parameters,
                                                                 'wp04_method_binding': metadata}})
        except BaseException as exc:
            numeric = ('CANCELLED' if isinstance(exc, asyncio.CancelledError) else
                       'TIMED_OUT' if isinstance(exc, TimeoutError) else
                       'FAILED' if state['dispatch_count'] else 'NONE')
            await self._observe_wp04(task, 'EXECUTION_FINISHED' if state['dispatch_count'] else 'DENIED',
                getattr(exc, 'support', 'SUPPORTED'), getattr(exc, 'code', type(exc).__name__), numeric)
            raise

    async def _execute_calculation(
        self,
        *,
        task: Task,
        capability_id: str,
        inputs: dict[str, object],
        context: CapabilityContext,
    ):
        self._require_bound_invocation(task)
        from src.application.execution_profiles import validate_runtime_profile

        profile = validate_runtime_profile(self._service, self._aggregate, task)
        profile.require_tool(capability_id)
        profile.require_method(capability_id + "_v1")
        calculation_id = str(inputs.get("calculation_id", ""))
        if capability_id == 'revenue_growth' and task.wp04_method_requirement is not None:
            return await self._execute_wp04(task, inputs, context)
        version = None
        if self._aggregate.node_binding is not None:
            capability = self._service.capability_registry.get(capability_id)
            version = capability.definition.version
            source = inspect.getsourcefile(type(capability))
            if not source:
                raise BindingDenied("CAPABILITY_UNAVAILABLE", capability_id)
            from src.domain.financial_validation import REVENUE_GROWTH_FORMULA_ID

            await self._bind_step(
                task,
                "calculation:" + calculation_id,
                {
                    "inputs": canonical_value(inputs),
                    "context": canonical_value(context),
                    "capability": canonical_value(capability.definition),
                    "formula_id": REVENUE_GROWTH_FORMULA_ID
                    if capability_id == "revenue_growth"
                    else "ebitda_margin_v1",
                    "implementation_hash": "sha256:"
                    + hashlib.sha256(await asyncio.to_thread(Path(source).read_bytes)).hexdigest(),
                },
            )
        reservation = self._aggregate.node_binding.attempts[task.task_id]
        if reservation.prior_reservation_id is not None:
            prior = [b for b in self._aggregate.node_binding.resolved_inputs.values()
                     if b.reservation_id == reservation.prior_reservation_id
                     and b.step_id == "calculation:" + calculation_id]
            bound = self._bound_steps[-1]
            if len(prior) != 1 or prior[0].payload_snapshot != bound.payload_snapshot:
                raise BindingDenied("STALE_INPUT", "recovery calculation input")
            saved = await self._service.repository.get_calculation(calculation_id)
            if saved is not None:
                return saved
        async with self._service.instrumentation.calculation(
            run_id=task.run_id,
            task_id=task.task_id,
            attributes={
                "calculation_id": calculation_id,
                "capability": capability_id,
            },
        ):
            async with self._service.instrumentation.tool(
                run_id=task.run_id,
                task_id=task.task_id,
                attributes={"tool_name": "native_financial_code", "capability": capability_id},
            ):
                return await self._service.tool_runtime.execute(
                    capability_id,
                    inputs,
                    context,
                    version=version,
                )

    async def _commit_calculation(self, task, calculation):
        self._require_bound_invocation(task)
        if calculation.run_id != task.run_id or calculation.task_id != task.task_id:
            raise ValueError("calculation commit returned cross-task lineage")
        existing = next(
            (
                item
                for item in self._aggregate.artifacts.calculations
                if item.calculation_id == calculation.calculation_id
            ),
            None,
        )
        if existing is not None:
            if existing != calculation:
                raise ValueError("calculation identity is immutable")
            return
        if self._aggregate.node_binding is not None:
            bound = next(
                (
                    item
                    for item in self._bound_steps
                    if item.step_id == "calculation:" + calculation.calculation_id
                ),
                None,
            )
            if bound is None:
                raise BindingDenied("MISSING_INPUT", "calculation step binding")
            expected = bound.payload_snapshot
            if (
                calculation.capability_id,
                calculation.capability_version,
                calculation.formula_id,
                calculation.implementation_hash or calculation.code_hash,
            ) != (
                expected["capability"]["capability_id"],
                expected["capability"]["version"],
                expected["formula_id"],
                expected["implementation_hash"],
            ):
                raise BindingDenied("IDENTITY_MISMATCH", "calculation implementation")
        if task.wp04_method_requirement is not None and calculation.capability_id == 'revenue_growth':
            from src.domain.financial_validation import validate_decimal_observation, MethodDenied
            metadata = calculation.parameters.get('wp04_method_binding', {})
            validate_decimal_observation(metadata.get('decimal_flags_observation'))
            self._service._verify_wp04_load(task.wp04_method_requirement.descriptor)
        try:
            await self._service.repository.save_calculation(calculation)
        except BaseException as exc:
            if task.wp04_method_requirement is not None and calculation.capability_id == 'revenue_growth':
                await self._observe_wp04(task, 'EXECUTION_FINISHED', 'SUPPORTED',
                                         getattr(exc, 'code', 'PERSISTENCE_UNAVAILABLE'), 'RESULT_UNKNOWN')
                if isinstance(exc, BindingDenied):
                    raise
                raise MethodDenied('PERSISTENCE_UNAVAILABLE', 'SUPPORTED', 'RESULT_UNKNOWN') from exc
            raise
        self._aggregate.artifacts.calculations.append(calculation)
        if task.wp04_method_requirement is not None and calculation.capability_id == 'revenue_growth':
            await self._observe_wp04(task, 'EXECUTION_FINISHED', 'SUPPORTED', 'NONE',
                                     'SUCCEEDED', calculation=calculation)
        # Technical MACD has multiple records; branch-level publication owns that
        # compound output. Single native anchors are published only after durable save.
        if calculation.capability_id in {"revenue_growth", "ebitda_margin"}:
            publish_output(
                self._aggregate.runtime.task(task.task_id),
                calculation.capability_id,
                OutputStatus.COMPLETED,
                refs=[calculation.calculation_id],
            )
        await self._service.event_store.emit(
            run_id=task.run_id,
            task_id=task.task_id,
            event_type=RuntimeEventType.CALCULATION_COMPLETED,
            payload={
                "calculation_id": calculation.calculation_id,
                "capability_id": calculation.capability_id,
            },
        )

    async def _execute_risk_analysis(self, task: Task) -> TaskExecutionResult:
        self._require_bound_invocation(task)
        agent_result = await self._invoke_research_agent(
            task,
            supporting_output={"status": "agent_assessment_required"},
        )
        if agent_result is not None:
            execution = self._accept_research_agent_output(
                task,
                agent_result,
                supporting_output={},
            )
            if agent_result.replan_request is not None:
                if self._aggregate.node_binding is not None:
                    raise BindingDenied("UNSUPPORTED_NEW_BOUND_HANDLER", "dynamic follow-up")
                await self._apply_risk_replan(task, agent_result.replan_request)
            return execution

        return await self._execute_deterministic_risk_analysis(task)

    async def _execute_deterministic_risk_analysis(self, task: Task) -> TaskExecutionResult:
        self._require_bound_invocation(task)
        if self._aggregate.node_binding is not None:
            raise BindingDenied(
                "UNSUPPORTED_NEW_BOUND_HANDLER", "deterministic risk requires dynamic follow-up"
            )
        synthesis = next(
            candidate
            for candidate in self._aggregate.runtime.actual_graph.tasks
            if candidate.task_type == "report_synthesis"
        )
        request = ReplanRequest(
            replan_id=f"REPLAN-{task.run_id}-RISK",
            run_id=task.run_id,
            requesting_task_id=task.task_id,
            requested_by=task.assigned_agent,
            reason_code="MATERIAL_RISK_FOLLOW_UP",
            reason_detail="Specialist requests a focused risk follow-up child task.",
            proposed_graph_change={
                "operation": "insert_task_between",
                "add_child_task_type": "risk_follow_up",
                "remove_edge": [task.task_id, synthesis.task_id],
                "add_edges": [
                    [task.task_id, f"{task.run_id}:risk-follow-up"],
                    [f"{task.run_id}:risk-follow-up", synthesis.task_id],
                ],
            },
        )
        specialist_result = SpecialistResult(
            output={"risk_signal": "requires_follow_up"},
            decision=StructuredAgentDecision(
                decision_id=f"DEC-{task.run_id}-RISK",
                run_id=task.run_id,
                task_id=task.task_id,
                decision_type="REQUEST_REPLAN",
                reason_code=request.reason_code,
                summary=request.reason_detail,
                evidence_ids=list(
                    self._aggregate.runtime.task(task.task_id).task_input_evidence_ids
                ),
                requires_review=True,
            ),
            replan_request=request,
        )
        pending = specialist_result.replan_request
        assert pending is not None and pending.decision is ReplanDecision.PENDING
        self._aggregate.artifacts.task_outputs[task.task_id] = specialist_result.output
        await self._apply_risk_replan(task, pending)
        return TaskExecutionResult(result_ref=f"analysis://{task.task_id}")

    async def _apply_risk_replan(self, task: Task, pending: ReplanRequest) -> None:
        synthesis = next(
            candidate
            for candidate in self._aggregate.runtime.actual_graph.tasks
            if candidate.task_type == "report_synthesis"
        )
        if (
            pending.run_id != task.run_id
            or pending.requesting_task_id != task.task_id
            or pending.requested_by != task.assigned_agent
            or pending.decision is not ReplanDecision.PENDING
        ):
            raise ValueError("risk replan request does not close to its authoritative task")
        self._aggregate.artifacts.replans.append(pending)
        async with self._service.instrumentation.replan(
            run_id=task.run_id,
            task_id=task.task_id,
            attributes={"replan_id": pending.replan_id, "reason_code": pending.reason_code},
        ):
            await self._service.event_store.emit(
                run_id=task.run_id,
                task_id=task.task_id,
                event_type=RuntimeEventType.REPLAN_REQUESTED,
                payload={"replan_id": pending.replan_id, "decision": pending.decision.value},
            )
            # Requested and approved remain separate awaited durable events;
            # browser presentation must not impose a minimum runtime dwell.
            decision = ResearchLeadReplanDecider().decide(
                pending,
                outcome=ReplanDecision.APPROVED,
                decision_id=f"DEC-{task.run_id}-REPLAN-APPROVED",
                reason_code="LEAD_APPROVED_FOCUSED_FOLLOW_UP",
                summary="Research Lead approved the bounded child task.",
            )
            child = Task(
                task_id=f"{task.run_id}:risk-follow-up",
                run_id=task.run_id,
                parent_task_id=task.task_id,
                task_type="risk_follow_up",
                goal="Validate the material risk signal as a bounded child task",
                assigned_agent="risk_analyst",
                skill_id="risk_analysis_v1",
                dependencies=[],
                origin=TaskOrigin.REPLAN,
                reason_code=pending.reason_code,
            )
            approved = decision.request.model_copy(update={"created_task_ids": [child.task_id]})
            self._aggregate.artifacts.replans[-1] = approved
            await self._service.event_store.emit(
                run_id=task.run_id,
                task_id=task.task_id,
                event_type=RuntimeEventType.REPLAN_APPROVED,
                payload={
                    "replan_id": pending.replan_id,
                    "decided_by": approved.decided_by,
                },
            )
            await GraphMutationService(
                self._service.event_store, repository=self._service.repository
            ).insert_node_between(
                state=self._aggregate.runtime,
                request=approved,
                task=child,
                predecessor_task_id=task.task_id,
                successor_task_id=synthesis.task_id,
                actor=GraphMutationActor("research_lead", GraphMutationRole.RESEARCH_LEAD),
            )

    async def _execute_peer_analysis(self, task: Task) -> TaskExecutionResult:
        self._require_bound_invocation(task)
        routed_task = self._aggregate.runtime.task(task.task_id)
        input_ids = set(routed_task.task_input_evidence_ids) | set(
            routed_task.task_output_evidence_ids
        )
        evidence = [
            record
            for record in self._aggregate.artifacts.evidence
            if record.evidence_id in input_ids
        ]
        subject = PeerCompanyFacts(
            symbol=str(_evidence_value(evidence, "symbol", "UNKNOWN")),
            industry=_optional_string(_evidence_value(evidence, "industry")),
            sector=_optional_string(_evidence_value(evidence, "sector")),
            market_cap=_optional_decimal(
                _evidence_value(evidence, "provider_reference_market_cap")
            ),
            source_evidence_ids=tuple(
                record.evidence_id
                for record in evidence
                if record.normalized_field
                in {"symbol", "industry", "sector", "provider_reference_market_cap"}
            ),
        )
        selection = PeerSelectionService().select(
            subject=subject,
            stock_peer_evidence=evidence,
            facts_by_symbol={},
            business_relevance={},
            required_metrics=frozenset({"revenue", "ebitda", "provider_reference_pe"}),
        )
        supporting_output = {
            "candidate_source": "fmp.stock_peers",
            "candidates": [item.model_dump(mode="json") for item in selection.candidates],
            "selection_decisions": [item.model_dump(mode="json") for item in selection.decisions],
            "selected_comparables": [
                item.model_dump(mode="json") for item in selection.selected_comparables
            ],
            "status": (
                "selected"
                if selection.selected_comparables
                else "no_selected_comparables_due_missing_enrichment"
            ),
        }
        agent_result = await self._invoke_research_agent(
            task,
            supporting_output=supporting_output,
        )
        if agent_result is not None:
            return self._accept_research_agent_output(
                task,
                agent_result,
                supporting_output=supporting_output,
            )
        self._aggregate.artifacts.task_outputs[task.task_id] = supporting_output
        return TaskExecutionResult(result_ref=f"peer-selection://{task.task_id}")

    async def _execute_risk_follow_up(self, task: Task) -> TaskExecutionResult:
        self._require_bound_invocation(task)
        supporting_output = {
            "finding": (
                "No additional quantified risk can be supported by the available accepted evidence."
            ),
            "limitation": True,
        }
        agent_result = await self._invoke_research_agent(
            task,
            supporting_output=supporting_output,
        )
        if agent_result is not None:
            return self._accept_research_agent_output(
                task,
                agent_result,
                supporting_output=supporting_output,
            )
        self._aggregate.artifacts.task_outputs[task.task_id] = supporting_output
        return TaskExecutionResult(result_ref=f"analysis://{task.task_id}")

    async def _execute_research_news_analysis(self, task: Task) -> TaskExecutionResult:
        self._require_bound_invocation(task)
        """Represent unavailable licensed news as a limitation, never as a success claim."""

        accepted = [
            record
            for record in self._aggregate.artifacts.evidence
            if record.evidence_id
            in self._aggregate.runtime.task(task.task_id).task_input_evidence_ids
            and record.evidence_category in {EvidenceCategory.NEWS, EvidenceCategory.TRANSCRIPT}
        ]
        dependency_statuses = {
            self._aggregate.runtime.task(dependency).evidence_acquisition_status
            for dependency in task.dependencies
        }
        dependency_statuses.add(
            self._aggregate.runtime.task(task.task_id).evidence_acquisition_status
        )
        source_coverage: dict[str, object] = {}
        for dependency in task.dependencies:
            candidate = self._aggregate.runtime.task(dependency).evidence_source_coverage
            if candidate:
                source_coverage.update(candidate)
        source_coverage.update(self._aggregate.runtime.task(task.task_id).evidence_source_coverage)
        source_coverage = {
            key: value for key, value in source_coverage.items() if key in {"news", "transcript"}
        }
        category_by_source = {
            "news": EvidenceCategory.NEWS,
            "transcript": EvidenceCategory.TRANSCRIPT,
        }
        for source, category in category_by_source.items():
            details = source_coverage.setdefault(
                source,
                {
                    "status": "EMPTY",
                    "http_status": 0,
                    "error_code": "NO_ENDPOINT_RESULT",
                    "accepted_count": 0,
                },
            )
            if isinstance(details, dict):
                details["accepted_evidence_ids"] = [
                    record.evidence_id
                    for record in accepted
                    if record.evidence_category is category
                ]
        if accepted and all(
            isinstance(item, dict) and item.get("status") == "AVAILABLE"
            for item in source_coverage.values()
        ):
            status = "completed"
            limitation = False
            reason = None
        elif accepted:
            status = "partial"
            limitation = True
            reason = "PARTIAL_NEWS_TRANSCRIPT_COVERAGE"
        elif EvidenceAcquisitionStatus.ENTITLEMENT_BLOCKED in dependency_statuses:
            status = "entitlement_blocked"
            limitation = True
            reason = "NEWS_TRANSCRIPT_ENTITLEMENT_BLOCKED"
        else:
            status = "insufficient_evidence"
            limitation = True
            reason = "NO_ACCEPTED_NEWS_OR_TRANSCRIPT_EVIDENCE"

        output: dict[str, object] = {
            "status": status,
            "accepted_evidence_ids": [record.evidence_id for record in accepted],
            "limitation": limitation,
            "source_coverage": source_coverage,
        }
        if reason is not None:
            output["reason_code"] = reason
        agent_result = await self._invoke_research_agent(
            task,
            supporting_output=output,
            additional_input_refs=tuple(record.evidence_id for record in accepted),
        )
        if agent_result is not None:
            return self._accept_research_agent_output(
                task,
                agent_result,
                supporting_output=output,
                additional_output_refs=tuple(record.evidence_id for record in accepted),
            )
        self._aggregate.artifacts.task_outputs[task.task_id] = output
        return TaskExecutionResult(
            result_ref=f"research-news://{task.task_id}/{status}",
            output_refs=tuple(record.evidence_id for record in accepted),
        )

    async def _execute_valuation_analysis(self, task: Task) -> TaskExecutionResult:
        self._require_bound_invocation(task)
        supporting_output = {
            "status": "not_quantified_in_current_scope",
            "quantified_valuation_available": False,
        }
        if self._service.valuation_context_enabled:
            from src.agentic.valuation_context import ValuationInteraction, validate_composition
            from src.application.research_context import ContextProjection

            agent = self._research_agent(task)
            route = validate_composition(agent, task)
            projection = ContextProjection(
                self, task, node_invocation.get(), agent._provider.model_name, route
            )
            self._wp03_interaction = ValuationInteraction(agent, projection)
            context = SpecialistExecutionContext(
                task=task,
                accepted_evidence_ids=[
                    m.record_id
                    for m in projection.materials
                    if m.kind == "EVIDENCE" and m.payload_snapshot.get("status") == "ACCEPTED"
                ],
                inputs={"input_refs": [m.record_id for m in projection.materials]},
            )
            agent_result = await self._wp03_interaction.run(context)
            self._append_agent_output(agent_result.agent_output, task)
        else:
            agent_result = await self._invoke_research_agent(
                task, supporting_output=supporting_output
            )

        if agent_result is not None:
            return self._accept_research_agent_output(
                task,
                agent_result,
                supporting_output=supporting_output,
            )
        self._aggregate.artifacts.task_outputs[task.task_id] = supporting_output
        return TaskExecutionResult(result_ref=f"analysis://{task.task_id}")

    async def _execute_report_synthesis(self, task: Task) -> TaskExecutionResult:
        self._require_bound_invocation(task)
        supporting_output = {
            "status": "best_effort_not_released",
            **availability_map(self._aggregate, task),
        }
        agent_result = await self._invoke_research_agent(
            task,
            supporting_output=supporting_output,
        )
        if agent_result is not None:
            required_actors = {output.output_id for output in self._upstream_agent_outputs(task)}
            consumed_actors = {
                output.output_id
                for output in self._upstream_agent_outputs(task)
                if output.output_id in agent_result.agent_output.input_refs
            }
            missing = required_actors - consumed_actors
            if missing:
                raise ValueError(
                    "research synthesis did not consume every available specialist output: "
                    f"{sorted(missing)}"
                )
            return self._accept_research_agent_output(
                task,
                agent_result,
                supporting_output=supporting_output,
            )
        self._aggregate.artifacts.task_outputs[task.task_id] = supporting_output
        return TaskExecutionResult(result_ref=f"analysis://{task.task_id}")

    def _research_agent(self, task):
        from src.agentic.composition import selected_research_agent
        from src.domain.model_selection import selected_model

        if task.run_id != self._aggregate.run.run_id:
            raise ValueError("research Agent dispatch attempted cross-Run execution")
        return selected_research_agent(
            self._service.agent_registry,
            task,
            selected_model(self._aggregate.goal.preferences),
            getattr(self._service, "selected_provider_factory", None),
        )

    async def _invoke_research_agent(
        self,
        task: Task,
        *,
        supporting_output: dict[str, object],
        additional_input_refs: tuple[str, ...] = (),
    ) -> SpecialistResult | None:
        try:
            agent = self._research_agent(task)
        except RegistrationNotFoundError:
            if (
                self._service.agent_registry.registered_ids()
                or "model_selection" in self._aggregate.goal.preferences
            ):
                raise
            return None
        if task.task_type not in agent.supported_task_types:
            raise ValueError(
                f"registered research Agent does not support task type {task.task_type}"
            )
        if task.run_id != self._aggregate.run.run_id:
            raise ValueError("research Agent dispatch attempted cross-Run execution")
        current_task = self._aggregate.runtime.task(task.task_id)
        if current_task.run_id != task.run_id or current_task.assigned_agent != task.assigned_agent:
            raise ValueError("research Agent dispatch does not match authoritative Task identity")

        normalized_evidence = self._normalized_evidence_for_task(task)
        upstream_outputs = self._upstream_agent_outputs(task)
        availability = availability_map(self._aggregate, task)
        recovery_store = self._service.recovery_evidence_store
        recovery_scope = {item["task_id"] for item in availability["output_availability"]}
        recovery_scope.add(task.task_id)
        availability["recovery_evidence"] = [
            {
                key: record.model_dump(mode="json")[key]
                for key in (
                    "record_id",
                    "route",
                    "model",
                    "actual_model",
                    "outcome",
                    "failure_class",
                    "capability_check",
                )
            }
            for record in (await recovery_store.records(task.run_id) if recovery_store else [])
            if record.scope.task_id in recovery_scope
        ]
        input_refs = list(
            dict.fromkeys(
                [
                    self._aggregate.goal.goal_id,
                    self._aggregate.scheme.scheme_id,
                    *(item["evidence_id"] for item in normalized_evidence),
                    *(item.output_id for item in upstream_outputs),
                    *additional_input_refs,
                    *(item["calculation_id"] for item in availability["available_calculations"]),
                    *(
                        ref
                        for item in availability["available_calculations"]
                        for ref in item["input_evidence_ids"]
                    ),
                    *(ref for item in availability["output_availability"] for ref in item["refs"]),
                    *(item["record_id"] for item in availability["recovery_evidence"]),
                ]
            )
        )
        supporting_output = {
            **supporting_output,
            **availability,
            "financial_branch_availability": availability["financial_branches"],
            "availability_rule": (
                "Use only COMPLETED calculations as numeric findings. Do not infer any "
                "numeric result or directional claim for unavailable branches."
                " Never reconstruct failed Agent narratives or absent transcript content. "
                "Every conclusion requires its own accepted evidence/calculation references."
            ),
        }
        context = SpecialistExecutionContext(
            task=task,
            accepted_evidence_ids=[item["evidence_id"] for item in normalized_evidence],
            inputs={
                "research_object_id": self._aggregate.run.research_object_id,
                "goal_id": self._aggregate.goal.goal_id,
                "scheme_id": self._aggregate.scheme.scheme_id,
                "as_of": self._aggregate.run.as_of.isoformat(),
                "research_goal": self._aggregate.goal.goal_text,
                "normalized_evidence": normalized_evidence,
                "deterministic_support": _compact_json_value(
                    _peer_model_support(supporting_output)
                    if task.task_type == "peer_analysis"
                    else supporting_output
                ),
                "upstream_agent_outputs": [
                    {
                        "output_id": output.output_id,
                        "task_id": output.task_id,
                        "actor": output.actor,
                        **output.structured_output.model_dump(mode="json"),
                    }
                    for output in upstream_outputs
                    if output.structured_output is not None
                ],
                "input_refs": input_refs,
            },
        )
        if task.task_type == "risk_follow_up":
            from src.application.risk_follow_up import build_risk_follow_up_context

            context = SpecialistExecutionContext(
                task=task,
                accepted_evidence_ids=current_task.task_input_evidence_ids,
                inputs=build_risk_follow_up_context(self._aggregate, task, normalized_evidence),
            )
        if self._aggregate.node_binding is not None:
            reservation = self._aggregate.node_binding.attempts[task.task_id]
            if reservation.prior_reservation_id is not None:
                prior_steps = [b for b in self._aggregate.node_binding.resolved_inputs.values()
                               if b.reservation_id == reservation.prior_reservation_id
                               and b.step_id == "agent-context"]
                if len(prior_steps) != 1:
                    raise BindingDenied("MISSING_INPUT", "prior exact agent context")
                context = SpecialistExecutionContext.model_validate(
                    prior_steps[0].payload_snapshot["context"]
                )
            source = inspect.getsourcefile(type(agent))
            if not source:
                raise BindingDenied("IDENTITY_MISMATCH", "Agent transform source")
            await self._bind_step(
                task,
                "agent-context",
                {
                    "context": canonical_value(context),
                    "transform_source_hash": "sha256:"
                    + hashlib.sha256(await asyncio.to_thread(Path(source).read_bytes)).hexdigest(),
                },
            )
            context_digest = digest(context)
        try:
            result = await agent.execute(context)
            if self._aggregate.node_binding is not None and digest(context) != context_digest:
                raise BindingDenied("IDENTITY_MISMATCH", "Agent changed input material")
        except ResearchAgentInvocationError as exc:
            self._append_agent_output(exc.record, task)
            publish_output(
                self._aggregate.runtime.task(task.task_id),
                "agent_output",
                OutputStatus.FAILED,
                refs=[exc.record.output_id],
                reason=exc.record.failure_code,
            )
            # Authorization, unknown preflight and storage errors are NOT localized.
            if exc.record.failure_code in {
                "read_timeout",
                "connect_timeout",
                "provider_unavailable",
                "remote_protocol_error",
                "quota_or_rate_limit",
                "retryable_http_failure",
                "overall_deadline_exceeded",
                "invalid_provider_response",
                "semantic_schema_failure",
                "model_identity_mismatch",
            }:
                raise LocalOutputFailure("Recorded model output failure") from exc
            raise
        record = result.agent_output
        if record is None or record.status != "SUCCESS":
            raise ValueError("research Agent did not return a successful output record")
        self._append_agent_output(record, task)
        if result.decision.run_id != task.run_id or result.decision.task_id != task.task_id:
            raise ValueError("research Agent decision does not match authoritative Task identity")
        return result

    def _accept_research_agent_output(
        self,
        task: Task,
        result: SpecialistResult,
        *,
        supporting_output: dict[str, object],
        additional_output_refs: tuple[str, ...] = (),
    ) -> TaskExecutionResult:
        record = result.agent_output
        if record is None or record.run_id != task.run_id or record.task_id != task.task_id:
            raise ValueError("research Agent output does not close to its authoritative Task")
        self._aggregate.artifacts.task_outputs[task.task_id] = {
            **supporting_output,
            **result.output,
        }
        publish_output(
            self._aggregate.runtime.task(task.task_id),
            "agent_output",
            OutputStatus.COMPLETED,
            refs=[record.output_id],
        )
        return TaskExecutionResult(
            result_ref=record.artifact_ref,
            output_refs=tuple(dict.fromkeys([*additional_output_refs, record.output_id])),
        )

    def _append_agent_output(
        self,
        record: ResearchAgentOutputRecord,
        task: Task,
    ) -> None:
        if (
            record.run_id != self._aggregate.run.run_id
            or record.run_id != task.run_id
            or record.task_id != task.task_id
            or record.actor != task.assigned_agent
        ):
            raise ValueError("research Agent output attempted cross-Run or cross-Task persistence")
        if any(
            candidate.output_id == record.output_id
            for candidate in self._aggregate.artifacts.agent_outputs
        ):
            raise ValueError("research Agent output identity must be unique within a Run")
        self._aggregate.artifacts.agent_outputs.append(record)

    def _upstream_agent_outputs(self, task: Task) -> list[ResearchAgentOutputRecord]:
        upstream_task_ids = self._upstream_task_ids(task)
        outputs = [
            output
            for output in self._aggregate.artifacts.agent_outputs
            if output.status == "SUCCESS" and output.task_id in upstream_task_ids
        ]
        foreign = [output.output_id for output in outputs if output.run_id != task.run_id]
        if foreign:
            raise ValueError(f"upstream research Agent outputs crossed Run identity: {foreign}")
        return sorted(outputs, key=lambda output: (output.created_at, output.output_id))

    def _upstream_task_ids(self, task: Task) -> set[str]:
        dependencies_by_id = {
            candidate.task_id: tuple(candidate.dependencies)
            for candidate in self._aggregate.runtime.actual_graph.tasks
        }
        result: set[str] = set()
        pending = list(task.dependencies)
        while pending:
            task_id = pending.pop()
            if task_id in result:
                continue
            result.add(task_id)
            pending.extend(dependencies_by_id.get(task_id, ()))
        return result

    def _normalized_evidence_for_task(self, task: Task) -> list[dict[str, object]]:
        permitted_ids = set(self._aggregate.runtime.task(task.task_id).task_input_evidence_ids)
        permitted_ids.update(self._aggregate.runtime.task(task.task_id).task_output_evidence_ids)
        candidates = [
            record
            for record in self._aggregate.artifacts.evidence
            if record.evidence_id in permitted_ids
        ]
        if any(
            record.run_id != task.run_id
            or record.object_id != self._aggregate.run.research_object_id
            for record in candidates
        ):
            raise ValueError("research Agent evidence crossed Run or Object identity")
        selected = _select_agent_evidence(task.task_type, candidates)
        return [
            {
                "evidence_id": record.evidence_id,
                "provider": record.provider,
                "category": record.evidence_category.value,
                "field": record.normalized_field,
                "value": _compact_json_value(record.normalized_value),
                "unit": record.unit,
                "currency": record.currency,
                "period": record.period,
                "as_of": record.as_of.isoformat(),
                "actuality": record.actuality.value,
            }
            for record in selected
        ]

    async def _execute_generic(self, task: Task) -> TaskExecutionResult:
        self._require_bound_invocation(task)
        input_ids = list(self._aggregate.runtime.task(task.task_id).task_input_evidence_ids)
        self._aggregate.artifacts.task_outputs[task.task_id] = {
            "status": "completed",
            "accepted_evidence_ids": input_ids,
        }
        return TaskExecutionResult(result_ref=f"analysis://{task.task_id}")

    def _require_bound_invocation(self, task):
        if self._aggregate.node_binding is None:
            raise BindingDenied("STATE_REFRESH_REQUIRED", "legacy Executor is read only")
        if self._aggregate.node_binding is not None:
            admission = node_invocation.get()
            if (
                admission is None
                or admission.run_id != task.run_id
                or admission.task_id != task.task_id
            ):
                raise BindingDenied("STATE_REFRESH_REQUIRED", "Executor invocation")

    def admission_requirements(self, task):
        handler = self._handler_for(task).__name__
        supported = {
            "_execute_evidence_collection",
            "_execute_fundamental_analysis",
            "_execute_peer_analysis",
            "_execute_risk_analysis",
            "_execute_risk_follow_up",
            "_execute_research_news_analysis",
            "_execute_valuation_analysis",
            "_execute_report_synthesis",
        }
        if handler not in supported or (
            handler == "_execute_fundamental_analysis" and self._service.calculation_extensions
        ):
            raise BindingDenied("UNSUPPORTED_NEW_BOUND_HANDLER", handler)
        if task.task_type == "risk_follow_up" and (
            not task.parent_task_id or task.parent_task_id not in self._upstream_task_ids(task)
        ):
            raise BindingDenied("IDENTITY_MISMATCH", "initial follow-up parent")
        from src.application.execution_profiles import frozen_profile

        profile = frozen_profile(self._aggregate, task)
        profile.require_method(task.skill_id)
        from src.application.evidence_routing import EvidenceTaskRouter

        scope = EvidenceTaskRouter._acquisition_scope(EvidenceTaskRouter, task)
        return {
            **({'wp04_candidates': wp04_candidate_snapshot(self._aggregate, task)}
               if task.wp04_method_requirement is not None else {}),
            "task": task_semantics(task),
            "scheme": canonical_value(self._aggregate.scheme),
            "resolved_handler": handler,
            "execution_profile_digest": digest(profile, "node-execution-profile/v1"),
            "acquisition_scope": scope.value if scope else None,
            "acquire": self._should_acquire_evidence(task),
        }

    def _bound_materials(self, task):
        current = self._aggregate.runtime.task(task.task_id)
        ids = set(current.task_input_evidence_ids) | set(current.task_output_evidence_ids)
        records = []
        admission = node_invocation.get()
        allowed = {
            record.record_id
            for dep in admission.dependency_result_bindings
            for record in self._aggregate.node_binding.results[dep.result_id].output_records
        }
        allowed.update(record.record_id for record in admission.preexisting_inputs)
        if self._service.valuation_context_enabled and task.task_type == "valuation_analysis":
            ids.update(
                e.evidence_id
                for e in self._aggregate.artifacts.evidence
                if e.evidence_id in allowed
            )
        for evidence in self._aggregate.artifacts.evidence:
            if evidence.evidence_id not in ids:
                continue
            if (
                evidence.run_id != task.run_id
                or evidence.object_id != self._aggregate.run.research_object_id
            ):
                raise BindingDenied("IDENTITY_MISMATCH", evidence.evidence_id)
            if evidence.producer_task_id != task.task_id and evidence.evidence_id not in allowed:
                raise BindingDenied("STALE_INPUT", evidence.evidence_id)
            path = Path(evidence.raw_artifact_ref)
            if not path.is_absolute() or not path.is_file():
                raise BindingDenied("MISSING_INPUT", "raw evidence bytes")
            if hashlib.sha256(path.read_bytes()).hexdigest() != evidence.snapshot_hash.removeprefix(
                "sha256:"
            ):
                raise BindingDenied("IDENTITY_MISMATCH", evidence.evidence_id)
            payload = canonical_value(evidence)
            records.append(
                OutputRecord(
                    kind="EVIDENCE",
                    record_id=evidence.evidence_id,
                    content_digest=digest(payload, "evidence-record/v1"),
                    location=evidence.raw_artifact_ref,
                    record_schema="evidence-record/v1",
                    payload_snapshot=payload,
                )
            )
        if ids != {record.record_id for record in records}:
            raise BindingDenied("MISSING_INPUT", "exact evidence set")
        for calc in self._aggregate.artifacts.calculations:
            if calc.task_id == task.task_id or calc.calculation_id in allowed:
                payload = calculation_core(calc)
                records.append(
                    OutputRecord(
                        kind="CALCULATION_CORE",
                        record_id=calc.calculation_id,
                        content_digest=digest(payload, "calculation-core/v1"),
                        location="calculation_records/" + calc.calculation_id,
                        record_schema="calculation-core/v1",
                        payload_snapshot=payload,
                    )
                )
        for output in self._aggregate.artifacts.agent_outputs:
            if output.task_id == task.task_id or output.output_id in allowed:
                agent = self._service.agent_registry.get(output.actor)
                store = getattr(agent, "_artifacts", None)
                if store is None:
                    raise BindingDenied("MISSING_INPUT", "Agent artifact resolver")
                store.read_verified(output)
                payload = canonical_value(output)
                records.append(
                    OutputRecord(
                        kind="AGENT_OUTPUT",
                        record_id=output.output_id,
                        content_digest=digest(payload, "agent-output-record/v1"),
                        location=str(
                            store.root
                            / "blobs"
                            / "sha256"
                            / output.artifact_sha256.removeprefix("sha256:")
                        ),
                        record_schema="agent-output-record/v1",
                        payload_snapshot=payload,
                    )
                )
        return tuple(records)

    async def _bind_step(self, task, step, payload):
        self._require_bound_invocation(task)
        material = self._bound_materials(task)
        for record in material:
            if record.kind == "EVIDENCE":
                persisted = await self._service.evidence_repository.get(record.record_id)
                if persisted is None or canonical_value(persisted) != record.payload_snapshot:
                    raise BindingDenied("MISSING_INPUT", "evidence original not committed")
        reservation = self._aggregate.node_binding.attempts[task.task_id]
        if reservation.prior_reservation_id is not None and step.startswith("calculation:"):
            prior = [b for b in self._aggregate.node_binding.resolved_inputs.values()
                     if b.reservation_id == reservation.prior_reservation_id and b.step_id == step]
            if len(prior) != 1:
                raise BindingDenied("MISSING_INPUT", "prior calculation binding")
            proposed = canonical_value(payload)
            previous = prior[0].payload_snapshot
            def semantics(value):
                return {**value, **{
                    key: {k: v for k, v in value[key].items()
                          if k not in {"created_at", "updated_at"}}
                    for key in ("context", "capability")
                }}
            if semantics(proposed) != semantics(previous):
                raise BindingDenied("STALE_INPUT", "recovery calculation semantics")
            payload = previous
        binding = await self._service.repository.bind_resolved_inputs(
            node_invocation.get(), step_id=step, materials=material, payload=payload
        )
        self._bound_steps.append(binding)
        return binding

    async def _commit_bound_result(self, task, result):
        if task.wp04_method_requirement is not None:
            self._service._verify_wp04_load(task.wp04_method_requirement.descriptor)
        interaction = getattr(self, "_wp03_interaction", None)
        if interaction is not None:
            await interaction.final_checkpoint()
        admission = node_invocation.get()
        materials = self._bound_materials(task)
        by_id = {item.record_id: item for item in materials}
        for step in self._bound_steps:
            for material in step.material_refs:
                if material.record_id not in by_id or by_id[material.record_id] != material:
                    raise BindingDenied("IDENTITY_MISMATCH", "resolved material changed")
        current = self._aggregate.runtime.task(task.task_id)
        payload = {
            "task_output": canonical_value(
                self._aggregate.artifacts.task_outputs.get(task.task_id, {})
            ),
            "output_outcomes": canonical_value(current.output_outcomes),
            "coverage": canonical_value(current.evidence_source_coverage),
            "admission_binding_id": admission.admission_binding_id,
            "resolved_inputs": [item.resolved_input_binding_id for item in self._bound_steps],
        }
        snapshot_digest = digest(payload, "task-output-snapshot/v1")
        snapshot = OutputRecord(
            kind="TASK_OUTPUT_SNAPSHOT",
            record_id=snapshot_digest,
            content_digest=snapshot_digest,
            location="node_binding.results",
            record_schema="task-output-snapshot/v1",
            payload_snapshot=payload,
        )
        current.result_ref = result.result_ref
        committed = await self._service.repository.commit_node_result(
            admission,
            task=current,
            artifacts=self._aggregate.artifacts,
            output_records=(*materials, snapshot),
            resolved_ids=[item.resolved_input_binding_id for item in self._bound_steps],
            observed={
                **({"wp03_context": interaction.summary()} if interaction else {}),
                "agent_outputs": [
                    canonical_value(item)
                    for item in self._aggregate.artifacts.agent_outputs
                    if item.task_id == task.task_id
                ],
            },
        )
        return replace(result, result_binding_id=committed.result_id)

    def _handler_for(self, task: Task):
        by_skill = {
            "evidence_collection_v1": self._execute_evidence_collection,
            "fundamental_analysis_v1": self._execute_fundamental_analysis,
            "peer_analysis_v1": self._execute_peer_analysis,
            "risk_analysis_v1": self._execute_risk_analysis,
        }
        if task.origin is TaskOrigin.PLAN and task.skill_id in by_skill:
            return by_skill[task.skill_id]
        return getattr(self, f"_execute_{task.task_type}", self._execute_generic)

    def _should_acquire_evidence(self, task: Task) -> bool:
        from src.agentic.runtime_bindings import NATIVE_PLANNING_TASK_TYPES

        if task.task_type in NATIVE_PLANNING_TASK_TYPES:
            return True
        return not self._has_specialized_collection_tasks and task.task_type in {
            "peer_analysis",
            "research_news_analysis",
        }


def _find(records: list, *, field: str, period: str):
    for record in records:
        if record.normalized_field == field and record.period == period:
            return record
    raise LookupError(f"accepted evidence missing: {field}/{period}")


def _select_financial_inputs(records: list):
    revenues = sorted(
        (
            record
            for record in records
            if record.normalized_field == "revenue" and record.period.startswith("FY")
        ),
        key=lambda record: (record.as_of, record.period),
    )
    if len(revenues) < 2:
        raise LookupError("accepted evidence requires two annual revenue periods")
    prior, current = revenues[-2:]
    ebitda = _find(records, field="ebitda", period=current.period)
    mismatch = next(
        (
            record
            for record in records
            if record.normalized_field == "revenue"
            and record.period != current.period
            and record.period.startswith("Q")
        ),
        prior,
    )
    return prior, current, mismatch, ebitda


def decimal_as_float(value: object) -> float:
    return float(Decimal(str(value)))


def _evidence_value(records: list, field: str, default: object = None) -> object:
    return next(
        (record.normalized_value for record in records if record.normalized_field == field),
        default,
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


_COMMON_AGENT_FIELDS = {
    "symbol",
    "company_name",
    "industry",
    "sector",
    "revenue",
    "ebitda",
    "operating_cash_flow",
    "capital_expenditure",
    "provider_reference_free_cash_flow",
    "total_assets",
    "total_debt",
    "total_stockholders_equity",
    "provider_reference_market_cap",
    "price",
}
_AGENT_FIELDS_BY_TASK = {
    "fundamental_analysis": _COMMON_AGENT_FIELDS - {"price"},
    "peer_analysis": {
        "symbol",
        "company_name",
        "industry",
        "sector",
        "provider_reference_market_cap",
        "price",
    },
    "research_news_analysis": set(),
    "valuation_analysis": _COMMON_AGENT_FIELDS
    | {"buy", "hold", "sell", "strong_buy", "strong_sell"},
    "risk_analysis": _COMMON_AGENT_FIELDS | {"buy", "hold", "sell", "strong_buy", "strong_sell"},
    "risk_follow_up": _COMMON_AGENT_FIELDS,
    "report_synthesis": _COMMON_AGENT_FIELDS | {"buy", "hold", "sell", "strong_buy", "strong_sell"},
}
_FIELD_PRIORITY = {
    field: index
    for index, field in enumerate(
        (
            "symbol",
            "company_name",
            "industry",
            "sector",
            "revenue",
            "ebitda",
            "operating_cash_flow",
            "capital_expenditure",
            "provider_reference_free_cash_flow",
            "total_assets",
            "total_debt",
            "total_stockholders_equity",
            "provider_reference_market_cap",
            "price",
            "strong_buy",
            "buy",
            "hold",
            "sell",
            "strong_sell",
        )
    )
}


def _select_agent_evidence(task_type: str, records: list) -> list:
    """Return a bounded, task-relevant normalized evidence slice for an Agent."""

    allowed = _AGENT_FIELDS_BY_TASK.get(task_type, _COMMON_AGENT_FIELDS)
    if task_type == "research_news_analysis":
        relevant = [
            record
            for record in records
            if record.evidence_category in {EvidenceCategory.NEWS, EvidenceCategory.TRANSCRIPT}
        ]
    else:
        relevant = [
            record
            for record in records
            if record.normalized_field in allowed
            or (task_type == "peer_analysis" and record.normalized_field.startswith("peer_symbol_"))
        ]
    relevant.sort(
        key=lambda record: (
            _FIELD_PRIORITY.get(
                record.normalized_field,
                100 if record.normalized_field.startswith("peer_symbol_") else 200,
            ),
            -record.as_of.toordinal(),
            record.period,
            record.evidence_id,
        )
    )
    selected: list = []
    counts: dict[str, int] = {}
    for record in relevant:
        field = record.normalized_field
        maximum = 9 if field.startswith("peer_symbol_") else 5
        if counts.get(field, 0) >= maximum:
            continue
        counts[field] = counts.get(field, 0) + 1
        selected.append(record)
        if len(selected) == 40:
            break
    return selected


def _peer_model_support(support: dict[str, object]) -> dict[str, object]:
    """Exclude assembly-clock metadata only from the Peer model projection.

    PeerCandidate/PeerSelectionDecision created_at records object construction,
    not an evidence observation date. Preserve original domain/task artifacts and
    all business fields; never strip timestamps from evidence or other inputs.
    """
    return {
        key: [
            {field: value for field, value in item.items() if field != "created_at"}
            for item in rows
        ]
        if key in {"candidates", "selection_decisions", "selected_comparables"}
        and isinstance(rows, list)
        and all(isinstance(item, dict) for item in rows)
        else rows
        for key, rows in support.items()
    }


def _compact_json_value(value: Any, *, depth: int = 0) -> Any:
    """Normalize bounded provider inputs without carrying raw artifacts or payloads."""

    # C-03: retain semantic fields and their paths, not the whole enclosing
    # context. Unrelated narrative still follows the original clipping contract.
    from src.application.semantic_context import (
        check_semantic_bound,
        contains_semantics,
        normalize_semantics,
        semantic_key,
    )

    if depth > 4 and not contains_semantics(value):
        return "[bounded]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, str):
        return value if len(value) <= 1000 else f"{value[:997]}..."
    if isinstance(value, dict):
        result = {
            str(key): normalize_semantics(item)
            if semantic_key(key)
            else _compact_json_value(item, depth=depth + 1)
            for index, (key, item) in enumerate(
                sorted(value.items(), key=lambda pair: str(pair[0]))
            )
            if index < 30 or semantic_key(key) or contains_semantics(item)
        }
        if any(semantic_key(key) for key in value):
            check_semantic_bound(result)
        return result
    if isinstance(value, (list, tuple)):
        return [
            _compact_json_value(item, depth=depth + 1)
            for index, item in enumerate(value)
            if index < 30 or contains_semantics(item)
        ]
    return _compact_json_value(str(value), depth=depth + 1)


def wp04_candidate_snapshot(aggregate, task):
    """A's exact authorized preexisting/dependency candidates, never latest lookup."""
    allowed = set(task.task_input_evidence_ids)
    pending = list(task.dependencies)
    seen = set()
    while pending:
        key = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        pending.extend(aggregate.runtime.task(key).dependencies)
        result = aggregate.node_binding.results.get(aggregate.node_binding.current_results.get(key))
        if result is not None:
            allowed.update(r.record_id for r in result.output_records if r.kind == 'EVIDENCE')
    candidates = [record for record in aggregate.artifacts.evidence
                  if record.evidence_id in allowed and record.normalized_field == 'revenue']
    return [{'evidence_id': r.evidence_id, 'content_digest': digest(r, 'evidence-record/v1'),
             'snapshot': canonical_value(r)} for r in sorted(candidates, key=lambda r: r.evidence_id)]


def wp04_bind_inputs(requirement, candidates, run_as_of):
    """C2 exact role selection and retained raw scale witness, without arithmetic rounding."""
    import json
    import re
    from src.domain.evidence import EvidenceRecord
    from src.domain.financial_validation import MethodDenied, wp04_decimal
    records = []
    for item in candidates:
        snapshot = item['snapshot']
        if (digest(snapshot, 'evidence-record/v1') != item['content_digest']
                or snapshot.get('evidence_id') != item['evidence_id']):
            raise MethodDenied('INPUT_IDENTITY_MISMATCH')
        # Do not let EvidenceRecord's legacy post-init fill missing WP04 semantics.
        if not snapshot.get('period_basis'):
            raise MethodDenied('SEMANTIC_INPUT_MISMATCH', 'UNSUPPORTED')
        if snapshot['period_basis'] == 'FY':
            required = ('statement_series', 'currency', 'unit', 'period', 'as_of',
                        'normalized_field', 'object_id', 'run_id', 'raw_artifact_ref', 'snapshot_hash')
            if (snapshot.get('actuality') not in ('ACTUAL', 'ESTIMATE')
                    or any(not isinstance(snapshot.get(k), str) or not snapshot[k].strip()
                           for k in required)):
                raise MethodDenied('SEMANTIC_INPUT_MISMATCH', 'UNSUPPORTED')
            wp04_decimal(snapshot.get('normalized_value'))
        try:
            record = EvidenceRecord.model_validate(snapshot)
        except ValueError as exc:
            raise MethodDenied('SEMANTIC_INPUT_MISMATCH', 'UNSUPPORTED') from exc
        if (canonical_value(record) != snapshot
                or digest(record, 'evidence-record/v1') != item['content_digest']):
            raise MethodDenied('SEMANTIC_INPUT_MISMATCH', 'UNSUPPORTED')
        records.append(record)
    annual = [r for r in records if r.period_basis and r.period_basis.value == 'FY']
    # No latest-like tie breaker: even two viable adjacent pairs are ambiguous.
    pairs = [(p, c) for p in annual for c in annual
             if re.fullmatch(r'FY[0-9]{4}', p.period) and re.fullmatch(r'FY[0-9]{4}', c.period)
             and int(c.period[2:]) - int(p.period[2:]) == 1]
    if len(annual) < 2:
        raise MethodDenied('MISSING_REQUIRED_INPUT', 'MISSING_INPUT')
    if len(pairs) != 1:
        raise MethodDenied('SEMANTIC_INPUT_MISMATCH', 'UNSUPPORTED')
    prior, current = pairs[0]
    witnesses = []
    for record in (prior, current):
        value = wp04_decimal(record.normalized_value)
        if (record.run_id != requirement.run_id or record.object_id != requirement.object_id
                or record.status.value != 'ACCEPTED' or record.unit != 'CURRENCY'
                or record.actuality.value not in ('ACTUAL', 'ESTIMATE')
                or not record.statement_series or not record.statement_series.strip()
                or not record.currency or not re.fullmatch('[A-Z]{3}', record.currency)
                or record.as_of > run_as_of):
            raise MethodDenied('SEMANTIC_INPUT_MISMATCH', 'UNSUPPORTED')
        try:
            path = Path(record.raw_artifact_ref)
            if not path.is_absolute():
                raise ValueError('retained raw path must be absolute')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != record.snapshot_hash.removeprefix('sha256:'):
                raise ValueError('raw hash differs')
            payload = json.loads(raw, parse_float=Decimal, parse_int=Decimal)
            rows = payload['records']
            if not isinstance(rows, list):
                raise ValueError('unknown raw shape')
            matches = []
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    raise ValueError('unknown raw record')
                currency = row.get('currency', payload.get('object', {}).get('currency'))
                if (row.get('field'), row.get('period'), row.get('as_of'), currency) != (
                        record.normalized_field, record.period, record.as_of.isoformat(), record.currency):
                    continue
                unit = row.get('unit')
                scales = {currency: 0, currency + '_THOUSAND': 3,
                          currency + '_MILLION': 6, currency + '_BILLION': 9}
                if unit not in scales:
                    raise ValueError('unknown scale')
                raw_value = wp04_decimal(row.get('value'))
                t = raw_value.as_tuple()
                normalized = Decimal((t.sign, t.digits, t.exponent + scales[unit]))
                if normalized == value:
                    matches.append({'raw_sha256': record.snapshot_hash,
                                    'raw_artifact_ref': str(path), 'pointer': '/records/' + str(index),
                                    'raw_value': str(raw_value), 'raw_unit': unit,
                                    'original_scale': 10 ** scales[unit], 'normalized_scale': 1})
            if len(matches) != 1:
                raise ValueError('nonunique retained witness')
            witnesses.append(matches[0])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise MethodDenied('SEMANTIC_INPUT_MISMATCH', 'UNSUPPORTED') from exc
    if (prior.evidence_id == current.evidence_id or prior.currency != current.currency
            or prior.actuality != current.actuality or prior.statement_series != current.statement_series
            or witnesses[0]['original_scale'] != witnesses[1]['original_scale']):
        raise MethodDenied('SEMANTIC_INPUT_MISMATCH', 'UNSUPPORTED')
    if wp04_decimal(prior.normalized_value) <= 0:
        raise MethodDenied('NOT_APPLICABLE_PRECONDITION', 'NOT_APPLICABLE')
    binding = {'schema_version': 'wp04-input-binding/v1',
               'object_id': requirement.object_id, 'run_id': requirement.run_id,
               'task_id': requirement.task_id, 'requirement_digest': requirement.requirement_digest,
               'input_evidence_ids': [prior.evidence_id, current.evidence_id],
               'evidence_digests': [next(v['content_digest'] for v in candidates
                                         if v['evidence_id'] == r.evidence_id) for r in (prior, current)],
               'raw_witnesses': witnesses, 'semantics': [{
                   'period': r.period, 'period_basis': r.period_basis.value,
                   'actuality': r.actuality.value, 'statement_series': r.statement_series,
                   'statement_cohort': r.statement_cohort, 'as_of': r.as_of.isoformat(),
                   'currency': r.currency, 'unit': r.unit, 'normalized_value': str(r.normalized_value),
               } for r in (prior, current)],
               'semantic_policy_digest': requirement.descriptor.semantic_policy_digest}
    binding['input_identity_digest'] = digest(binding, binding['schema_version'])
    return prior, current, binding
