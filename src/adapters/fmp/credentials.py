from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic import SecretStr

from src.adapters.fmp.models import FMPAccessStatus, FMPResponseEnvelope


@dataclass(slots=True)
class FMPKeyPool:
    """Finite execution-scoped FMP credential rotation without secret observability."""

    _credentials: tuple[SecretStr, ...] = field(repr=False)
    _active_slot: int = 0
    _rate_limited_slots: set[int] = field(default_factory=set)
    _invalid_slots: set[int] = field(default_factory=set)
    _attempt_count: int = 0
    _last_selected_slot: int | None = None
    _last_status: FMPAccessStatus | None = None
    _rotation_occurred: bool = False
    _last_rotation_reason: str | None = None

    @classmethod
    def from_credentials(cls, credentials: Sequence[SecretStr]) -> FMPKeyPool:
        if not credentials:
            raise ValueError("FMP credential pool is empty")
        return cls(tuple(credentials))

    @property
    def key_count(self) -> int:
        return len(self._credentials)

    @property
    def rate_limited_key_count(self) -> int:
        return len(self._rate_limited_slots)

    @property
    def invalid_key_count(self) -> int:
        return len(self._invalid_slots)

    @property
    def pool_exhausted(self) -> bool:
        unavailable = self._rate_limited_slots | self._invalid_slots
        return len(unavailable) == self.key_count

    @property
    def all_keys_rate_limited(self) -> bool:
        return self.rate_limited_key_count == self.key_count

    def select(self, attempted_slots: set[int]) -> tuple[int, SecretStr] | None:
        unavailable = self._rate_limited_slots | self._invalid_slots | attempted_slots
        for offset in range(self.key_count):
            slot_index = (self._active_slot + offset) % self.key_count
            if slot_index not in unavailable:
                self._last_selected_slot = slot_index
                self._attempt_count += 1
                return slot_index, self._credentials[slot_index]
        return None

    def record(self, slot_index: int, envelope: FMPResponseEnvelope) -> bool:
        """Record one response and return whether the next slot must be tried."""

        self._last_status = envelope.status
        if envelope.http_status == 429:
            self._rate_limited_slots.add(slot_index)
            self._rotate_after(slot_index, reason="RATE_LIMIT_429")
            return True
        if envelope.http_status in {401, 403}:
            self._invalid_slots.add(slot_index)
            self._rotate_after(slot_index, reason=f"CREDENTIAL_HTTP_{envelope.http_status}")
            return True
        self._active_slot = slot_index
        return False

    def safe_status(self) -> dict[str, str | int | bool | None]:
        return {
            "provider": "FMP",
            "configured_keys": self.key_count,
            "rate_limited_keys": self.rate_limited_key_count,
            "invalid_keys": self.invalid_key_count,
            "attempt_count": self._attempt_count,
            "selected_key_slot": (
                f"KEY_{self._last_selected_slot + 1}"
                if self._last_selected_slot is not None
                else None
            ),
            "status_classification": (
                self._last_status.value if self._last_status is not None else None
            ),
            "rotation_occurred": self._rotation_occurred,
            "rotation_reason": self._last_rotation_reason,
            "pool_exhausted": self.pool_exhausted,
        }

    def _rotate_after(self, slot_index: int, *, reason: str) -> None:
        self._active_slot = (slot_index + 1) % self.key_count
        self._rotation_occurred = True
        self._last_rotation_reason = reason
