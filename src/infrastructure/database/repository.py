from typing import Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class Repository(Protocol[T]):
    async def add(self, entity: T) -> T: ...

    async def get(self, entity_id: str) -> T | None: ...

    async def list(self) -> list[T]: ...
