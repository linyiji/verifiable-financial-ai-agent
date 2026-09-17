import asyncio
import json
import os
import sys

import pytest
from sqlalchemy import text

from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("SAME_NODE_DISPOSABLE_POSTGRES"), reason="Disposable PostgreSQL required"
)


async def test_process_boundary(database, tmp_path):  # noqa: F811
    engine, sessions = database
    async with sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
    for phase in ("A", "B"):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "tests.same_node_recovery.process_worker",
            os.environ["TEST_POSTGRESQL_URL"],
            schema,
            str(tmp_path),
            phase,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await process.communicate()
        assert process.returncode == 0, output.decode()
    first = json.loads((tmp_path / "process-A.json").read_text())
    second = json.loads((tmp_path / "process-B.json").read_text())
    a, b = first["root"], second["root"]
    assert first["run_id"] == second["run_id"]
    assert a["frozen_graph"] == b["frozen_graph"]
    assert a["execution_profile_snapshot_digest"] == b["execution_profile_snapshot_digest"]
    assert a["scenario_snapshot_digest"] == b["scenario_snapshot_digest"]
    assert set(a["results"]) <= set(b["results"])
    failed = next(v for v in a["attempts"].values() if v["status"] == "FAILED")
    task_id = failed["admission"]["task_id"]
    succeeded = b["attempts"][task_id]
    assert succeeded["status"] == "COMMITTED" and succeeded["generation"] == 2
    assert failed["admission"]["task_fingerprint"] == succeeded["admission"]["task_fingerprint"]
    assert b["attempt_history"][failed["admission"]["attempt_reservation_id"]] == failed
    assert second["records"][: len(first["records"])] == first["records"]
    assert len({v["producer_task_id"] for v in b["results"].values()}) == len(b["results"]) == 2
    assert second["upstream_calls_in_process"] == 0
    assert first["saved_calculations"] == second["saved_calculations"]
    assert first["native_calls"] == ["revenue_growth", "ebitda_margin", "ebitda_margin"]
    assert second["native_calls"] == ["ebitda_margin"]  # Rejected mismatch; no saved result.
    assert all(b["results"][key] == value for key, value in a["results"].items())
    destination = os.environ.get("SAME_NODE_RECEIPTS")
    if destination:
        from pathlib import Path

        for phase in ("A", "B"):
            await asyncio.to_thread(
                Path(destination, f"process-{phase}.json").write_bytes,
                (tmp_path / f"process-{phase}.json").read_bytes(),
            )


async def test_postgresql_owner_and_reservation_race(database, tmp_path):  # noqa: F811
    from src.application.execution import IntegratedTaskExecutor
    from src.application.persistence import SQLAlchemyApplicationRepository
    from src.domain.node_binding import BindingDenied
    from src.infrastructure.database.recovery import RecoveryEvidenceStore
    from tests.same_node_recovery.test_durable import configured

    _, sessions = database
    repository = SQLAlchemyApplicationRepository(sessions)
    service, value, _, _ = await configured(
        tmp_path,
        repository=repository,
        store=RecoveryEvidenceStore(sessions),
        sessions=sessions,
    )
    pending = await service.execute_run(value.run.run_id)
    target = pending.runtime.actual_graph.tasks[1]
    prior = pending.node_binding.attempts[target.task_id].admission
    fresh_repository = SQLAlchemyApplicationRepository(sessions)
    owners = await asyncio.gather(
        repository.claim_execution(value.run.run_id),
        fresh_repository.claim_execution(value.run.run_id),
        return_exceptions=True,
    )
    assert sum(isinstance(v, BindingDenied) for v in owners) == 1
    owner = next(v for v in owners if not isinstance(v, BaseException))
    fresh = await fresh_repository.validate_execution(owner)
    requirements = IntegratedTaskExecutor(service, fresh).admission_requirements(target)
    reservations = await asyncio.gather(
        repository.reserve_node(owner, target, requirements),
        fresh_repository.reserve_node(owner, target, requirements),
        return_exceptions=True,
    )
    assert sum(isinstance(v, BindingDenied) for v in reservations) == 1
    with pytest.raises(BindingDenied):
        await fresh_repository.dispatch_node(prior)
    root = (await fresh_repository.get_run_fresh(value.run.run_id)).node_binding
    assert len(root.attempt_history) == 1
    assert sum(a.status in {"RESERVED", "DISPATCHED"} for a in root.attempts.values()) == 1
