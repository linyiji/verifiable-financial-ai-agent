from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from src.domain.base import JsonObject, TimestampedModel
from src.domain.enums import CapabilityBackend


class CapabilityDefinition(TimestampedModel):
    capability_id: str
    version: str
    name: str
    category: str
    backend: CapabilityBackend
    input_schema: JsonObject = Field(default_factory=dict)
    output_schema: JsonObject = Field(default_factory=dict)
    deterministic: bool
    proof_eligible: bool = False
    lifecycle: str = "CERTIFIED"
    implementation_ref: str
    owner: str = "system"


class CapabilityContext(TimestampedModel):
    run_id: str
    task_id: str
    accepted_evidence_ids: list[str] = Field(default_factory=list)


@runtime_checkable
class Capability(Protocol):
    definition: CapabilityDefinition

    async def execute(self, inputs: JsonObject, context: CapabilityContext) -> Any: ...

