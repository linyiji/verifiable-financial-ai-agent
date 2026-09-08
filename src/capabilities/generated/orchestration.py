from __future__ import annotations

import asyncio
from platform import python_version
from uuid import uuid4

from src.adapters.llm.provider import LLMFailureClassification, LLMProviderError
from src.capabilities.generated.builder import CodeBuilderModelIdentityError
from src.capabilities.generated.builder import (
    GeneratedCapabilityDeadlineExceededError as BuilderDeadline,
)
from src.capabilities.generated.contract import GeneratedCapabilityBundleValidationError
from src.capabilities.generated.models import (
    CapabilityBuildRequest,
    CapabilityOrchestrationResult,
    GeneratedCapabilityCandidate,
    ResearchLeadCapabilityApproval,
    SpecialistCapabilityRequest,
)
from src.capabilities.generated.ports import (
    CapabilityValidationProgressPort,
    CapabilityWorkflowRecorder,
    CodeBuilder,
    GeneratedCapabilityValidationPort,
    NoopCapabilityWorkflowRecorder,
    ResearchLeadCapabilityAuthority,
    ScopedCapabilityRegistryPort,
)
from src.capabilities.generated.spec import GeneratedCapabilitySpecValidationError
from src.capabilities.generated.telemetry import GeneratedCapabilityTrace
from src.capabilities.generated.validation import GeneratedCapabilityValidationError
from src.domain.capability import (
    Capability,
    CapabilityBuildRecord,
    CapabilityGapRecord,
    GeneratedCapabilityRecord,
    ScopedCapabilityRegistration,
)
from src.domain.enums import CapabilityLifecycle, CapabilityScope, TaskStatus
from src.domain.runtime_event import RuntimeEventType
from src.domain.task import Task
from src.runtime.diagnostics import task_failure_diagnostic
from src.runtime.events import RuntimeEventStore
from src.runtime.state import RuntimeState
from src.tooling.generated_sandbox import SandboxEnvironmentUnavailableError


class CapabilityBuildFailedError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        gap: CapabilityGapRecord,
        build_records: tuple[CapabilityBuildRecord, ...],
        failure_stage: str | None = None,
        diagnostic_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.gap = gap
        self.build_records = build_records
        self.failure_stage = failure_stage
        self.diagnostic_id = diagnostic_id


class CapabilityAuthorityError(ValueError):
    pass


class CapabilityGenerationUnavailableError(CapabilityBuildFailedError):
    """Classified generation/validation rejection, scoped to its financial output."""


def local_build_failure(error, stage):
    if stage == "generation":
        if isinstance(error, (GeneratedCapabilityDeadlineExceededError, BuilderDeadline)):
            return True
        if isinstance(error, GeneratedCapabilitySpecValidationError):
            return True
        if isinstance(error, GeneratedCapabilityBundleValidationError):
            return bool(error.codes) and all(
                not code.startswith("GC_SECURITY") for code in error.codes
            )
        return isinstance(error, LLMProviderError) and error.failure_classification in {
            LLMFailureClassification.PROVIDER_UNAVAILABLE,
            LLMFailureClassification.CONNECT_TIMEOUT,
            LLMFailureClassification.READ_TIMEOUT,
            LLMFailureClassification.OVERALL_DEADLINE_EXCEEDED,
            LLMFailureClassification.REMOTE_PROTOCOL_ERROR,
            LLMFailureClassification.RETRYABLE_HTTP_FAILURE,
            LLMFailureClassification.SEMANTIC_SCHEMA_FAILURE,
            LLMFailureClassification.INVALID_PROVIDER_RESPONSE,
        }
    return (
        stage == "validation"
        and isinstance(error, GeneratedCapabilityValidationError)
        and error.stage
        in {
            "syntax_compile",
            "unit_tests",
            "edge_cases",
            "deterministic_double_run",
            "financial_validation",
            "financial_invariants",
            "output_schema",
            "unit_validation",
        }
    )


class GeneratedCapabilityDeadlineExceededError(RuntimeError):
    """Secret-safe owned deadline failure for Generated Capability construction."""

    failure_classification = "overall_deadline_exceeded"
    retryable = True


