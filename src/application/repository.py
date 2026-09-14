from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import uuid4

from src.application.models import ResearchRunDraft, RunAggregate
from src.domain.calculation import CalculationRecord
from src.domain.node_binding import (
    AdmissionBinding,
    AttemptReservation,
    BindingDenied,
    GraphIdentity,
    NodeBindingState,
    OutputRecord,
    OwnerToken,
    ResolvedInputBinding,
    ResultBinding,
    calculation_core,
    canonical_value,
    check_value_identity,
    digest,
    task_fingerprint,
    task_semantics,
    value_identity,
)
from src.domain.research_object import ResearchObject
from src.domain.runtime_event import RuntimeEvent

# Ephemeral invocation context, never serialized or restored from a checkpoint.
node_invocation = ContextVar("vefin_node_invocation", default=None)


def initialize_binding(aggregate):
    from src.application.research_outputs import configure_output_contracts

    configure_output_contracts(aggregate.runtime)
    if aggregate.node_binding is not None:
        validate_root(aggregate)
        return
    aggregate.node_binding = NodeBindingState(
        run_id=aggregate.run.run_id,
        execution_mode="DEFAULT",
        owner_generation=0,
        owner_id=None,
        lifecycle="UNCLAIMED",
        binding_revision=0,
        frozen_graph=GraphIdentity.of(aggregate.runtime.actual_graph),
    )
    aggregate.runtime.binding_ref = aggregate.node_binding.reference()


def validate_root(aggregate, owner=None):
    root = aggregate.node_binding
    if root is None:
        raise BindingDenied("STATE_REFRESH_REQUIRED", "missing node binding")
    if aggregate.scheme.confirmed_at is None:
        raise BindingDenied("STATE_REFRESH_REQUIRED", "Scheme not confirmed")
    # Revalidate rather than trust a mutable model or cached reference.
    NodeBindingState.model_validate(root.model_dump())
    if (
        aggregate.runtime.run_id != aggregate.run.run_id
        or aggregate.runtime.actual_graph.run_id != aggregate.run.run_id
        or any(task.run_id != aggregate.run.run_id for task in aggregate.runtime.actual_graph.tasks)
        or aggregate.run.goal_id != aggregate.goal.goal_id
        or aggregate.run.scheme_id != aggregate.scheme.scheme_id
        or aggregate.run.research_object_id != aggregate.goal.research_object_id
        or aggregate.run.research_object_id != aggregate.scheme.research_object_id
    ):
        raise BindingDenied("IDENTITY_MISMATCH", "Run/graph/goal/Scheme")
    if root.run_id != aggregate.run.run_id or root.frozen_graph != GraphIdentity.of(
        aggregate.runtime.actual_graph
    ):
        raise BindingDenied("STATE_REFRESH_REQUIRED", "graph identity")
    if root.execution_mode != "DEFAULT":
        raise BindingDenied("EXECUTION_MODE_CONFLICT", root.execution_mode)
    if owner is not None and (
        root.run_id,
        root.owner_generation,
        root.owner_id,
        root.lifecycle,
    ) != (owner.run_id, owner.owner_generation, owner.owner_id, "ACTIVE"):
        raise BindingDenied("STALE_WRITE_REJECTED", "execution owner")
    return root


def compare_whole(current, proposed):
    root = validate_root(current)
    other = validate_root(proposed)
    if (root.binding_revision, root.owner_id, root.owner_generation, root.lifecycle) != (
        other.binding_revision,
        other.owner_id,
        other.owner_generation,
        other.lifecycle,
    ):
        raise BindingDenied("STALE_WRITE_REJECTED", "whole aggregate revision")
    lifecycle_fields = {"status", "started_at", "completed_at", "updated_at"}
    if current.run.model_dump(exclude=lifecycle_fields) != proposed.run.model_dump(
        exclude=lifecycle_fields
    ):
        raise BindingDenied("IDENTITY_MISMATCH", "immutable Run identity")
    if root != other or current.scheme != proposed.scheme or current.goal != proposed.goal:
        raise BindingDenied("STALE_WRITE_REJECTED", "whole aggregate immutable binding")
    if (
        current.runtime.actual_graph != proposed.runtime.actual_graph
        or current.runtime.planned_graph != proposed.runtime.planned_graph
        or current.runtime.completed_output_refs != proposed.runtime.completed_output_refs
    ):
        raise BindingDenied("STALE_WRITE_REJECTED", "whole save cannot change committed tasks")
    for field in (
        "evidence",
        "agent_outputs",
        "task_outputs",
        "corrections",
        "replans",
        "financial_branches",
        "generated_capability_refs",
        "judgments",
        "wp04_method_observations",
    ):
        if getattr(current.artifacts, field) != getattr(proposed.artifacts, field):
            raise BindingDenied("STALE_WRITE_REJECTED", "whole save cannot change " + field)
    if [calculation_core(item) for item in current.artifacts.calculations] != [
        calculation_core(item) for item in proposed.artifacts.calculations
    ]:
        raise BindingDenied("STALE_WRITE_REJECTED", "calculation core")
    return root


