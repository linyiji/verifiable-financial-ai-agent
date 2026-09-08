"""One owner-authorized, closure-only attempt. Never invokes the research scheduler.

The original failed aggregate and event digest are retained before staging work.
A crash/failed attempt consumes the authorization: this operation never retries.
"""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from src.application.extensions import ProofWorkflowOutcome
from src.application.persistence import (
    ResearchRunAggregateRow,
    RuntimeEventRow,
    SQLAlchemyApplicationRepository,
)
from src.assurance.proof_policy import ProofPolicy
from src.domain.enums import RunStatus
from src.domain.proof import (
    ProofArtifactReference,
    ProofInputCommitment,
    ProofRecord,
    ProofVerificationRecord,
)
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType
from src.infrastructure.database.base import Base
from src.infrastructure.database.models import (
    ProofArtifactReferenceRow,
    ProofInputCommitmentRow,
    ProofRecordRow,
    ProofVerificationRecordRow,
)
from src.runtime.events import InMemoryRuntimeEventStore, validate_event_log


class ClosureRecoveryRecordRow(Base):
    __tablename__ = "closure_recovery_records"
    __table_args__ = (UniqueConstraint("run_id", "kind"),)
    record_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.run_id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)


def fingerprint(value):
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
    )


class NoProofExecution:
    async def execute(self, **kwargs):
        raise RuntimeError("Closure recovery must never execute a Proof workflow")


async def retained_proof_outcome(session, aggregate):
    run_id = aggregate.run.run_id
    collections = []
    manifest = {}
    for row_type, model, key in (
        (ProofRecordRow, ProofRecord, "proof_id"),
        (ProofInputCommitmentRow, ProofInputCommitment, "commitment_id"),
        (ProofVerificationRecordRow, ProofVerificationRecord, "verification_id"),
        (ProofArtifactReferenceRow, ProofArtifactReference, "artifact_id"),
    ):
        rows = list(await session.scalars(select(row_type).where(row_type.run_id == run_id)))
        values = []
        for row in rows:
            item = model.model_validate(row.payload)
            if getattr(row, key) != getattr(item, key) or getattr(item, "run_id", run_id) != run_id:
                raise ValueError("Retained Proof row identity mismatch")
            values.append(item)
        collections.append(values)
        manifest[row_type.__tablename__] = sorted(
            (item.model_dump(mode="json") for item in values), key=lambda value: value[key]
        )
    proofs, commitments, verifications, artifacts = collections
    if not proofs or any(p.status.value != "VERIFIED" for p in proofs):
        raise ValueError("Only existing VERIFIED Proofs can be reused")

    def exact(items, attr, value):
        matches = [item for item in items if getattr(item, attr) == value]
        if len(matches) != 1:
            raise ValueError("Retained Proof lineage must be unambiguous")
        return matches[0]

    outcome = ProofWorkflowOutcome(
        requirements={
            c.calculation_id: ProofPolicy(require_material_calculations=True).requirement_for(c)
            for c in aggregate.artifacts.calculations
        },
        proofs={p.calculation_id: p for p in proofs},
        input_commitments={
            p.calculation_id: exact(commitments, "calculation_id", p.calculation_id) for p in proofs
        },
        verifications={
            p.calculation_id: exact(verifications, "proof_id", p.proof_id) for p in proofs
        },
        artifacts={p.calculation_id: exact(artifacts, "proof_id", p.proof_id) for p in proofs},
        runtime_state={
            "status": "VERIFIED",
            "proof_id": proofs[0].proof_id,
            "image_id": proofs[0].image_id,
            "dev_mode": False,
        },
        limitations=(
            "The RISC Zero proof verifies program execution over bound inputs; it "
            "does not prove that provider data is objectively true.",
        ),
    )
    return outcome, fingerprint(manifest)


