from typing import Any, Protocol

from src.domain.base import JsonObject
from src.domain.capability import CapabilityContext


class GeneratedCapabilityExecutor(Protocol):
    async def execute_approved(
        self, capability_id: str, inputs: JsonObject, context: CapabilityContext
    ) -> Any: ...


class GeneratedToolBackend:
    def __init__(self, executor: GeneratedCapabilityExecutor):
        self._executor = executor

    async def execute(
        self,
        tool_id: str,
        inputs: JsonObject,
        context: CapabilityContext,
        version: str | None = None,
    ) -> Any:
        del version
        return await self._executor.execute_approved(tool_id, inputs, context)
