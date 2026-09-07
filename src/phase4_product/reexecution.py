"""Explicit failed-attempt authorization and atomic new execution admission.

No prepare/Scheme generation path exists here. Local single-user authority is
explicit at authorization; calling these functions is not itself owner approval.
"""

import inspect
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import select

from src.agentic.llm_integration import PlannerProviderResearchLeadPlanner
from src.agentic.planning_errors import GraphPlanningFailure
from src.agentic.runtime_bindings import GraphRuntimeBindingError, validate_graph_runtime_bindings
from src.application.models import RunAggregate
from src.application.persistence import (
    ResearchGoalRow,
    ResearchRunAggregateRow,
    ResearchRunDraftRow,
    ResearchSchemeSnapshotRow,
    RuntimeEventRow,
    SQLAlchemyApplicationRepository,
    TaskRow,
)
from src.domain.enums import RunStatus
from src.domain.research_goal import ResearchGoal
from src.domain.research_run import ResearchRun
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.infrastructure.database.phase4_product import (
    Phase4ActualGraphRow,
    Phase4IdempotencyOutcomeRow,
    Phase4PlannedGraphRow,
    Phase4SchedulerAdmissionRow,
    _scheduler_row,
)
from src.infrastructure.database.reexecution import ReexecutionAuthorizationRow
from src.infrastructure.database.research_memory import (
    ResearchMemoryPointerRow,
    ResearchViewVersionRow,
)
from src.phase4_product.admission import DRAFT_EXPIRY, RunSchedulerAdmissionV1, draft_hash_is_valid
from src.phase4_product.contracts import FrozenWireModel, NonBlank, ResearchRunDraftV1, Sha256
from src.phase4_product.errors import product_error
from src.phase4_product.hashing import canonical_json_sha256, idempotency_key_digest
from src.phase4_product.incremental import bind_incremental_plan
from src.runtime.state import RuntimeState

AUTHORIZE_ROUTE = "/api/research-runs/{run_id}/reexecution-authorizations"
ADMIT_ROUTE = "/api/research-runs/{run_id}/reexecute"


class AuthorizeReexecutionRequest(FrozenWireModel):
    research_object_id: NonBlank
    authorize_reexecution: Literal[True]


class ReexecuteRequest(FrozenWireModel):
    research_object_id: NonBlank
    authorization_id: NonBlank


class ReexecutionAuthorization(FrozenWireModel):
    schema_version: Literal["phase5-reexecution-authorization/v1"] = (
        "phase5-reexecution-authorization/v1"
    )
    authorization_id: NonBlank
    research_object_id: NonBlank
    reexecution_of_run_id: NonBlank
    scheme_id: NonBlank
    scheme_hash: Sha256
    goal_hash: Sha256
    base_run_id: NonBlank
    base_research_view_version: NonBlank
    authorized_by: Literal["LOCAL_SINGLE_USER"] = "LOCAL_SINGLE_USER"
    authorized_at: datetime
    expires_at: datetime


class ReexecutionAdmission(FrozenWireModel):
    schema_version: Literal["phase5-reexecution-admission/v1"] = "phase5-reexecution-admission/v1"
    authorization_id: NonBlank
    admission_id: NonBlank
    run_id: NonBlank
    research_object_id: NonBlank
    reexecution_of_run_id: NonBlank
    scheme_id: NonBlank
    scheme_hash: Sha256
    base_run_id: NonBlank
    base_research_view_version: NonBlank
    planned_graph_id: NonBlank
    status: Literal["PLANNING"] = "PLANNING"
    admitted_at: datetime
    idempotency_replayed: bool = False


def reject(reason):
    raise product_error(
        "CONFLICT", "re-execution authority validation failed", details={"reason_code": reason}
    )


