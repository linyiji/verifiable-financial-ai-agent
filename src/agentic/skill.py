"""Skill package contract kept separate from capability implementations."""

from typing import Protocol, runtime_checkable

from pydantic import Field

from src.domain.base import DomainModel, JsonObject
from src.domain.decision import StructuredAgentDecision


class SkillDefinition(DomainModel):
    skill_id: str
    version: str
    name: str
    input_schema: JsonObject = Field(default_factory=dict)
    output_schema: JsonObject = Field(default_factory=dict)
    allowed_capability_ids: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    validation_rules: list[str] = Field(default_factory=list)
    correction_strategy: list[str] = Field(default_factory=list)
    evaluation_rules: list[str] = Field(default_factory=list)


class SkillContext(DomainModel):
    run_id: str
    task_id: str
    accepted_evidence_ids: list[str] = Field(default_factory=list)


class SkillResult(DomainModel):
    output: JsonObject = Field(default_factory=dict)
    decision: StructuredAgentDecision


@runtime_checkable
class Skill(Protocol):
    definition: SkillDefinition

    async def execute(self, inputs: JsonObject, context: SkillContext) -> SkillResult: ...
