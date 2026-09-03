from typing import Protocol

from src.domain.review import ReviewRecord


class HumanReviewResolver(Protocol):
    async def resolve(self, review: ReviewRecord, action: str, actor_id: str) -> ReviewRecord: ...