async def authority(session, prior_id, object_id):
    """Resolve exact durable intent; distrust caller-supplied snapshots and aliases."""
    prior = await session.get(ResearchRunAggregateRow, prior_id, with_for_update=True)
    if prior is None or prior.object_id != object_id or prior.status != "FAILED":
        reject("REEXECUTION_PRIOR_INVALID")
    run = ResearchRun.model_validate(prior.payload["run"])
    scheme = ResearchSchemeSnapshot.model_validate(prior.payload["scheme"])
    goal = ResearchGoal.model_validate(prior.payload["goal"])
    context = scheme.incremental_context
    if (
        run.run_id != prior_id
        or run.status != RunStatus.FAILED
        or run.research_object_id != object_id
        or scheme.research_object_id != object_id
        or goal.research_object_id != object_id
        or run.scheme_id != scheme.scheme_id
        or run.goal_id != goal.goal_id
        or scheme.goal_id != goal.goal_id
        or scheme.confirmed_at is None
        or context is None
        or (run.base_run_id, run.base_research_view_version)
        != (context.base_run_id, context.base_research_view_version)
    ):
        reject("REEXECUTION_INTENT_INVALID")
    snapshot = await session.get(ResearchSchemeSnapshotRow, scheme.scheme_id, with_for_update=True)
    if (
        snapshot is None
        or not snapshot.confirmed
        or snapshot.payload != scheme.model_dump(mode="json")
    ):
        reject("REEXECUTION_SCHEME_INTEGRITY")
    persisted_goal = await session.get(ResearchGoalRow, goal.goal_id, with_for_update=True)
    if persisted_goal is None or persisted_goal.payload != goal.model_dump(mode="json"):
        reject("REEXECUTION_GOAL_INTEGRITY")
    drafts = list(
        await session.scalars(
            select(ResearchRunDraftRow).where(
                ResearchRunDraftRow.object_id == object_id,
                ResearchRunDraftRow.payload["scheme_snapshot"]["scheme_id"].as_string()
                == scheme.scheme_id,
            )
        )
    )
    if len(drafts) != 1:
        reject("REEXECUTION_ORIGINAL_CONFIRMATION_INVALID")
    draft = ResearchRunDraftV1.model_validate(drafts[0].payload)
    if (
        not draft_hash_is_valid(draft)
        or drafts[0].consumed_at is None
        or draft.goal.model_dump(mode="json") != goal.model_dump(mode="json")
        or draft.scheme_snapshot.model_dump(mode="json", exclude={"confirmed_at"})
        != scheme.model_dump(mode="json", exclude={"confirmed_at"})
    ):
        reject("REEXECUTION_ORIGINAL_CONFIRMATION_INVALID")
    cursor, seen = run, set()
    while cursor.reexecution_of_run_id:
        if cursor.run_id in seen:
            reject("REEXECUTION_LINEAGE_INVALID")
        seen.add(cursor.run_id)
        ancestor = await session.get(ResearchRunAggregateRow, cursor.reexecution_of_run_id)
        if ancestor is None or ancestor.status != "FAILED" or ancestor.object_id != object_id:
            reject("REEXECUTION_LINEAGE_INVALID")
        if ancestor.payload["scheme"] != scheme.model_dump(mode="json"):
            reject("REEXECUTION_LINEAGE_INVALID")
        cursor = ResearchRun.model_validate(ancestor.payload["run"])
    if drafts[0].consumed_run_id != cursor.run_id:
        reject("REEXECUTION_ORIGINAL_CONFIRMATION_INVALID")
    base = await session.get(ResearchRunAggregateRow, run.base_run_id, with_for_update=True)
    pointer = await session.get(ResearchMemoryPointerRow, object_id, with_for_update=True)
    view = await session.scalar(
        select(ResearchViewVersionRow).where(
            ResearchViewVersionRow.object_id == object_id,
            ResearchViewVersionRow.source_run_id == run.base_run_id,
        )
    )
    if (
        base is None
        or base.status != "RELEASED"
        or base.object_id != object_id
        or pointer is None
        or pointer.latest_released_run_id != run.base_run_id
        or view is None
        or view.version != pointer.latest_research_view_version
        or view.payload["research_view_version_id"] != run.base_research_view_version
    ):
        reject("REEXECUTION_BASE_INVALID")
    released = await session.scalar(
        select(ResearchRunAggregateRow.run_id).where(
            ResearchRunAggregateRow.object_id == object_id,
            ResearchRunAggregateRow.status == "RELEASED",
            ResearchRunAggregateRow.payload["run"]["scheme_id"].as_string() == scheme.scheme_id,
        )
    )
    if released:
        reject("REEXECUTION_INTENT_ALREADY_RELEASED")
    return run, goal, scheme


