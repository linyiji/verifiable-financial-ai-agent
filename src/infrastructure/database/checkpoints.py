from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.task import PlannedTaskGraph
from src.infrastructure.database.models import RuntimeCheckpointRow
from src.runtime.checkpoint import RuntimeCheckpoint, RuntimeCheckpointIntegrityError
from src.runtime.state import RuntimeState


class SQLAlchemyCheckpointStore:
    """Durable checkpoint store shared by SQLite tests and PostgreSQL runtime."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def save(self, checkpoint: RuntimeCheckpoint) -> None:
        checkpoint.validate_payload_identity()
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
        if row is None:
            return None
        try:
            checkpoint = RuntimeCheckpoint.model_validate(row.payload)
        except (TypeError, ValueError) as exc:
            raise RuntimeCheckpointIntegrityError("stored checkpoint payload is malformed") from exc
        if (
            row.run_id != run_id
            or checkpoint.run_id != run_id
            or checkpoint.checkpoint_id != row.checkpoint_id
        ):
            raise RuntimeCheckpointIntegrityError(
                "stored checkpoint identity does not match its exact Run row"
            )
        checkpoint.validate_payload_identity()
        return checkpoint


def restore_runtime_state(
    checkpoint: RuntimeCheckpoint,
    *,
    planned_graph: PlannedTaskGraph,
) -> RuntimeState:
    """Restore mutable runtime state while retaining the approved planned snapshot."""

    return checkpoint.restore(planned_graph=planned_graph)
