"""Opt-in atomic lease-fenced use of the existing ResearchMemoryRepository.

No automatic production selection. A separately authorized frozen closure operation
must bind the exact previously validated Memory snapshot and durable released result.
Existing Memory repository release/base/consecutive-version guards remain intact.
"""

from copy import deepcopy

from sqlalchemy import select, update

from src.application.persistence import ReleasedResearchResultRow
from src.domain.execution_contract import ContractDenied, fingerprint
from src.domain.released_research_result import ReleasedResearchResult
from src.infrastructure.database.execution_ledger import ExecutionIntentRow
from src.infrastructure.database.research_memory import (
    ResearchObjectVersionRow,
    ResearchViewVersionRow,
)


def memory_snapshot_hash(obj, view, expected_base=None):
    return fingerprint(
        {
            "object": obj.model_dump(mode="json"),
            "view": view.model_dump(mode="json"),
            "expected_base": expected_base,
        }
    )


async def materialize_memory_v1(
    *,
    repository,
    store,
    token,
    obj,
    view,
    clock,
    memory_authorized,
    expected_base=None,
    checkpoint=None,
):
    """Materialize missing Memory once; ledger + Memory commit or rollback together.

    No Proof, calculation, research or Run-state mutation occurs here. The caller
    constructs ``obj/view`` through the existing validated Memory-source builder,
    then prospectively freezes their digest into the closure contract.
    """
    if not memory_authorized:
        raise ContractDenied("MEMORY_AUTHORIZATION_REQUIRED")
    expected_hash = memory_snapshot_hash(obj, view, expected_base)

    async def guard(session):
        locked = await session.execute(
            update(ExecutionIntentRow)
            .where(
                ExecutionIntentRow.intent_id == token.intent_id,
            )
            .values(revision=ExecutionIntentRow.revision + 1)
        )
        if locked.rowcount != 1:
            raise ContractDenied("LEGACY_NOT_RESUMABLE")
        row = await session.scalar(
            select(ExecutionIntentRow)
            .where(
                ExecutionIntentRow.intent_id == token.intent_id,
            )
            .execution_options(populate_existing=True)
        )
        doc = deepcopy(row.payload)
        operation = store._fence(doc, token, clock())
        contract = operation["contract"]
        if (
            obj.research_object_id != contract["object_id"]
            or obj.source_run_id != contract["run_id"]
            or obj.source_run_id != doc["run_id"]
            or contract["input_hashes"].get("memory_snapshot") != expected_hash
        ):
            raise ContractDenied("MEMORY_SNAPSHOT_IDENTITY_MISMATCH")
        released = doc["release"].get("RELEASED")
        if (
            released is None
            or released["reference"] != obj.source_released_result_id
            or released["object_id"] != obj.research_object_id
            or released["run_id"] != obj.source_run_id
        ):
            raise ContractDenied("RELEASE_IDENTITY_MISMATCH")
        result_row = await session.get(ReleasedResearchResultRow, obj.source_released_result_id)
        if (
            result_row is None
            or result_row.run_id != obj.source_run_id
            or fingerprint(result_row.payload) != contract["input_hashes"].get("released_result")
        ):
            raise ContractDenied("DURABLE_RELEASE_BINDING_MISMATCH")
        result = ReleasedResearchResult.model_validate(result_row.payload)
        if (
            result.result_id != obj.source_released_result_id
            or result.run_id != obj.source_run_id
            or result.canonical_record_id != obj.source_canonical_record_id
        ):
            raise ContractDenied("DURABLE_RELEASE_BINDING_MISMATCH")
        # Existing repository's idempotent branch returns by source Run; V1 also
        # requires exact immutable content, never accepts another same-Run payload.
        for model, expected, version in (
            (ResearchObjectVersionRow, obj, obj.object_version),
            (ResearchViewVersionRow, view, view.research_view_version),
        ):
            existing = await session.get(model, (obj.research_object_id, version))
            if existing is not None and fingerprint(existing.payload) != fingerprint(expected):
                raise ContractDenied("MEMORY_IMMUTABLE_CONTENT_CONFLICT")
        stages = doc["release"]
        for stage, reference in (
            ("MEMORY_MATERIALIZED", view.research_view_version_id),
            ("COMPLETED", obj.source_released_result_id),
        ):
            prior = stages.get(stage)
            if prior and (
                prior["reference"] != reference
                or prior["run_id"] != obj.source_run_id
                or prior["object_id"] != obj.research_object_id
            ):
                raise ContractDenied("MEMORY_STAGE_BINDING_CONFLICT")
            if not prior:
                stages[stage] = {
                    "reference": reference,
                    "run_id": obj.source_run_id,
                    "object_id": obj.research_object_id,
                    "epoch": token.epoch,
                }
        row.payload = doc

    return await repository.materialize(
        obj, view, expected_base=expected_base, checkpoint=checkpoint, transaction_guard=guard
    )
