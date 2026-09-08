from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from src.domain.base import DomainModel, TimestampedModel


class ResearchAgentStructuredOutput(DomainModel):
    """Strict business output returned by a research role.

    Prompts, provider response bodies, and private reasoning have no field in this
    contract. Financial values remain authoritative only in Evidence and
    Calculation records; this object is the Agent's bounded interpretation.
    """

    summary: str = Field(min_length=1, max_length=800)
    key_findings: list[str] = Field(min_length=1, max_length=5)
    risks: list[str] = Field(max_length=5)
    limitations: list[str] = Field(max_length=5)
    requires_follow_up: bool

    @field_validator("summary")
    @classmethod
    def strip_summary(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("research Agent summary must not be blank")
        return stripped

    @field_validator("key_findings", "risks", "limitations")
    @classmethod
    def validate_bounded_text(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 800 for value in normalized):
            raise ValueError("research Agent list text must be non-blank and bounded")
        if len(normalized) != len(set(normalized)):
            raise ValueError("research Agent list text must be unique")
        return normalized


class StandardResearchAgentStructuredOutput(ResearchAgentStructuredOutput):
    requires_follow_up: Literal[False]


class RiskResearchAgentStructuredOutput(ResearchAgentStructuredOutput):
    requires_follow_up: bool


class ResearchAgentOutputRecord(TimestampedModel):
    """Durable exact-Run/Task binding for one observable model invocation."""

    output_id: str
    run_id: str
    task_id: str
    actor: str
    provider: str
    requested_model: str
    actual_model: str | None = None
    execution_policy: dict | None = None
    execution_outcome: str | None = None
    attempted_models: list[str] = Field(default_factory=list)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    duration_ms: int = Field(ge=0)
    status: Literal["SUCCESS", "FAILED"]
    input_refs: list[str] = Field(default_factory=list)
    structured_output: ResearchAgentStructuredOutput | None = None
    failure_code: str | None = None
    artifact_id: str
    artifact_ref: str
    artifact_sha256: str
    artifact_size_bytes: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_identity_and_status(self) -> ResearchAgentOutputRecord:
        if self.execution_policy is not None:
            from src.domain.model_execution import ModelExecutionPolicy

            policy = ModelExecutionPolicy.model_validate(self.execution_policy)
            outcome = policy.outcome(self.provider, policy.preferred_model, self.actual_model)
            if self.status == "SUCCESS" and (
                outcome not in {"MODEL_EXECUTION_DIRECT", "MODEL_EXECUTION_SUBSTITUTED"}
                or outcome != self.execution_outcome
            ):
                raise ValueError("Agent output execution identity is outside policy")
        required = (
            self.output_id,
            self.run_id,
            self.task_id,
            self.actor,
            self.provider,
            self.requested_model,
            self.artifact_id,
            self.artifact_ref,
            self.artifact_sha256,
        )
        if any(not value.strip() for value in required):
            raise ValueError("research Agent output identity fields must not be blank")
        if len(self.input_refs) != len(set(self.input_refs)) or any(
            not value.strip() for value in self.input_refs
        ):
            raise ValueError("research Agent input refs must be unique and non-blank")
        if len(self.attempted_models) != len(set(self.attempted_models)) or any(
            not value.strip() for value in self.attempted_models
        ):
            raise ValueError("attempted model identities must be unique and non-blank")
        if self.artifact_id != self.artifact_sha256:
            raise ValueError("research Agent artifact id must equal its content hash")
        if len(self.artifact_sha256) != 71 or not self.artifact_sha256.startswith("sha256:"):
            raise ValueError("research Agent artifact hash must use sha256 identity")
        try:
            int(self.artifact_sha256.removeprefix("sha256:"), 16)
        except ValueError as exc:
            raise ValueError("research Agent artifact hash must be hexadecimal") from exc
        if self.artifact_ref != (
            f"agent-output://sha256/{self.artifact_sha256.removeprefix('sha256:')}"
        ):
            raise ValueError("research Agent artifact reference must encode its exact hash")
        if self.status == "SUCCESS":
            if (
                self.actual_model is None
                or not self.actual_model.strip()
                or self.structured_output is None
            ):
                raise ValueError("successful research Agent output requires model and output")
            if self.failure_code is not None:
                raise ValueError("successful research Agent output cannot carry a failure code")
        elif self.structured_output is not None or self.failure_code is None:
            raise ValueError("failed research Agent output requires only a safe failure code")
        return self
