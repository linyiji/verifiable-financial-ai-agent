from src.capabilities.financial.growth import RevenueGrowthCapability
from src.capabilities.registry import (
    CapabilityAlreadyRegisteredError,
    CapabilityNotFoundError,
    CapabilityRegistry,
)
from src.domain.enums import CapabilityBackend
from src.tooling.native import NativeToolBackend
from src.tooling.runtime import ToolRuntime


def test_registry_contract() -> None:
    registry = CapabilityRegistry()
    capability = RevenueGrowthCapability()
    registry.register(capability)
    assert registry.is_available("revenue_growth")
    assert registry.get("revenue_growth") is capability
    assert registry.list()[0].backend is CapabilityBackend.NATIVE

    try:
        registry.register(capability)
    except CapabilityAlreadyRegisteredError:
        pass
    else:  # pragma: no cover
        raise AssertionError("duplicate registration should fail")

    try:
        registry.get("missing")
    except CapabilityNotFoundError:
        pass
    else:  # pragma: no cover
        raise AssertionError("missing lookup should fail")


def test_tool_runtime_uses_registry_backend_boundary() -> None:
    registry = CapabilityRegistry()
    registry.register(RevenueGrowthCapability())
    runtime = ToolRuntime(
        registry=registry,
        backends={CapabilityBackend.NATIVE: NativeToolBackend(registry)},
    )
    assert runtime is not None
