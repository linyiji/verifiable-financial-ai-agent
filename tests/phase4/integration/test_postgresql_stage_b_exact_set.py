"""Exact membership and submitted order through the real PostgreSQL committer."""
import os
from contextlib import asynccontextmanager

import pytest

from src.domain.node_binding import BindingDenied, OutputRecord, canonical_value, digest
from tests.phase4.integration.test_postgresql_watermark_binding import bound_publisher

pytestmark = pytest.mark.skipif(
    "TEST_POSTGRESQL_URL" not in os.environ, reason="isolated PostgreSQL required",
)

SHAPES = [
    ("acquisition", "calculation:GROWTH", "calculation:MARGIN-BAD",
     "calculation:MARGIN", "agent-context"),
    ("acquisition", "agent-context"),
]


async def inputs(repo, admission, steps):
    return tuple([
        (await repo.bind_resolved_inputs(
            admission, step_id=step, materials=(), payload={"step": step},
        )).resolved_input_binding_id
        for step in steps
    ])


def snapshot(value, admission, ids):
    task = value.runtime.task(admission.task_id)
    payload = {
        "task_output": canonical_value(value.artifacts.task_outputs.get(task.task_id, {})),
        "output_outcomes": canonical_value(task.output_outcomes),
        "coverage": canonical_value(task.evidence_source_coverage),
        "admission_binding_id": admission.admission_binding_id,
        "resolved_inputs": list(ids),
    }
    identity = digest(payload, "task-output-snapshot/v1")
    return OutputRecord(
        kind="TASK_OUTPUT_SNAPSHOT", record_id=identity, content_digest=identity,
        location="node_binding.results", record_schema="task-output-snapshot/v1",
        payload_snapshot=payload,
    )


@pytest.mark.parametrize("steps", SHAPES, ids=["fundamentals-five", "peers-two"])
@pytest.mark.parametrize("reverse", [False, True], ids=["root-forward", "root-reverse"])
@pytest.mark.parametrize("submit_reverse", [False, True])
async def test_root_order_only_preserves_submitted_snapshot_and_result(
    monkeypatch, steps, reverse, submit_reverse,
):
    async with bound_publisher() as (repo, backend, admissions, owner):
        admission = admissions[0]
        ids = await inputs(repo, admission, steps)
        before = await repo.get_run_fresh(owner.run_id)
        assert set(before.node_binding.resolved_inputs) == set(ids)  # real jsonb roundtrip
        submitted = ids[::-1] if submit_reverse else ids
        original = repo._binding_transaction
        seen = []

        @asynccontextmanager
        async def permuted(run_id):
            async with original(run_id) as value:
                root = value.node_binding
                unchanged = digest(root)
                order = ids[::-1] if reverse else ids
                root.resolved_inputs = {key: root.resolved_inputs[key] for key in order}
                assert digest(root) == unchanged  # only map iteration changed
                seen.append(tuple(root.resolved_inputs))
                yield value

        monkeypatch.setattr(repo, "_binding_transaction", permuted)
        await repo.commit_node_result(
            admission, task=before.runtime.task(admission.task_id), artifacts=before.artifacts,
            output_records=(snapshot(before, admission, submitted),), resolved_ids=submitted,
        )
        assert seen == [ids[::-1] if reverse else ids]
        committed = await repo.get_run_fresh(owner.run_id)
        result = committed.node_binding.results[
            committed.node_binding.current_results[admission.task_id]
        ]
        assert result.resolved_input_binding_ids == submitted
        assert result.output_records[0].payload_snapshot["resolved_inputs"] == list(submitted)
        assert tuple(committed.node_binding.resolved_inputs) == tuple(
            before.node_binding.resolved_inputs
        )


@pytest.mark.parametrize("steps", SHAPES, ids=["fundamentals-five", "peers-two"])
@pytest.mark.parametrize("change", [
    "empty", "missing", "extra", "duplicate", "substitute", "digest", "reservation",
    "ref", "snapshot-order", "stale-owner", "cross-run",
])
async def test_invalid_membership_identity_and_freshness_fail_closed(monkeypatch, steps, change):
    async with bound_publisher() as (repo, backend, admissions, owner):
        admission = admissions[0]
        ids = await inputs(repo, admission, steps)
        before = await repo.get_run_fresh(owner.run_id)
        submitted = ids
        expected_error = "MISSING_INPUT: exact Stage B set"
        if change == "empty":
            submitted = ()
        elif change == "missing":
            submitted = ids[:-1]
        elif change == "extra":
            submitted = (*ids, "foreign-identity")
        elif change == "duplicate":
            submitted = (*ids, ids[0])
        elif change == "substitute":
            submitted = (*ids[:-1], "foreign-identity")
        elif change in {"digest", "reservation", "ref"}:
            original = repo._binding_transaction

            @asynccontextmanager
            async def corrupted(run_id):
                async with original(run_id) as value:
                    step = value.node_binding.resolved_inputs[ids[0]]
                    field = {"digest": "input_digest", "reservation": "reservation_id",
                             "ref": "resolved_input_binding_id"}[change]
                    value.node_binding.resolved_inputs[ids[0]] = step.model_copy(
                        update={field: "forged"},
                    )
                    yield value

            monkeypatch.setattr(repo, "_binding_transaction", corrupted)
            expected_error = "IDENTITY_MISMATCH"
        elif change == "snapshot-order":
            expected_error = "IDENTITY_MISMATCH: scoped task output versus Result snapshot"
        elif change == "stale-owner":
            await repo.close_execution(owner)
            before = await repo.get_run_fresh(owner.run_id)
            expected_error = "STALE_WRITE_REJECTED"
        elif change == "cross-run":
            admission = admission.model_copy(update={"run_id": "FOREIGN-RUN"})
            expected_error = "STATE_REFRESH_REQUIRED"
        record = snapshot(before, admissions[0], ids[::-1] if change == "snapshot-order" else ids)
        with pytest.raises(BindingDenied, match=expected_error):
            await repo.commit_node_result(
                admission, task=before.runtime.task(admissions[0].task_id),
                artifacts=before.artifacts, output_records=(record,), resolved_ids=submitted,
            )
        after = await repo.get_run_fresh(owner.run_id)
        assert repo._payload(after) == repo._payload(before)
        assert not after.node_binding.results
