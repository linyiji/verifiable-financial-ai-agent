from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pydantic import Field

from src.domain.base import DomainModel, JsonObject
from src.domain.calculation import CalculationRecord
from src.domain.capability import CapabilityContext
from src.domain.enums import ProofRequirement
from src.domain.evidence import EvidenceRecord
from src.domain.financial_branch import FinancialBranchResult
from src.domain.proof import (
    ProofArtifactReference,
    ProofInputCommitment,
    ProofRecord,
    ProofResult,
    ProofVerificationRecord,
)
from src.domain.task import Task
from src.runtime.state import RuntimeState


class TaskCalculationExtensionResult(DomainModel):
    branch_results: list[FinancialBranchResult] = Field(default_factory=list)
    calculations: list[CalculationRecord] = Field(default_factory=list)
    generated_capability_refs: list[str] = Field(default_factory=list)
    judgments: list[JsonObject] = Field(default_factory=list)
    task_output: JsonObject = Field(default_factory=dict)


@runtime_checkable
class TaskCalculationExtension(Protocol):
    async def execute(
        self,
        *,
        task: Task,
        state: RuntimeState,
        evidence: list[EvidenceRecord],
        context: CapabilityContext,
    ) -> TaskCalculationExtensionResult: ...


@dataclass(frozen=True, slots=True)
class ProofWorkflowOutcome:
    requirements: dict[str, ProofRequirement]
    proofs: dict[str, ProofRecord | ProofResult]
    runtime_state: JsonObject
    limitations: tuple[str, ...] = ()
    input_commitments: dict[str, ProofInputCommitment] = field(default_factory=dict)
    verifications: dict[str, ProofVerificationRecord] = field(default_factory=dict)
    artifacts: dict[str, ProofArtifactReference] = field(default_factory=dict)


@runtime_checkable
class ProofWorkflow(Protocol):
    async def execute(
        self,
        *,
        run_id: str,
        calculations: list[CalculationRecord],
    ) -> ProofWorkflowOutcome: ...
