from src.domain.capability import Capability, CapabilityDefinition


class CapabilityAlreadyRegisteredError(ValueError):
    pass


class CapabilityNotFoundError(KeyError):
    pass


class CapabilityRegistry:
    """Registry boundary used by agents/tooling without exposing implementations."""

    def __init__(self) -> None:
        self._capabilities: dict[tuple[str, str], Capability] = {}

    def register(self, capability: Capability) -> None:
        key = (capability.definition.capability_id, capability.definition.version)
        if key in self._capabilities:
            raise CapabilityAlreadyRegisteredError(f"capability already registered: {key}")
        self._capabilities[key] = capability

    def get(self, capability_id: str, version: str | None = None) -> Capability:
        candidates = [
            capability
            for (registered_id, registered_version), capability in self._capabilities.items()
            if registered_id == capability_id and (version is None or registered_version == version)
        ]
        if not candidates:
            raise CapabilityNotFoundError(capability_id)
        if version is not None:
            return candidates[0]
        return sorted(candidates, key=lambda item: item.definition.version)[-1]

    def list(self) -> list[CapabilityDefinition]:
        return sorted(
            (item.definition for item in self._capabilities.values()),
            key=lambda item: (item.capability_id, item.version),
        )

    def is_available(self, capability_id: str, version: str | None = None) -> bool:
        try:
            self.get(capability_id, version)
        except CapabilityNotFoundError:
            return False
        return True
