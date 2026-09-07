"""Production PostgreSQL composition for the Phase 4 Product HTTP surface."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.models import CompletedRunArtifacts
from src.application.persistence import (
    ResearchObjectRow,
    ResearchRunAggregateRow,
    RuntimeEventRow,
    SQLAlchemyApplicationRepository,
)
from src.application.service import ResearchApplicationService
from src.domain.enums import ReplanDecision, RunStatus
from src.domain.proof import (
    ProofInputCommitment,
    ProofPolicyDecision,
    ProofRecord,
    ProofVerificationRecord,
)
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.domain.research_run import ResearchRun
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType, normalize_runtime_event_v1
from src.domain.task import ActualRuntimeGraph, PlannedTaskGraph
from src.infrastructure.database.phase3_records import SQLAlchemyPhase3RecordRepository
from src.infrastructure.database.phase4_product import (
    PHASE4_SINGLE_INSTANCE_SCOPE,
    Phase4RunProjectionRow,
    PostgreSQLProductUnitOfWorkFactory,
)
from src.phase4_product.admission import (
    CONFIRM_ROUTE_TEMPLATE,
    CREATE_OBJECT_ROUTE_TEMPLATE,
    PREPARE_ROUTE_TEMPLATE,
    ResearchRunDraftRecordV1,
    build_confirm_response,
    build_prepare_draft,
    build_run_admission,
    build_scheduler_admission,
    confirmation_request_hash,
    create_object_request_hash,
    mark_draft_consumed,
    prepare_request_hash,
    validate_confirm_request,
)
from src.phase4_product.api import VerifiedArtifactBytes
from src.phase4_product.contracts import (
    ArtifactSummaryV1,
    AtomicRunProjectionV1,
    AvailabilityStatus,
    AvailabilityV1,
    AvailableRunHistoryItemV1,
    ConfirmResearchRunRequestV1,
    ConfirmRunResponseV1,
    CreateResearchObjectRequestV1,
    ExecutionRecordSurfaceV1,
    ExecutionSummaryV1,
    FinancialReviewSurfaceV1,
    PrepareResearchRunRequestV1,
    ProofSummaryV1,
    RendererIdentityV1,
    ReportArtifactGroupV1,
    ReportArtifactRepresentationV1,
    ReportSurfaceV1,
    ResearchObjectCollectionV1,
    ResearchObjectDetailV1,
    ResearchRunDetailV1,
    ResearchRunDraftV1,
    ResearchRunHistoryCollectionV1,
    ResultSummaryV1,
    ResultsWorkspaceV1,
    ReviewSummaryV1,
    RunCollectionObjectV1,
    RunLifecycleV1,
    SafeRuntimeActivityV1,
    TerminalStateV1,
    UnavailableIncompatibleRunHistoryItemV1,
)
from src.phase4_product.durability import (
    AtomicConfirmCommit,
    AtomicObjectCreateCommit,
    AtomicPrepareCommit,
    DurableIdempotencyOutcomeV1,
    DurableObjectCreateOutcomeV1,
    DurablePrepareOutcomeV1,
    ProjectionCommitFence,
    ProjectionWriteSet,
    acknowledge_scheduler_admission,
    lease_scheduler_admission,
    record_scheduler_run_start,
)
from src.phase4_product.errors import ProductError, product_error
from src.phase4_product.hashing import idempotency_key_digest
from src.phase4_product.projections import (
    ProjectionIntegrityError,
    RunCollectionSource,
    build_atomic_run_projection,
    build_released_result_projection,
    build_run_history_collection,
    calculate_run_progress,
    project_event,
    project_goal,
    project_graph,
    project_object,
    project_path_change,
    project_run_collection_item,
    project_run_detail,
    project_run_status,
    project_scheme,
)
from src.phase4_product.results import (
    ResultsIdentityError,
    ResultsIntegrityError,
    build_execution_record_surface,
    build_financial_review_surface,
    build_report_surface,
    build_results_workspace,
)
from src.phase4_product.safety import UnsafeProjectionData, safe_text
from src.runtime.events import CursorPreflight, build_cursor_preflight
from src.runtime.state import RuntimeState

_CURSOR_SIGNING_KEY = b"phase4-vs01-local-run-collection-v1"


def _object_summary_time(value: object) -> datetime | None:
    """Missing/naive release or activity time is unknown, never a default now."""
    try:
        at = datetime.fromisoformat(value) if isinstance(value, str) else value
        return at.astimezone(UTC) if isinstance(at, datetime) and at.tzinfo else None
    except ValueError:
        return None


def _unavailable_history_item(
    row: ResearchRunAggregateRow,
    research_object: ResearchObject,
) -> UnavailableIncompatibleRunHistoryItemV1:
    """Retain only durable identity/status fields from an incompatible aggregate."""

    payload = row.payload
    if not isinstance(payload, Mapping):
        raise ProjectionIntegrityError("Run history aggregate payload is not an object")
    raw_run = payload.get("run")
    if not isinstance(raw_run, Mapping):
        raise ProjectionIntegrityError("Run history aggregate lacks its exact Run identity")
    if (
        raw_run.get("run_id") != row.run_id
        or raw_run.get("research_object_id") != row.object_id
        or raw_run.get("status") != row.status
    ):
        raise ProjectionIntegrityError("Run history durable identity columns disagree with payload")
    object_projection = project_object(research_object)
    if object_projection.object_id != row.object_id:
        raise ProjectionIntegrityError("Run history Object ownership closure failed")
    status = project_run_status(row.status).status
    return UnavailableIncompatibleRunHistoryItemV1(
        run_id=row.run_id,
        object=RunCollectionObjectV1(
            object_id=object_projection.object_id,
            symbol=object_projection.symbol,
            company_name=object_projection.company_name,
        ),
        status=status,
        updated_at=row.updated_at,
    )


class _ProjectionPublishingEventStore:
    """Delegate durable events and publish the matching aggregate watermark."""

    def __init__(
        self,
        delegate: object,
        publish: Callable[[RuntimeEvent], Awaitable[None]],
        published_sequence: Callable[[str], Awaitable[int]],
    ) -> None:
        self._delegate = delegate
        self._publish = publish
        self._published_sequence = published_sequence

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    async def emit(self, **kwargs: Any) -> RuntimeEvent:
        event = await self._delegate.emit(**kwargs)
        await self._publish(event)
        return event

    async def replay(self, run_id: str, *, after_sequence: int = 0) -> list[RuntimeEvent]:
        events = await self._delegate.replay(run_id, after_sequence=after_sequence)
        published_sequence = await self._published_sequence(run_id)
        return [event for event in events if event.sequence <= published_sequence]

    async def wait_for_events(
        self,
        run_id: str,
        *,
        after_sequence: int,
        timeout_seconds: float,
    ) -> list[RuntimeEvent]:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        deadline = monotonic() + timeout_seconds
        while True:
            events = await self.replay(run_id, after_sequence=after_sequence)
            if events:
                return events
            remaining = deadline - monotonic()
            if remaining <= 0:
                return []
            await asyncio.sleep(min(0.05, remaining))

    async def preflight_cursor(
        self,
        run_id: str,
        last_event_id: str | None,
    ) -> CursorPreflight:
        events = await self.replay(run_id)
        return build_cursor_preflight(
            run_id=run_id,
            last_event_id=last_event_id,
            events=events,
        )

    async def resolve_resume_sequence(self, run_id: str, last_event_id: str | None) -> int:
        return (await self.preflight_cursor(run_id, last_event_id)).sequence


class PostgreSQLPhase4ProductBackend:
    """Exact-identity Product backend backed by one PostgreSQL database."""

    def __init__(
        self,
        *,
        sessions: async_sessionmaker[AsyncSession],
        service: ResearchApplicationService,
    ) -> None:
        self.sessions = sessions
        self.service = service
        self.uow_factory = PostgreSQLProductUnitOfWorkFactory(sessions)
        self._confirm_uow_factory = PostgreSQLProductUnitOfWorkFactory(
            sessions,
            isolation_level="READ COMMITTED",
        )
        self._run_admission_scope = PHASE4_SINGLE_INSTANCE_SCOPE
        service.event_store = _ProjectionPublishingEventStore(
            service.event_store,
            self._publish_runtime_event,
            self._published_projection_sequence,
        )
        self._worker_id = f"phase4-worker-{uuid4()}"
        self._worker: asyncio.Task[None] | None = None
        self._executions: set[asyncio.Task[None]] = set()
        self._wake = asyncio.Event()
        self._projection_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._scheduler_loop())
            self._wake.set()

    async def close(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
        executions = tuple(self._executions)
        for execution in executions:
            execution.cancel()
        if executions:
            await asyncio.gather(*executions, return_exceptions=True)

    async def create_object(
        self,
        payload: CreateResearchObjectRequestV1,
        *,
        idempotency_key: str,
        request_id: str | None,
    ) -> ResearchObjectDetailV1:
        del request_id
        request_hash = create_object_request_hash(payload)
        key_digest = idempotency_key_digest(
            idempotency_key, method="POST", route_template=CREATE_OBJECT_ROUTE_TEMPLATE
        )
        async with self.uow_factory() as uow:
            stored = await uow.admission.get_idempotency_outcome_for_update(
                effective_access_scope_key="LOCAL_SINGLE_USER",
                method="POST",
                route_template=CREATE_OBJECT_ROUTE_TEMPLATE,
                idempotency_key_digest=key_digest,
            )
            if stored is not None:
                if (
                    not isinstance(stored, DurableObjectCreateOutcomeV1)
                    or stored.request_hash != request_hash
                ):
                    raise self._idempotency_conflict()
                await uow.rollback()
                return await self.get_object(stored.object_id)
            object_id = f"OBJ-{payload.symbol}"
            if await uow.session.get(ResearchObjectRow, object_id) is not None:
                raise product_error(
                    "CONFLICT",
                    "research object already exists",
                    resource_type="research_object",
                    resource_id=object_id,
                )
            entity = ResearchObject(object_id=object_id, **payload.model_dump())
            outcome = DurableObjectCreateOutcomeV1(
                outcome_id=f"OUT-{uuid4()}",
                effective_access_scope_key="LOCAL_SINGLE_USER",
                idempotency_key_digest=key_digest,
                method="POST",
                route_template=CREATE_OBJECT_ROUTE_TEMPLATE,
                request_hash=request_hash,
                object_id=object_id,
                created_at=entity.created_at,
            )
            commit = AtomicObjectCreateCommit(
                outcome=outcome,
                idempotency_key=idempotency_key,
                request=payload,
                research_object=entity,
            )
            await uow.admission.insert_object_create_commit(commit)
            await uow.commit()
        return self._object_detail(entity, runs=(), latest_events=())

    async def list_objects(
        self,
        *,
        symbol: str | None,
        query: str | None,
        cursor: str | None,
        limit: int,
    ) -> ResearchObjectCollectionV1:
        if cursor is not None:
            raise product_error("INVALID_CURSOR", "object cursor is invalid")
        async with self.sessions() as session:
            rows = list((await session.scalars(select(ResearchObjectRow))).all())
            details: list[ResearchObjectDetailV1] = []
            for row in rows:
                entity = ResearchObject.model_validate(row.payload)
                if symbol is not None and entity.symbol != symbol.strip().upper():
                    continue
                if (
                    query is not None
                    and query.lower() not in (entity.symbol + " " + entity.company_name).lower()
                ):
                    continue
                details.append(await self._persisted_object_detail(session, entity))
        return ResearchObjectCollectionV1(items=tuple(details[:limit]), next_cursor=None)

    async def get_object(self, object_id: str) -> ResearchObjectDetailV1:
        async with self.sessions() as session:
            row = await session.get(ResearchObjectRow, object_id)
            if row is None:
                raise self._not_found("research_object", object_id)
            return await self._persisted_object_detail(
                session, ResearchObject.model_validate(row.payload)
            )

    async def _persisted_object_detail(
        self, session: AsyncSession, entity: ResearchObject
    ) -> ResearchObjectDetailV1:
        runs = tuple(
            (
                await session.scalars(
                    select(ResearchRunAggregateRow).where(
                        ResearchRunAggregateRow.object_id == entity.object_id
                    )
                )
            ).all()
        )
        # Sequence orders events within a Run only; cross-Run ordering below
        # uses persisted timestamps, never Run IDs or database return order.
        latest = (
            select(RuntimeEventRow.run_id, func.max(RuntimeEventRow.sequence).label("sequence"))
            .join(ResearchRunAggregateRow, ResearchRunAggregateRow.run_id == RuntimeEventRow.run_id)
            .where(ResearchRunAggregateRow.object_id == entity.object_id)
            .group_by(RuntimeEventRow.run_id)
            .subquery()
        )
        events = tuple(
            (
                await session.scalars(
                    select(RuntimeEventRow).join(
                        latest,
                        (
                            (RuntimeEventRow.run_id == latest.c.run_id)
                            & (RuntimeEventRow.sequence == latest.c.sequence)
                        ),
                    )
                )
            ).all()
        )
        return self._object_detail(entity, runs=runs, latest_events=events)

    async def prepare_run(
        self,
        payload: PrepareResearchRunRequestV1,
        *,
        idempotency_key: str,
        request_id: str | None,
    ) -> ResearchRunDraftV1:
        del request_id
        request_hash = prepare_request_hash(payload)
        key_digest = idempotency_key_digest(
            idempotency_key, method="POST", route_template=PREPARE_ROUTE_TEMPLATE
        )
        async with self.uow_factory() as uow:
            stored = await uow.admission.get_idempotency_outcome_for_update(
                effective_access_scope_key="LOCAL_SINGLE_USER",
                method="POST",
                route_template=PREPARE_ROUTE_TEMPLATE,
                idempotency_key_digest=key_digest,
            )
            if stored is not None:
                if (
                    not isinstance(stored, DurablePrepareOutcomeV1)
                    or stored.request_hash != request_hash
                ):
                    raise self._idempotency_conflict()
                return stored.draft
            object_row = await uow.session.get(ResearchObjectRow, payload.research_object_id)
            if object_row is None:
                raise self._not_found("research_object", payload.research_object_id)
            research_object = ResearchObject.model_validate(object_row.payload)
            goal = ResearchGoal(
                goal_id=f"GOAL-{uuid4()}",
                research_object_id=payload.research_object_id,
                goal_text=payload.research_goal,
                as_of=payload.as_of,
                preferences=payload.preferences,
            )
            generated = self.service.scheme_generator.generate(
                research_object=research_object, goal=goal
            )
            scheme = await generated if inspect.isawaitable(generated) else generated
            allowed_assurance = {
                name: value
                for name, value in scheme.assurance_requirements.items()
                if name
                in {
                    "financial_review",
                    "proof_policy",
                    "required",
                    "reviewer",
                    "policy_id",
                }
            }
            scheme = scheme.model_copy(
                update={"assurance_requirements": allowed_assurance}
            )
            goal_projection = project_goal(goal, expected_object_id=payload.research_object_id)
            scheme_projection = project_scheme(
                scheme,
                expected_object_id=payload.research_object_id,
                expected_goal_id=goal.goal_id,
                require_confirmed=False,
            )
            draft = build_prepare_draft(
                payload,
                draft_id=f"DRAFT-{uuid4()}",
                goal=goal_projection,
                scheme_snapshot=scheme_projection,
                created_at=goal.created_at,
            )
            outcome = DurablePrepareOutcomeV1(
                outcome_id=f"OUT-{uuid4()}",
                effective_access_scope_key="LOCAL_SINGLE_USER",
                idempotency_key_digest=key_digest,
                method="POST",
                route_template=PREPARE_ROUTE_TEMPLATE,
                request_hash=request_hash,
                draft=draft,
                created_at=draft.created_at,
            )
            await uow.admission.insert_prepare_commit(
                AtomicPrepareCommit(
                    outcome=outcome,
                    idempotency_key=idempotency_key,
                    request=payload,
                    draft_record=ResearchRunDraftRecordV1(draft=draft),
                    goal=goal,
                    scheme=scheme,
                )
            )
            await uow.commit()
            return draft

    async def confirm_run(
        self,
        payload: ConfirmResearchRunRequestV1,
        *,
        idempotency_key: str,
        request_id: str | None,
    ) -> ConfirmRunResponseV1:
        request_hash = confirmation_request_hash(payload)
        key_digest = idempotency_key_digest(
            idempotency_key, method="POST", route_template=CONFIRM_ROUTE_TEMPLATE
        )
        async with self._confirm_uow_factory() as uow:
            await uow.admission.lock_run_admission_scope(self._run_admission_scope)
            stored = await uow.admission.get_idempotency_outcome_for_update(
                effective_access_scope_key="LOCAL_SINGLE_USER",
                method="POST",
                route_template=CONFIRM_ROUTE_TEMPLATE,
                idempotency_key_digest=key_digest,
            )
            if stored is not None:
                if (
                    not isinstance(stored, DurableIdempotencyOutcomeV1)
                    or stored.confirmation_request_hash != request_hash
                ):
                    raise self._idempotency_conflict()
                return build_confirm_response(
                    stored.admission, request_id=request_id, idempotency_replayed=True
                )
            draft_record = await uow.admission.get_draft_for_update(payload.draft_id)
            if draft_record is None:
                raise self._not_found("research_run_draft", payload.draft_id)
            validated = validate_confirm_request(draft_record, payload)
            active_run_id = await uow.admission.get_active_run_id_for_update(
                self._run_admission_scope
            )
            if active_run_id is not None:
                raise self._active_run_conflict(active_run_id)
            goal = ResearchGoal.model_validate(validated.draft.goal.model_dump(mode="json"))
            scheme = ResearchSchemeSnapshot.model_validate(
                validated.draft.scheme_snapshot.model_dump(mode="json")
            ).model_copy(update={"confirmed_at": datetime.now(UTC)})
            run_id = f"RUN-{uuid4()}"
            planned_value = self.service.planner.plan(run_id=run_id, goal=goal, scheme=scheme)
            planned = await planned_value if inspect.isawaitable(planned_value) else planned_value
            runtime = RuntimeState.create(run_id=run_id, planned_graph=planned)
            admitted_at = datetime.now(UTC)
            run = ResearchRun(
                run_id=run_id,
                research_object_id=validated.draft.object_id,
                goal_id=goal.goal_id,
                scheme_id=scheme.scheme_id,
                status=RunStatus.PLANNING,
                as_of=goal.as_of,
                planned_graph_id=planned.graph_id,
                actual_graph_id=runtime.actual_graph.graph_id,
                created_at=admitted_at,
                updated_at=admitted_at,
            )
            admission = build_run_admission(
                validated,
                admission_id=f"ADM-{uuid4()}",
                run_id=run_id,
                planned_graph_id=planned.graph_id,
                admitted_at=admitted_at,
            )
            outcome = DurableIdempotencyOutcomeV1(
                outcome_id=f"OUT-{uuid4()}",
                effective_access_scope_key="LOCAL_SINGLE_USER",
                idempotency_key_digest=key_digest,
                method="POST",
                route_template=CONFIRM_ROUTE_TEMPLATE,
                confirmation_request_hash=request_hash,
                admission=admission,
                created_at=admitted_at,
            )
            initial_events = self._initial_events(
                run=run, scheme=scheme, planned=planned, timestamp=admitted_at
            )
            commit = AtomicConfirmCommit(
                consumed_draft=mark_draft_consumed(
                    draft_record, admission=admission, consumed_at=admitted_at
                ),
                idempotency_outcome=outcome,
                idempotency_key=idempotency_key,
                request=payload,
                scheduler_admission=build_scheduler_admission(
                    admission,
                    idempotency_outcome_id=outcome.outcome_id,
                    created_at=admitted_at,
                ),
                goal=goal,
                scheme=scheme,
                run=run,
                planned_graph=planned,
                actual_graph=runtime.actual_graph,
                tasks=tuple(runtime.actual_graph.tasks),
                initial_events=initial_events,
            )
            await uow.admission.insert_confirm_commit(commit)
            await uow.commit()
        self._wake.set()
        return build_confirm_response(admission, request_id=request_id, idempotency_replayed=False)

    async def get_run(self, run_id: str) -> ResearchRunDetailV1:
        async with self.sessions() as session:
            row = await session.get(ResearchRunAggregateRow, run_id)
            if row is None:
                raise self._not_found("research_run", run_id)
            run = ResearchRun.model_validate(row.payload["run"])
            return project_run_detail(
                run,
                projection_revision=row.projection_revision,
                projection_sequence=row.projection_sequence,
            )

    async def get_projection(self, run_id: str):
        async with self.sessions() as session:
            row = await session.get(ResearchRunAggregateRow, run_id)
            if row is None:
                raise self._not_found("research_run", run_id)
            obj_row = await session.get(ResearchObjectRow, row.object_id)
            event_rows = list(
                (
                    await session.scalars(
                        select(RuntimeEventRow)
                        .where(
                            RuntimeEventRow.run_id == run_id,
                            RuntimeEventRow.sequence <= row.projection_sequence,
                        )
                        .order_by(RuntimeEventRow.sequence)
                    )
                ).all()
            )
            aggregate = row.payload
            research_object = ResearchObject.model_validate(obj_row.payload)
            run = ResearchRun.model_validate(aggregate["run"])
            goal = ResearchGoal.model_validate(aggregate["goal"])
            scheme = ResearchSchemeSnapshot.model_validate(aggregate["scheme"])
            planned = PlannedTaskGraph.model_validate(aggregate["runtime"]["planned_graph"])
            actual = ActualRuntimeGraph.model_validate(aggregate["runtime"]["actual_graph"])
            artifacts = CompletedRunArtifacts.model_validate(aggregate["artifacts"])
            events = tuple(RuntimeEvent.model_validate(item.payload) for item in event_rows)
            pending = AvailabilityV1.unavailable(AvailabilityStatus.PENDING, "REVIEW_PENDING")
            not_generated = AvailabilityV1.unavailable(
                AvailabilityStatus.NOT_GENERATED, "NOT_GENERATED"
            )
            normalized_events = tuple(normalize_runtime_event_v1(event) for event in events)
            path_changes = self._path_change_sources(artifacts, actual)
            if run.status is RunStatus.RELEASED:
                projection = self._released_projection(
                    object_id=row.object_id,
                    revision=row.projection_revision,
                    sequence=row.projection_sequence,
                    research_object=research_object,
                    run=run,
                    goal=goal,
                    scheme=scheme,
                    planned=planned,
                    actual=actual,
                    artifacts=artifacts,
                    events=normalized_events,
                    path_changes=path_changes,
                )
            else:
                terminal_event = (
                    normalized_events[-1]
                    if run.status in {RunStatus.FAILED, RunStatus.CANCELLED}
                    else None
                )
                safe_failure = terminal_event.payload if terminal_event is not None else None
                projection = build_atomic_run_projection(
                    expected_object_id=row.object_id,
                    expected_run_id=run_id,
                    projection_revision=row.projection_revision,
                    projection_sequence=row.projection_sequence,
                    generated_at=datetime.now(UTC),
                    research_object=research_object,
                    run=run,
                    goal=goal,
                    confirmed_scheme=scheme,
                    planned_graph=planned,
                    actual_graph=actual,
                    proof_summary=ProofSummaryV1(
                        availability=not_generated, policy="UNKNOWN", status=None
                    ),
                    review_availability=(
                        pending
                        if run.status not in {RunStatus.FAILED, RunStatus.CANCELLED}
                        else not_generated
                    ),
                    result_availability=not_generated,
                    artifact_availability=not_generated,
                    execution_availability=not_generated,
                    path_changes=path_changes,
                    events=normalized_events,
                    terminal_event=terminal_event,
                    safe_failure=safe_failure,
                )
            await session.execute(
                pg_insert(Phase4RunProjectionRow)
                .values(
                    run_id=run_id,
                    object_id=row.object_id,
                    revision=row.projection_revision,
                    sequence=row.projection_sequence,
                    payload=projection.model_dump(mode="json"),
                    generated_at=projection.generated_at,
                )
                .on_conflict_do_update(
                    index_elements=[Phase4RunProjectionRow.run_id],
                    set_={
                        "revision": row.projection_revision,
                        "sequence": row.projection_sequence,
                        "payload": projection.model_dump(mode="json"),
                        "generated_at": projection.generated_at,
                    },
                )
            )
            await session.commit()
            return projection

    async def list_runs(
        self,
        *,
        object_id: str | None,
        statuses: tuple[str, ...],
        result_availability: str | None,
        cursor: str | None,
        limit: int,
    ) -> ResearchRunHistoryCollectionV1:
        async with self.sessions() as session:
            statement = select(ResearchRunAggregateRow)
            if object_id is not None:
                statement = statement.where(ResearchRunAggregateRow.object_id == object_id)
            rows = list((await session.scalars(statement)).all())
            history_items: list[
                AvailableRunHistoryItemV1 | UnavailableIncompatibleRunHistoryItemV1
            ] = []
            for row in rows:
                obj = await session.get(ResearchObjectRow, row.object_id)
                if obj is None:
                    raise ProjectionIntegrityError(
                        "Run history references a missing Research Object"
                    )
                research_object = ResearchObject.model_validate(obj.payload)
                latest = await session.scalar(
                    select(RuntimeEventRow)
                    .where(
                        RuntimeEventRow.run_id == row.run_id,
                        RuntimeEventRow.sequence <= row.projection_sequence,
                    )
                    .order_by(RuntimeEventRow.sequence.desc())
                    .limit(1)
                )
                try:
                    payload = row.payload
                    if not isinstance(payload, Mapping):
                        raise ProjectionIntegrityError(
                            "Run history aggregate payload is not an object"
                        )
                    runtime = payload.get("runtime")
                    if not isinstance(runtime, Mapping):
                        raise ProjectionIntegrityError(
                            "Run history aggregate runtime is not an object"
                        )
                    run = ResearchRun.model_validate(payload.get("run"))
                    artifacts = CompletedRunArtifacts.model_validate(
                        payload.get("artifacts")
                    )
                    source = RunCollectionSource(
                        run=run,
                        research_object=research_object,
                        actual_graph=ActualRuntimeGraph.model_validate(
                            runtime.get("actual_graph")
                        ),
                        latest_event=(
                            None
                            if latest is None
                            else normalize_runtime_event_v1(
                                RuntimeEvent.model_validate(latest.payload)
                            )
                        ),
                        projection_revision=row.projection_revision,
                        projection_sequence=row.projection_sequence,
                        result_availability=(
                            AvailabilityV1.available()
                            if run.status is RunStatus.RELEASED
                            else AvailabilityV1.unavailable(
                                AvailabilityStatus.FAILED,
                                "RUN_TERMINAL_WITHOUT_RELEASE",
                            )
                            if run.status in {RunStatus.FAILED, RunStatus.CANCELLED}
                            else AvailabilityV1.unavailable(
                                AvailabilityStatus.PENDING,
                                "RUN_NONTERMINAL",
                            )
                        ),
                        release_closure_valid=(
                            run.status is RunStatus.RELEASED
                            and artifacts.review is not None
                            and artifacts.review.run_id == run.run_id
                            and artifacts.review.status.value == "PASS"
                            and artifacts.canonical_record is not None
                            and artifacts.canonical_record.run_id == run.run_id
                            and artifacts.canonical_record.runtime_outcome
                            == RunStatus.RELEASED.value
                            and artifacts.released_result is not None
                            and artifacts.released_result.run_id == run.run_id
                            and artifacts.released_result.canonical_record_id
                            == artifacts.canonical_record.record_id
                            and artifacts.projections is not None
                            and artifacts.projections.canonical_record_id
                            == artifacts.canonical_record.record_id
                            and artifacts.report is not None
                            and len(artifacts.report_artifacts) == 1
                            and artifacts.report_artifacts[0].run_id == run.run_id
                        ),
                    )
                    history_items.append(
                        AvailableRunHistoryItemV1(
                            run=project_run_collection_item(source)
                        )
                    )
                except (ProjectionIntegrityError, ValidationError):
                    history_items.append(
                        _unavailable_history_item(row, research_object)
                    )
        return build_run_history_collection(
            items=history_items,
            cursor_signing_key=_CURSOR_SIGNING_KEY,
            limit=limit,
            object_id=object_id,
            statuses=statuses,
            result_availability=result_availability,
            cursor=cursor,
        )

    async def list_object_runs(
        self,
        object_id: str,
        *,
        cursor: str | None,
        limit: int,
    ) -> ResearchRunHistoryCollectionV1:
        await self.get_object(object_id)
        return await self.list_runs(
            object_id=object_id,
            statuses=(),
            result_availability=None,
            cursor=cursor,
            limit=limit,
        )

    async def get_result(self, run_id: str):
        aggregate = await self.service.get_run(run_id)
        result = aggregate.artifacts.released_result
        canonical = aggregate.artifacts.canonical_record
        if aggregate.run.status is not RunStatus.RELEASED or result is None or canonical is None:
            raise self._unavailable("released_result", run_id, "NOT_GENERATED")
        records = SQLAlchemyPhase3RecordRepository(self.sessions)
        return build_released_result_projection(
            expected_object_id=aggregate.run.research_object_id,
            expected_run_id=run_id,
            run=aggregate.run,
            canonical_record=canonical,
            released_result=result,
            calculations=tuple(aggregate.artifacts.calculations),
            evidence=tuple(aggregate.artifacts.evidence),
            proof_policy_decisions=tuple(await records.list(ProofPolicyDecision, run_id)),
            proof_records=tuple(await records.list(ProofRecord, run_id)),
            proof_verifications=tuple(await records.list(ProofVerificationRecord, run_id)),
            proof_commitments=tuple(await records.list(ProofInputCommitment, run_id)),
        )

    def _released_projection(
        self,
        *,
        object_id: str,
        revision: int,
        sequence: int,
        research_object: ResearchObject,
        run: ResearchRun,
        goal: ResearchGoal,
        scheme: ResearchSchemeSnapshot,
        planned: PlannedTaskGraph,
        actual: ActualRuntimeGraph,
        artifacts: CompletedRunArtifacts,
        events: tuple[Any, ...],
        path_changes: tuple[object, ...],
    ) -> AtomicRunProjectionV1:
        canonical = artifacts.canonical_record
        released = artifacts.released_result
        review = artifacts.review
        if canonical is None or released is None or review is None or not events:
            raise product_error(
                "INTEGRITY_FAILURE",
                "released Run is missing its authoritative release records",
            )
        html_artifacts = [
            artifact
            for artifact in artifacts.report_artifacts
            if artifact.artifact_type == "text/html"
            and artifact.run_id == run.run_id
            and artifact.canonical_record_id == canonical.record_id
            and artifact.released_result_id == released.result_id
        ]
        if len(html_artifacts) != 1:
            raise product_error(
                "INTEGRITY_FAILURE",
                "released Run requires exactly one retained HTML report artifact",
            )
        html_artifact = html_artifacts[0]
        proof_records = [
            proof
            for proof in artifacts.proofs
            if isinstance(proof, ProofRecord) and proof.run_id == run.run_id
        ]
        if set(canonical.proof_refs) != {proof.proof_id for proof in proof_records}:
            raise product_error(
                "INTEGRITY_FAILURE",
                "released Run Proof summary does not match the canonical record",
            )
        proof_policy = "MUST_PROVE" if proof_records else "NOT_REQUIRED"
        proof_status = (
            "VERIFIED"
            if proof_records and all(proof.status.value == "VERIFIED" for proof in proof_records)
            else "NOT_REQUIRED"
            if not proof_records
            else proof_records[0].status.value
        )
        available = AvailabilityV1.available()
        run_status = project_run_status(run.status)
        planned_projection = project_graph(
            planned,
            expected_run_id=run.run_id,
            expected_graph_id=run.planned_graph_id,
        )
        actual_projection = project_graph(
            actual,
            expected_run_id=run.run_id,
            expected_graph_id=run.actual_graph_id,
        )
        tasks = actual_projection.tasks
        activity = tuple(
            project_event(
                event,
                expected_run_id=run.run_id,
                known_task_ids={task.task_id for task in tasks},
                projection_sequence=sequence,
            )
            for event in events
        )
        changes = tuple(
            project_path_change(change, expected_run_id=run.run_id)
            for change in path_changes
        )
        terminal_event = events[-1]
        if terminal_event.type is not RuntimeEventType.RUN_COMPLETED:
            raise product_error(
                "INTEGRITY_FAILURE",
                "released Run does not close with run.completed",
            )
        return AtomicRunProjectionV1(
            projection_revision=revision,
            projection_sequence=sequence,
            generated_at=datetime.now(UTC),
            object=project_object(research_object),
            run=project_run_detail(
                run,
                projection_revision=revision,
                projection_sequence=sequence,
            ),
            goal=project_goal(goal, expected_object_id=object_id),
            confirmed_scheme=project_scheme(
                scheme,
                expected_object_id=object_id,
                expected_goal_id=goal.goal_id,
            ),
            planned_graph=planned_projection,
            actual_graph=actual_projection,
            graph_version=actual_projection.version,
            tasks=tasks,
            path_changes=changes,
            activity=activity,
            lifecycle=RunLifecycleV1(
                status=run_status.status,
                stage=run_status.stage,
                progress=calculate_run_progress(
                    tasks,
                    run_status=run.status,
                    release_closure_valid=True,
                ),
                terminal=True,
                terminal_outcome="SUCCESS",
                safe_failure=None,
            ),
            review=ReviewSummaryV1(
                availability=available,
                review_id=review.review_id,
                status=review.status.value,
            ),
            result=ResultSummaryV1(
                availability=available,
                released_result_id=released.result_id,
                canonical_record_id=canonical.record_id,
                released_at=released.released_at,
            ),
            artifacts=ArtifactSummaryV1(
                availability=available,
                report_id=released.result_id,
                representation_ids=(html_artifact.artifact_id,),
            ),
            proof=ProofSummaryV1(
                availability=available,
                policy=proof_policy,
                status=proof_status,
                proof_refs=tuple(proof.proof_id for proof in proof_records),
            ),
            execution=ExecutionSummaryV1(
                availability=available,
                canonical_record_id=canonical.record_id,
            ),
            terminal=TerminalStateV1(
                is_terminal=True,
                outcome="SUCCESS",
                event_id=terminal_event.event_id,
                sequence=terminal_event.sequence,
            ),
        )

    @staticmethod
    def _path_change_sources(
        artifacts: CompletedRunArtifacts,
        actual: ActualRuntimeGraph,
    ) -> tuple[object, ...]:
        sources: list[object] = list(artifacts.corrections)
        histories = {
            item.get("replan_id"): item
            for item in actual.mutation_history
            if isinstance(item, dict) and isinstance(item.get("replan_id"), str)
        }
        for replan in artifacts.replans:
            history = histories.get(replan.replan_id)
            raw_operations = (
                history.get("operations", []) if isinstance(history, dict) else []
            )
            operations: list[dict[str, object]] = []
            for operation in raw_operations:
                if not isinstance(operation, dict):
                    continue
                kind = operation.get("operation")
                if kind == "add_node":
                    operations.append(
                        {"operation": kind, "task_id": operation.get("task_id")}
                    )
                elif kind in {"add_edge", "remove_edge"}:
                    operations.append(
                        {
                            "operation": kind,
                            "task_id": operation.get("target_task_id"),
                            "dependency_task_id": operation.get("source_task_id"),
                        }
                    )
            if not operations and replan.decision is not ReplanDecision.PENDING:
                continue
            task_refs = tuple(
                dict.fromkeys(
                    str(value)
                    for operation in operations
                    for value in (
                        operation.get("task_id"),
                        operation.get("dependency_task_id"),
                    )
                    if isinstance(value, str)
                )
            )
            if not task_refs:
                task_refs = (replan.requesting_task_id,)
            sources.append(
                {
                    "run_id": replan.run_id,
                    "source_kind": "REPLAN",
                    "source_id": replan.replan_id,
                    "replan_id": replan.replan_id,
                    "change_kind": "ADD_TASK",
                    "status": replan.decision.value,
                    "decision": replan.decision.value,
                    "reason_code": replan.reason_code,
                    "task_refs": task_refs,
                    "operations": operations,
                    "graph_version_before": (
                        history.get("version_before") if isinstance(history, dict) else None
                    ),
                    "graph_version_after": (
                        history.get("version_after") if isinstance(history, dict) else None
                    ),
                    "created_at": replan.created_at,
                    "resolved_at": (
                        None
                        if replan.decision is ReplanDecision.PENDING
                        else replan.created_at
                    ),
                }
            )
        return tuple(sources)

    async def get_claim(self, run_id: str, claim_id: str):
        await self.get_run(run_id)
        raise self._unavailable("claim", claim_id, "NOT_GENERATED")

    async def _results_surfaces(
        self, run_id: str
    ) -> tuple[
        ResultsWorkspaceV1,
        ReportSurfaceV1,
        FinancialReviewSurfaceV1,
        ExecutionRecordSurfaceV1,
    ]:
        """Build every M1 surface from one exact aggregate without latest lookup."""

        aggregate = await self.service.get_run(run_id)
        run = aggregate.run
        artifacts = aggregate.artifacts
        canonical = artifacts.canonical_record
        released = artifacts.released_result
        review = artifacts.review
        if (
            run.run_id != run_id
            or run.status is not RunStatus.RELEASED
            or canonical is None
            or released is None
            or review is None
        ):
            raise self._unavailable("results_workspace", run_id, "NOT_RELEASED")
        actual_graph = aggregate.runtime.actual_graph
        if actual_graph is None:
            raise product_error(
                "INTEGRITY_FAILURE",
                "released Results Workspace lacks its exact actual graph",
                resource_type="results_workspace",
                resource_id=run_id,
            )
        research_object = await self.service.get_object(run.research_object_id)
        events = tuple(await self.service.event_store.replay(run_id))
        tasks = tuple(actual_graph.tasks)
        retained_children = (
            *artifacts.agent_outputs,
            *artifacts.evidence,
            *artifacts.calculations,
            *artifacts.corrections,
            *artifacts.replans,
            *artifacts.report_artifacts,
        )
        if any(item.run_id != run_id for item in retained_children):
            raise product_error(
                "IDENTITY_MISMATCH",
                "Results Workspace retained child belongs to another Run",
                resource_type="results_workspace",
                resource_id=run_id,
            )
        html_artifacts = tuple(
            item
            for item in artifacts.report_artifacts
            if item.artifact_type == "text/html"
        )
        if len(html_artifacts) != 1:
            raise product_error(
                "INTEGRITY_FAILURE",
                "Results Workspace requires one exact HTML Report representation",
                resource_type="results_workspace",
                resource_id=run_id,
            )
        authoritative_subject_refs = {
            run_id,
            run.research_object_id,
            run.goal_id,
            run.scheme_id,
            canonical.record_id,
            released.result_id,
            review.review_id,
            *(item.task_id for item in tasks),
            *(item.output_id for item in artifacts.agent_outputs),
            *(item.event_id for item in events),
            *(item.evidence_id for item in artifacts.evidence),
            *(item.calculation_id for item in artifacts.calculations),
            *(item.correction_id for item in artifacts.corrections),
            *(item.replan_id for item in artifacts.replans),
            *canonical.metric_refs,
            *canonical.claim_refs,
            *canonical.judgment_refs,
            *canonical.decision_refs,
            *canonical.generated_capability_refs,
            *canonical.proof_refs,
        }
        try:
            report_surface = build_report_surface(
                expected_run_id=run_id,
                expected_object_id=run.research_object_id,
                run=run,
                research_object=research_object,
                canonical_record=canonical,
                released_result=released,
                report_artifact=html_artifacts[0],
                tasks=tasks,
                agent_outputs=tuple(artifacts.agent_outputs),
                events=events,
                review=review,
            )
            review_surface = build_financial_review_surface(
                expected_run_id=run_id,
                expected_object_id=run.research_object_id,
                review=review,
                canonical_record=canonical,
                released_result=released,
                authoritative_subject_refs=authoritative_subject_refs,
            )
            execution_surface = build_execution_record_surface(
                expected_run_id=run_id,
                expected_object_id=run.research_object_id,
                run=run,
                canonical_record=canonical,
                released_result=released,
                review=review,
                tasks=tasks,
                agent_outputs=tuple(artifacts.agent_outputs),
                events=events,
                report_contributions=report_surface.source_contributions,
            )
            workspace = build_results_workspace(
                run=run,
                report=report_surface,
                review=review_surface,
                execution=execution_surface,
            )
        except (ResultsIdentityError, ResultsIntegrityError, ValidationError) as exc:
            raise product_error(
                "INTEGRITY_FAILURE",
                "exact-Run Results Workspace integrity validation failed",
                resource_type="results_workspace",
                resource_id=run_id,
            ) from exc
        return workspace, report_surface, review_surface, execution_surface

    async def get_results(self, run_id: str) -> ResultsWorkspaceV1:
        return (await self._results_surfaces(run_id))[0]

    async def get_report(self, run_id: str) -> ReportSurfaceV1:
        return (await self._results_surfaces(run_id))[1]

    async def get_review(self, run_id: str) -> FinancialReviewSurfaceV1:
        return (await self._results_surfaces(run_id))[2]

    async def get_execution(self, run_id: str, **_kwargs) -> ExecutionRecordSurfaceV1:
        return (await self._results_surfaces(run_id))[3]

    async def get_trace(self, run_id: str, claim_id: str):
        await self.get_run(run_id)
        raise self._unavailable("trace_bundle", claim_id, "NOT_GENERATED")

    async def get_artifacts(self, run_id: str):
        aggregate = await self.service.get_run(run_id)
        if aggregate.run.status is not RunStatus.RELEASED:
            raise self._unavailable("report_artifact", run_id, "NOT_RELEASED")
        canonical = aggregate.artifacts.canonical_record
        released = aggregate.artifacts.released_result
        html_records = [
            record
            for record in aggregate.artifacts.report_artifacts
            if record.artifact_type == "text/html"
        ]
        if canonical is None or released is None or not html_records:
            raise self._unavailable("report_artifact", run_id, "NOT_GENERATED")
        if len(html_records) != 1:
            raise product_error(
                "INTEGRITY_FAILURE",
                "the exact Run must have one HTML report representation",
                resource_type="report_artifact",
                resource_id=run_id,
            )
        record = html_records[0]
        if (
            record.run_id != run_id
            or record.canonical_record_id != canonical.record_id
            or record.released_result_id != released.result_id
            or record.anchor_manifest_id is None
            or record.anchor_manifest_hash is None
        ):
            raise product_error(
                "IDENTITY_MISMATCH",
                "report artifact does not close to the exact released Run",
                resource_type="report_artifact",
                resource_id=record.artifact_id,
            )
        available = AvailabilityV1.available()
        return ReportArtifactGroupV1(
            object_id=aggregate.run.research_object_id,
            run_id=run_id,
            report_id=released.result_id,
            canonical_record_id=canonical.record_id,
            released_result_id=released.result_id,
            anchor_manifest_id=record.anchor_manifest_id,
            anchor_manifest_sha256=record.anchor_manifest_hash,
            availability=available,
            representations=(
                ReportArtifactRepresentationV1(
                    format="HTML",
                    required_for_release=True,
                    content_type="text/html; charset=utf-8",
                    availability=available,
                    artifact_id=record.artifact_id,
                    safe_failure_code=None,
                    generation_attempt_id=f"ATTEMPT-{record.artifact_id}",
                    generation_attempt_count=1,
                    sha256=record.content_hash,
                    size_bytes=record.size_bytes,
                    renderer=RendererIdentityV1(
                        renderer_id="professional-html",
                        renderer_version=record.renderer_version,
                    ),
                    generated_at=record.created_at,
                    authorized_ref=(
                        f"/api/research-runs/{run_id}/artifacts/"
                        f"{record.artifact_id}/content"
                    ),
                ),
                ReportArtifactRepresentationV1(
                    format="PDF",
                    required_for_release=False,
                    content_type="application/pdf",
                    availability=AvailabilityV1.unavailable(
                        AvailabilityStatus.NOT_GENERATED,
                        "PDF_DEFERRED_MINIMUM_DEMO",
                    ),
                    artifact_id=None,
                    safe_failure_code=None,
                    generation_attempt_id=None,
                    generation_attempt_count=0,
                    sha256=None,
                    size_bytes=None,
                    renderer=None,
                    generated_at=None,
                    authorized_ref=None,
                ),
            ),
        )

    async def get_artifact_content(self, run_id: str, artifact_id: str):
        aggregate = await self.service.get_run(run_id)
        if aggregate.run.status is not RunStatus.RELEASED:
            raise self._unavailable("report_artifact", artifact_id, "NOT_RELEASED")
        records = [
            record
            for record in aggregate.artifacts.report_artifacts
            if record.artifact_id == artifact_id and record.artifact_type == "text/html"
        ]
        if not records:
            raise self._not_found("report_artifact", artifact_id)
        if len(records) != 1 or records[0].run_id != run_id:
            raise product_error(
                "IDENTITY_MISMATCH",
                "report artifact does not belong to the exact requested Run",
                resource_type="report_artifact",
                resource_id=artifact_id,
            )
        publisher = self.service.report_publisher
        if publisher is None:
            raise self._unavailable("report_artifact", artifact_id, "NOT_GENERATED")
        record = records[0]
        canonical = aggregate.artifacts.canonical_record
        released = aggregate.artifacts.released_result
        if (
            canonical is None
            or released is None
            or record.canonical_record_id != canonical.record_id
            or record.released_result_id != released.result_id
        ):
            raise product_error(
                "IDENTITY_MISMATCH",
                "report artifact does not close to the exact released result",
                resource_type="report_artifact",
                resource_id=artifact_id,
            )
        content = publisher.read_verified(record)
        return VerifiedArtifactBytes(
            run_id=run_id,
            artifact_id=artifact_id,
            content=content,
            content_type="text/html; charset=utf-8",
            sha256=record.content_hash,
            filename="report.html",
            disposition="inline",
        )

    async def get_released_object(self, object_id: str):
        await self.get_object(object_id)
        raise self._unavailable("released_object", object_id, "NOT_RELEASED")

    async def _publish_runtime_event(self, event: RuntimeEvent) -> None:
        async with self._projection_lock:
            aggregate = await self.service.repository.get_run(event.run_id)
            if aggregate is None:
                return
            if event.type is RuntimeEventType.RUN_FAILED:
                terminal_status = RunStatus(str(event.payload.get("status", "")))
                if terminal_status not in {RunStatus.FAILED, RunStatus.CANCELLED}:
                    raise ValueError("run.failed requires a failed or cancelled Run status")
                aggregate.run.status = terminal_status
                aggregate.run.completed_at = event.timestamp
                aggregate.runtime.run_status = terminal_status
            if event.timestamp > aggregate.run.updated_at:
                aggregate.run.updated_at = event.timestamp
            repository = self.service.repository
            if not isinstance(repository, SQLAlchemyApplicationRepository):
                raise RuntimeError(
                    "PostgreSQL Product event publication requires its SQLAlchemy repository"
                )
            await repository.save_run_with_projection_watermark(
                aggregate,
                projection_sequence=event.sequence,
            )

    async def _published_projection_sequence(self, run_id: str) -> int:
        async with self.sessions() as session:
            sequence = await session.scalar(
                select(ResearchRunAggregateRow.projection_sequence).where(
                    ResearchRunAggregateRow.run_id == run_id
                )
            )
        return int(sequence or 0)

    async def _scheduler_loop(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=0.25)
            except TimeoutError:
                pass
            self._wake.clear()
            async with self.uow_factory() as uow:
                due = await uow.scheduler.list_due_admission_ids(due_at=datetime.now(UTC), limit=16)
            for admission_id in due:
                try:
                    await self._start_admitted_run(admission_id)
                except ProductError:
                    continue

    async def _start_admitted_run(self, admission_id: str) -> None:
        now = datetime.now(UTC)
        async with self.uow_factory() as uow:
            current = await uow.scheduler.get_for_update(admission_id)
            if current is None:
                return
            leased, fence = lease_scheduler_admission(
                current,
                worker_id=self._worker_id,
                leased_at=now,
                lease_duration=timedelta(minutes=5),
            )
            if not await uow.scheduler.replace_fenced(
                leased, expected_lease_generation=current.lease_generation
            ):
                return
            row = await uow.session.get(ResearchRunAggregateRow, leased.run_id)
            if row is None:
                raise self._not_found("research_run", leased.run_id)
            run = ResearchRun.model_validate(row.payload["run"]).model_copy(
                update={
                    "status": RunStatus.RUNNING,
                    "started_at": now,
                    "updated_at": now,
                }
            )
            event = RuntimeEvent(
                event_id=f"EVT-{uuid4()}",
                run_id=run.run_id,
                type=RuntimeEventType.RUN_STARTED,
                timestamp=now,
                sequence=row.projection_sequence + 1,
                payload={"actual_graph_version": row.payload["runtime"]["actual_graph"]["version"]},
            )
            await uow.projection.publish(
                ProjectionWriteSet(
                    fence=ProjectionCommitFence(
                        run_id=run.run_id, expected_revision=row.projection_revision
                    ),
                    run=run,
                    events=(event,),
                )
            )
            started = record_scheduler_run_start(
                leased,
                fence,
                started_at=now,
                run_started_event_id=event.event_id,
                run_started_sequence=event.sequence,
            )
            acknowledged = acknowledge_scheduler_admission(started, fence, acknowledged_at=now)
            if not await uow.scheduler.replace_fenced(
                acknowledged, expected_lease_generation=fence.generation
            ):
                raise product_error("CONFLICT", "scheduler fence was lost")
            await uow.commit()
        execution = asyncio.create_task(self._execute_started_run(leased.run_id))
        self._executions.add(execution)
        execution.add_done_callback(self._executions.discard)

    async def _execute_started_run(self, run_id: str) -> None:
        try:
            await self.service.execute_run(run_id, emit_run_started=False)
        except asyncio.CancelledError:
            raise
        except Exception:
            # The application service has already persisted the FAILED aggregate and
            # terminal event. The Product worker still has to publish that snapshot.
            pass
        await self._publish_latest_projection_watermark(run_id)

    async def _publish_latest_projection_watermark(self, run_id: str) -> None:
        """Publish the completed aggregate and its durable event tail as one snapshot fence."""

        async with self.sessions() as session, session.begin():
            row = await session.scalar(
                select(ResearchRunAggregateRow)
                .where(ResearchRunAggregateRow.run_id == run_id)
                .with_for_update()
            )
            if row is None:
                raise self._not_found("research_run", run_id)
            latest_sequence = await session.scalar(
                select(func.max(RuntimeEventRow.sequence)).where(RuntimeEventRow.run_id == run_id)
            )
            sequence = int(latest_sequence or 0)
            if sequence < row.projection_sequence:
                raise product_error(
                    "INTEGRITY_FAILURE",
                    "runtime event tail is behind the published projection watermark",
                )
            row.projection_sequence = sequence
            row.projection_revision += 1

    @staticmethod
    def _initial_events(*, run, scheme, planned, timestamp: datetime) -> tuple[RuntimeEvent, ...]:
        specs = [
            (RuntimeEventType.RUN_CREATED, None, {"object_id": run.research_object_id}),
            (
                RuntimeEventType.SCHEME_GENERATED,
                None,
                {
                    "scheme_id": scheme.scheme_id,
                    "generated_by": scheme.generated_by,
                    "generated_at": scheme.created_at.isoformat(),
                    "generation_stage": "prepare",
                    "retrospective": True,
                },
            ),
            (RuntimeEventType.SCHEME_CONFIRMED, None, {"scheme_id": scheme.scheme_id}),
            (
                RuntimeEventType.PLAN_GENERATED,
                None,
                {"graph_id": planned.graph_id, "task_count": len(planned.tasks)},
            ),
            *(
                (RuntimeEventType.TASK_CREATED, task.task_id, {"task_type": task.task_type})
                for task in planned.tasks
            ),
        ]
        return tuple(
            RuntimeEvent(
                event_id=f"EVT-{uuid4()}",
                run_id=run.run_id,
                task_id=task_id,
                type=event_type,
                timestamp=timestamp,
                sequence=index,
                payload=payload,
            )
            for index, (event_type, task_id, payload) in enumerate(specs, start=1)
        )

    @staticmethod
    def _object_detail(
        entity: ResearchObject,
        *,
        runs: tuple[ResearchRunAggregateRow, ...],
        latest_events: tuple[RuntimeEventRow, ...],
    ) -> ResearchObjectDetailV1:
        scoped = {row.run_id: row for row in runs if row.object_id == entity.object_id}
        if len(scoped) != sum(row.object_id == entity.object_id for row in runs):
            raise ProjectionIntegrityError("Object summary has duplicate Run identities")
        releases: list[tuple[str, datetime | None]] = []
        for row in scoped.values():
            raw = row.payload.get("run", {})
            if (
                raw.get("run_id") != row.run_id
                or raw.get("research_object_id") != entity.object_id
                or raw.get("status") != row.status
            ):
                raise ProjectionIntegrityError("Object summary Run ownership/status mismatch")
            if row.status == RunStatus.RELEASED.value:
                result = (row.payload.get("artifacts") or {}).get("released_result")
                if result is not None and result.get("run_id") != row.run_id:
                    raise ProjectionIntegrityError("Object summary release belongs to another Run")
                releases.append(
                    (
                        row.run_id,
                        _object_summary_time(
                            result.get("released_at") if result is not None else None
                        ),
                    )
                )
        latest_run_id = None
        if releases and all(at is not None for _, at in releases):
            newest = max(at for _, at in releases if at is not None)
            winners = [run_id for run_id, at in releases if at == newest]
            if len(winners) == 1:
                latest_run_id = winners[0]
        availability = (
            AvailabilityV1.available()
            if latest_run_id is not None
            else AvailabilityV1.unavailable(
                AvailabilityStatus.UNAVAILABLE if releases else AvailabilityStatus.NOT_RELEASED,
                "RELEASED_RUN_LATEST_UNAVAILABLE" if releases else "NO_RELEASED_RUN",
            )
        )
        activities: dict[str, SafeRuntimeActivityV1 | None] = {}
        for row in latest_events:
            if row.run_id not in scoped:
                continue
            if row.run_id in activities:
                raise ProjectionIntegrityError("Object summary latest event is ambiguous")
            raw = row.payload
            if (
                raw.get("run_id") != row.run_id
                or raw.get("event_id") != row.event_id
                or raw.get("sequence") != row.sequence
            ):
                raise ProjectionIntegrityError("Object summary activity identity mismatch")
            at = _object_summary_time(raw.get("timestamp"))
            try:
                # Project only safe event identity and time; never forward a
                # legacy aggregate's raw event payload or manufacture an event.
                activities[row.run_id] = (
                    None
                    if at is None
                    else SafeRuntimeActivityV1(
                        event_id=safe_text(row.event_id),
                        type=safe_text(raw.get("type")),
                        sequence=row.sequence,
                        timestamp=at,
                        task_id=(
                            safe_text(raw["task_id"]) if raw.get("task_id") is not None else None
                        ),
                        message_code="OBJECT_RUN_ACTIVITY",
                    )
                )
            except (UnsafeProjectionData, ValidationError):
                activities[row.run_id] = None
        activity = None
        if scoped and set(activities) == set(scoped) and all(activities.values()):
            newest = max(item.timestamp for item in activities.values() if item is not None)
            winners = [item for item in activities.values() if item and item.timestamp == newest]
            if len(winners) == 1:
                activity = winners[0]
        return ResearchObjectDetailV1(
            object=project_object(entity),
            latest_released_run_id=latest_run_id,
            released_result_availability=availability,
            run_count=len(scoped),
            last_activity=activity,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    @staticmethod
    def _not_found(resource_type: str, resource_id: str) -> ProductError:
        return product_error(
            "NOT_FOUND",
            "the exact requested resource was not found",
            resource_type=resource_type,
            resource_id=resource_id,
        )

    @staticmethod
    def _unavailable(resource_type: str, resource_id: str, reason: str) -> ProductError:
        code = "NOT_RELEASED" if reason == "NOT_RELEASED" else "NOT_GENERATED"
        return product_error(
            code,
            "the exact requested resource is not available",
            resource_type=resource_type,
            resource_id=resource_id,
            details={"reason_code": reason},
        )

    @staticmethod
    def _idempotency_conflict() -> ProductError:
        return product_error(
            "CONFLICT",
            "Idempotency-Key was already used for a different request",
            details={"reason_code": "IDEMPOTENCY_REQUEST_MISMATCH"},
        )

    @staticmethod
    def _active_run_conflict(run_id: str) -> ProductError:
        return product_error(
            "CONFLICT",
            "A research run is already active. Wait for it to finish before starting another.",
            resource_type="research_run",
            resource_id=run_id,
            details={"reason_code": "RUN_ALREADY_ACTIVE"},
        )