async def authorize(backend, prior_id, request, key):
    digest = idempotency_key_digest(key, method="POST", route_template=AUTHORIZE_ROUTE)
    request_hash = canonical_json_sha256(
        {"prior_run_id": prior_id, **request.model_dump(mode="json")}
    )
    async with backend._confirm_uow_factory() as uow:
        await uow.admission.lock_run_admission_scope(backend._run_admission_scope)
        stored = await uow.session.scalar(
            select(ReexecutionAuthorizationRow).where(
                ReexecutionAuthorizationRow.key_digest == digest
            )
        )
        if stored:
            if stored.request_hash != request_hash:
                reject("REEXECUTION_IDEMPOTENCY_CONFLICT")
            return ReexecutionAuthorization.model_validate(stored.payload)
        run, goal, scheme = await authority(uow.session, prior_id, request.research_object_id)
        now = datetime.now(UTC)
        value = ReexecutionAuthorization(
            authorization_id=f"REAUTH-{uuid4()}",
            research_object_id=request.research_object_id,
            reexecution_of_run_id=prior_id,
            scheme_id=scheme.scheme_id,
            scheme_hash=canonical_json_sha256(scheme.model_dump(mode="json")),
            goal_hash=canonical_json_sha256(goal.model_dump(mode="json")),
            base_run_id=run.base_run_id,
            base_research_view_version=run.base_research_view_version,
            authorized_at=now,
            expires_at=now + DRAFT_EXPIRY,
        )
        uow.session.add(
            ReexecutionAuthorizationRow(
                authorization_id=value.authorization_id,
                prior_run_id=prior_id,
                key_digest=digest,
                request_hash=request_hash,
                payload=value.model_dump(mode="json"),
            )
        )
        await uow.commit()
    return value


