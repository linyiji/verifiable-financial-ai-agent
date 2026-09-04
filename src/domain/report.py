from pydantic import ConfigDict, Field

from src.domain.base import DomainModel, JsonObject, TimestampedModel


class CanonicalReportDTO(DomainModel):
    """Immutable presentation input derived only from released/canonical records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_record_id: str
    released_result_id: str
    run_id: str
    research_object: str
    structured_financial_results: JsonObject = Field(default_factory=dict)
    released_claims: list[JsonObject] = Field(default_factory=list)
    judgments: list[JsonObject] = Field(default_factory=list)
    risk_output: JsonObject = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    calculation_refs: list[str] = Field(default_factory=list)
    proof_refs: list[str] = Field(default_factory=list)
    provenance: JsonObject = Field(default_factory=dict)


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
