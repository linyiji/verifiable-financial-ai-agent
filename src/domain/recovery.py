"""Closed, provider-neutral Phase 6 recovery contracts. No prompts or error text."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FailureClass(StrEnum):
    READ_TIMEOUT = "READ_TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    REMOTE_PROTOCOL_ERROR = "REMOTE_PROTOCOL_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    PROVIDER_5XX = "PROVIDER_5XX"
    OUTPUT_CONTRACT_FAILURE = "OUTPUT_CONTRACT_FAILURE"
    NON_RECOVERABLE_RUNTIME_FAILURE = "NON_RECOVERABLE_RUNTIME_FAILURE"
    RESEARCH_SEMANTIC_FAILURE = "RESEARCH_SEMANTIC_FAILURE"
    UNKNOWN = "UNKNOWN"


class Action(StrEnum):
    RETRY_SAME_ROUTE = "RETRY_SAME_ROUTE"
    SWITCH_MODEL = "SWITCH_MODEL"
    SWITCH_PROVIDER = "SWITCH_PROVIDER"
    CAPABILITY_CHECK = "CAPABILITY_CHECK"
    WAIT_AND_RETRY = "WAIT_AND_RETRY"
    REPLAN_TASK = "REPLAN_TASK"
    CORRECT_RESEARCH_PATH = "CORRECT_RESEARCH_PATH"
    FAIL_TASK = "FAIL_TASK"
    FAIL_RUN = "FAIL_RUN"


class Health(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class Capability(StrEnum):
    VERIFIED = "VERIFIED"
    CANDIDATE = "CANDIDATE"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"
    QUARANTINED = "QUARANTINED"


RouteId = Literal["teamorouter-sol", "teamorouter-luna", "mimo-direct"]
ModelId = Literal["gpt-5.6-sol", "gpt-5.6-luna", "mimo-v2.5", "mimo-v2.5-pro"]


class Scope(Frozen):
    run_id: str
    task_id: str
    object_id: str
    scheme_id: str
    task_profile: str
    agent_id: str
    context_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    contract_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def exact_identity(self):
        if not self.task_id.startswith(self.run_id + ":"):
            raise ValueError("Recovery task must belong to exact Run")
        for field in (
            self.run_id,
            self.task_id,
            self.object_id,
            self.scheme_id,
            self.task_profile,
            self.agent_id,
        ):
            if not field or len(field) > 256 or any(c.isspace() for c in field):
                raise ValueError("Invalid recovery identity")
        return self


class FailureAssessment(Frozen):
    failure_class: FailureClass
    failure_stage: Literal["PROVIDER", "OUTPUT", "IDENTITY", "RESEARCH", "RUNTIME"]
    recoverable: bool


class RecoveryBudget(Frozen):
    max_total_attempts_per_task: int = Field(default=3, ge=1, le=3)
    max_same_route_attempts: int = Field(default=1, ge=1, le=2)
    max_model_fallbacks: int = Field(default=1, ge=0, le=1)
    max_cross_provider_switches: int = Field(default=1, ge=0, le=1)
    max_capability_checks: int = Field(default=1, ge=0, le=1)
    max_recovery_decisions: int = Field(default=5, ge=0, le=5)
    max_runtime_replans: int = Field(default=0, ge=0, le=0)
    max_total_recovery_time: float = Field(default=300, gt=0, le=300)
    max_total_recovery_cost: float | None = Field(default=None, ge=0)


class Candidate(Frozen):
    route: RouteId
    provider: Literal["teamorouter", "mimo"]
    model: ModelId
    authority_exists: bool
    health: Health = Health.UNKNOWN
    capability: Capability = Capability.UNKNOWN
    exhausted: bool = False
    eligible: bool = False
    next_allowed_action: Action = Action.FAIL_TASK
    capability_evidence_refs: tuple[str, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def governed_route(self):
        expected = {
            "teamorouter-sol": ("teamorouter", {"gpt-5.6-sol"}),
            "teamorouter-luna": ("teamorouter", {"gpt-5.6-luna"}),
            "mimo-direct": ("mimo", {"mimo-v2.5", "mimo-v2.5-pro"}),
        }
        provider, models = expected[self.route]
        if self.provider != provider or self.model not in models:
            raise ValueError("Route/provider/model identity mismatch")
        return self


class RecoveryDecision(Frozen):
    scope: Scope
    action: Action
    target_route: RouteId | None = None
    reason_code: Literal[
        "NEXT_GOVERNED_ROUTE",
        "CAPABILITY_REQUIRED",
        "NO_ALLOWED_ROUTE",
        "BUDGET_EXHAUSTED",
        "NONRECOVERABLE",
    ]
    confidence: float = Field(default=1, ge=0, le=1)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=12)


class RecoveryContext(Frozen):
    scope: Scope
    failure: FailureAssessment
    current_route: RouteId
    candidates: tuple[Candidate, ...] = Field(max_length=3)
    attempt_history: tuple[RouteId, ...] = Field(max_length=3)
    remaining_attempts: int = Field(ge=0, le=3)
    remaining_checks: int = Field(ge=0, le=1)
    remaining_decisions: int = Field(ge=0, le=5)
    remaining_seconds: float = Field(ge=0, le=300)
    dependency_state: Literal["CURRENT_TASK_RUNNING"] = "CURRENT_TASK_RUNNING"
    downstream_state: Literal["WAITING_FOR_CURRENT_TASK"] = "WAITING_FOR_CURRENT_TASK"
    scheme_requirement: Literal["UNCHANGED_EXACT_INTENT"] = "UNCHANGED_EXACT_INTENT"
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=12)


class RecoveryEvidence(Frozen):
    record_id: str = Field(pattern=r"^REC-[0-9a-f-]{36}$")
    scope: Scope
    kind: Literal["ATTEMPT_STARTED", "ATTEMPT_COMPLETED", "DECISION", "TERMINAL"]
    attempt_id: str | None = Field(default=None, pattern=r"^ATT-[0-9a-f-]{36}$")
    attempt_number: int = Field(default=0, ge=0, le=4)
    route: RouteId | None = None
    provider: Literal["teamorouter", "mimo"] | None = None
    model: ModelId | None = None
    capability_check: bool = False
    outcome: Literal["STARTED", "PASS", "FAIL", "ALLOW", "DENY", "CANCELLED"]
    failure_class: FailureClass | None = None
    reason_code: Literal[
        "OBSERVED",
        "POLICY_DENIED",
        "RECOVERY_BUDGET_EXHAUSTED",
        "INTERRUPTED_EXECUTION",
        "NONRECOVERABLE",
    ] = "OBSERVED"
    action: Action | None = None
    decision: RecoveryDecision | None = None
    recovery_context: RecoveryContext | None = None
    timestamp: str
    latency_ms: float | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    output_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
