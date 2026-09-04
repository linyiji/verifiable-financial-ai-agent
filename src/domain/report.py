from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Self

from pydantic import ConfigDict, Field, field_serializer

from src.domain.base import DomainModel, TimestampedModel
from src.domain.financial_semantics import (
    MaterialCalculationDisposition,
    MaterialFinancialClaim,
    ReleasedFinancialMetric,
    ResearchSourceCoverage,
)


class FrozenJsonMapping(Mapping[str, Any]):
    """Recursively immutable JSON object with value-based equality."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, Any]) -> None:
        self._values = {key: _freeze_json(value) for key, value in values.items()}

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __deepcopy__(self, memo: dict[int, Any]) -> FrozenJsonMapping:
        del memo
        return self

    def __repr__(self) -> str:
        return f"FrozenJsonMapping({_thaw_json(self)!r})"


class FrozenJsonSequence(Sequence[Any]):
    """Recursively immutable JSON array that compares like a list."""

    __slots__ = ("_values",)

    def __init__(self, values: Sequence[Any]) -> None:
        self._values = tuple(_freeze_json(value) for value in values)

    def __getitem__(self, index: int) -> Any:
        return self._values[index]

    def __len__(self) -> int:
        return len(self._values)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Sequence):
            return False
        return list(self) == list(other)

    def __deepcopy__(self, memo: dict[int, Any]) -> FrozenJsonSequence:
        del memo
        return self

    def __repr__(self) -> str:
        return f"FrozenJsonSequence({_thaw_json(self)!r})"


def _freeze_json(value: Any) -> Any:
    if isinstance(value, FrozenJsonMapping):
        return value
    if isinstance(value, Mapping):
        return FrozenJsonMapping(value)
    if isinstance(value, FrozenJsonSequence):
        return value
    if isinstance(value, (list, tuple)):
        return FrozenJsonSequence(value)
    if value is None or isinstance(value, (bool, int, float, str, Decimal, date, datetime)):
        return value
    raise TypeError(f"unsupported mutable or non-JSON report value: {type(value).__name__}")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, FrozenJsonSequence):
        return [_thaw_json(item) for item in value]
    return value


class CanonicalReportDTO(DomainModel):
    """Immutable presentation input derived only from released/canonical records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_record_id: str
    released_result_id: str
    run_id: str
    research_object: str
    structured_financial_results: Mapping[str, Any] = Field(default_factory=dict)
    released_claims: Sequence[Mapping[str, Any]] = Field(default_factory=tuple)
    released_metrics: Sequence[ReleasedFinancialMetric] = Field(default_factory=tuple)
    material_claims: Sequence[MaterialFinancialClaim] = Field(default_factory=tuple)
    material_calculation_dispositions: Sequence[MaterialCalculationDisposition] = Field(
        default_factory=tuple
    )
    research_source_coverage: ResearchSourceCoverage | None = None
    judgments: Sequence[Mapping[str, Any]] = Field(default_factory=tuple)
    risk_output: Mapping[str, Any] = Field(default_factory=dict)
    limitations: Sequence[str] = Field(default_factory=tuple)
    calculation_refs: Sequence[str] = Field(default_factory=tuple)
    proof_refs: Sequence[str] = Field(default_factory=tuple)
    provenance: Mapping[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        del __context
        for field_name in (
            "structured_financial_results",
            "released_claims",
            "judgments",
            "risk_output",
            "limitations",
            "calculation_refs",
            "proof_refs",
            "provenance",
        ):
            object.__setattr__(self, field_name, _freeze_json(getattr(self, field_name)))
        for field_name in (
            "released_metrics",
            "material_claims",
            "material_calculation_dispositions",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))

    @field_serializer(
        "structured_financial_results",
        "released_claims",
        "judgments",
        "risk_output",
        "limitations",
        "calculation_refs",
        "proof_refs",
        "provenance",
    )
    def serialize_frozen_json(self, value: Any) -> Any:
        return _thaw_json(value)

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        del deep
        payload = self.model_dump(mode="python", round_trip=True)
        if update:
            payload.update(update)
        return type(self).model_validate(payload)


class ReportArtifactRecord(TimestampedModel):
    artifact_id: str
    run_id: str
    artifact_type: str
    artifact_ref: str
    content_hash: str
    renderer_version: str
    canonical_record_id: str
    released_result_id: str
    size_bytes: int = Field(ge=0)
    semantic_hash: str | None = None
    metric_semantics_hash: str | None = None
