from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.task import ActualRuntimeGraph, PlannedTaskGraph
from src.infrastructure.database.models import RuntimeCheckpointRow
from src.runtime.checkpoint import RuntimeCheckpoint
from src.runtime.state import RuntimeState


class SQLAlchemyCheckpointStore:
    """Durable checkpoint store shared by SQLite tests and PostgreSQL runtime."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def save(self, checkpoint: RuntimeCheckpoint) -> None:
        async with self._sessions() as session:
            if await session.get(RuntimeCheckpointRow, checkpoint.checkpoint_id) is not None:
                raise ValueError(f"duplicate checkpoint id: {checkpoint.checkpoint_id}")
            session.add(
                RuntimeCheckpointRow(
                    checkpoint_id=checkpoint.checkpoint_id,
                    run_id=checkpoint.run_id,
                    created_at=checkpoint.created_at,
                    payload=checkpoint.model_dump(mode="json"),
                )
            )
            await session.commit()

    async def load_latest(self, run_id: str) -> RuntimeCheckpoint | None:
        async with self._sessions() as session:
            statement = (
                select(RuntimeCheckpointRow)
                .where(RuntimeCheckpointRow.run_id == run_id)
                .order_by(
                    RuntimeCheckpointRow.created_at.desc(),
                    RuntimeCheckpointRow.checkpoint_id.desc(),
                )
                .limit(1)
            )
            row = (await session.scalars(statement)).first()
        return RuntimeCheckpoint.model_validate(row.payload) if row is not None else None


def restore_runtime_state(
    checkpoint: RuntimeCheckpoint,
    *,
    planned_graph: PlannedTaskGraph,
) -> RuntimeState:
    """Restore mutable runtime state while retaining the approved planned snapshot."""

    if checkpoint.run_id != planned_graph.run_id:
        raise ValueError("checkpoint and planned graph belong to different runs")
    actual_graph = ActualRuntimeGraph.model_validate(checkpoint.actual_graph)
    if actual_graph.run_id != checkpoint.run_id:
        raise ValueError("checkpoint actual graph belongs to a different run")
    if actual_graph.version != checkpoint.actual_graph_version:
        raise ValueError("checkpoint graph version does not match actual graph payload")
    actual_task_states = {task.task_id: task.status for task in actual_graph.tasks}
    if actual_task_states != checkpoint.task_states:
        raise ValueError("checkpoint task states do not match actual graph payload")
    return RuntimeState(
        run_id=checkpoint.run_id,
        planned_graph=planned_graph.model_copy(deep=True),
        actual_graph=actual_graph,
        run_status=checkpoint.run_status,
        completed_output_refs={
            task_id: list(refs) for task_id, refs in checkpoint.completed_output_refs.items()
        },
        evidence_refs=list(checkpoint.evidence_refs),
        workspace_refs=list(checkpoint.workspace_refs),
        review_state=dict(checkpoint.review_state),
        proof_state=dict(checkpoint.proof_state),
        cost=checkpoint.cost,
    )
