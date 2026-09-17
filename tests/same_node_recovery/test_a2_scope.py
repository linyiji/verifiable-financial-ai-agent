"""Admission and execution must agree on the exact saved evidence stream."""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from src.application.persistence import SQLAlchemyApplicationRepository
from src.domain.node_binding import BindingDenied
from src.domain.recovery import recovery_decision_is_current
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401
from tests.same_node_recovery.a2_process_worker import unrelated
from tests.same_node_recovery.test_a1_admission import pending_case
from tests.same_node_recovery.test_durable import configured

pytestmark = pytest.mark.skipif(
    not os.environ.get("SAME_NODE_DISPOSABLE_POSTGRES"), reason="Disposable PostgreSQL required",
)


@pytest.mark.parametrize("case", ["context", "contract", "lineage", "task", "operation", "exact"])
async def test_fresh_process_scope(database, tmp_path, case):  # noqa: F811
    _, sessions = database
    async with sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
    for phase in ("A", "B"):
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "tests.same_node_recovery.a2_process_worker",
            os.environ["TEST_POSTGRESQL_URL"], schema, str(tmp_path), phase, case,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await process.communicate()
        assert process.returncode == 0, output.decode()
    first, second = [json.loads((tmp_path / f"{p}.json").read_text()) for p in ("A", "B")]
    a, b = first["root"], second["root"]
    assert first["run_id"] == second["run_id"] and first["task_id"] == second["task_id"]
    for field in ("frozen_graph", "execution_profile_snapshot_digest", "scenario_snapshot_digest"):
        assert a[field] == b[field]
    current = b["attempts"][first["task_id"]]
    if case == "exact":
        assert second["denied"] and current["generation"] == 1 and current["status"] == "FAILED"
        assert not second["entries"] and not any(second["calls"].values())
        assert a == b
    else:
        assert not second["denied"] and current["generation"] == 2
        assert current["status"] == "COMMITTED" and len(second["entries"]) == 1
        assert all(r["reason_code"] != "INTERRUPTED_EXECUTION" for r in second["records"])
        assert len(b["current_results"]) == 2
    if destination := os.environ.get("SAME_NODE_RECEIPTS"):
        folder = Path(destination) / "a2-process" / case
        folder.mkdir(parents=True, exist_ok=True)
        for phase in ("A", "B"):
            (folder / f"{phase}.json").write_bytes((tmp_path / f"{phase}.json").read_bytes())


@pytest.mark.parametrize("case", ["context", "contract", "lineage", "task", "operation", "exact"])
async def test_admission_adaptive_invariant(database, tmp_path, case):  # noqa: F811
    _, sessions = database
    _, pending, target, store, terminal = await pending_case(tmp_path, sessions)
    await store.append(unrelated(terminal, case))
    prior = pending.node_binding.attempts[target.task_id]
    records = await store.records(pending.run.run_id, target.task_id)
    # This is the same current-decision function called by AdaptiveRecovery.
    execution_allowed = recovery_decision_is_current(
        records, terminal.scope, prior.admission.attempt_reservation_id, prior.recovery,
    )
    try:
        repo = SQLAlchemyApplicationRepository(sessions)
        async with repo._binding_transaction(pending.run.run_id):
            await repo._validate_current_recovery_evidence(prior)
        admission_allowed = True
    except BindingDenied:
        admission_allowed = False
    assert admission_allowed == execution_allowed == (case != "exact")
    assert recovery_decision_is_current(
        list(reversed(records)), terminal.scope,
        prior.admission.attempt_reservation_id, prior.recovery,
    ) == execution_allowed  # List / database row order cannot decide authority.


async def test_applicable_terminal_after_reservation(database, tmp_path):  # noqa: F811
    _, sessions = database
    _, pending, target, store, terminal = await pending_case(tmp_path, sessions)
    repo = SQLAlchemyApplicationRepository(sessions)
    service, _, _, clients = await configured(
        tmp_path, repository=repo, store=store, sessions=sessions, persist=False,
    )
    original = repo.enter_node_execution

    async def enter(admission):
        # After legal reservation, before AdaptiveRecovery guard.
        await store.append(terminal)
        return await original(admission)

    repo.enter_node_execution = enter
    with pytest.raises(ExceptionGroup, match="runtime tasks failed"):
        await service.execute_run(pending.run.run_id)
    after = await repo.get_run_fresh(pending.run.run_id)
    assert after.node_binding.attempts[target.task_id].generation == 2
    assert after.node_binding.attempts[target.task_id].status == "RESULT_UNKNOWN"
    assert not any(client.calls for client in clients.values())
    latest = (await store.records(pending.run.run_id, target.task_id))[-1]
    assert latest.reason_code == "INTERRUPTED_EXECUTION"


async def test_authoritative_timestamp_and_ties(database, tmp_path):  # noqa: F811
    _, sessions = database
    _, pending, target, store, terminal = await pending_case(tmp_path, sessions)
    prior = pending.node_binding.attempts[target.task_id]
    records = await store.records(pending.run.run_id, target.task_id)
    decision = next(r for r in records if r.record_id == prior.recovery["refs"][-1])
    next_time = datetime.fromisoformat(decision.timestamp) + timedelta(seconds=1)
    newer = decision.model_copy(update={
        "record_id": "REC-" + str(uuid4()),
        "timestamp": next_time.isoformat(),
    })
    args = (terminal.scope, prior.admission.attempt_reservation_id, prior.recovery)
    assert recovery_decision_is_current(list(reversed(records)), *args)
    assert not recovery_decision_is_current([newer, *records], *args)
    tied = newer.model_copy(update={"timestamp": decision.timestamp})
    assert not recovery_decision_is_current([tied, *records], *args)
    assert not recovery_decision_is_current([*records, tied], *args)
    # Missing reservation is exact, never a wildcard for this durable lineage.
    missing = terminal.model_copy(update={"node_reservation_id": None})
    assert recovery_decision_is_current([*records, missing], *args)


@pytest.mark.parametrize("field", [
    "run_id", "task_id", "object_id", "scheme_id", "task_profile", "agent_id",
    "operation_id", "context_hash", "contract_hash",
])
async def test_every_scope_component_is_exact(database, tmp_path, field):  # noqa: F811
    from src.domain.recovery import Scope, applicable_recovery_evidence

    _, sessions = database
    _, _, _, _, terminal = await pending_case(tmp_path, sessions)
    identity = terminal.scope.model_dump()
    if field == "run_id":
        identity["run_id"] = "OTHER-RUN"
        identity["task_id"] = "OTHER-RUN:1"
    elif field == "task_id":
        identity[field] = identity["run_id"] + ":other"
    elif field.endswith("_hash"):
        identity[field] = "sha256:" + "0" * 64
    else:
        identity[field] = "other"
    changed = terminal.model_copy(update={"scope": Scope.model_validate(identity)})
    assert applicable_recovery_evidence(
        [terminal, changed], terminal.scope, terminal.node_reservation_id,
    ) == [terminal]
    legacy = terminal.model_copy(update={"node_reservation_id": None})
    assert applicable_recovery_evidence([terminal, legacy], terminal.scope, None) == [legacy]