@runtime_checkable
class ApplicationRepository(Protocol):
    async def get_run_fresh(self, run_id: str) -> RunAggregate | None: ...
    async def claim_execution(self, run_id: str) -> OwnerToken: ...
    async def begin_scheduler(self, owner: OwnerToken) -> None: ...
    async def validate_execution(self, owner: OwnerToken) -> RunAggregate: ...
    async def reserve_node(
        self, owner: OwnerToken, task, requirements: dict, preexisting=()
    ) -> AdmissionBinding: ...
    async def dispatch_node(self, admission: AdmissionBinding) -> RunAggregate: ...
    async def enter_node_execution(self, admission: AdmissionBinding) -> RunAggregate: ...
    async def bind_resolved_inputs(
        self, admission: AdmissionBinding, *, step_id: str, materials, payload: dict
    ) -> ResolvedInputBinding: ...
    async def commit_node_result(
        self,
        admission: AdmissionBinding,
        *,
        task,
        artifacts,
        output_records,
        resolved_ids,
        observed=None,
    ) -> ResultBinding: ...
    async def close_execution(
        self, owner: OwnerToken, *, unknown: bool = False
    ) -> RunAggregate: ...
    async def save_calculation(self, calculation: CalculationRecord) -> None: ...
    async def add_object(self, entity: ResearchObject) -> ResearchObject: ...

    async def get_object(self, object_id: str) -> ResearchObject | None: ...

    async def list_objects(self) -> list[ResearchObject]: ...

    async def add_draft(self, draft: ResearchRunDraft) -> ResearchRunDraft: ...

    async def get_draft(self, draft_id: str) -> ResearchRunDraft | None: ...

    async def add_run(self, aggregate: RunAggregate) -> None: ...

    async def save_run(self, aggregate: RunAggregate) -> None: ...

    async def save_runtime_events(self, events: list[RuntimeEvent]) -> None: ...

    async def get_run(self, run_id: str) -> RunAggregate | None: ...

    async def list_runs_for_object(self, object_id: str) -> list[RunAggregate]: ...


