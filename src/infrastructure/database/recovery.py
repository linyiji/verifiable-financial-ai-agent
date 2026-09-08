"""Additive append-only recovery evidence, independent of historical aggregates."""

from sqlalchemy import JSON, ForeignKey, Index, String, select, text
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.recovery import Capability, RecoveryEvidence
from src.infrastructure.database.base import Base


class RecoveryEvidenceRow(Base):
    __tablename__ = "phase6_recovery_evidence"
    __table_args__ = (
        Index(
            "phase6_recovery_single_entry",
            "run_id",
            "task_id",
            text("(coalesce(payload->'scope'->>'operation_id', 'specialist'))"),
            unique=True,
            postgresql_where=text(
                "payload->>'kind'='ATTEMPT_STARTED' AND payload->>'attempt_number'='1' "
                "AND payload->>'capability_check'='false'"
            ),
        ),
    )
    record_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.run_id"), index=True)
    task_id: Mapped[str] = mapped_column(String(256), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class RecoveryEvidenceStore:
    def __init__(self, sessions):
        self.sessions = sessions

    async def append(self, record):
        record = RecoveryEvidence.model_validate(record)
        async with self.sessions() as session, session.begin():
            session.add(
                RecoveryEvidenceRow(
                    record_id=record.record_id,
                    run_id=record.scope.run_id,
                    task_id=record.scope.task_id,
                    payload=record.model_dump(mode="json"),
                )
            )

    async def records(self, run_id=None, task_id=None):
        query = select(RecoveryEvidenceRow)
        if run_id is not None:
            query = query.where(RecoveryEvidenceRow.run_id == run_id)
        if task_id is not None:
            query = query.where(RecoveryEvidenceRow.task_id == task_id)
        async with self.sessions() as session:
            rows = list(await session.scalars(query))
        result = []
        for row in rows:
            value = RecoveryEvidence.model_validate(row.payload)
            if (
                value.scope.run_id != row.run_id
                or value.scope.task_id != row.task_id
                or value.record_id != row.record_id
            ):
                raise ValueError("Recovery evidence identity mismatch")
            result.append(value)
        return sorted(result, key=lambda item: (item.timestamp, item.record_id))

    async def capabilities(self, scope, routes):
        return capability_facts(await self.records(), scope, routes)


def capability_facts(records, scope, routes):
    return {key: value[0] for key, value in capability_provenance(records, scope, routes).items()}


def capability_provenance(records, scope, routes):
    result = {}
    starts = {r.attempt_id: r for r in records if r.kind == "ATTEMPT_STARTED"}
    for record in records:
        if (
            record.kind != "ATTEMPT_COMPLETED"
            or record.scope.task_profile != scope.task_profile
            or record.scope.contract_hash != scope.contract_hash
            or record.route not in routes
            or record.model != routes[record.route].model
            or record.provider != routes[record.route].provider
        ):
            continue
        start = starts.get(record.attempt_id)
        if start is None or any(
            getattr(start, key) != getattr(record, key)
            for key in ("scope", "route", "provider", "model", "attempt_number", "capability_check")
        ):
            continue
        if record.outcome == "PASS" and record.output_hash:
            result[record.route] = (Capability.VERIFIED, record.record_id)
        elif record.outcome != "PASS" and (
            record.capability_check or record.failure_class == "MODEL_IDENTITY_MISMATCH"
        ):
            result[record.route] = (Capability.QUARANTINED, record.record_id)
    return result


class MemoryRecoveryEvidenceStore:
    """Explicit isolated-test store, never selected by production composition."""

    def __init__(self):
        self.values = []

    async def append(self, record):
        record = RecoveryEvidence.model_validate(record)
        if any(value.record_id == record.record_id for value in self.values):
            raise ValueError("Duplicate immutable record")
        if (
            record.kind == "ATTEMPT_STARTED"
            and record.attempt_number == 1
            and not record.capability_check
            and any(
                value.scope.task_id == record.scope.task_id
                and value.scope.run_id == record.scope.run_id
                and value.scope.operation_id == record.scope.operation_id
                and value.kind == "ATTEMPT_STARTED"
                and value.attempt_number == 1
                and not value.capability_check
                for value in self.values
            )
        ):
            raise ValueError("Duplicate task recovery entry")
        self.values.append(record)

    async def records(self, run_id=None, task_id=None):
        return [
            v
            for v in self.values
            if (run_id is None or v.scope.run_id == run_id)
            and (task_id is None or v.scope.task_id == task_id)
        ]

    async def capabilities(self, scope, routes):
        return capability_facts(self.values, scope, routes)
