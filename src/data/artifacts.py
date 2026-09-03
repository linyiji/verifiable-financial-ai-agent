import os
from pathlib import Path
from typing import Any, Protocol

from src.data.hashing import canonical_json


class RawArtifactStore(Protocol):
    async def put_raw_snapshot(
        self,
        *,
        run_id: str,
        snapshot_hash: str,
        payload: Any,
    ) -> str: ...


class LocalRawArtifactStore:
    """Content-addressed local raw snapshot storage with atomic promotion."""

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root

    async def put_raw_snapshot(
        self,
        *,
        run_id: str,
        snapshot_hash: str,
        payload: Any,
    ) -> str:
        target = (
            self._artifact_root
            / "runs"
            / _safe_segment(run_id)
            / "evidence"
            / f"{snapshot_hash}.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        data = canonical_json(payload)
        if target.exists():
            if target.read_bytes() != data:
                raise ValueError("content-addressed artifact hash collision")
            return str(target)

        temporary = target.with_suffix(f".tmp-{os.getpid()}")
        temporary.write_bytes(data)
        temporary.replace(target)
        return str(target)


def _safe_segment(value: str) -> str:
    if not value or value in {".", ".."} or any(character in value for character in "/\\"):
        raise ValueError("artifact path identifier contains unsafe characters")
    return value
