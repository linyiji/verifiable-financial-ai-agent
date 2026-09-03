import json
from datetime import UTC, datetime
from pathlib import Path

from src.data.hashing import snapshot_hash
from src.data.provider import ProviderRequest, RawProviderSnapshot


class FixtureProvider:
    """Deterministic provider for offline development and acceptance tests."""

    name = "fixture"

    def __init__(self, fixture_path: Path) -> None:
        self._fixture_path = fixture_path

    async def fetch(self, request: ProviderRequest) -> RawProviderSnapshot:
        payload = json.loads(self._fixture_path.read_text(encoding="utf-8"))
        records = payload.get("records")
        if not isinstance(records, list):
            raise ValueError("fixture payload must contain a records list")

        fixture_symbol = payload.get("object", {}).get("symbol")
        if fixture_symbol and fixture_symbol.upper() != request.symbol.upper():
            raise ValueError(
                f"fixture symbol {fixture_symbol!r} does not match request {request.symbol!r}"
            )

        digest = snapshot_hash(payload)
        retrieved_at = _deterministic_retrieved_at(records)
        selected_records = records
        if request.fields:
            selected_records = [
                record
                for record in records
                if isinstance(record, dict) and record.get("field") in request.fields
            ]
        return RawProviderSnapshot(
            provider=str(payload.get("provider", self.name)),
            source_locator=str(self._fixture_path),
            retrieved_at=retrieved_at,
            raw_artifact_ref=f"fixture://{self._fixture_path.name}#{digest}",
            snapshot_hash=digest,
            raw_payload=payload,
            records=selected_records,
        )


def _deterministic_retrieved_at(records: list[object]) -> datetime:
    dates = [
        record["as_of"]
        for record in records
        if isinstance(record, dict) and isinstance(record.get("as_of"), str)
    ]
    if not dates:
        return datetime(1970, 1, 1, tzinfo=UTC)
    return datetime.fromisoformat(max(dates)).replace(tzinfo=UTC)
