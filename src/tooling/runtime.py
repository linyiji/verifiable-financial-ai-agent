from typing import Any, Protocol

from src.capabilities.registry import CapabilityRegistry
from src.domain.base import JsonObject
from src.domain.capability import CapabilityContext
from src.domain.enums import CapabilityBackend


class ToolBackend(Protocol):
    async def execute(
        self,
        tool_id: str,
        inputs: JsonObject,
        context: CapabilityContext,
        version: str | None = None,
    ) -> Any: ...


class ToolRuntime:
    def __init__(
        self, registry: CapabilityRegistry, backends: dict[CapabilityBackend, ToolBackend]
    ):
        self._registry = registry
        self._backends = backends

    async def execute(
        self,
        tool_id: str,
        inputs: JsonObject,
        context: CapabilityContext,
        version: str | None = None,
    ) -> Any:
        capability = self._registry.get(tool_id, version)
        backend = self._backends.get(capability.definition.backend)
        if backend is None:
            raise RuntimeError(f"backend not configured: {capability.definition.backend.value}")
        return await backend.execute(tool_id, inputs, context, version)