class GeneratedCapabilityOrchestrator:
    """Coordinate a registry miss without adding a Research Task to the graph."""

    def __init__(
        self,
        *,
        registry: ScopedCapabilityRegistryPort,
        research_lead: ResearchLeadCapabilityAuthority,
        code_builder: CodeBuilder,
        validator: GeneratedCapabilityValidationPort,
        event_store: RuntimeEventStore,
        recorder: CapabilityWorkflowRecorder | None = None,
        trace: GeneratedCapabilityTrace | None = None,
        max_attempts: int = 2,
        overall_generation_deadline_seconds: float | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        inferred_policy = getattr(code_builder, "execution_policy", None)
        inferred_deadline = getattr(inferred_policy, "overall_workload_deadline_seconds", None)
        deadline = (
            overall_generation_deadline_seconds
            if overall_generation_deadline_seconds is not None
            else inferred_deadline
        )
        if deadline is not None and (
            not isinstance(deadline, (int, float)) or isinstance(deadline, bool) or deadline <= 0
        ):
            raise ValueError("overall generation deadline must be positive")
        self._registry = registry
        self._research_lead = research_lead
        self._code_builder = code_builder
        self._validator = validator
        self._event_store = event_store
        self._recorder = recorder or NoopCapabilityWorkflowRecorder()
        self._trace = trace or GeneratedCapabilityTrace()
        self._max_attempts = min(
            max_attempts, getattr(code_builder, "max_build_attempts", max_attempts)
        )
        self._overall_generation_deadline_seconds = (
            float(deadline) if deadline is not None else None
        )

    async def lookup_or_build(
        self,
        *,
        state: RuntimeState,
        request: SpecialistCapabilityRequest,
    ) -> Capability | CapabilityOrchestrationResult:
        """Return an existing capability or build, validate, scope, and resume the same task."""

        task = _validate_request(state, request)
        if request.requested_by == self._research_lead.lead_agent_id:
            raise CapabilityAuthorityError(
                "Research Lead identity cannot be used as the Specialist requester"
            )
        existing = await self._registry.lookup(
            request.requirement.capability_id,
            version=None,
            run_id=request.run_id,
            task_id=request.task_id,
        )
        if existing is not None:
            return existing

        gap = CapabilityGapRecord(
            gap_id=f"GAP-{uuid4()}",
            run_id=request.run_id,
            task_id=request.task_id,
            requirement=request.requirement,
            requested_by=request.requested_by,
            detail="Capability Registry lookup returned NOT FOUND.",
        )
        task.status = TaskStatus.WAITING_FOR_CAPABILITY
        await self._recorder.record_gap(gap)
        await self._emit(
            RuntimeEventType.CAPABILITY_GAP_DETECTED,
            request=request,
            payload={
                "gap_id": gap.gap_id,
                "capability_id": request.requirement.capability_id,
                "skill_id": request.skill_id,
                "requested_by": request.requested_by,
            },
        )
        await self._emit(
            RuntimeEventType.TASK_WAITING_FOR_CAPABILITY,
            request=request,
            payload={"gap_id": gap.gap_id},
        )

        spec_approval = await self._research_lead.approve_spec(gap)
        try:
            _require_approval(spec_approval, gap=gap, phase="SPEC", authority=self._research_lead)
        except CapabilityAuthorityError as exc:
            task.status = TaskStatus.CAPABILITY_BUILD_FAILED
            await self._fail_without_build(request=request, gap=gap, error=exc)
            raise CapabilityBuildFailedError(
                "Research Lead did not approve capability build",
                gap=gap,
                build_records=(),
            ) from exc

        builds: list[CapabilityBuildRecord] = []
        last_error: Exception | None = None
        last_diagnostic = None
        generation_deadline_at = (
            asyncio.get_running_loop().time() + self._overall_generation_deadline_seconds
            if self._overall_generation_deadline_seconds is not None
            else None
        )
        for attempt in range(1, self._max_attempts + 1):
            generated: GeneratedCapabilityRecord | None = None
            artifact_retention = None
            build = CapabilityBuildRecord(
                build_id=f"BUILD-{uuid4()}",
                gap_id=gap.gap_id,
                run_id=request.run_id,
                task_id=request.task_id,
                requested_by=request.requested_by,
                approved_by=spec_approval.approved_by,
                attempt=attempt,
                max_attempts=self._max_attempts,
                lifecycle=CapabilityLifecycle.SPEC_APPROVED,
            )
            builds.append(build)
            await self._recorder.record_build(build)
            await self._emit(
                RuntimeEventType.CAPABILITY_BUILD_REQUESTED,
                request=request,
                payload={
                    "gap_id": gap.gap_id,
                    "build_id": build.build_id,
                    "attempt": attempt,
                    "max_attempts": self._max_attempts,
                    "approved_by": spec_approval.approved_by,
                },
            )
            await self._emit(
                RuntimeEventType.CAPABILITY_BUILD_STARTED,
                request=request,
                payload={"build_id": build.build_id, "attempt": attempt},
            )
            build_request = CapabilityBuildRequest(
                build_id=build.build_id,
                gap=gap,
                approval=spec_approval,
                attempt=attempt,
                max_attempts=self._max_attempts,
            )
            try:
                failure_stage = "generation"
                if generation_deadline_at is None:
                    candidate = await self._code_builder.generate(build_request)
                else:
                    remaining = generation_deadline_at - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise GeneratedCapabilityDeadlineExceededError(
                            "Generated Capability exceeded its owned overall deadline"
                        )
                    try:
                        async with asyncio.timeout(remaining):
                            candidate = await self._code_builder.generate(build_request)
                    except TimeoutError:
                        raise GeneratedCapabilityDeadlineExceededError(
                            "Generated Capability exceeded its owned overall deadline"
                        ) from None
                generated = _generated_record(request, gap, candidate)
                build = build.model_copy(
                    update={
                        "requested_model": candidate.requested_model,
                        "actual_model": candidate.actual_model,
                        "provider": candidate.provider,
                        "lifecycle": CapabilityLifecycle.GENERATED,
                        "generated_capability_ref": generated.generated_capability_id,
                    }
                )
                builds[-1] = build
                await self._recorder.record_build(build)
                await self._recorder.record_generated(generated)
                await self._emit(
                    RuntimeEventType.CAPABILITY_GENERATED,
                    request=request,
                    payload={
                        "build_id": build.build_id,
                        "generated_capability_id": generated.generated_capability_id,
                        "implementation_hash": generated.implementation_hash,
                        "provider": candidate.provider,
                        "requested_model": candidate.requested_model,
                        "actual_model": candidate.actual_model,
                        "input_tokens": candidate.input_tokens,
                        "output_tokens": candidate.output_tokens,
                        "latency_ms": candidate.latency_ms,
                    },
                )
                progress = _ValidationProgress(
                    event_store=self._event_store,
                    trace=self._trace,
                    request=request,
                    build_id=build.build_id,
                )
                failure_stage = "validation"
                handoff = await self._validator.validate(candidate, progress=progress)
                handoff.assert_ready_for_task_approval(candidate)
                progress.assert_complete()
                generated = generated.model_copy(
                    update={
                        "lifecycle": CapabilityLifecycle.FINANCIAL_VALIDATED,
                        "runtime_version": handoff.sandbox_execution.runtime_version,
                    }
                )
                build = build.model_copy(
                    update={"lifecycle": CapabilityLifecycle.FINANCIAL_VALIDATED}
                )
                builds[-1] = build
                failure_stage = "artifact_retention"
                artifact_retention = await self._recorder.retain_generated_artifacts(
                    generated=generated,
                    candidate=candidate,
                    sandbox_execution=handoff.sandbox_execution,
                )
                await self._recorder.record_build(build)
                await self._recorder.record_generated(generated)
                await self._recorder.record_validation(
                    handoff.validation, handoff.sandbox_execution
                )
                failure_stage = "activation_approval"
                activation = await self._research_lead.approve_activation(
                    gap, generated, handoff.validation
                )
                _require_approval(
                    activation,
                    gap=gap,
                    phase="ACTIVATION",
                    authority=self._research_lead,
                )
                generated = generated.model_copy(
                    update={"lifecycle": CapabilityLifecycle.TASK_APPROVED}
                )
                build = build.model_copy(update={"lifecycle": CapabilityLifecycle.TASK_APPROVED})
                builds[-1] = build
                await self._recorder.record_build(build)
                await self._recorder.record_generated(generated)
                registration = ScopedCapabilityRegistration(
                    registration_id=f"REG-{uuid4()}",
                    generated_capability_ref=generated.generated_capability_id,
                    capability_id=generated.capability_id,
                    capability_version=generated.capability_version,
                    scope=request.scope,
                    run_id=request.run_id,
                    task_id=(request.task_id if request.scope is CapabilityScope.TASK else None),
                    approved_by=activation.approved_by,
                    lifecycle=CapabilityLifecycle.TASK_APPROVED,
                )
                await self._emit(
                    RuntimeEventType.CAPABILITY_APPROVED,
                    request=request,
                    payload={
                        "build_id": build.build_id,
                        "registration_id": registration.registration_id,
                        "approved_by": activation.approved_by,
                        "scope": registration.scope.value,
                    },
                )
                failure_stage = "registration"
                active = await self._registry.register(registration, handoff.capability)
                _require_active_registration(active, request=request, generated=generated)
                generated = generated.model_copy(
                    update={"lifecycle": CapabilityLifecycle.ACTIVE_FOR_SCOPE}
                )
                build = build.model_copy(update={"lifecycle": CapabilityLifecycle.ACTIVE_FOR_SCOPE})
                builds[-1] = build
                await self._recorder.record_build(build)
                await self._recorder.record_generated(generated)
                await self._recorder.record_registration(active)
                await self._emit(
                    RuntimeEventType.CAPABILITY_REGISTERED,
                    request=request,
                    payload={
                        "registration_id": active.registration_id,
                        "capability_id": active.capability_id,
                        "capability_version": active.capability_version,
                        "scope": active.scope.value,
                    },
                )
                resolved = await self._registry.lookup(
                    active.capability_id,
                    version=active.capability_version,
                    run_id=request.run_id,
                    task_id=request.task_id,
                )
                if resolved is None:
                    raise ValueError("scoped registration is not visible to the original task")
                task.status = TaskStatus.READY
                task.status = TaskStatus.RUNNING
                await self._emit(
                    RuntimeEventType.TASK_RESUMED,
                    request=request,
                    payload={
                        "gap_id": gap.gap_id,
                        "registration_id": active.registration_id,
                        "status": TaskStatus.RUNNING.value,
                    },
                )
                return CapabilityOrchestrationResult(
                    gap=gap,
                    build_records=tuple(builds),
                    generated=generated,
                    artifact_retention=artifact_retention,
                    validation=handoff.validation,
                    sandbox_execution=handoff.sandbox_execution,
                    registration=active,
                    capability=resolved,
                )
            except SandboxEnvironmentUnavailableError:
                # Preserve generated/validated state. No code regeneration and no
                # assertion that the formula failed: the sandbox did not start.
                task.status = TaskStatus.RUNNING
                await self._emit(
                    RuntimeEventType.TASK_PROGRESS,
                    request=request,
                    payload={"progress": task.progress, "message_code": "BLOCKED_BY_RUNTIME"},
                )
                raise
            except Exception as exc:
                last_error = exc
                last_diagnostic = task_failure_diagnostic(exc, task=task, attempt=attempt)
                if (
                    generated is not None
                    and generated.lifecycle is not CapabilityLifecycle.ACTIVE_FOR_SCOPE
                ):
                    generated = generated.model_copy(
                        update={"lifecycle": CapabilityLifecycle.BUILD_FAILED}
                    )
                    await self._recorder.record_generated(generated)
                if failure_stage == "validation":
                    await self._emit(
                        RuntimeEventType.CAPABILITY_TEST_FAILED,
                        request=request,
                        payload={
                            "build_id": build.build_id,
                            "attempt": attempt,
                            "error_type": type(exc).__name__,
                        },
                    )
                failed_build = build.model_copy(
                    update={
                        "lifecycle": CapabilityLifecycle.BUILD_FAILED,
                        "error_code": type(exc).__name__,
                        "error_detail": f"Generated capability failed during {failure_stage}.",
                    }
                )
                builds[-1] = failed_build
                await self._recorder.record_build(failed_build)
                await self._emit(
                    RuntimeEventType.CAPABILITY_BUILD_FAILED,
                    request=request,
                    payload={
                        "build_id": build.build_id,
                        "attempt": attempt,
                        "max_attempts": self._max_attempts,
                        "error_type": type(exc).__name__,
                        "terminal": (
                            attempt == self._max_attempts
                            or isinstance(
                                exc, (GeneratedCapabilityDeadlineExceededError, BuilderDeadline)
                            )
                            or isinstance(exc, CodeBuilderModelIdentityError)
                            or not local_build_failure(exc, failure_stage)
                        ),
                        "internal_diagnostic": last_diagnostic,
                    },
                )
                if isinstance(
                    exc,
                    (
                        GeneratedCapabilityDeadlineExceededError,
                        BuilderDeadline,
                        CodeBuilderModelIdentityError,
                    ),
                ) or not local_build_failure(exc, failure_stage):
                    break

        task.status = TaskStatus.CAPABILITY_BUILD_FAILED
        local_generation_failure = local_build_failure(last_error, failure_stage)
        error_type = (
            CapabilityGenerationUnavailableError
            if local_generation_failure
            else CapabilityBuildFailedError
        )
        raise error_type(
            f"capability build failed after {len(builds)} attempt(s): "
            f"{type(last_error).__name__ if last_error else 'unknown'}",
            gap=gap,
            build_records=tuple(builds),
            failure_stage=failure_stage,
            diagnostic_id=last_diagnostic["diagnostic_id"] if last_diagnostic else None,
        ) from last_error

    async def _fail_without_build(
        self,
        *,
        request: SpecialistCapabilityRequest,
        gap: CapabilityGapRecord,
        error: Exception,
    ) -> None:
        await self._emit(
            RuntimeEventType.CAPABILITY_BUILD_FAILED,
            request=request,
            payload={
                "gap_id": gap.gap_id,
                "error_type": type(error).__name__,
                "terminal": True,
            },
        )

    async def _emit(
        self,
        event_type: RuntimeEventType,
        *,
        request: SpecialistCapabilityRequest,
        payload: dict[str, object],
    ) -> None:
        await self._event_store.emit(
            run_id=request.run_id,
            task_id=request.task_id,
            event_type=event_type,
            payload=payload,
        )
        await self._trace.event(
            event_type.value,
            run_id=request.run_id,
            task_id=request.task_id,
            attributes=payload,
        )


class _ValidationProgress(CapabilityValidationProgressPort):
    _STAGES = ("static", "sandbox", "tests", "financial")

    def __init__(
        self,
        *,
        event_store: RuntimeEventStore,
        trace: GeneratedCapabilityTrace,
        request: SpecialistCapabilityRequest,
        build_id: str,
    ) -> None:
        self._event_store = event_store
        self._trace = trace
        self._request = request
        self._build_id = build_id
        self._completed: list[str] = []

    async def static_validated(self, implementation_hash: str) -> None:
        await self._advance(
            "static", RuntimeEventType.CAPABILITY_STATIC_VALIDATED, implementation_hash
        )

    async def sandbox_started(self, implementation_hash: str) -> None:
        await self._advance(
            "sandbox", RuntimeEventType.CAPABILITY_SANDBOX_STARTED, implementation_hash
        )

    async def tests_passed(self, implementation_hash: str) -> None:
        await self._advance("tests", RuntimeEventType.CAPABILITY_TEST_PASSED, implementation_hash)

    async def financial_validated(self, implementation_hash: str) -> None:
        await self._advance(
            "financial", RuntimeEventType.CAPABILITY_FINANCIAL_VALIDATED, implementation_hash
        )

    async def _advance(
        self,
        stage: str,
        event_type: RuntimeEventType,
        implementation_hash: str,
    ) -> None:
        expected = self._STAGES[len(self._completed)] if len(self._completed) < 4 else None
        if stage != expected:
            raise ValueError(f"validation progress out of order: expected {expected}, got {stage}")
        payload = {
            "build_id": self._build_id,
            "implementation_hash": implementation_hash,
        }
        await self._event_store.emit(
            run_id=self._request.run_id,
            task_id=self._request.task_id,
            event_type=event_type,
            payload=payload,
        )
        await self._trace.event(
            event_type.value,
            run_id=self._request.run_id,
            task_id=self._request.task_id,
            attributes=payload,
        )
        self._completed.append(stage)

    def assert_complete(self) -> None:
        if tuple(self._completed) != self._STAGES:
            raise ValueError("validation port did not report every required progress stage")


def _validate_request(state: RuntimeState, request: SpecialistCapabilityRequest) -> Task:
    if state.run_id != request.run_id:
        raise ValueError("capability request belongs to a different run")
    task = state.task(request.task_id)
    if task.run_id != request.run_id:
        raise ValueError("task belongs to a different run")
    if task.skill_id != request.skill_id:
        raise ValueError("capability request must originate from the task's assigned Skill")
    if task.assigned_agent != request.requested_by:
        raise CapabilityAuthorityError("only the assigned Specialist may request capability build")
    if task.status is not TaskStatus.RUNNING:
        raise ValueError("capability lookup must occur while the original task is RUNNING")
    if not request.requirement.deterministic:
        raise ValueError("Phase 3 generated capabilities must be deterministic")
    return task


def _require_approval(
    approval: ResearchLeadCapabilityApproval,
    *,
    gap: CapabilityGapRecord,
    phase: str,
    authority: ResearchLeadCapabilityAuthority,
) -> None:
    if approval.authority_role != "RESEARCH_LEAD":
        raise CapabilityAuthorityError("approval authority must be Research Lead")
    if approval.approved_by != authority.lead_agent_id:
        raise CapabilityAuthorityError("approval signer does not match Research Lead authority")
    if not approval.approved or approval.phase != phase:
        raise CapabilityAuthorityError(f"Research Lead {phase} approval is required")
    if (
        approval.run_id != gap.run_id
        or approval.task_id != gap.task_id
        or approval.gap_id != gap.gap_id
    ):
        raise CapabilityAuthorityError("approval and gap identifiers do not match")


def _generated_record(
    request: SpecialistCapabilityRequest,
    gap: CapabilityGapRecord,
    candidate: GeneratedCapabilityCandidate,
) -> GeneratedCapabilityRecord:
    output = candidate.output
    generated_id = f"GEN-{uuid4()}"
    return GeneratedCapabilityRecord(
        generated_capability_id=generated_id,
        run_id=request.run_id,
        task_id=request.task_id,
        gap_id=gap.gap_id,
        capability_id=output.capability_id,
        capability_version=output.version,
        formula_id=output.formula_id,
        purpose=output.purpose,
        input_schema=output.input_schema,
        output_schema=output.output_schema,
        formula_description=output.formula_description,
        implementation_hash=candidate.implementation_hash,
        source_ref=f"generated://{candidate.build_id}/source.py",
        unit_test_ref=f"generated://{candidate.build_id}/tests.py",
        allowed_imports=output.allowed_imports,
        financial_invariants=output.financial_invariants,
        runtime_version=f"Python {python_version()}",
        lifecycle=CapabilityLifecycle.GENERATED,
    )


def _require_active_registration(
    registration: ScopedCapabilityRegistration,
    *,
    request: SpecialistCapabilityRequest,
    generated: GeneratedCapabilityRecord,
) -> None:
    if registration.lifecycle is not CapabilityLifecycle.ACTIVE_FOR_SCOPE:
        raise ValueError("registry must return ACTIVE_FOR_SCOPE after registration")
    if registration.scope is not request.scope:
        raise ValueError("registry changed approved capability scope")
    if registration.run_id != request.run_id:
        raise ValueError("registry changed approved run scope")
    if request.scope is CapabilityScope.TASK and registration.task_id != request.task_id:
        raise ValueError("registry changed approved task scope")
    if registration.generated_capability_ref != generated.generated_capability_id:
        raise ValueError("registry changed generated capability reference")
    if (
        registration.capability_id != generated.capability_id
        or registration.capability_version != generated.capability_version
    ):
        raise ValueError("registry changed generated capability identity")
