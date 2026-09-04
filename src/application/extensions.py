from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from src.domain.base import DomainModel, JsonObject
from src.domain.calculation import CalculationRecord
from src.domain.capability import CapabilityContext
from src.domain.evidence import EvidenceRecord
from src.domain.task import Task
from src.runtime.state import RuntimeState


class TaskCalculationExtensionResult(DomainModel):
    calculations: list[CalculationRecord] = Field(default_factory=list)
    generated_capability_refs: list[str] = Field(default_factory=list)
    judgments: list[JsonObject] = Field(default_factory=list)
    task_output: JsonObject = Field(default_factory=dict)


@runtime_checkable
class TaskCalculationExtension(Protocol):
    async def execute(
        self,
        *,
        task: Task,
        state: RuntimeState,
        evidence: list[EvidenceRecord],
        context: CapabilityContext,
    ) -> TaskCalculationExtensionResult: ...
