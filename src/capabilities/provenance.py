from __future__ import annotations

import hashlib
import platform
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CalculationSourceProvenance:
    """Stable implementation identity fields for a CalculationRecord."""

    code_hash: str
    source_ref: str
    runtime_version: str


def sha256_source_bytes(source: bytes) -> str:
    """Hash implementation bytes without run-specific values or filesystem metadata."""

    return f"sha256:{hashlib.sha256(source).hexdigest()}"


def calculation_source_provenance(
    source_path: str | Path,
    *,
    source_ref: str,
) -> CalculationSourceProvenance:
    """Fingerprint the checked-in capability source used to produce a calculation."""

    path = Path(source_path)
    if not source_ref.strip():
        raise ValueError("source_ref must not be empty")
    source = path.read_bytes()
    return CalculationSourceProvenance(
        code_hash=sha256_source_bytes(source),
        source_ref=source_ref,
        runtime_version=f"Python {platform.python_version()}",
    )