class InMemoryApplicationRepository:
    def __init__(self) -> None:
        self._objects: dict[str, ResearchObject] = {}
        self._drafts: dict[str, ResearchRunDraft] = {}
        self._runs: dict[str, RunAggregate] = {}
        self._lock = asyncio.Lock()
        self._calculations: dict[str, CalculationRecord] = {}

    async def save_calculation(self, calculation: CalculationRecord) -> None:
        async with self._lock:
            aggregate = self._runs.get(calculation.run_id)
            if aggregate is not None and aggregate.node_binding is not None:
                admission = node_invocation.get()
                if (
                    admission is None
                    or admission.run_id != calculation.run_id
                    or admission.task_id != calculation.task_id
                ):
                    raise BindingDenied("STATE_REFRESH_REQUIRED", "calculation invocation")
                self._validate_admission(aggregate, admission, require_started=True)
            previous = self._calculations.get(calculation.calculation_id)
            if previous is not None and previous != calculation:
                raise ValueError("calculation identity is immutable")
            self._calculations[calculation.calculation_id] = calculation.model_copy(deep=True)

    async def add_object(self, entity: ResearchObject) -> ResearchObject:
        async with self._lock:
            if entity.object_id in self._objects:
                raise ValueError(f"research object already exists: {entity.object_id}")
            self._objects[entity.object_id] = entity
        return entity

    async def get_object(self, object_id: str) -> ResearchObject | None:
        return self._objects.get(object_id)

    async def list_objects(self) -> list[ResearchObject]:
        return list(self._objects.values())

    async def add_draft(self, draft: ResearchRunDraft) -> ResearchRunDraft:
        async with self._lock:
            if draft.draft_id in self._drafts:
                raise ValueError(f"draft already exists: {draft.draft_id}")
            self._drafts[draft.draft_id] = draft
        return draft

    async def get_draft(self, draft_id: str) -> ResearchRunDraft | None:
        return self._drafts.get(draft_id)

    async def add_run(self, aggregate: RunAggregate) -> None:
        async with self._lock:
            if aggregate.run.run_id in self._runs:
                raise ValueError(f"run already exists: {aggregate.run.run_id}")
            self._runs[aggregate.run.run_id] = deepcopy(aggregate)

    async def get_run(self, run_id: str) -> RunAggregate | None:
        current = self._runs.get(run_id)
        return deepcopy(current) if current and current.node_binding is not None else current

    async def save_run(self, aggregate: RunAggregate) -> None:
        async with self._lock:
            if aggregate.run.run_id not in self._runs:
                raise KeyError(aggregate.run.run_id)
            current = self._runs[aggregate.run.run_id]
            if current.node_binding is not None or aggregate.node_binding is not None:
                compare_whole(current, aggregate)
                aggregate = deepcopy(aggregate)
                aggregate.node_binding.binding_revision += 1
                aggregate.runtime.binding_ref = aggregate.node_binding.reference()
            self._runs[aggregate.run.run_id] = deepcopy(aggregate)

    async def save_runtime_events(self, events: list[RuntimeEvent]) -> None:
        del events

    async def list_runs_for_object(self, object_id: str) -> list[RunAggregate]:
        return [
            aggregate
            for aggregate in self._runs.values()
            if aggregate.run.research_object_id == object_id
        ]

    @asynccontextmanager
    async def _binding_transaction(self, run_id):
        """Isolated in-memory test implementation; SQL subclass supplies durability."""
        async with self._lock:
            current = self._runs.get(run_id)
            if current is None:
                raise BindingDenied("STATE_REFRESH_REQUIRED", run_id)
            snapshot = deepcopy(current)
            validate_root(snapshot)
            for result in snapshot.node_binding.results.values():
                await self.verify_materials(result.output_records, run_id=run_id)
            yield snapshot
            snapshot.node_binding.binding_revision += 1
            snapshot.runtime.binding_ref = snapshot.node_binding.reference()
            self._runs[run_id] = deepcopy(snapshot)

    async def get_run_fresh(self, run_id):
        async with self._lock:
            return deepcopy(self._runs.get(run_id))

    async def claim_execution(self, run_id):
        async with self._binding_transaction(run_id) as aggregate:
            root = validate_root(aggregate)
            if root.lifecycle != "UNCLAIMED" or root.owner_generation != 0 or root.owner_id:
                raise BindingDenied("OWNER_ALREADY_CLAIMED", run_id)
            root.owner_generation = 1
            root.owner_id = str(uuid4())
            root.lifecycle = "ACTIVE"
            from datetime import UTC, datetime

            from src.domain.enums import RunStatus

            aggregate.run.status = RunStatus.RUNNING
            aggregate.runtime.run_status = RunStatus.RUNNING
            aggregate.run.started_at = datetime.now(UTC)
            aggregate.run.updated_at = aggregate.run.started_at
            token = OwnerToken(run_id=run_id, owner_generation=1, owner_id=root.owner_id)
        return token

    async def begin_scheduler(self, owner):
        async with self._binding_transaction(owner.run_id) as aggregate:
            root = validate_root(aggregate, owner)
            if root.scheduler_started:
                raise BindingDenied("OWNER_ALREADY_CLAIMED", "Scheduler already started")
            root.scheduler_started = True

    async def validate_execution(self, owner):
        aggregate = await self.get_run_fresh(owner.run_id)
        if aggregate is None:
            raise BindingDenied("STATE_REFRESH_REQUIRED", owner.run_id)
        validate_root(aggregate, owner)
        return aggregate

    @staticmethod
    def _current_dependencies(aggregate, task):
        root = validate_root(aggregate)
        ancestor_ids = set(task.dependencies)
        pending = list(ancestor_ids)
        while pending:
            for key in aggregate.runtime.task(pending.pop()).dependencies:
                if key not in ancestor_ids:
                    ancestor_ids.add(key)
                    pending.append(key)
        bindings = []
        for task_id in sorted(ancestor_ids):
            result_id = root.current_results.get(task_id)
            result = root.results.get(result_id)
            if result is None or result_id in root.invalidation_refs:
                raise BindingDenied("STALE_INPUT", task_id)
            check_value_identity(result, "result_digest", "result_id")
            if (
                result.result_id != result.result_digest
                or result.producer_task_id != task_id
                or result.run_id != root.run_id
                or result.graph != root.frozen_graph
                or result.task_fingerprint != task_fingerprint(aggregate.runtime.task(task_id))
            ):
                raise BindingDenied("IDENTITY_MISMATCH", task_id)
            reservation = root.attempts.get(task_id)
            if (
                reservation is None
                or reservation.status != "COMMITTED"
                or reservation.admission.admission_binding_id != result.admission_binding_id
                or reservation.admission.attempt_reservation_id != result.reservation_id
                or result.owner_generation != root.owner_generation
            ):
                raise BindingDenied("STALE_INPUT", task_id)
            for ref in result.resolved_input_binding_ids:
                resolved = root.resolved_inputs.get(ref)
                if resolved is None or resolved.admission_binding_id != result.admission_binding_id:
                    raise BindingDenied("MISSING_INPUT", ref)
                check_value_identity(resolved, "resolved_input_binding_id")
            for record in result.output_records:
                if digest(record.payload_snapshot, record.record_schema) != record.content_digest:
                    raise BindingDenied("IDENTITY_MISMATCH", record.record_id)
            bindings.append(result.dependency())
        return tuple(bindings)

    @staticmethod
    def _validate_admission(aggregate, admission, status="DISPATCHED", *, require_started=False):
        root = validate_root(aggregate, admission.owner)
        check_value_identity(admission, "admission_binding_id")
        task = aggregate.runtime.task(admission.task_id)
        reservation = root.attempts.get(task.task_id)
        if (
            reservation is None
            or reservation.status != status
            or reservation.admission != admission
        ):
            raise BindingDenied("STALE_WRITE_REJECTED", "reservation")
        if (
            root.frozen_graph != admission.graph
            or task_fingerprint(task) != admission.task_fingerprint
        ):
            raise BindingDenied("IDENTITY_MISMATCH", task.task_id)
        if (
            digest(aggregate.goal) != admission.goal_hash
            or digest(aggregate.scheme) != admission.scheme_hash
        ):
            raise BindingDenied("IDENTITY_MISMATCH", "confirmed inputs")
        if require_started and not reservation.execution_started:
            raise BindingDenied("STATE_REFRESH_REQUIRED", "Executor entry not committed")
        if (
            InMemoryApplicationRepository._current_dependencies(aggregate, task)
            != admission.dependency_result_bindings
        ):
            raise BindingDenied("STALE_INPUT", "dependency pointer")
        return root

    async def record_method_observation(self, owner, task_id, observation, admission=None, calculation=None):
        from src.domain.financial_validation import MethodObservation
        observation = MethodObservation.model_validate(observation.model_dump())
        if observation != observation.identified():
            raise BindingDenied('IDENTITY_MISMATCH', 'method observation digest')
        async with self._binding_transaction(owner.run_id) as aggregate:
            root = validate_root(aggregate, owner)
            task = aggregate.runtime.task(task_id)
            req = task.wp04_method_requirement
            if (req is None or not root.scheduler_started or observation.run_id != owner.run_id
                    or observation.task_id != task_id or observation.object_id != aggregate.run.research_object_id
                    or observation.owner_id != owner.owner_id or observation.owner_generation != owner.owner_generation
                    or observation.task_fingerprint != task_fingerprint(task)
                    or observation.requirement_id != req.requirement_id
                    or observation.requirement_digest != req.requirement_digest
                    or observation.requirement_state != req.requirement_state):
                raise BindingDenied('STALE_WRITE_REJECTED', 'method observation owner')
            req.verify()
            if (observation.descriptor != req.descriptor
                    or observation.descriptor_digest != req.descriptor.descriptor_digest):
                raise BindingDenied('IDENTITY_MISMATCH', 'observation expected method')
            if observation.input_binding is not None:
                input_body = {k: v for k, v in observation.input_binding.items() if k != 'input_identity_digest'}
                if (observation.input_identity_digest != digest(input_body, 'wp04-input-binding/v1')
                        or observation.input_binding.get('input_identity_digest') != observation.input_identity_digest
                        or observation.input_binding.get('requirement_digest') != req.requirement_digest):
                    raise BindingDenied('IDENTITY_MISMATCH', 'observation exact inputs')
            if observation.phase == 'PREPARED' and (
                    observation.support_status != 'SUPPORTED' or observation.numeric_outcome != 'NONE'
                    or observation.dispatch_count != 0 or observation.B_ref is not None
                    or observation.input_binding is None):
                raise BindingDenied('IDENTITY_MISMATCH', 'PREPARED does not claim future execution')
            if admission is not None:
                self._validate_admission(aggregate, admission, require_started=True)
                if (observation.admission_binding_id != admission.admission_binding_id
                        or observation.reservation_id != admission.attempt_reservation_id
                        or observation.phase == 'DENIED_BEFORE_A'):
                    raise BindingDenied('IDENTITY_MISMATCH', 'method admission')
            elif (observation.phase != 'DENIED_BEFORE_A' or task_id in root.attempts
                    or observation.admission_binding_id is not None or observation.reservation_id is not None
                    or observation.B_ref is not None or observation.dispatch_count != 0):
                raise BindingDenied('STALE_WRITE_REJECTED', 'before-A observation')
            collection = aggregate.artifacts.wp04_method_observations or {}
            if observation.observation_id in collection:
                if collection[observation.observation_id] != observation:
                    raise BindingDenied('IDENTITY_MISMATCH', 'observation replay')
                return observation
            slot = lambda o: (o.run_id, o.task_fingerprint, o.owner_generation,
                               o.requirement_digest, o.reservation_id, o.phase)
            if any(slot(item) == slot(observation) for item in collection.values()):
                raise BindingDenied('STALE_WRITE_REJECTED', 'observation slot is immutable')
            if observation.previous_observation_id is not None:
                previous = collection.get(observation.previous_observation_id)
                if previous is None or previous.task_id != task_id or previous.reservation_id != observation.reservation_id:
                    raise BindingDenied('IDENTITY_MISMATCH', 'observation predecessor')
            if observation.B_ref is not None:
                b = root.resolved_inputs.get(observation.B_ref)
                if b is None or b.admission_binding_id != observation.admission_binding_id:
                    raise BindingDenied('IDENTITY_MISMATCH', 'observation B')
            if observation.numeric_outcome == 'SUCCEEDED':
                if (calculation is None or calculation.calculation_id != observation.calculation_ref
                        or calculation.task_id != task_id or observation.phase != 'EXECUTION_FINISHED'
                        or observation.support_status != 'SUPPORTED' or observation.dispatch_count != 1
                        or observation.B_ref is None):
                    raise BindingDenied('IDENTITY_MISMATCH', 'observation calculation')
                payload = calculation_core(calculation)
                await self.verify_materials([OutputRecord(kind='CALCULATION_CORE',
                    record_id=calculation.calculation_id, content_digest=digest(payload, 'calculation-core/v1'),
                    record_schema='calculation-core/v1', payload_snapshot=payload,
                    location=calculation.calculation_id)], run_id=owner.run_id)
            elif observation.calculation_ref is not None:
                raise BindingDenied('IDENTITY_MISMATCH', 'denial cannot claim calculation')
            collection[observation.observation_id] = observation.model_copy(deep=True)
            aggregate.artifacts.wp04_method_observations = collection
        return observation

    async def reserve_node(self, owner, task, requirements, preexisting=()):
        try:
            return await self._reserve_node(owner, task, requirements, preexisting)
        except BindingDenied as exc:
            if task.wp04_method_requirement is None:
                raise
            # The denied reservation transaction has rolled back. Commit diagnostic
            # in its own owner-fenced transaction before propagating the original denial.
            from datetime import UTC, datetime
            from src.domain.financial_validation import MethodObservation
            req = task.wp04_method_requirement
            observation = MethodObservation(run_id=task.run_id, object_id=req.object_id,
                task_id=task.task_id, owner_id=owner.owner_id, owner_generation=owner.owner_generation,
                task_fingerprint=task_fingerprint(task), requirement_id=req.requirement_id,
                requirement_digest=req.requirement_digest, requirement_state=req.requirement_state,
                descriptor=req.descriptor, descriptor_digest=req.descriptor.descriptor_digest,
                phase='DENIED_BEFORE_A', support_status=getattr(exc, 'support', 'UNKNOWN'),
                diagnostic_code=exc.code, numeric_outcome='NONE', observed_at=datetime.now(UTC)).identified()
            try:
                await self.record_method_observation(owner, task.task_id, observation)
            except BaseException as persistence_error:
                # Duplicate/stale invocations cannot write canonical observations.
                store = getattr(self, 'wp04_diagnostic_store', None)
                try:
                    if store is None:
                        raise OSError('method diagnostic store unavailable')
                    store.retain_method_diagnostic(run_id=task.run_id, task_id=task.task_id,
                        requirement_id=req.requirement_id, diagnostic_code=exc.code,
                        secondary_diagnostic_code='PERSISTENCE_UNAVAILABLE',
                        observation_id=observation.observation_id)
                except Exception:
                    pass  # Lost diagnostic retention never replaces the original denial.
                raise exc from persistence_error
            raise

    async def _reserve_node(self, owner, task, requirements, preexisting=()):
        async with self._binding_transaction(owner.run_id) as aggregate:
            root = validate_root(aggregate, owner)
            current = aggregate.runtime.task(task.task_id)
            if task_fingerprint(current) != task_fingerprint(task):
                raise BindingDenied("IDENTITY_MISMATCH", task.task_id)
            if task.task_id in root.attempts:
                raise BindingDenied("RESULT_UNKNOWN", "reservation already exists")
            if requirements.get("task") != task_semantics(current) or requirements.get(
                "scheme"
            ) != canonical_value(aggregate.scheme):
                raise BindingDenied("IDENTITY_MISMATCH", "authorized requirements")
            if current.wp04_method_requirement is not None:
                from src.application.execution import wp04_candidate_snapshot
                req = current.wp04_method_requirement
                req.verify()
                verifier = getattr(self, 'wp04_verify_load', None)
                if verifier is None:
                    raise BindingDenied('METHOD_LOAD_EXPECTATION_MISSING')
                verifier(req.descriptor)
                if (req.scheme_hash != digest(aggregate.scheme) or req.scheme_id != aggregate.scheme.scheme_id
                        or req.task_id != current.task_id or req.run_id != owner.run_id
                        or req.object_id != aggregate.run.research_object_id
                        or 'revenue_growth' not in aggregate.scheme.calculation_requirements
                        or (current.task_type, current.assigned_agent, current.skill_id) !=
                           ('fundamental_analysis', 'fundamental_analyst', 'fundamental_analysis_v1')
                        or requirements.get('wp04_candidates') != wp04_candidate_snapshot(aggregate, current)):
                    raise BindingDenied('IDENTITY_MISMATCH', 'WP04 requirement/candidates')
            dependencies = self._current_dependencies(aggregate, current)
            input_ids = set(current.task_input_evidence_ids)
            records = {item.evidence_id: item for item in aggregate.artifacts.evidence}
            resolved_preexisting = []
            for identity in sorted(input_ids):
                record = records.get(identity)
                if (
                    record is None
                    or record.run_id != owner.run_id
                    or record.object_id != aggregate.run.research_object_id
                ):
                    raise BindingDenied("MISSING_INPUT", "preexisting Evidence " + identity)
                payload = canonical_value(record)
                resolved_preexisting.append(
                    OutputRecord(
                        kind="EVIDENCE",
                        record_id=identity,
                        content_digest=digest(payload, "evidence-record/v1"),
                        location=record.raw_artifact_ref,
                        record_schema="evidence-record/v1",
                        payload_snapshot=payload,
                    )
                )
            await self.verify_materials(resolved_preexisting, run_id=owner.run_id)
            if preexisting and tuple(preexisting) != tuple(resolved_preexisting):
                raise BindingDenied("IDENTITY_MISMATCH", "preexisting Evidence manifest")
            preexisting = tuple(resolved_preexisting)
            from src.runtime.output_dependencies import resolve_outputs

            if (
                resolve_outputs(
                    aggregate.runtime,
                    current,
                    committed_results=root.current_results,
                    require_current=True,
                )[0]
                != "READY"
            ):
                raise BindingDenied("MISSING_INPUT", "output requirements")
            admission = AdmissionBinding(
                admission_binding_id="",
                object_id=aggregate.run.research_object_id,
                run_id=owner.run_id,
                goal_id=aggregate.goal.goal_id,
                goal_hash=digest(aggregate.goal),
                scheme_id=aggregate.scheme.scheme_id,
                scheme_hash=digest(aggregate.scheme),
                graph=root.frozen_graph,
                task_id=task.task_id,
                task_fingerprint=task_fingerprint(current),
                owner=owner,
                attempt_reservation_id=str(uuid4()),
                authorized_input_requirements=canonical_value(requirements),
                preexisting_inputs=preexisting,
                dependency_result_bindings=dependencies,
                policy_refs={
                    "confirmed_scheme": aggregate.scheme.scheme_id,
                    "scope": "fixed-initial-graph-default/v1",
                },
            )
            admission = admission.model_copy(
                update={"admission_binding_id": value_identity(admission, "admission_binding_id")}
            )
            root.attempts[task.task_id] = AttemptReservation(admission=admission, status="RESERVED")
        return admission

    async def dispatch_node(self, admission):
        async with self._binding_transaction(admission.run_id) as aggregate:
            root = self._validate_admission(aggregate, admission, "RESERVED")
            root.attempts[admission.task_id] = AttemptReservation(
                admission=admission, status="DISPATCHED"
            )
            from src.domain.enums import TaskStatus

            task = aggregate.runtime.task(admission.task_id)
            task.status = TaskStatus.RUNNING
            task.attempt_count = 1
        return aggregate

    async def enter_node_execution(self, admission):
        async with self._binding_transaction(admission.run_id) as aggregate:
            root = self._validate_admission(aggregate, admission)
            attempt = root.attempts[admission.task_id]
            if attempt.execution_started:
                raise BindingDenied("RESULT_UNKNOWN", "reservation already dispatched to Executor")
            root.attempts[admission.task_id] = attempt.model_copy(
                update={"execution_started": True}
            )
        return aggregate

    async def check_invocation(self, admission):
        aggregate = await self.get_run_fresh(admission.run_id)
        if aggregate is None:
            raise BindingDenied("STATE_REFRESH_REQUIRED", admission.run_id)
        self._validate_admission(aggregate, admission)
        return aggregate

    async def bind_resolved_inputs(self, admission, *, step_id, materials, payload):
        async with self._binding_transaction(admission.run_id) as aggregate:
            root = self._validate_admission(aggregate, admission, require_started=True)
            await self.verify_materials(materials, run_id=admission.run_id)
            snapshot = canonical_value(payload)
            resolved = ResolvedInputBinding(
                resolved_input_binding_id="",
                admission_binding_id=admission.admission_binding_id,
                reservation_id=admission.attempt_reservation_id,
                step_id=step_id,
                material_refs=tuple(materials),
                payload_snapshot=snapshot,
                input_digest=digest(snapshot, "wp02-input-payload/v1"),
            )
            resolved = resolved.model_copy(
                update={
                    "resolved_input_binding_id": value_identity(
                        resolved, "resolved_input_binding_id"
                    )
                }
            )
            if any(
                item.reservation_id == resolved.reservation_id and item.step_id == step_id
                for item in root.resolved_inputs.values()
            ):
                raise BindingDenied("STALE_WRITE_REJECTED", "step already bound")
            root.resolved_inputs[resolved.resolved_input_binding_id] = resolved
        return resolved

    async def commit_node_result(
        self, admission, *, task, artifacts, output_records, resolved_ids, observed=None
    ):
        async with self._binding_transaction(admission.run_id) as aggregate:
            root = self._validate_admission(aggregate, admission, require_started=True)
            actual = tuple(
                key
                for key, value in root.resolved_inputs.items()
                if value.admission_binding_id == admission.admission_binding_id
            )
            if not actual or actual != tuple(resolved_ids):
                raise BindingDenied("MISSING_INPUT", "exact Stage B set")
            for key in actual:
                step = root.resolved_inputs[key]
                check_value_identity(step, "resolved_input_binding_id")
                if (
                    step.input_digest != digest(step.payload_snapshot, "wp02-input-payload/v1")
                    or step.reservation_id != admission.attempt_reservation_id
                ):
                    raise BindingDenied("IDENTITY_MISMATCH", "resolved input digest")
                await self.verify_materials(step.material_refs, run_id=admission.run_id)
            if task_fingerprint(task) != admission.task_fingerprint:
                raise BindingDenied("IDENTITY_MISMATCH", task.task_id)
            await self.verify_materials(output_records, run_id=admission.run_id)
            for record in output_records:
                if digest(record.payload_snapshot, record.record_schema) != record.content_digest:
                    raise BindingDenied("IDENTITY_MISMATCH", record.record_id)
            expected_snapshot = {
                "task_output": canonical_value(artifacts.task_outputs.get(task.task_id, {})),
                "output_outcomes": canonical_value(task.output_outcomes),
                "coverage": canonical_value(task.evidence_source_coverage),
                "admission_binding_id": admission.admission_binding_id,
                "resolved_inputs": list(actual),
            }
            snapshots = [
                record for record in output_records if record.kind == "TASK_OUTPUT_SNAPSHOT"
            ]
            if (
                len(snapshots) != 1
                or snapshots[0].payload_snapshot != expected_snapshot
                or snapshots[0].record_id != digest(expected_snapshot, "task-output-snapshot/v1")
            ):
                raise BindingDenied(
                    "IDENTITY_MISMATCH", "scoped task output versus Result snapshot"
                )
            by_id = {record.record_id: record for record in output_records}
            for field, identity_field, kind in (
                ("evidence", "evidence_id", "EVIDENCE"),
                ("calculations", "calculation_id", "CALCULATION_CORE"),
                ("agent_outputs", "output_id", "AGENT_OUTPUT"),
            ):
                for item in getattr(artifacts, field):
                    if (
                        getattr(item, "task_id", getattr(item, "producer_task_id", None))
                        != task.task_id
                    ):
                        continue
                    payload = (
                        calculation_core(item)
                        if kind == "CALCULATION_CORE"
                        else canonical_value(item)
                    )
                    record = by_id.get(getattr(item, identity_field))
                    if (
                        item.run_id != admission.run_id
                        or record is None
                        or record.kind != kind
                        or record.payload_snapshot != payload
                    ):
                        raise BindingDenied("IDENTITY_MISMATCH", "scoped artifact versus Result")
            self._validate_wp04_result(aggregate, task, artifacts)
            result = ResultBinding(
                result_id="",
                producer_task_id=task.task_id,
                run_id=admission.run_id,
                graph=admission.graph,
                task_fingerprint=admission.task_fingerprint,
                admission_binding_id=admission.admission_binding_id,
                resolved_input_binding_ids=actual,
                owner_generation=admission.owner.owner_generation,
                reservation_id=admission.attempt_reservation_id,
                result_version=1,
                result_digest="",
                output_records=tuple(output_records),
                producer_owner=admission.owner.owner_id,
                observed_execution=observed or {"provider": "UNKNOWN"},
            )
            identity = value_identity(result, "result_id", "result_digest")
            result = result.model_copy(update={"result_id": identity, "result_digest": identity})
            root.results[identity] = result
            root.current_results[task.task_id] = identity
            root.attempts[task.task_id] = AttemptReservation(
                admission=admission, status="COMMITTED", execution_started=True
            )
            from src.domain.enums import TaskStatus

            committed_task = task.model_copy(deep=True)
            committed_task.status = TaskStatus.COMPLETED
            committed_task.progress = 1.0
            aggregate.runtime.actual_graph.tasks = [
                committed_task if item.task_id == task.task_id else item
                for item in aggregate.runtime.actual_graph.tasks
            ]
            aggregate.runtime.completed_output_refs[task.task_id] = [
                item.record_id for item in output_records
            ]
            # Scoped merge only; other concurrent task patches must survive.
            for field, identity_field in (
                ("evidence", "evidence_id"),
                ("calculations", "calculation_id"),
                ("corrections", "correction_id"),
                ("agent_outputs", "output_id"),
            ):
                collection = getattr(aggregate.artifacts, field)
                ids = {getattr(item, identity_field): item for item in collection}
                for item in getattr(artifacts, field):
                    producer = getattr(item, "task_id", getattr(item, "producer_task_id", None))
                    if producer != task.task_id:
                        continue
                    key = getattr(item, identity_field)
                    if key in ids and ids[key] != item:
                        raise BindingDenied("IDENTITY_MISMATCH", key)
                    if key not in ids:
                        collection.append(item.model_copy(deep=True))
            if task.task_id in artifacts.task_outputs:
                aggregate.artifacts.task_outputs[task.task_id] = canonical_value(
                    artifacts.task_outputs[task.task_id]
                )
        return result

    @staticmethod
    def _validate_wp04_result(aggregate, task, artifacts):
        if task.wp04_method_requirement is None:
            return
        from src.domain.financial_validation import validate_decimal_observation
        req = task.wp04_method_requirement
        selected = [c for c in artifacts.calculations if c.task_id == task.task_id
                    and c.capability_id == 'revenue_growth']
        if len(selected) != 1:
            raise BindingDenied('IDENTITY_MISMATCH', 'WP04 result cardinality')
        calc = selected[0]
        metadata = calc.parameters.get('wp04_method_binding', {})
        flags = validate_decimal_observation(metadata.get('decimal_flags_observation'))
        finishes = [o for o in (aggregate.artifacts.wp04_method_observations or {}).values()
                    if o.task_id == task.task_id and o.requirement_digest == req.requirement_digest
                    and o.numeric_outcome == 'SUCCEEDED' and o.calculation_ref == calc.calculation_id
                    and o.B_ref == metadata.get('B_ref')]
        if len(finishes) != 1 or metadata.get('resulting_decimal_flags') != flags:
            raise BindingDenied('IDENTITY_MISMATCH', 'WP04 finish evidence')

    async def close_execution(self, owner, *, unknown=False):
        async with self._binding_transaction(owner.run_id) as aggregate:
            root = validate_root(aggregate, owner)
            root.lifecycle = "RESULT_UNKNOWN" if unknown else "CLOSED"
            if unknown:
                for key, attempt in tuple(root.attempts.items()):
                    if attempt.status in {"RESERVED", "DISPATCHED"}:
                        root.attempts[key] = attempt.model_copy(update={"status": "RESULT_UNKNOWN"})
            root.owner_generation += 1
        return aggregate

    async def verify_materials(self, materials, *, run_id):
        for material in materials:
            payload = material.payload_snapshot
            if digest(payload, material.record_schema) != material.content_digest:
                raise BindingDenied("IDENTITY_MISMATCH", material.record_id)
            if material.kind != "TASK_OUTPUT_SNAPSHOT" and payload.get("run_id") != run_id:
                raise BindingDenied("IDENTITY_MISMATCH", "foreign material")
            if material.kind in {"EVIDENCE", "AGENT_OUTPUT"}:
                location = Path(material.location)
                expected = payload[
                    "snapshot_hash" if material.kind == "EVIDENCE" else "artifact_sha256"
                ]
                if not location.is_absolute():
                    raise BindingDenied("IDENTITY_MISMATCH", "retained artifact location")
                try:
                    retained_bytes = await asyncio.to_thread(location.read_bytes)
                except OSError as exc:
                    raise BindingDenied("MISSING_INPUT", "retained artifact bytes") from exc
                if hashlib.sha256(retained_bytes).hexdigest() != expected.removeprefix("sha256:"):
                    raise BindingDenied("IDENTITY_MISMATCH", "retained artifact bytes")
            if material.kind == "AGENT_OUTPUT":
                import json

                body = json.loads(retained_bytes)
                if any(
                    payload.get(key) != value
                    for key, value in body.items()
                    if key != "schema_version"
                ):
                    raise BindingDenied("IDENTITY_MISMATCH", "Agent record versus artifact")
            if material.kind == "CALCULATION_CORE" and type(self) is InMemoryApplicationRepository:
                from src.domain.node_binding import calculation_core

                original = self._calculations.get(material.record_id)
                if original is None or calculation_core(original) != payload:
                    raise BindingDenied("MISSING_INPUT", material.record_id)
