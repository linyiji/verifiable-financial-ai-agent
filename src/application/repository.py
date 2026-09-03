from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable

from src.application.models import ResearchRunDraft, RunAggregate
from src.domain.research_object import ResearchObject
from src.domain.runtime_event import RuntimeEvent


@runtime_checkable
class ApplicationRepository(Protocol):
    async def add_object(self, entity: ResearchObject) -> ResearchObject: ...

    async def get_object(self, object_id: str) -> ResearchObject | None: ...

    async def list_objects(self) -> list[ResearchObject]: ...

    async def add_draft(self, draft: ResearchRunDraft) -> ResearchRunDraft: ...

    async def get_draft(self, draft_id: str) -> ResearchRunDraft | None: ...

    async def add_run(self, aggregate: RunAggregate) -> None: ...

    async def save_run(self, aggregate: RunAggregate) -> None: ...

    async def save_runtime_events(self, events: list[RuntimeEvent]) -> None: ...

    async def get_run(self, run_id: str) -> RunAggregate | None: ...

    async def list_runs_for_object(self, object_id: str) -> list[RunAggregate]: ...


class InMemoryApplicationRepository:
    def __init__(self) -> None:
        self._objects: dict[str, ResearchObject] = {}
        self._drafts: dict[str, ResearchRunDraft] = {}
        self._runs: dict[str, RunAggregate] = {}
        self._lock = asyncio.Lock()

    async def add_object(self, entity: ResearchObject) -> ResearchObject:
        async with self._lock:
            if entity.object_id in self._objects:
                raise ValueError(f"research object already exists: {entity.object_id}")
            self._objects[entity.object_id] = entity
        return entity

    async def get_object(self, object_id: str) -> ResearchObject | None:
        return self._objects.get(object_id)

    async def list_objects(self) -> list[ResearchObject]:
        return list(self._objects.values())

    async def add_draft(self, draft: ResearchRunDraft) -> ResearchRunDraft:
        async with self._lock:
            if draft.draft_id in self._drafts:
                raise ValueError(f"draft already exists: {draft.draft_id}")
            self._drafts[draft.draft_id] = draft
        return draft

    async def get_draft(self, draft_id: str) -> ResearchRunDraft | None:
        return self._drafts.get(draft_id)

    async def add_run(self, aggregate: RunAggregate) -> None:
        async with self._lock:
            if aggregate.run.run_id in self._runs:
                raise ValueError(f"run already exists: {aggregate.run.run_id}")
            self._runs[aggregate.run.run_id] = aggregate

    async def get_run(self, run_id: str) -> RunAggregate | None:
        return self._runs.get(run_id)

    async def save_run(self, aggregate: RunAggregate) -> None:
        async with self._lock:
            if aggregate.run.run_id not in self._runs:
                raise KeyError(aggregate.run.run_id)
            self._runs[aggregate.run.run_id] = aggregate

    async def save_runtime_events(self, events: list[RuntimeEvent]) -> None:
        del events

    async def list_runs_for_object(self, object_id: str) -> list[RunAggregate]:
        return [
            aggregate
            for aggregate in self._runs.values()
            if aggregate.run.research_object_id == object_id
        ]