async def admit(backend, prior_id, request, key):
    digest = idempotency_key_digest(key, method="POST", route_template=ADMIT_ROUTE)
    async with backend._confirm_uow_factory() as uow:
        await uow.admission.lock_run_admission_scope(backend._run_admission_scope)
        row = await uow.session.get(
            ReexecutionAuthorizationRow, request.authorization_id, with_for_update=True
        )
        if row is None:
            reject("REEXECUTION_AUTHORIZATION_UNKNOWN")
        auth = ReexecutionAuthorization.model_validate(row.payload)
        if (
            auth.reexecution_of_run_id != prior_id
            or row.prior_run_id != prior_id
            or auth.research_object_id != request.research_object_id
        ):
            reject("REEXECUTION_AUTHORIZATION_TARGET_MISMATCH")
        if row.consumed_by_run_id:
            if row.admission_key_digest != digest:
                reject("REEXECUTION_AUTHORIZATION_CONSUMED")
            return ReexecutionAdmission.model_validate(row.admission_response).model_copy(
                update={"idempotency_replayed": True}
            )
        used_key = await uow.session.scalar(
            select(ReexecutionAuthorizationRow.authorization_id).where(
                ReexecutionAuthorizationRow.admission_key_digest == digest
            )
        )
        if used_key:
            reject("REEXECUTION_IDEMPOTENCY_CONFLICT")
        if datetime.now(UTC) >= auth.expires_at:
            reject("REEXECUTION_AUTHORIZATION_EXPIRED")
        prior, goal, scheme = await authority(uow.session, prior_id, request.research_object_id)
        scheme_data, goal_data = scheme.model_dump(mode="json"), goal.model_dump(mode="json")
        if (
            auth.scheme_id != scheme.scheme_id
            or auth.scheme_hash != canonical_json_sha256(scheme_data)
            or auth.goal_hash != canonical_json_sha256(goal_data)
            or (auth.base_run_id, auth.base_research_view_version)
            != (prior.base_run_id, prior.base_research_view_version)
        ):
            reject("REEXECUTION_AUTHORIZATION_BINDING_INVALID")
        if await uow.admission.get_active_run_id_for_update(backend._run_admission_scope):
            reject("REEXECUTION_ACTIVE_RUN")
        planner = backend.incremental_planner
        if planner is None or (
            isinstance(planner, PlannerProviderResearchLeadPlanner)
            and (
                planner._max_validation_attempts != 1
                or not planner._fail_closed
                or planner._agent_registry is not backend.service.agent_registry
            )
        ):
            reject("REEXECUTION_PLANNER_BUDGET_INVALID")
        run_id = f"RUN-{uuid4()}"
        try:
            planned = planner.plan(run_id=run_id, goal=goal, scheme=scheme)
            if inspect.isawaitable(planned):
                planned = await planned
            if (
                planned.run_id != run_id
                or planned.graph_id == prior.planned_graph_id
                or scheme.model_dump(mode="json") != scheme_data
                or goal.model_dump(mode="json") != goal_data
            ):
                raise GraphRuntimeBindingError()
            validate_graph_runtime_bindings(planned, backend.service.agent_registry, scheme=scheme)
            planned = bind_incremental_plan(planned, scheme.incremental_context)
        except (GraphPlanningFailure, GraphRuntimeBindingError):
            reject("GRAPH_RUNTIME_BINDING_INVALID")
        if datetime.now(UTC) >= auth.expires_at:
            reject("REEXECUTION_AUTHORIZATION_EXPIRED")
        now = datetime.now(UTC)
        runtime = RuntimeState.create(run_id=run_id, planned_graph=planned)
        run = ResearchRun(
            run_id=run_id,
            research_object_id=auth.research_object_id,
            goal_id=goal.goal_id,
            scheme_id=scheme.scheme_id,
            as_of=goal.as_of,
            status=RunStatus.PLANNING,
            base_run_id=auth.base_run_id,
            base_research_view_version=auth.base_research_view_version,
            reexecution_of_run_id=prior_id,
            planned_graph_id=planned.graph_id,
            actual_graph_id=runtime.actual_graph.graph_id,
            created_at=now,
            updated_at=now,
        )
        result = ReexecutionAdmission(
            authorization_id=auth.authorization_id,
            admission_id=f"ADM-{uuid4()}",
            run_id=run_id,
            research_object_id=auth.research_object_id,
            reexecution_of_run_id=prior_id,
            scheme_id=scheme.scheme_id,
            scheme_hash=auth.scheme_hash,
            base_run_id=auth.base_run_id,
            base_research_view_version=auth.base_research_view_version,
            planned_graph_id=planned.graph_id,
            admitted_at=now,
        )
        aggregate = RunAggregate(run=run, goal=goal, scheme=scheme, runtime=runtime)
        events = backend._initial_events(run=run, scheme=scheme, planned=planned, timestamp=now)
        root = SQLAlchemyApplicationRepository._row(aggregate)
        root.projection_sequence = len(events)
        uow.session.add(root)
        await uow.session.flush()  # establish FK target within this same uncommitted transaction
        uow.session.add(
            Phase4PlannedGraphRow(
                graph_id=planned.graph_id, run_id=run_id, payload=planned.model_dump(mode="json")
            )
        )
        uow.session.add(
            Phase4ActualGraphRow(
                graph_id=runtime.actual_graph.graph_id,
                run_id=run_id,
                payload=runtime.actual_graph.model_dump(mode="json"),
            )
        )
        for task in runtime.actual_graph.tasks:
            uow.session.add(
                TaskRow(task_id=task.task_id, run_id=run_id, payload=task.model_dump(mode="json"))
            )
        for event in events:
            uow.session.add(
                RuntimeEventRow(
                    event_id=event.event_id,
                    run_id=run_id,
                    sequence=event.sequence,
                    payload=event.model_dump(mode="json"),
                )
            )
        outcome_id = f"OUT-{uuid4()}"
        uow.session.add(
            Phase4IdempotencyOutcomeRow(
                outcome_id=outcome_id,
                access_scope="LOCAL_SINGLE_USER",
                method="POST",
                route_template=ADMIT_ROUTE,
                key_digest=digest,
                request_hash=canonical_json_sha256(
                    {"prior_run_id": prior_id, **request.model_dump(mode="json")}
                ),
                kind="REEXECUTION",
                object_id=auth.research_object_id,
                run_id=run_id,
                payload=result.model_dump(mode="json"),
                created_at=now,
            )
        )
        scheduler = RunSchedulerAdmissionV1(
            admission_id=result.admission_id,
            run_id=run_id,
            idempotency_outcome_id=outcome_id,
            next_attempt_at=now,
            created_at=now,
            updated_at=now,
        )
        uow.session.add(Phase4SchedulerAdmissionRow(**_scheduler_row(scheduler)))
        row.consumed_by_run_id, row.consumed_at = run_id, now
        row.admission_key_digest, row.admission_response = digest, result.model_dump(mode="json")
        await uow.commit()
    backend._wake.set()
    return result
