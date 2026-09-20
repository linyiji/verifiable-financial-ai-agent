"""Closed values for the single human-authorized Risk child transition.

These values are embedded in existing Run owners; they are never a second store.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from src.domain.node_binding import BindingValue, GraphIdentity, OutputRecord, digest

POLICY = "RISK_ADD_CHILD_TASK_HUMAN_V1"
SCHEMA = "risk-follow-up-replan/v1"


class RiskFollowUpPolicyV1(BindingValue):
    policy_version: Literal["RISK_ADD_CHILD_TASK_HUMAN_V1"] = POLICY
    max_approved_expansions_per_run: Literal[1] = 1
    max_per_source_node: Literal[1] = 1
    max_child_expansions: Literal[0] = 0
    decline_policy: Literal["DURABLE_DECLINED_INCOMPLETE_PAUSE/v1"]
    child_template: dict
    child_template_digest: str


class RiskReplanAudit(BindingValue):
    schema_version: Literal["risk-follow-up-audit/v1"] = "risk-follow-up-audit/v1"
    event_id: str
    type: Literal[
        "replan.requested",
        "replan.waiting_for_decision",
        "replan.approved",
        "replan.rejected",
        "replan.paused_incomplete",
        "replan.reopened",
        "replan.applied",
        "replan.stale_rejected",
        "replan.reopen_stale_rejected",
        "replan.failed",
        "replan.fulfilled",
        "research.cancelled",
    ]
    run_id: str
    object_id: str
    proposal_id: str
    proposal_digest: str
    base_graph: GraphIdentity
    graph: GraphIdentity
    control_revision: int = Field(ge=0)
    actor: Literal["LOCAL_SINGLE_USER"] | None
    decision_id: str | None
    timestamp: datetime
    failure_code: str | None
    # Historical v1 events remain readable without inventing missing lineage.
    authorized_diff_digest: str | None = None
    transition_id: str | None = None
    old_execution_snapshot_digest: str | None = None
    new_execution_snapshot_digest: str | None = None
    command_key_digest: str | None = None
    request_hash: str | None = None
    decision_revision: int | None = Field(default=None, ge=0, strict=True)
    terminal_status: Literal["CANCELLED", "FAILED", "RELEASED"] | None = None


class CandidateBinding(BindingValue):
    schema_version: Literal["risk-follow-up-candidate/v1"] = "risk-follow-up-candidate/v1"
    candidate_id: str
    candidate_digest: str
    run_id: str
    task_id: str
    graph: GraphIdentity
    task_fingerprint: str
    admission_binding_id: str
    reservation_id: str
    attempt_id: str
    resolved_input_binding_ids: tuple[str, ...]
    output_record: OutputRecord
    source_output_digest: str
    source_artifact_sha256: str
    schema_identity: str
    schema_digest: str
    profile_digest: str
    created_at: datetime


class CandidateDependency(BindingValue):
    proposal_id: str
    proposal_digest: str
    transition_id: str
    candidate_id: str
    candidate_digest: str
    source_attempt_id: str


class RiskFollowUpDiff(BindingValue):
    operation: Literal["ADD_CHILD_TASK"] = "ADD_CHILD_TASK"
    child_task_id: str
    source_task_id: str
    synthesis_task_id: str
    child_type: Literal["risk_follow_up"] = "risk_follow_up"
    assigned_agent: Literal["risk_analyst"] = "risk_analyst"
    skill_id: Literal["risk_analysis_v1"] = "risk_analysis_v1"
    goal: Literal["Validate the material risk signal as a bounded child task"] = (
        "Validate the material risk signal as a bounded child task"
    )
    origin: Literal["REPLAN"] = "REPLAN"
    reason_code: Literal["MATERIAL_RISK_FOLLOW_UP"] = "MATERIAL_RISK_FOLLOW_UP"
    output_requirements: dict


class ReplanDecisionRecord(BindingValue):
    decision_id: str
    action: Literal["APPROVE", "DECLINE", "REOPEN", "CANCEL"]
    actor: Literal["LOCAL_SINGLE_USER"]
    prior_revision: int = Field(ge=0)
    new_revision: int = Field(ge=1)
    prior_decision_id: str | None
    proposal_digest: str
    graph: GraphIdentity
    decided_at: datetime


class ReplanProposalV1(BindingValue):
    schema_version: Literal["risk-follow-up-replan/v1"] = SCHEMA
    source_candidate_id: str
    source_output_id: str
    source_admission_binding_id: str
    source_reservation_id: str
    source_attempt_id: str
    source_output_digest: str
    source_artifact_sha256: str
    base_graph: GraphIdentity
    base_execution_snapshot_digest: str
    scenario_snapshot_digest: str
    proposal_type: Literal["ADD_CHILD_TASK"] = "ADD_CHILD_TASK"
    diff: RiskFollowUpDiff
    reason_summary: str = Field(min_length=1, max_length=800)
    relevant_evidence_refs: tuple[str, ...] = ()
    relevant_claim_refs: tuple[str, ...] = ()
    required_child_profile: dict
    child_profile_digest: str
    output_contract_digest: str
    policy_version: Literal["RISK_ADD_CHILD_TASK_HUMAN_V1"] = POLICY
    expansion_ordinal: Literal[1] = 1
    proposal_digest: str
    decision_revision: int = Field(default=0, ge=0)
    latest_decision_id: str | None = None
    history: tuple[ReplanDecisionRecord, ...] = ()
    disposition: Literal["DECLINED"] | None = None
    application_state: Literal["NOT_AUTHORIZED", "AWAITING_QUIESCENCE", "APPLIED", "FAILED"] = (
        "NOT_AUTHORIZED"
    )
    applied_graph: GraphIdentity | None = None
    transition_id: str | None = None
    failure_code: str | None = None
    decline_base_graph: GraphIdentity | None = None
    reopened: bool = False

    def semantic_digest(self, request):
        immutable = self.model_dump(
            exclude={
                "proposal_digest",
                "decision_revision",
                "latest_decision_id",
                "history",
                "disposition",
                "application_state",
                "applied_graph",
                "transition_id",
                "failure_code",
                "decline_base_graph",
                "reopened",
            }
        )
        return digest(
            {
                "proposal": immutable,
                "identity": {
                    key: getattr(request, key)
                    for key in (
                        "replan_id",
                        "run_id",
                        "requesting_task_id",
                        "requested_by",
                        "reason_code",
                        "proposed_graph_change",
                    )
                },
            },
            SCHEMA,
        )


class ResultReuseCertificate(BindingValue):
    transition_id: str
    source_result_id: str
    source_result_digest: str
    source_graph: GraphIdentity
    target_graph: GraphIdentity
    task_fingerprint: str
    admission_digest: str
    profile_digest: str
    output_contract_digest: str
    dependency_result_ids: tuple[str, ...]
    material_digests: tuple[str, ...]
    verification: Literal["VERIFIED_UNCHANGED_CLOSURE"] = "VERIFIED_UNCHANGED_CLOSURE"


class RecoveryCarryCertificate(BindingValue):
    transition_id: str
    reservation_id: str
    prior_admission_digest: str
    source_graph: GraphIdentity
    target_graph: GraphIdentity
    task_fingerprint: str
    profile_digest: str
    recovery_digest: str
    dependency_result_ids: tuple[str, ...]


class ReplanTransition(BindingValue):
    transition_id: str
    run_id: str
    proposal_id: str
    proposal_digest: str
    decision_id: str
    actor: Literal["LOCAL_SINGLE_USER"]
    base_graph: GraphIdentity
    new_graph: GraphIdentity
    authorized_diff: RiskFollowUpDiff
    old_graph_snapshot: dict
    old_execution_snapshot: dict
    old_execution_snapshot_digest: str
    new_execution_snapshot_digest: str
    applied_at: datetime
    reused_results: tuple[ResultReuseCertificate, ...] = ()
    carried_recovery: tuple[RecoveryCarryCertificate, ...] = ()


class FinalizationBinding(BindingValue):
    finalization_id: str
    finalization_digest: str
    run_id: str
    source_task_id: str
    source_candidate_id: str
    source_candidate_digest: str
    source_admission_binding_id: str
    source_graph: GraphIdentity
    source_profile_digest: str
    target_graph: GraphIdentity
    transition_id: str
    proposal_digest: str
    decision_id: str
    fulfilling_child_task_id: str
    child_output_id: str
    child_output_content_digest: str
    finalization_group_id: str
    committed_at: datetime


class ReplanControl(BindingValue):
    schema_version: Literal["risk-follow-up-control/v1"] = "risk-follow-up-control/v1"
    active_proposal_id: str
    control_revision: int = Field(default=0, ge=0)
    wait_reason: Literal[
        "DECISION",
        "DECLINED_INCOMPLETE",
        "DECISION_APPLY",
        "FOLLOW_UP_EXECUTION",
        "FULFILLED",
        "CANCELLED",
        "CONTROL_FAILED",
    ] = "DECISION"
    reopenable: bool = False
    resume_eligible: bool = False
    expansion_count: int = Field(default=0, ge=0, le=1)
    candidate: CandidateBinding
    transition: ReplanTransition | None = None
    finalization: FinalizationBinding | None = None
    receipts: dict[str, dict] = Field(default_factory=dict)
    audit: tuple[dict, ...] = ()
