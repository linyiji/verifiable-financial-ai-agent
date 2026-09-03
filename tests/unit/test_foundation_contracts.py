from datetime import date

import pytest
from pydantic import ValidationError

from contracts.api.models import PrepareResearchRunRequest
from src.adapters.risc0.pending import PendingProofAdapter
from src.domain.enums import ProofStatus, RunStatus, TaskStatus
from src.domain.proof import ProofRequest
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType
from src.domain.task import PlannedTaskGraph, Task


def test_frozen_status_values() -> None:
    assert RunStatus.RELEASED.value == "RELEASED"
    assert TaskStatus.SELF_CORRECTING.value == "SELF_CORRECTING"


def test_api_contract_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PrepareResearchRunRequest(
            research_object_id="OBJ-NVDA",
            research_goal="Research NVIDIA",
            as_of=date(2026, 9, 3),
            surprise=True,
        )


def test_graph_rejects_unknown_dependency() -> None:
    task = Task(
        task_id="TASK-A",
        run_id="RUN-1",
        task_type="fundamental_analysis",
        goal="Analyze fundamentals",
        assigned_agent="fundamental_analyst",
        skill_id="fundamental_analysis_v1",
        dependencies=["TASK-MISSING"],
    )
    with pytest.raises(ValidationError, match="unknown task dependencies"):
        PlannedTaskGraph(graph_id="PG-1", run_id="RUN-1", tasks=[task])


def test_runtime_event_requires_positive_sequence() -> None:
    with pytest.raises(ValidationError):
        RuntimeEvent(
            event_id="EVT-1",
            run_id="RUN-1",
            type=RuntimeEventType.RUN_CREATED,
            sequence=0,
        )


def test_runtime_event_schema_covers_model_event_types() -> None:
    import json
    from pathlib import Path

    schema = json.loads(Path("contracts/events/runtime_event.schema.json").read_text())
    assert set(schema["properties"]["type"]["enum"]) == {
        event_type.value for event_type in RuntimeEventType
    }


@pytest.mark.asyncio
async def test_pending_proof_is_explicitly_not_implemented() -> None:
    adapter = PendingProofAdapter()
    result = await adapter.prove(
        ProofRequest(
            proof_id="PROOF-1",
            run_id="RUN-1",
            calculation_id="CALC-1",
            program_id="revenue-growth-v1",
        )
    )
    assert result.status is ProofStatus.NOT_IMPLEMENTED
    assert await adapter.verify(result) is False
