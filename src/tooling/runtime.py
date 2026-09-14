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
        *, wp04_expected=None,
    ) -> Any:
        if wp04_expected is not None:
            from src.capabilities.provenance import verify_wp04_method
            if (tool_id, version) != ('revenue_growth', '1.1.0'):
                raise ValueError('WP04 exact dispatch required')
            descriptor, manifest_hash, load_receipt, frozen = wp04_expected
            capability, observed = verify_wp04_method(self._registry, self, descriptor, manifest_hash, expectation=frozen)
            if observed != load_receipt:
                raise ValueError('WP04 load receipt changed')
            backend = self._backends[capability.definition.backend]
            return await backend.execute(tool_id, inputs, context, version,
                                         wp04_expected=(*wp04_expected, self))
        capability = self._registry.get(tool_id, version)
        backend = self._backends.get(capability.definition.backend)
        if backend is None:
            raise RuntimeError(f"backend not configured: {capability.definition.backend.value}")
        return await backend.execute(tool_id, inputs, context, version)


_WP04_RUNTIME_EXECUTE = ToolRuntime.execute
