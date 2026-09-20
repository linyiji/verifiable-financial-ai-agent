"""Versioned values for explicit, same-Run Risk execution cycles.

These values alone grant no permission. The Application repository must validate
and commit them under the aggregate lock before a worker may consume a cycle.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from src.domain.node_binding import BindingReference, BindingValue, GraphIdentity, digest
from src.domain.recovery import RecoveryBudget

VERSION = "external-failure-risk-resume/v1"
ROUTES = ("teamorouter-sol", "teamorouter-terra")


class FailureCycleIdentity(BindingValue):
    operation_id: str
    failed_reservation_id: str
    failed_reservation_generation: int = Field(ge=1)
    terminal_receipt_id: str
    terminal_receipt_digest: str
    ordered_receipts_digest: str
    failed_state_snapshot_digest: str


class HistoricalAdoption(BindingValue):
    contract_version: Literal["external-failure-risk-resume/v1"] = VERSION
    expected_legacy_snapshot_digest: str
    acknowledge_preserved_terminal_history: Literal[True]


class ResumeExternalFailure(BindingValue):
    run_id: str
    failed_node_id: str
    actor: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=256)
    expected_run_state: Literal["FAILED"] = "FAILED"
    expected_binding_ref: BindingReference
    expected_owner_generation: int = Field(ge=0)
    expected_graph_identity: GraphIdentity
    expected_profile_digest: str
    expected_scenario_digest: str
    expected_research_object_id: str
    expected_goal_hash: str
    expected_scheme_hash: str
    expected_as_of: str
    expected_failure_cycle_identity: FailureCycleIdentity
    expected_resume_envelope_digest: str
    historical_adoption: HistoricalAdoption | None = None


class CompletedWorkReuseDecisionV1(BindingValue):
    kind: Literal["Evidence", "Fundamentals", "Peers", "ResearchNews", "Valuation"]
    producer_task_id: str
    result_id: str
    result_digest: str
    decision: Literal["REUSE_ALLOWED_WITH_VALIDATION"] = "REUSE_ALLOWED_WITH_VALIDATION"
    validation_authority: Literal["ApplicationRepository/v1"] = "ApplicationRepository/v1"
    binding_ref: BindingReference
    graph: GraphIdentity
    scenario_digest: str
    profile_digest: str
    research_object_id: str
    as_of: str
    dependency_bindings: tuple[dict, ...]
    material_manifest_digest: str
    checks: tuple[str, ...]
    reason_codes: tuple[str, ...] = ()


class FailureClosureV1(BindingValue):
    failure_id: str
    identity: FailureCycleIdentity
    task_id: str
    original_completed_at: datetime
    closed_at: datetime
    archived_reservation: dict
    receipts: tuple[dict, ...]
    legacy_snapshot: dict | None = None


class RiskResumeExecutionEnvelopeV1(BindingValue):
    schema_version: Literal["external-failure-risk-resume/v1"] = VERSION
    authorization_id: str
    cycle_id: str
    operation_id: str
    cycle_ordinal: int = Field(default=1, ge=1)
    prior_failure_cycle_identity: FailureCycleIdentity
    run_id: str
    task_id: str
    object_id: str
    goal_hash: str
    scheme_hash: str
    as_of: str
    graph: GraphIdentity
    scenario_digest: str
    profile_digest: str
    task_fingerprint: str
    reuse_manifest_digest: str
    policy_digest: str
    authorized_at: datetime
    deadline_at: datetime
    budget: RecoveryBudget
    routes: tuple[Literal["teamorouter-sol", "teamorouter-terra"], ...] = ROUTES

    @model_validator(mode="after")
    def bounded(self):
        b = self.budget
        if (
            self.operation_id != "risk-resume:" + self.cycle_id
            or self.routes != ROUTES
            or b.max_total_attempts_per_task > 2
            or b.max_same_route_attempts != 1
            or b.max_model_fallbacks > 1
            or b.max_cross_provider_switches
            or b.max_capability_checks
            or b.max_runtime_replans
            or self.deadline_at <= self.authorized_at
            or (self.deadline_at - self.authorized_at).total_seconds()
            > min(300, b.max_total_recovery_time)
        ):
            raise ValueError("Invalid Risk Resume execution envelope")
        return self


class ResumeReceiptV1(BindingValue):
    authorization_id: str
    request_digest: str
    actor: str
    idempotency_key: str
    prior_failure_id: str
    new_cycle_id: str
    envelope_digest: str
    reuse_manifest: tuple[CompletedWorkReuseDecisionV1, ...]
    reuse_manifest_digest: str
    authorized_at: datetime
    committed_revision: int
    event_id: str
    original_failure_timestamp: datetime
    outcome: Literal["AUTHORIZED"] = "AUTHORIZED"


class ExternalFailureResumeV1(BindingValue):
    schema_version: Literal["external-failure-risk-resume/v1"] = VERSION
    failures: tuple[FailureClosureV1, ...] = ()
    envelopes: tuple[RiskResumeExecutionEnvelopeV1, ...] = ()
    receipts: tuple[ResumeReceiptV1, ...] = ()
    current_failure_id: str | None = None
    current_cycle_id: str | None = None
    audit: tuple[dict, ...] = ()

    @model_validator(mode="after")
    def consistent(self):
        failures = {v.failure_id: v for v in self.failures}
        cycles = {v.cycle_id: v for v in self.envelopes}
        if len(failures) != len(self.failures) or len(cycles) != len(self.envelopes):
            raise ValueError("Duplicate failure/cycle identity")
        keys, consumed, authorized_cycles = set(), set(), set()
        if len(self.receipts) != len(self.envelopes):
            raise ValueError("Cycle without exactly one authorization")
        for receipt in self.receipts:
            key = (receipt.actor, receipt.idempotency_key)
            cycle = cycles.get(receipt.new_cycle_id)
            failure = failures.get(receipt.prior_failure_id)
            if (
                key in keys
                or receipt.prior_failure_id in consumed
                or receipt.new_cycle_id in authorized_cycles
                or len(receipt.reuse_manifest) != 5
                or {item.kind for item in receipt.reuse_manifest}
                != {"Evidence", "Fundamentals", "Peers", "ResearchNews", "Valuation"}
                or cycle is None
                or failure is None
                or cycle.prior_failure_cycle_identity != failure.identity
                or cycle.authorization_id != receipt.authorization_id
                or digest(cycle, VERSION) != receipt.envelope_digest
                or digest(receipt.reuse_manifest, VERSION) != receipt.reuse_manifest_digest
                or cycle.reuse_manifest_digest != receipt.reuse_manifest_digest
            ):
                raise ValueError("Invalid Resume authorization binding")
            keys.add(key)
            consumed.add(receipt.prior_failure_id)
            authorized_cycles.add(receipt.new_cycle_id)
        if (self.current_failure_id is not None and self.current_failure_id not in failures) or (
            self.current_cycle_id is not None and self.current_cycle_id not in cycles
        ):
            raise ValueError("Missing current failure/cycle")
        return self


class ExternalFailureAuditV1(BindingValue):
    event_id: str
    type: Literal[
        "external_failure.closed", "external_failure.resume_authorized",
        "external_failure.cycle_claimed", "external_failure.cycle_succeeded",
    ]
    timestamp: datetime
    run_id: str
    failure_id: str
    cycle_id: str | None = None
    authorization_id: str | None = None
    binding_revision: int = Field(ge=1)
