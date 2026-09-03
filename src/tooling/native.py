from typing import Any

from src.capabilities.registry import CapabilityRegistry
from src.domain.base import JsonObject
from src.domain.capability import CapabilityContext


class NativeToolBackend:
    def __init__(self, registry: CapabilityRegistry):
        self._registry = registry

    async def execute(
        self,
        tool_id: str,
        inputs: JsonObject,
        context: CapabilityContext,
        version: str | None = None,
    ) -> Any:
        capability = self._registry.get(tool_id, version)
        return await capability.execute(inputs, context)
