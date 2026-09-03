from copy import deepcopy
from typing import TypeVar

SnapshotValue = TypeVar("SnapshotValue")


def snapshot(value: SnapshotValue) -> SnapshotValue:
    """Detach mutable source data before publishing an output model."""

    return deepcopy(value)


def ordered_unique(values: list[str] | tuple[str, ...]) -> list[str]:
    """Return stable, non-empty references without duplicating lineage links."""

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            raise ValueError("canonical references must not be blank")
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result
