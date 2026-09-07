"""Additive durable research assets; never updates historical Run records."""

from collections.abc import Callable

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from src.application.persistence import ResearchObjectRow, ResearchRunAggregateRow
from src.infrastructure.database.base import Base
from src.phase4_product.errors import product_error
from src.phase4_product.memory_contracts import (
    ResearchMemorySnapshot,
    ResearchObjectVersion,
    ResearchViewVersion,
)


class ResearchObjectVersionRow(Base):
    __tablename__ = "research_object_versions"
    __table_args__ = (
        UniqueConstraint("object_id", "source_run_id"),
        CheckConstraint("version >= 1"),
    )
    object_id: Mapped[str] = mapped_column(
        ForeignKey("research_objects.object_id"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.run_id"))
    payload: Mapped[dict] = mapped_column(JSON)


class ResearchViewVersionRow(Base):
    __tablename__ = "research_view_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "object_version"],
            ["research_object_versions.object_id", "research_object_versions.version"],
        ),
        UniqueConstraint("object_id", "source_run_id"),
        UniqueConstraint("object_id", "object_version"),
        CheckConstraint("version >= 1"),
    )
    object_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    object_version: Mapped[int] = mapped_column(Integer)
    source_run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.run_id"))
    payload: Mapped[dict] = mapped_column(JSON)


class ResearchMemoryPointerRow(Base):
    __tablename__ = "research_object_memory_pointers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "latest_research_object_version"],
            ["research_object_versions.object_id", "research_object_versions.version"],
        ),
        ForeignKeyConstraint(
            ["object_id", "latest_research_view_version"],
            ["research_view_versions.object_id", "research_view_versions.version"],
        ),
    )
    object_id: Mapped[str] = mapped_column(
        ForeignKey("research_objects.object_id"), primary_key=True
    )
    latest_released_run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.run_id"))
    latest_research_object_version: Mapped[int] = mapped_column(Integer)
    latest_research_view_version: Mapped[int] = mapped_column(Integer)


