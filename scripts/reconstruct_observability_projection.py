"""Read-only, in-memory historical reconstruction with the production projection builder.

Stdout is consumed in memory by the replay harness, never saved as diagnostics.
This is not a claim that an original intermediate HTTP response was retained.
"""

import json
import subprocess
from datetime import UTC, datetime

import src.phase4_product.postgresql_backend as backend
from src.domain.enums import TaskStatus

RUN = "RUN-645b12e5-12a1-4a50-8446-684c1c8b9cfc"


def query(sql):
    return json.loads(
        subprocess.check_output(
            [
                "docker",
                "exec",
                "verifiable-financial-postgres",
                "psql",
                "-U",
                "vfa",
                "-d",
                "verifiable_financial_agent",
                "-At",
                "-c",
                sql,
            ],
            text=True,
        )
    )


aggregate = query(f"SELECT payload FROM research_runs WHERE run_id='{RUN}'")
obj = query("SELECT payload FROM research_objects WHERE object_id='OBJ-NVDA'")
events = [
    backend.RuntimeEvent.model_validate(e)
    for e in query(
        f"SELECT jsonb_agg(payload ORDER BY sequence) FROM runtime_events WHERE run_id='{RUN}'"
    )
]
artifacts = backend.CompletedRunArtifacts.model_validate(aggregate["artifacts"])


def reconstruct(sequence):
    run = backend.ResearchRun.model_validate(aggregate["run"])
    run.status = backend.RunStatus.RUNNING if sequence == 606 else backend.RunStatus.REVIEW
    run.completed_at = None
    run.updated_at = next(e.timestamp for e in events if e.sequence == sequence)
    actual = backend.ActualRuntimeGraph.model_validate(aggregate["runtime"]["actual_graph"])
    if sequence == 606:
        task = next(t for t in actual.tasks if t.task_id.endswith(":synthesis"))
        task.status = TaskStatus.RUNNING
        task.progress = next(e.payload["progress"] for e in events if e.sequence == 606)
        task.result_ref = None
    absent = backend.AvailabilityV1.unavailable(
        backend.AvailabilityStatus.NOT_GENERATED, "NOT_GENERATED"
    )
    projection = backend.build_atomic_run_projection(
        expected_object_id="OBJ-NVDA",
        expected_run_id=RUN,
        projection_revision=sequence - 13,
        projection_sequence=sequence,
        generated_at=datetime.now(UTC),
        research_object=backend.ResearchObject.model_validate(obj),
        run=run,
        goal=backend.ResearchGoal.model_validate(aggregate["goal"]),
        confirmed_scheme=backend.ResearchSchemeSnapshot.model_validate(aggregate["scheme"]),
        planned_graph=backend.PlannedTaskGraph.model_validate(
            aggregate["runtime"]["planned_graph"]
        ),
        actual_graph=actual,
        proof_summary=backend.ProofSummaryV1(availability=absent, policy="UNKNOWN", status=None),
        review_availability=backend.AvailabilityV1.unavailable(
            backend.AvailabilityStatus.PENDING, "REVIEW_PENDING"
        ),
        result_availability=absent,
        artifact_availability=absent,
        execution_availability=absent,
        path_changes=backend.PostgreSQLPhase4ProductBackend._path_change_sources(artifacts, actual),
        events=tuple(
            backend.normalize_runtime_event_v1(e) for e in events if e.sequence <= sequence
        ),
    )
    return projection.model_dump(mode="json")


print(json.dumps({"initial": reconstruct(606), "review": reconstruct(609)}))