async def recover_closure(
    *,
    sessions,
    service,
    run_id,
    expected_snapshot_hash,
    source_sha,
    owner_authorization,
    materialize_memory,
):
    if owner_authorization != "REUSE_REVIEW_AND_VERIFIED_PROOF_RELEASE_REPORT_MEMORY_ONCE":
        raise ValueError("Explicit closure-only owner authorization is required")
    if len(source_sha) != 40 or any(c not in "0123456789abcdef" for c in source_sha):
        raise ValueError("A source commit is required")
    attempt_id = f"CLOSURE-{uuid4()}"
    async with sessions() as session, session.begin():
        row = await session.scalar(
            select(ResearchRunAggregateRow)
            .where(ResearchRunAggregateRow.run_id == run_id)
            .with_for_update()
        )
        if (
            row is None
            or row.status != "FAILED"
            or fingerprint(row.payload) != expected_snapshot_hash
        ):
            raise ValueError("Exact failed snapshot precondition failed")
        if await session.scalar(
            select(ClosureRecoveryRecordRow).where(ClosureRecoveryRecordRow.run_id == run_id)
        ):
            raise ValueError("Closure recovery attempt already consumed; no retry")
        aggregate = SQLAlchemyApplicationRepository._to_aggregate(row.payload)
        if aggregate.artifacts.released_result is not None or aggregate.artifacts.review is None:
            raise ValueError("Expected failed, reviewed, unreleased Run")
        diagnostic = aggregate.artifacts.closure_diagnostic
        if not diagnostic or diagnostic.get("code") != "RELEASE_GATE_BLOCKED":
            raise ValueError("Only a Release gate closure failure is eligible")
        rows = list(
            await session.scalars(
                select(RuntimeEventRow)
                .where(RuntimeEventRow.run_id == run_id)
                .order_by(RuntimeEventRow.sequence)
            )
        )
        events = [RuntimeEvent.model_validate(r.payload) for r in rows]
        terminal = validate_event_log(run_id, events)
        if (
            terminal is None
            or terminal.type is not RuntimeEventType.RUN_FAILED
            or terminal.payload.get("status") != "FAILED"
        ):
            raise ValueError("Exact failed terminal event is required")
        outcome, proof_hash = await retained_proof_outcome(session, aggregate)
        original_events_hash = fingerprint([e.model_dump(mode="json") for e in events])
        session.add(
            ClosureRecoveryRecordRow(
                record_id=attempt_id,
                run_id=run_id,
                kind="STARTED",
                payload={
                    "attempt_id": attempt_id,
                    "source_sha": source_sha,
                    "owner_authorization": owner_authorization,
                    "started_at": datetime.now(UTC).isoformat(),
                    "snapshot_hash": expected_snapshot_hash,
                    "failed_snapshot": row.payload,
                    "failed_event_id": terminal.event_id,
                    "event_hash": original_events_hash,
                    "proof_manifest_hash": proof_hash,
                },
            )
        )
    # Stage against an isolated in-memory stream. No running worker or provider is used.
    try:
        store = InMemoryRuntimeEventStore()
        for event in events:
            await store.append(event)
        await store.emit(
            run_id=run_id,
            event_type=RuntimeEventType.CLOSURE_RECOVERY_STARTED,
            payload={
                "attempt_id": attempt_id,
                "failed_event_id": terminal.event_id,
                "snapshot_hash": expected_snapshot_hash,
                "status": "REVIEW",
            },
        )
        service.event_store = store
        service.proof_workflow = NoProofExecution()
        await service._assure_and_release(aggregate, proof_outcome=outcome, retain_review=True)
        if aggregate.run.status is not RunStatus.RELEASED:
            raise ValueError("Closure did not release")
        all_events = list(await store.replay(run_id))
        validate_event_log(run_id, all_events)
        async with sessions() as session, session.begin():
            row = await session.scalar(
                select(ResearchRunAggregateRow)
                .where(ResearchRunAggregateRow.run_id == run_id)
                .with_for_update()
            )
            existing_events = list(
                await session.scalars(
                    select(RuntimeEventRow)
                    .where(RuntimeEventRow.run_id == run_id)
                    .order_by(RuntimeEventRow.sequence)
                )
            )
            if (
                fingerprint(row.payload) != expected_snapshot_hash
                or fingerprint([r.payload for r in existing_events]) != original_events_hash
            ):
                raise ValueError("Failed history changed while staging recovery")
            _, current_proof_hash = await retained_proof_outcome(session, aggregate)
            if current_proof_hash != proof_hash:
                raise ValueError("Proof records changed during recovery")
            row.payload = SQLAlchemyApplicationRepository._payload(aggregate)
            row.status = "RELEASED"
            row.updated_at = aggregate.run.completed_at
            row.projection_revision += 1
            row.projection_sequence = all_events[-1].sequence
            await SQLAlchemyApplicationRepository._persist_children(session, aggregate)
            for event in all_events[len(events) :]:
                session.add(
                    RuntimeEventRow(
                        event_id=event.event_id,
                        run_id=run_id,
                        sequence=event.sequence,
                        payload=event.model_dump(mode="json"),
                    )
                )
            session.add(
                ClosureRecoveryRecordRow(
                    record_id=attempt_id + "-RELEASED",
                    run_id=run_id,
                    kind="RELEASED",
                    payload={
                        "attempt_id": attempt_id,
                        "completed_at": datetime.now(UTC).isoformat(),
                        "projection_sequence": all_events[-1].sequence,
                        "model_calls": 0,
                        "proof_calls": 0,
                        "calculation_calls": 0,
                    },
                )
            )
        memory = await materialize_memory(aggregate.run.research_object_id, run_id)
        async with sessions() as session, session.begin():
            session.add(
                ClosureRecoveryRecordRow(
                    record_id=attempt_id + "-COMPLETED",
                    run_id=run_id,
                    kind="COMPLETED",
                    payload={
                        "attempt_id": attempt_id,
                        "completed_at": datetime.now(UTC).isoformat(),
                        "memory": memory.model_dump(mode="json"),
                    },
                )
            )
        return aggregate
    except Exception as exc:
        async with sessions() as session, session.begin():
            session.add(
                ClosureRecoveryRecordRow(
                    record_id=attempt_id + "-FAILED",
                    run_id=run_id,
                    kind="FAILED",
                    payload={
                        "attempt_id": attempt_id,
                        "failed_at": datetime.now(UTC).isoformat(),
                        "error_type": type(exc).__name__,
                    },
                )
            )
        raise
