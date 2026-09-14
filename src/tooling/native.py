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
        *, wp04_expected=None,
    ) -> Any:
        if wp04_expected is not None:
            from src.capabilities.provenance import verify_wp04_method
            descriptor, manifest_hash, load_receipt, frozen, runtime = wp04_expected
            capability, observed = verify_wp04_method(self._registry, runtime, descriptor, manifest_hash, expectation=frozen)
            if (tool_id, version) != ('revenue_growth', '1.1.0') or observed != load_receipt:
                raise ValueError('WP04 native identity changed')
        else:
            capability = self._registry.get(tool_id, version)
        return await capability.execute(inputs, context)


_WP04_NATIVE_EXECUTE = NativeToolBackend.execute
