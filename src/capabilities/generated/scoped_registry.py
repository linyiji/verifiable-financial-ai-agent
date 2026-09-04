"""TASK/RUN overlays for validated generated capabilities."""

from __future__ import annotations

import asyncio

from src.capabilities.registry import CapabilityNotFoundError, CapabilityRegistry
from src.domain.capability import Capability, ScopedCapabilityRegistration
from src.domain.enums import CapabilityBackend, CapabilityLifecycle, CapabilityScope


class ScopedCapabilityAlreadyRegisteredError(ValueError):
    pass


class ScopedCapabilityRegistry:
    """Lookup TASK, then RUN, then the owned global Native registry.

    Registration mutates only the task/run overlays. There is intentionally no
    API that promotes generated code into the global registry.
    """

    def __init__(self, global_native_registry: CapabilityRegistry):
        self._global = global_native_registry
        self._task: dict[tuple[str, str, str, str], Capability] = {}
        self._run: dict[tuple[str, str, str], Capability] = {}
        self._registrations: dict[str, ScopedCapabilityRegistration] = {}
        self._lock = asyncio.Lock()

    async def lookup(
        self,
        capability_id: str,
        *,
        version: str | None,
        run_id: str,
        task_id: str,
    ) -> Capability | None:
        task_match = _latest(
            capability
            for (
                registered_run,
                registered_task,
                registered_id,
                registered_version,
            ), capability in self._task.items()
            if registered_run == run_id
            and registered_task == task_id
            and registered_id == capability_id
            and (version is None or registered_version == version)
        )
        if task_match is not None:
            return task_match
        run_match = _latest(
            capability
            for (registered_run, registered_id, registered_version), capability in self._run.items()
            if registered_run == run_id
            and registered_id == capability_id
            and (version is None or registered_version == version)
        )
        if run_match is not None:
            return run_match
        try:
            global_match = self._global.get(capability_id, version)
        except CapabilityNotFoundError:
            return None
        if global_match.definition.backend is not CapabilityBackend.NATIVE:
            return None
        return global_match

    async def register(
        self,
        registration: ScopedCapabilityRegistration,
        capability: Capability,
    ) -> ScopedCapabilityRegistration:
        if registration.lifecycle is not CapabilityLifecycle.TASK_APPROVED:
            raise ValueError("TASK_APPROVED registration is required")
        definition = capability.definition
        if definition.backend is not CapabilityBackend.GENERATED:
            raise ValueError("scoped registration accepts only generated capabilities")
        if (
            definition.capability_id != registration.capability_id
            or definition.version != registration.capability_version
        ):
            raise ValueError("registration and capability identity do not match")

        async with self._lock:
            if registration.registration_id in self._registrations:
                raise ScopedCapabilityAlreadyRegisteredError(registration.registration_id)
            if registration.scope is CapabilityScope.TASK:
                if not registration.task_id:
                    raise ValueError("TASK scope requires task_id")
                key = (
                    registration.run_id,
                    registration.task_id,
                    registration.capability_id,
                    registration.capability_version,
                )
                target = self._task
            elif registration.scope is CapabilityScope.RUN:
                key = (
                    registration.run_id,
                    registration.capability_id,
                    registration.capability_version,
                )
                target = self._run
            else:  # pragma: no cover - frozen enum and Pydantic prevent this
                raise ValueError("unsupported capability scope")
            if key in target:
                raise ScopedCapabilityAlreadyRegisteredError(str(key))
            active = registration.model_copy(
                update={"lifecycle": CapabilityLifecycle.ACTIVE_FOR_SCOPE}
            )
            target[key] = capability
            self._registrations[active.registration_id] = active
            return active

    def registrations(self) -> tuple[ScopedCapabilityRegistration, ...]:
        return tuple(self._registrations.values())


def _latest(capabilities) -> Capability | None:
    values = list(capabilities)
    if not values:
        return None
    return sorted(values, key=lambda item: item.definition.version)[-1]
