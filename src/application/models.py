from enum import Enum

from pydantic import Field

from src.domain.agent_output import ResearchAgentOutputRecord
from src.domain.base import DomainModel, JsonObject
from src.domain.calculation import CalculationRecord
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.correction import CorrectionRecord
from src.domain.evidence import EvidenceRecord
from src.domain.financial_branch import FinancialBranchResult
from src.domain.node_binding import NodeBindingState
from src.domain.proof import ProofRecord, ProofResult
from src.domain.released_research_result import ReleasedResearchResult
from src.domain.report import ReportArtifactRecord
from src.domain.research_goal import ResearchGoal
from src.domain.research_run import ResearchRun
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.review import ReviewRecord
from src.domain.risk_admission import ConfirmedRiskSemanticBindingV1
from src.domain.task import ReplanRequest
from src.output.projections import CanonicalRecordProjections
from src.output.report import FinancialReport
from src.output.writeback import ObjectWritebackProposal
from src.runtime.state import RuntimeState


class ResearchRunDraft(DomainModel):
    draft_id: str
    goal: ResearchGoal
    scheme_snapshot: ResearchSchemeSnapshot
    status: str = "awaiting_confirmation"


from src.domain.financial_validation import MethodObservation


class CompletedRunArtifacts(DomainModel):
    wp04_method_observations: dict[str, MethodObservation] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    closure_diagnostic: JsonObject | None = None
    partial_research: JsonObject | None = None
    financial_branches: list[FinancialBranchResult] = Field(default_factory=list)
    agent_outputs: list[ResearchAgentOutputRecord] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    calculations: list[CalculationRecord] = Field(default_factory=list)
    corrections: list[CorrectionRecord] = Field(default_factory=list)
    replans: list[ReplanRequest] = Field(default_factory=list)
    review: ReviewRecord | None = None
    proofs: list[ProofRecord | ProofResult] = Field(default_factory=list)
    generated_capability_refs: list[str] = Field(default_factory=list)
    judgments: list[JsonObject] = Field(default_factory=list)
    report_artifacts: list[ReportArtifactRecord] = Field(default_factory=list)
    canonical_record: CanonicalExecutionRecord | None = None
    released_result: ReleasedResearchResult | None = None
    projections: CanonicalRecordProjections | None = None
    report: FinancialReport | None = None
    writeback: ObjectWritebackProposal | None = None
    task_outputs: JsonObject = Field(default_factory=dict)
    parallel_task_peak: int = 0


class _HistoricalCodecProvenance(Enum):
    PERSISTED_V1 = "persisted-aggregate-format/v1"


class RunAggregate:
    """Mutable application aggregate; repository snapshots detach its domain values."""

    def __init__(
        self,
        *,
        run: ResearchRun,
        goal: ResearchGoal,
        scheme: ResearchSchemeSnapshot,
        runtime: RuntimeState,
        node_binding: NodeBindingState | None = None,
        aggregate_schema_version: int = 2,
        confirmed_risk_semantic_binding: ConfirmedRiskSemanticBindingV1 | None = None,
    ) -> None:
        self._historical_codec_provenance = None
        self.aggregate_schema_version = aggregate_schema_version
        self.confirmed_risk_semantic_binding = confirmed_risk_semantic_binding
        self.run = run
        self.goal = goal
        self.scheme = scheme
        self.runtime = runtime
        self.node_binding = node_binding
        self.artifacts = CompletedRunArtifacts()
