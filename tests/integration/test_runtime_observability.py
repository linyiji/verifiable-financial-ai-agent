from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date

import pytest

from src.application.service import ResearchApplicationService
from src.observability import InMemoryTraceReferenceRepository


@dataclass
class _Span:
    trace_id: str
    span_id: str


class _RecordingTraceAdapter:
    def __init__(self) -> None:
        self.names: list[str] = []
        self.attributes: list[dict[str, object]] = []

    @asynccontextmanager
    async def span(self, name: str, *, attributes=None):
        self.names.append(name)
        self.attributes.append(attributes or {})
        yield _Span(trace_id="trace-integration", span_id=f"span-{len(self.names)}")

    @asynccontextmanager
    async def generation(self, name: str, **kwargs):
        self.names.append(name)
        self.attributes.append(kwargs.get("attributes") or {})
        yield _Span(trace_id="trace-integration", span_id=f"generation-{len(self.names)}")

    async def complete_generation(self, generation, **kwargs) -> None:
        del generation, kwargs

    async def event(self, name: str, *, attributes=None) -> None:
        del name, attributes


@pytest.mark.asyncio
async def test_runtime_observations_and_canonical_trace_references() -> None:
    adapter = _RecordingTraceAdapter()
    references = InMemoryTraceReferenceRepository()
    service = ResearchApplicationService(
        trace_adapter=adapter,
        trace_reference_repository=references,
    )
    research_object = await service.create_object(
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
    )
    draft = await service.prepare_run(
        research_object_id=research_object.object_id,
        research_goal="Verify runtime trace mapping",
        as_of=date(2026, 9, 4),
        preferences={},
    )
    aggregate = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    aggregate = await service.execute_run(aggregate.run.run_id)

    expected = {
        "vfas.run",
        "vfas.task",
        "vfas.agent",
        "vfas.skill",
        "vfas.tool",
        "vfas.evidence",
        "vfas.calculation",
        "vfas.self_correction",
        "vfas.replan",
        "vfas.review",
        "vfas.release",
    }
    assert expected.issubset(adapter.names)
    persisted = await references.list_by_run(aggregate.run.run_id)
    assert persisted
    assert {reference.trace_id for reference in persisted} == {"trace-integration"}
    assert aggregate.artifacts.canonical_record is not None
    assert aggregate.artifacts.canonical_record.trace_refs
    assert set(aggregate.artifacts.canonical_record.trace_refs).issubset(
        {reference.reference_id for reference in persisted}
    )


@pytest.mark.asyncio
async def test_preallocated_run_id_owns_prepare_observation() -> None:
    adapter = _RecordingTraceAdapter()
    service = ResearchApplicationService(trace_adapter=adapter)
    research_object = await service.create_object(
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
    )

    await service.prepare_run(
        research_object_id=research_object.object_id,
        research_goal="Keep the scheme observation in the authoritative run trace",
        as_of=date(2026, 9, 4),
        preferences={},
        observation_run_id="RUN-PREALLOCATED",
    )

    scheme_index = adapter.names.index("vfas.scheme")
    assert adapter.attributes[scheme_index]["run_id"] == "RUN-PREALLOCATED"
