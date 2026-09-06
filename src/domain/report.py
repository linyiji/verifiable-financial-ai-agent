from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, field_serializer, field_validator, model_validator

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


class ReportSourceContribution(DomainModel):
    """Safe, exact-identity bridge from one report anchor to one Agent execution.

    The contract intentionally has no prompt, raw provider payload, or reasoning
    field. ``observable_process`` may describe only retained system actions.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    report_id: str
    report_anchor: str
    execution_anchor: str
    report_section: str
    actor_id: str
    task_id: str
    agent_output_id: str
    agent_output_artifact_id: str
    execution_event_id: str
    status: Literal["SUCCESS"] = "SUCCESS"
    provider: str
    actual_model: str
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    duration_ms: int = Field(ge=0)
    input_refs: tuple[str, ...] = ()
    observable_process: tuple[str, ...] = ()
    output_summary: str
    key_findings: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    metric_name: str | None = None
    metric_value: str | None = None
    metric_unit: str | None = None
    calculation_id: str | None = None
    formula_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    review_id: str | None = None
    review_status: str | None = None
    proof_id: str | None = None
    proof_status: str | None = None

    @field_validator(
        "run_id",
        "report_id",
        "report_anchor",
        "execution_anchor",
        "report_section",
        "actor_id",
        "task_id",
        "agent_output_id",
        "agent_output_artifact_id",
        "execution_event_id",
        "provider",
        "actual_model",
        "output_summary",
    )
    @classmethod
    def reject_blank_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("report source identity and output fields must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def validate_safe_exact_source(self) -> ReportSourceContribution:
        safe_anchor_characters = (
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        )
        if any(
            character not in safe_anchor_characters
            for character in self.report_anchor + self.execution_anchor
        ):
            raise ValueError("report source anchors must be safe fragment identifiers")
        for values in (
            self.input_refs,
            self.observable_process,
            self.key_findings,
            self.risks,
            self.limitations,
            self.evidence_refs,
        ):
            if len(values) != len(set(values)) or any(not value.strip() for value in values):
                raise ValueError("report source sequences must be unique and non-blank")
        return self

    @field_serializer(
        "input_refs",
        "observable_process",
        "key_findings",
        "risks",
        "limitations",
        "evidence_refs",
    )
    def serialize_sequences(self, value: tuple[str, ...]) -> list[str]:
        return list(value)


class CanonicalReportDTO(DomainModel):
    """Immutable presentation input derived only from released/canonical records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_record_id: str
    released_result_id: str
    run_id: str
    research_object: str
    company_name: str | None = None
    symbol: str | None = None
    as_of: date | None = None
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
    source_contributions: Sequence[ReportSourceContribution] = Field(default_factory=tuple)

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
            "source_contributions",
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
    anchor_manifest_id: str | None = None
    anchor_manifest_hash: str | None = None
    source_contributions: list[ReportSourceContribution] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_manifest_identity(self) -> ReportArtifactRecord:
        if (self.anchor_manifest_id is None) != (self.anchor_manifest_hash is None):
            raise ValueError("report anchor manifest identity/hash are a pair")
        if self.source_contributions:
            if self.anchor_manifest_id is None:
                raise ValueError("report source contributions require an anchor manifest")
            if any(
                source.run_id != self.run_id
                or source.report_id != self.released_result_id
                for source in self.source_contributions
            ):
                raise ValueError("report source contribution crossed Run or Report identity")
            if len({source.report_anchor for source in self.source_contributions}) != len(
                self.source_contributions
            ):
                raise ValueError("report source anchors must be unique")
        return self
