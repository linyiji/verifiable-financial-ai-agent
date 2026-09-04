import pytest

from src.capabilities.generated.scoped_registry import (
    ScopedCapabilityAlreadyRegisteredError,
    ScopedCapabilityRegistry,
)
from src.capabilities.registry import CapabilityRegistry
from src.domain.base import JsonObject
from src.domain.capability import (
    CapabilityContext,
    CapabilityDefinition,
    ScopedCapabilityRegistration,
)
from src.domain.enums import CapabilityBackend, CapabilityLifecycle, CapabilityScope


class StubCapability:
    def __init__(self, name: str, version: str, backend: CapabilityBackend):
        self.name = name
        self.definition = CapabilityDefinition(
            capability_id="margin",
            version=version,
            name=name,
            category="financial_calculation",
            backend=backend,
            deterministic=True,
            implementation_ref=f"stub://{name}",
        )

    async def execute(self, inputs: JsonObject, context: CapabilityContext) -> object:
        del inputs, context
        return self.name


def registration(
    registration_id: str,
    *,
    scope: CapabilityScope,
    version: str,
    run_id: str = "RUN-1",
    task_id: str | None = "TASK-1",
) -> ScopedCapabilityRegistration:
    return ScopedCapabilityRegistration(
        registration_id=registration_id,
        generated_capability_ref=f"GEN-{registration_id}",
        capability_id="margin",
        capability_version=version,
        scope=scope,
        run_id=run_id,
        task_id=task_id if scope is CapabilityScope.TASK else None,
        approved_by="research_lead",
        lifecycle=CapabilityLifecycle.TASK_APPROVED,
    )


@pytest.mark.asyncio
async def test_lookup_order_is_task_then_run_then_global_native_without_promotion() -> None:
    global_registry = CapabilityRegistry()
    native = StubCapability("global-native", "1.0.0", CapabilityBackend.NATIVE)
    global_registry.register(native)
    scoped = ScopedCapabilityRegistry(global_registry)
    run_capability = StubCapability("run-generated", "2.0.0", CapabilityBackend.GENERATED)
    task_capability = StubCapability("task-generated", "3.0.0", CapabilityBackend.GENERATED)

    await scoped.register(
        registration("REG-RUN", scope=CapabilityScope.RUN, version="2.0.0"), run_capability
    )
    await scoped.register(
        registration("REG-TASK", scope=CapabilityScope.TASK, version="3.0.0"), task_capability
    )

    assert (
        await scoped.lookup("margin", version=None, run_id="RUN-1", task_id="TASK-1")
        is task_capability
    )
    assert (
        await scoped.lookup("margin", version=None, run_id="RUN-1", task_id="TASK-2")
        is run_capability
    )
    assert await scoped.lookup("margin", version=None, run_id="RUN-2", task_id="TASK-2") is native
    assert global_registry.list() == [native.definition]


@pytest.mark.asyncio
async def test_task_capability_never_leaks_to_another_task_or_run() -> None:
    scoped = ScopedCapabilityRegistry(CapabilityRegistry())
    generated = StubCapability("task-generated", "1", CapabilityBackend.GENERATED)
    active = await scoped.register(
        registration("REG-1", scope=CapabilityScope.TASK, version="1"), generated
    )
    assert active.lifecycle is CapabilityLifecycle.ACTIVE_FOR_SCOPE
    assert await scoped.lookup("margin", version="1", run_id="RUN-1", task_id="TASK-1")
    assert await scoped.lookup("margin", version="1", run_id="RUN-1", task_id="TASK-2") is None
    assert await scoped.lookup("margin", version="1", run_id="RUN-2", task_id="TASK-1") is None


@pytest.mark.asyncio
async def test_duplicate_and_non_generated_registration_are_rejected() -> None:
    scoped = ScopedCapabilityRegistry(CapabilityRegistry())
    generated = StubCapability("generated", "1", CapabilityBackend.GENERATED)
    record = registration("REG-1", scope=CapabilityScope.TASK, version="1")
    await scoped.register(record, generated)
    with pytest.raises(ScopedCapabilityAlreadyRegisteredError):
        await scoped.register(record, generated)
    with pytest.raises(ValueError, match="only generated"):
        await ScopedCapabilityRegistry(CapabilityRegistry()).register(
            registration("REG-2", scope=CapabilityScope.TASK, version="1"),
            StubCapability("native", "1", CapabilityBackend.NATIVE),
        )