class ResearchMemoryRepository:
    def __init__(self, sessions: async_sessionmaker):
        self.sessions = sessions

    async def _read(self, session, object_id):
        pointer = await session.get(ResearchMemoryPointerRow, object_id)
        if pointer is None:
            return ResearchMemorySnapshot(
                research_object_id=object_id,
                latest_released_run_id=None,
                latest_research_object_version=None,
                latest_research_view_version=None,
                object_version=None,
                current_view=None,
            )
        obj = await session.get(
            ResearchObjectVersionRow, (object_id, pointer.latest_research_object_version)
        )
        view = await session.get(
            ResearchViewVersionRow, (object_id, pointer.latest_research_view_version)
        )
        if obj is None or view is None:
            raise product_error("INTEGRITY_FAILURE", "memory pointer has no exact version")
        snapshot = ResearchMemorySnapshot(
            research_object_id=object_id,
            latest_released_run_id=pointer.latest_released_run_id,
            latest_research_object_version=pointer.latest_research_object_version,
            latest_research_view_version=pointer.latest_research_view_version,
            object_version=ResearchObjectVersion.model_validate(obj.payload),
            current_view=ResearchViewVersion.model_validate(view.payload),
        )
        if (
            obj.source_run_id != snapshot.latest_released_run_id
            or view.source_run_id != snapshot.latest_released_run_id
            or view.object_version != obj.version
        ):
            raise product_error("INTEGRITY_FAILURE", "memory row identity mismatch")
        return snapshot

    async def read(self, object_id):
        async with self.sessions() as session:
            if await session.get(ResearchObjectRow, object_id) is None:
                raise product_error("NOT_FOUND", "research Object not found")
            return await self._read(session, object_id)

    async def read_exact(self, object_id, base_run_id, base_view_id):
        async with self.sessions() as session:
            source = await session.get(ResearchRunAggregateRow, base_run_id)
            if source is None or source.object_id != object_id:
                raise product_error("IDENTITY_MISMATCH", "base Run belongs to another Object")
            if source.status != "RELEASED":
                raise product_error("NOT_RELEASED", "base Run must be released")
            row = await session.scalar(
                select(ResearchViewVersionRow).where(
                    ResearchViewVersionRow.object_id == object_id,
                    ResearchViewVersionRow.source_run_id == base_run_id,
                )
            )
            if row is None:
                raise product_error("NOT_FOUND", "exact base memory unavailable")
            view = ResearchViewVersion.model_validate(row.payload)
            if (
                view.research_object_id,
                view.source_run_id,
                view.research_view_version_id,
                view.research_view_version,
            ) != (object_id, base_run_id, base_view_id, row.version):
                raise product_error("IDENTITY_MISMATCH", "exact base view mismatch")
            return view

    async def historical_snapshot(self, object_id, base_run_id, base_view_id):
        view = await self.read_exact(object_id, base_run_id, base_view_id)
        async with self.sessions() as session:
            obj = await session.get(
                ResearchObjectVersionRow, (object_id, view.research_object_version)
            )
            if obj is None:
                raise product_error("INTEGRITY_FAILURE", "historical Object version missing")
            return ResearchMemorySnapshot(
                research_object_id=object_id,
                latest_released_run_id=base_run_id,
                latest_research_object_version=view.research_object_version,
                latest_research_view_version=view.research_view_version,
                object_version=ResearchObjectVersion.model_validate(obj.payload),
                current_view=view,
            )

    async def materialize(
        self,
        obj: ResearchObjectVersion,
        view: ResearchViewVersion,
        *,
        checkpoint: Callable[[str], None] | None = None,
        expected_base=None,
    ):
        # Validate closure even for direct repository callers. No update API exists.
        ResearchMemorySnapshot(
            research_object_id=obj.research_object_id,
            latest_released_run_id=obj.source_run_id,
            latest_research_object_version=obj.object_version,
            latest_research_view_version=view.research_view_version,
            object_version=obj,
            current_view=view,
        )
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"isolation_level": "READ COMMITTED"})
            locked = await session.scalar(
                select(ResearchObjectRow)
                .where(ResearchObjectRow.object_id == obj.research_object_id)
                .with_for_update()
            )
            if locked is None:
                raise product_error("NOT_FOUND", "research Object not found")
            source = await session.get(ResearchRunAggregateRow, obj.source_run_id)
            if source is None or source.object_id != obj.research_object_id:
                raise product_error("IDENTITY_MISMATCH", "memory source does not belong to Object")
            if source.status != "RELEASED":
                raise product_error("NOT_RELEASED", "memory requires a released Run")
            current = await self._read(session, obj.research_object_id)
            if current.latest_released_run_id == obj.source_run_id:
                return current
            if current.latest_released_run_id is not None:
                if expected_base is None:
                    raise product_error(
                        "CONFLICT", "current memory is bound; explicit advancement required"
                    )
                raw = source.payload.get("run", {})
                if (
                    expected_base is None
                    or (
                        current.latest_released_run_id,
                        current.current_view.research_view_version_id,
                    )
                    != expected_base
                    or (raw.get("base_run_id"), raw.get("base_research_view_version"))
                    != expected_base
                ):
                    raise product_error(
                        "CONFLICT", "explicit base authority or current pointer mismatch"
                    )
                if (
                    obj.object_version != current.latest_research_object_version + 1
                    or view.research_view_version != current.latest_research_view_version + 1
                ):
                    raise product_error("CONFLICT", "memory advancement must be consecutive")
            elif (
                expected_base is not None
                or obj.object_version != 1
                or view.research_view_version != 1
            ):
                raise product_error("CONFLICT", "initial memory must use version one")
            session.add(
                ResearchObjectVersionRow(
                    object_id=obj.research_object_id,
                    version=obj.object_version,
                    source_run_id=obj.source_run_id,
                    payload=obj.model_dump(mode="json"),
                )
            )
            await session.flush()
            if checkpoint:
                checkpoint("object")
            session.add(
                ResearchViewVersionRow(
                    object_id=obj.research_object_id,
                    version=view.research_view_version,
                    object_version=obj.object_version,
                    source_run_id=obj.source_run_id,
                    payload=view.model_dump(mode="json"),
                )
            )
            await session.flush()
            if checkpoint:
                checkpoint("view")
            pointer = await session.get(ResearchMemoryPointerRow, obj.research_object_id)
            if pointer is None:
                session.add(
                    ResearchMemoryPointerRow(
                        object_id=obj.research_object_id,
                        latest_released_run_id=obj.source_run_id,
                        latest_research_object_version=obj.object_version,
                        latest_research_view_version=view.research_view_version,
                    )
                )
            else:
                pointer.latest_released_run_id = obj.source_run_id
                pointer.latest_research_object_version = obj.object_version
                pointer.latest_research_view_version = view.research_view_version
            await session.flush()
            if checkpoint:
                checkpoint("pointer")
            return await self._read(session, obj.research_object_id)
