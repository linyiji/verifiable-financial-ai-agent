from pydantic import Field

from src.domain.base import DomainModel, JsonObject
from src.domain.calculation import CalculationRecord
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.correction import CorrectionRecord
from src.domain.evidence import EvidenceRecord
from src.domain.proof import ProofResult
from src.domain.released_research_result import ReleasedResearchResult
from src.domain.research_goal import ResearchGoal
from src.domain.research_run import ResearchRun
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.review import ReviewRecord
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


class CompletedRunArtifacts(DomainModel):
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    calculations: list[CalculationRecord] = Field(default_factory=list)
    corrections: list[CorrectionRecord] = Field(default_factory=list)
    replans: list[ReplanRequest] = Field(default_factory=list)
    review: ReviewRecord | None = None
    proofs: list[ProofResult] = Field(default_factory=list)
    canonical_record: CanonicalExecutionRecord | None = None
    released_result: ReleasedResearchResult | None = None
    projections: CanonicalRecordProjections | None = None
    report: FinancialReport | None = None
    writeback: ObjectWritebackProposal | None = None
    task_outputs: JsonObject = Field(default_factory=dict)
    parallel_task_peak: int = 0


class RunAggregate:
    """Mutable application aggregate; repository snapshots detach its domain values."""

    def __init__(
        self,
        *,
        run: ResearchRun,
        goal: ResearchGoal,
        scheme: ResearchSchemeSnapshot,
        runtime: RuntimeState,
    ) -> None:
        self.run = run
        self.goal = goal
        self.scheme = scheme
        self.runtime = runtime
        self.artifacts = CompletedRunArtifacts()
