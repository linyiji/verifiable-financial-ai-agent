"""Migration-independent Phase 4 product projection builders.

All builders are pure: repositories first reconstruct one transactionally
consistent Run snapshot, then pass the exact durable records here.  These
functions never search for a latest/first record, infer missing identities, or
manufacture facts that the frozen contract marks as durable.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from pydantic import BaseModel

from src.assurance.independent_financial_review import (
    financial_review_input_snapshot_hash,
)
from src.domain.calculation import CalculationRecord
from src.domain.enums import ProofRequirement
from src.domain.evidence import EvidenceRecord
from src.domain.financial_semantics import MaterialFinancialClaim, ReleasedFinancialMetric
from src.domain.proof import ProofPolicyDecision
from src.output.financial_metrics import MATERIAL_FORMULAS
from src.phase4_product.artifacts import (
    ArtifactProjectionError,
    ArtifactRepresentationSource,
    ValidatedAnchorManifest,
    build_report_artifact_group,
    validate_anchor_manifest,
    verify_artifact_bytes,
)
from src.phase4_product.contracts import (
    ArtifactSummaryV1,
    AtomicRunProjectionV1,
    AvailabilityStatus,
    AvailabilityV1,
    CalculationAvailabilityRefV1,
    ClaimDetailV1,
    ErrorCodeV1,
    EvidenceAvailabilityRefV1,
    ExecutionProjectionV1,
    ExecutionSummaryV1,
    FinancialReviewCheckProjectionV1,
    FinancialReviewProjectionV1,
    GoalProjectionV1,
    GraphProjectionV1,
    JudgmentAvailabilityV1,
    MethodMetadataV1,
    MethodParameterV1,
    MetricProofProjectionV1,
    ObjectIdentityV1,
    PathChangeProjectionV1,
    ProofSummaryV1,
    ProofTraceRefV1,
    ReleasedFinancialMetricProjectionV1,
    ReleasedObjectCoreV1,
    ReleasedResultProjectionV1,
    ReportArtifactGroupV1,
    ResearchRunCollectionV1,
    ResearchRunDetailV1,
    ResultSummaryV1,
    ReviewAvailabilityRefV1,
    ReviewCorrectionRefV1,
    ReviewSubjectV1,
    ReviewSummaryV1,
    RunCollectionActivityV1,
    RunCollectionItemV1,
    RunCollectionObjectV1,
    RunLifecycleV1,
    RunProgressV1,
    SafeJsonObject,
    SafeRuntimeActivityV1,
    SchemeProjectionV1,
    TaskAvailabilityRefV1,
    TaskProjectionV1,
    TerminalStateV1,
    TraceBundleV1,
    TraceReportV1,
    TraceRepresentationV1,
    TypedGraphOperationV1,
    TypedReleasedClaimV1,
)
from src.phase4_product.errors import ProductError
from src.phase4_product.hashing import canonical_json_sha256, require_sha256_identity
from src.phase4_product.safety import (
    JsonAllowlist,
    JsonKeyPattern,
    UnsafeProjectionData,
    safe_json,
    safe_json_object,
    safe_text,
)

_MISSING = object()
_SAFE_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")

_RELEASE_POLICY_VERSION = "phase4-release-eligibility/v1"
_REVIEW_POLICY_VERSION = "phase4-independent-financial-review/v1"
_MATERIAL_OUTPUT_POLICY_VERSION = "phase4-full-material-output/v1"
_ARTIFACT_POLICY_VERSION = "phase4-html-required-pdf-optional/v1"
_PROOF_POLICY_PREIMAGE_VERSION = "phase4-proof-policy-hash-preimage/v1"
_MATERIAL_OUTPUT_PREIMAGE_VERSION = "phase4-material-output-hash-preimage/v1"
_ARTIFACT_PREIMAGE_VERSION = "phase4-artifact-manifest-hash-preimage/v1"
_RELEASE_CLOSURE_PREIMAGE_VERSION = "phase4-release-closure-hash-preimage/v1"
_CANONICAL_EXECUTION_PREIMAGE_VERSION = "phase4-canonical-execution-release-preimage/v1"
_RUN_COLLECTION_CURSOR_VERSION = "phase4-run-collection-cursor/v1"
_RUN_COLLECTION_CURSOR_PREFIX = "p4rc1"
_RUN_COLLECTION_CURSOR_MAX_LENGTH = 2048

_RUN_STATUS: dict[str, tuple[str, bool, str | None]] = {
    "DRAFT": ("PREPARE", False, None),
    "SCHEME_GENERATING": ("PREPARE", False, None),
    "AWAITING_CONFIRMATION": ("CONFIRM", False, None),
    "PLANNING": ("PLANNING", False, None),
    "RUNNING": ("RESEARCH", False, None),
    "REVIEW": ("REVIEW", False, None),
    "PROVING": ("PROVING", False, None),
    "RELEASED": ("COMPLETE", True, "SUCCESS"),
    "FAILED": ("FAILED", True, "FAILURE"),
    "CANCELLED": ("CANCELLED", True, "CANCELLED"),
}
_TASK_STATUS: dict[str, tuple[str, bool]] = {
    "CREATED": ("QUEUED", False),
    "WAITING": ("QUEUED", False),
    "READY": ("READY", False),
    "RUNNING": ("ACTIVE", False),
    "WAITING_FOR_CAPABILITY": ("WAITING_SUPPORT", False),
    "SELF_CORRECTING": ("CORRECTING", False),
    "BLOCKED": ("BLOCKED", False),
    "REVIEW": ("REVIEW", False),
    "COMPLETED": ("COMPLETE", True),
    "FAILED": ("FAILED", True),
    "CAPABILITY_BUILD_FAILED": ("FAILED", True),
    "CANCELLED": ("CANCELLED", True),
}

_TASK_COVERAGE_ALLOWLIST: JsonAllowlist = {
    "news": {
        "status": None,
        "http_status": None,
        "error_code": None,
        "accepted_count": None,
        "accepted_evidence_ids": None,
    },
    "transcript": {
        "status": None,
        "http_status": None,
        "error_code": None,
        "accepted_count": None,
        "accepted_evidence_ids": None,
    },
}

_REVIEW_JSON_KEYS = frozenset(
    {
        "formula_ids",
        "count",
        "calculations",
        "metrics",
        "claims",
        "run_id",
        "status",
        "input_count",
        "resolved_input_count",
        "implementation_hash",
        "formula_id",
        "value",
        "tolerance",
        "bound_to_evidence",
        "metric_id",
        "unique",
        "unique_count",
        "must_prove_formula",
        "required_calculation_ids",
    }
)

_PEER_SYMBOL_KEYS = JsonKeyPattern(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
_CALCULATION_INPUT_KEYS: JsonAllowlist = {
    "actuality": None,
    "average_includes_latest_observation": None,
    "capital_expenditure": None,
    "close": None,
    "closes": None,
    "corporate_action_status": None,
    "currency": None,
    "current_period": None,
    "current_revenue": None,
    "decimal_context_policy_id": None,
    "decimal_precision": None,
    "decimal_rounding": None,
    "ebitda": None,
    "ema_adjust": None,
    "ema_seed": None,
    "fast_ema": None,
    "fast_span": None,
    "first_as_of": None,
    "free_cash_flow": None,
    "last_as_of": None,
    "observation_count": None,
    "operating_cash_flow": None,
    "peer_values": _PEER_SYMBOL_KEYS,
    "period": None,
    "period_basis": None,
    "price_change_count": None,
    "prior_period": None,
    "prior_revenue": None,
    "revenue": None,
    "rsi_method": None,
    "signal_ema": None,
    "signal_span": None,
    "slow_ema": None,
    "slow_span": None,
    "statement_cohort": None,
    "statement_series": None,
    "technical_price_basis": None,
    "value": None,
    "values": None,
    "volume": None,
    "volumes": None,
    "warmup_required": None,
    "warmup_satisfied": None,
    "window": None,
    "zero_gain_and_loss_policy": None,
}
_GENERATED_RESULT_KEYS: JsonAllowlist = {
    "unit": None,
    "value": None,
}
_CALCULATION_PARAMETER_KEYS: JsonAllowlist = {
    "actuality": None,
    "as_of": None,
    "capital_expenditure_sign_convention": None,
    "currency": None,
    "decimal_context_policy_id": None,
    "decimal_precision": None,
    "decimal_rounding": None,
    "ema_adjust": None,
    "ema_seed": None,
    "excluded_periods": None,
    "fast_span": None,
    "financial_validation_reason": None,
    "financial_validation_result": None,
    "formula_expression": None,
    "generated_source_hash": None,
    "generated_tests_hash": None,
    "live_input_commitment": None,
    "lookback": None,
    "method": None,
    "metric": None,
    "missing_value_policy": None,
    "owned_oracle_result": _GENERATED_RESULT_KEYS,
    "peer_count": None,
    "peer_symbols": None,
    "period": None,
    "period_basis": None,
    "projection_policy": None,
    "runtime_result": _GENERATED_RESULT_KEYS,
    "semantic_precondition": None,
    "signal_span": None,
    "slow_span": None,
    "statement_cohort": None,
    "validation_schema_version": None,
    "validation_scope": None,
    "warmup_required": None,
    "window": None,
}

_SOURCE_COVERAGE_ALLOWLIST: JsonAllowlist = {
    "news": {
        "status": None,
        "evidence_ids": None,
        "reason": None,
        "limitation": None,
    },
    "transcript": {
        "status": None,
        "evidence_ids": None,
        "reason": None,
        "limitation": None,
    },
    "limitations": None,
}

_SAFE_FAILURE_ALLOWLIST: JsonAllowlist = {
    "status": None,
    "failure_stage": None,
    "failure_code": None,
    "safe_message": None,
}

_SAFE_FAILURE_CODES_BY_STAGE: dict[str, frozenset[str]] = {
    "PLANNING": frozenset({"PLANNING_FAILED"}),
    "DATA_EVIDENCE": frozenset({"DATA_EVIDENCE_FAILED"}),
    "TASK_EXECUTION": frozenset({"TASK_EXECUTION_FAILED"}),
    "GENERATED_CAPABILITY": frozenset({"GENERATED_CAPABILITY_FAILED"}),
    "FINANCIAL_REVIEW": frozenset({"FINANCIAL_REVIEW_BLOCKED", "FINANCIAL_REVIEW_FAILED"}),
    "PROOF": frozenset({"PROOF_INVALID", "PROOF_FAILED"}),
    "ARTIFACT_GENERATION": frozenset({"REQUIRED_ARTIFACT_GENERATION_FAILED"}),
    "RELEASE": frozenset({"RELEASE_GATE_BLOCKED", "RELEASE_FAILED"}),
    "POST_SCHEDULER": frozenset({"POST_SCHEDULER_FAILED"}),
    "PERSISTENCE": frozenset({"PERSISTENCE_FINALIZATION_FAILED"}),
}

_EVENT_PAYLOAD_KEYS: dict[str, frozenset[str]] = {
    "run.created": frozenset({"object_id"}),
    "run.started": frozenset(),
    "run.status_changed": frozenset({"status"}),
    "run.completed": frozenset({"status"}),
    "run.failed": frozenset({"status", "failure_stage", "failure_code", "safe_message"}),
    "scheme.generated": frozenset(
        {"scheme_id", "generated_by", "generated_at", "generation_stage", "retrospective"}
    ),
    "scheme.confirmed": frozenset({"scheme_id"}),
    "plan.generated": frozenset({"graph_id", "task_count"}),
    "task.created": frozenset({"task_type"}),
    "task.ready": frozenset(),
    "task.started": frozenset({"attempt"}),
    "task.progress": frozenset(
        {
            "kind",
            "progress",
            "progress_scale",
            "stage",
            "message_code",
            "attempt",
            "error_code",
        }
    ),
    "task.waiting_for_capability": frozenset({"gap_id"}),
    "task.resumed": frozenset({"gap_id", "registration_id", "status"}),
    "task.self_correcting": frozenset({"problem_code"}),
    "task.correction_resolved": frozenset({"correction_id"}),
    "task.completed": frozenset({"attempt"}),
    "task.failed": frozenset({"attempt", "failure_code", "status", "retry_suppressed"}),
    "replan.requested": frozenset({"replan_id", "decision"}),
    "replan.approved": frozenset({"replan_id", "decided_by"}),
    "graph.task_added": frozenset({"replan_id"}),
    "graph.edge_added": frozenset({"replan_id", "source_task_id", "target_task_id"}),
    "graph.edge_removed": frozenset({"replan_id", "source_task_id", "target_task_id"}),
    "graph.version_changed": frozenset({"replan_id", "version_before", "version_after"}),
    "evidence.accepted": frozenset(
        {
            "evidence_id",
            "field",
            "producer_task_id",
            "source_endpoint",
            "evidence_purpose",
            "evidence_category",
        }
    ),
    "calculation.started": frozenset({"capability_id"}),
    "calculation.completed": frozenset({"calculation_id", "capability_id"}),
    "capability.gap_detected": frozenset({"gap_id", "capability_id", "skill_id", "requested_by"}),
    "capability.build_requested": frozenset(
        {"gap_id", "build_id", "attempt", "max_attempts", "approved_by"}
    ),
    "capability.build_started": frozenset({"build_id", "attempt"}),
    "capability.generated": frozenset(
        {"build_id", "generated_capability_id", "implementation_hash"}
    ),
    "capability.static_validated": frozenset({"build_id", "implementation_hash"}),
    "capability.sandbox_started": frozenset({"build_id", "implementation_hash"}),
    "capability.test_passed": frozenset({"build_id", "implementation_hash"}),
    "capability.test_failed": frozenset({"build_id", "attempt", "failure_code"}),
    "capability.financial_validated": frozenset({"build_id", "implementation_hash"}),
    "capability.approved": frozenset({"build_id", "registration_id", "approved_by", "scope"}),
    "capability.registered": frozenset(
        {"registration_id", "capability_id", "capability_version", "scope"}
    ),
    "capability.build_failed": frozenset(
        {"gap_id", "build_id", "attempt", "max_attempts", "failure_code", "terminal"}
    ),
    "review.started": frozenset(),
    "review.resolved": frozenset({"review_id", "status"}),
    "proof.required": frozenset({"proof_id", "calculation_id", "formula_id", "policy_id"}),
    "proof.started": frozenset({"proof_id", "backend"}),
    "proof.generated": frozenset({"proof_id", "backend"}),
    "proof.verified": frozenset(
        {"proof_id", "image_id", "receipt_hash", "journal_hash", "verified", "dev_mode"}
    ),
    "proof.failed": frozenset({"proof_id", "failure_code", "status"}),
    "release.completed": frozenset({"canonical_record_id", "result_id"}),
}


class ProjectionIntegrityError(ValueError):
    """Raised when exact durable Run/Object closure cannot be proven."""


@dataclass(frozen=True, slots=True)
class RunStatusProjection:
    status: str
    stage: str
    terminal: bool
    terminal_outcome: str | None


@dataclass(frozen=True, slots=True)
class TaskStatusProjection:
    status: str
    stage: str
    terminal: bool


@dataclass(frozen=True, slots=True)
class RunCollectionSource:
    """Exact records needed to project one global/Object Run collection item.

    Repository composition owns the authoritative snapshot query.  In
    particular, ``updated_at``, the projection revision/watermark,
    ``latest_event``, and ``result_availability`` must already describe the
    same committed view; this pure builder does not repair or infer them.
    """

    run: object
    research_object: object
    actual_graph: object | None
    latest_event: object | None
    projection_revision: int
    projection_sequence: int
    result_availability: AvailabilityV1
    release_closure_valid: bool = False


@dataclass(frozen=True, slots=True)
class _RunCollectionFilterSet:
    object_id: str | None
    statuses: tuple[str, ...]
    result_availability: str | None

    def cursor_value(self) -> dict[str, object]:
        return {
            "object_id": self.object_id,
            "result_availability": self.result_availability,
            "statuses": list(self.statuses),
        }


@dataclass(frozen=True, slots=True)
class MetricProofJoin:
    projection: MetricProofProjectionV1
    trace_refs: tuple[ProofTraceRefV1, ...]


@dataclass(frozen=True, slots=True)
class ReleaseCandidateSourceV1:
    """Exact retained rows used to rederive one release candidate.

    The projection DTOs and ReleaseValidation digests are not source authority:
    a reader must retain the independently reviewable records that produced
    Review B, Released Result L, Canonical Execution X and each Proof join.
    The Parent PostgreSQL adapter must load these rows in the same MVCC
    snapshot as the candidate and its validation history.
    """

    run: object
    review: object
    canonical_record: object
    released_result: object
    tasks: Sequence[object]
    proof_records: Sequence[object]
    correction_records: Sequence[object]
    evidence_records: Sequence[object]
    calculation_records: Sequence[object]
    metric_records: Sequence[object]
    claim_records: Sequence[object]
    judgment_records: Sequence[object]
    proof_policy_decisions: Sequence[object]
    anchor_manifest: object
    html_artifact: ArtifactRepresentationSource
    pdf_artifact: ArtifactRepresentationSource
    artifact_availability: AvailabilityV1
    html_payload: bytes
    pdf_payload: bytes | None = None
    proof_verifications: Sequence[object] = ()
    proof_commitments: Sequence[object] = ()


@dataclass(frozen=True, slots=True)
class EligibleReleasedObjectCandidate:
    """One fully validated release considered by Released Object Core ordering."""

    run: RunCollectionItemV1
    # This remains one field for source compatibility, but its value is the
    # complete persisted validation row collection for the Run.  A singular
    # mapping/object cannot prove database cardinality and therefore fails
    # closed in ``build_released_object_core``.
    validation: Sequence[object]
    review: FinancialReviewProjectionV1
    result: ReleasedResultProjectionV1
    execution: ExecutionProjectionV1
    artifacts: ReportArtifactGroupV1
    proof: ProofSummaryV1
    source: ReleaseCandidateSourceV1


@dataclass(frozen=True, slots=True)
class ReleaseValidationHashes:
    """RFC 8785 hashes recomputed from one exact release candidate.

    The four preimage-version tokens are implementation-local until the Parent
    persistence composition stores and freezes the same writer inputs.  They
    intentionally do not alter a public response DTO.
    """

    proof_policy_hash: str
    material_output_manifest_hash: str
    artifact_manifest_hash: str
    closure_hash: str


@dataclass(frozen=True, slots=True)
class _ClaimAssembly:
    claim: TypedReleasedClaimV1
    metric: ReleasedFinancialMetricProjectionV1
    task_refs: tuple[TaskAvailabilityRefV1, ...]
    primary_task_id: str | None
    evidence: tuple[SafeJsonObject, ...]
    evidence_refs: tuple[EvidenceAvailabilityRefV1, ...]
    calculations: tuple[SafeJsonObject, ...]
    calculation_refs: tuple[CalculationAvailabilityRefV1, ...]
    judgment_refs: tuple[JudgmentAvailabilityV1, ...]
    review_refs: tuple[ReviewAvailabilityRefV1, ...]
    proof_refs: tuple[ProofTraceRefV1, ...]
    canonical_record_id: str
    released_result_id: str
    manifest: ValidatedAnchorManifest
    report: TraceReportV1


def project_run_status(status: object) -> RunStatusProjection:
    raw = _enum_text(status, context="Run status")
    mapped = _RUN_STATUS.get(raw)
    if mapped is None:
        raise ProjectionIntegrityError(f"unsupported Run status: {raw}")
    stage, terminal, outcome = mapped
    return RunStatusProjection(
        status=raw,
        stage=stage,
        terminal=terminal,
        terminal_outcome=outcome,
    )


def project_task_status(status: object) -> TaskStatusProjection:
    raw = _enum_text(status, context="Task status")
    mapped = _TASK_STATUS.get(raw)
    if mapped is None:
        raise ProjectionIntegrityError(f"unsupported Task status: {raw}")
    stage, terminal = mapped
    return TaskStatusProjection(status=raw, stage=stage, terminal=terminal)


def calculate_run_progress(
    tasks: Sequence[object],
    *,
    run_status: object,
    release_closure_valid: bool = False,
) -> RunProgressV1:
    """Apply the frozen ACTUAL_TASK_MEAN_V1 algorithm exactly."""

    status = project_run_status(run_status)
    task_values = tuple(tasks)
    projected_statuses = tuple(project_task_status(_field(task, "status")) for task in task_values)
    completed = sum(item.status == "COMPLETED" for item in projected_statuses)
    total = len(task_values)
    progresses = tuple(
        _ratio(_field(task, "progress"), context=f"Task[{index}].progress")
        for index, task in enumerate(task_values)
    )

    if status.status == "RELEASED":
        if not release_closure_valid:
            raise ProjectionIntegrityError("RELEASED progress requires valid release closure")
        fraction = 1.0
    elif (
        status.status in {"FAILED", "CANCELLED"}
        and task_values
        and all(item.terminal for item in projected_statuses)
    ):
        fraction = 1.0
    elif total == 0:
        fraction = 0.0
    else:
        fraction = math.fsum(progresses) / total
    return RunProgressV1(
        completed_tasks=completed,
        total_tasks=total,
        fraction=fraction,
    )


def project_object(research_object: object) -> ObjectIdentityV1:
    return ObjectIdentityV1(
        object_id=_required_string(research_object, "object_id", "ResearchObject"),
        symbol=_required_string(research_object, "symbol", "ResearchObject"),
        company_name=_required_string(research_object, "company_name", "ResearchObject"),
        object_type=_required_string(research_object, "object_type", "ResearchObject"),
        exchange=_required_string(research_object, "exchange", "ResearchObject"),
        sector=_optional_string(_field(research_object, "sector", None), context="object.sector"),
        currency=_required_string(research_object, "currency", "ResearchObject"),
        identity_version=_positive_int(
            _field(research_object, "identity_version"),
            context="ResearchObject.identity_version",
        ),
    )


def project_goal(goal: object, *, expected_object_id: str) -> GoalProjectionV1:
    if _required_string(goal, "research_object_id", "Goal") != expected_object_id:
        raise ProjectionIntegrityError("Goal belongs to another ResearchObject")
    preferences = _field(goal, "preferences")
    # Preferences are an authoring surface, not an open channel.  The current
    # Core accepts only the frozen preparation keys.
    try:
        safe_preferences = safe_json_object(
            preferences,
            allowed_keys={"currency", "depth", "include_peers"},
            context="Goal.preferences",
        )
    except UnsafeProjectionData as exc:
        raise ProjectionIntegrityError(str(exc)) from exc
    return GoalProjectionV1(
        goal_id=_required_string(goal, "goal_id", "Goal"),
        research_object_id=expected_object_id,
        goal_type=_required_string(goal, "goal_type", "Goal"),
        goal_text=safe_text(_field(goal, "goal_text"), context="Goal.goal_text"),
        as_of=_required_date(goal, "as_of", "Goal"),
        preferences=safe_preferences,
        created_at=_required_datetime(goal, "created_at", "Goal"),
    )


def project_scheme(
    scheme: object,
    *,
    expected_object_id: str,
    expected_goal_id: str,
    require_confirmed: bool = True,
) -> SchemeProjectionV1:
    if (
        _required_string(scheme, "research_object_id", "Scheme") != expected_object_id
        or _required_string(scheme, "goal_id", "Scheme") != expected_goal_id
    ):
        raise ProjectionIntegrityError("Scheme belongs to another Object/Goal")
    confirmed_at = _optional_datetime(_field(scheme, "confirmed_at", None), "Scheme.confirmed_at")
    if require_confirmed and confirmed_at is None:
        raise ProjectionIntegrityError("Run projection requires an explicitly confirmed Scheme")
    try:
        assurance = safe_json_object(
            _field(scheme, "assurance_requirements"),
            allowed_keys={
                "financial_review",
                "proof_policy",
                "required",
                "reviewer",
                "policy_id",
            },
            context="Scheme.assurance_requirements",
        )
    except UnsafeProjectionData as exc:
        raise ProjectionIntegrityError(str(exc)) from exc
    return SchemeProjectionV1(
        scheme_id=_required_string(scheme, "scheme_id", "Scheme"),
        research_object_id=expected_object_id,
        goal_id=expected_goal_id,
        research_scope=_string_tuple(_field(scheme, "research_scope"), "Scheme.research_scope"),
        data_requirements=_string_tuple(
            _field(scheme, "data_requirements"), "Scheme.data_requirements"
        ),
        agent_requirements=_string_tuple(
            _field(scheme, "agent_requirements"), "Scheme.agent_requirements"
        ),
        skill_requirements=_string_tuple(
            _field(scheme, "skill_requirements"), "Scheme.skill_requirements"
        ),
        calculation_requirements=_string_tuple(
            _field(scheme, "calculation_requirements"),
            "Scheme.calculation_requirements",
        ),
        assurance_requirements=assurance,
        report_requirements=_string_tuple(
            _field(scheme, "report_requirements"), "Scheme.report_requirements"
        ),
        limitations=_string_tuple(_field(scheme, "limitations"), "Scheme.limitations"),
        generated_by=_required_string(scheme, "generated_by", "Scheme"),
        generated_model=_optional_string(
            _field(scheme, "generated_model", None), context="Scheme.generated_model"
        ),
        created_at=_required_datetime(scheme, "created_at", "Scheme"),
        confirmed_at=confirmed_at,
    )


def project_run_detail(
    run: object,
    *,
    projection_revision: int,
    projection_sequence: int,
) -> ResearchRunDetailV1:
    status = project_run_status(_field(run, "status"))
    return ResearchRunDetailV1(
        run_id=_required_string(run, "run_id", "Run"),
        research_object_id=_required_string(run, "research_object_id", "Run"),
        goal_id=_required_string(run, "goal_id", "Run"),
        scheme_id=_required_string(run, "scheme_id", "Run"),
        status=status.status,
        stage=status.stage,
        as_of=_required_date(run, "as_of", "Run"),
        planned_graph_id=_optional_string(
            _field(run, "planned_graph_id", None), context="Run.planned_graph_id"
        ),
        actual_graph_id=_optional_string(
            _field(run, "actual_graph_id", None), context="Run.actual_graph_id"
        ),
        execution_target=_required_string(run, "execution_target", "Run"),
        created_at=_required_datetime(run, "created_at", "Run"),
        updated_at=_required_datetime(run, "updated_at", "Run"),
        started_at=_optional_datetime(_field(run, "started_at", None), "Run.started_at"),
        completed_at=_optional_datetime(_field(run, "completed_at", None), "Run.completed_at"),
        terminal=status.terminal,
        projection_revision=_positive_int(
            projection_revision,
            context="projection_revision",
        ),
        projection_sequence=_nonnegative_int(
            projection_sequence,
            context="projection_sequence",
        ),
    )


def project_run_collection_item(source: RunCollectionSource) -> RunCollectionItemV1:
    """Project one exact Run collection row without choosing substitute records."""

    if not isinstance(source, RunCollectionSource):
        raise ProjectionIntegrityError("Run collection source must be an exact record set")
    if not isinstance(source.release_closure_valid, bool):
        raise ProjectionIntegrityError("release_closure_valid must be boolean")
    if not isinstance(source.result_availability, AvailabilityV1):
        raise ProjectionIntegrityError(
            "result_availability must be an exact AvailabilityV1 projection"
        )

    detail = project_run_detail(
        source.run,
        projection_revision=source.projection_revision,
        projection_sequence=source.projection_sequence,
    )
    object_projection = project_object(source.research_object)
    if detail.research_object_id != object_projection.object_id:
        raise ProjectionIntegrityError("Run collection Object/Run ownership closure failed")

    graph_id = detail.actual_graph_id
    if graph_id is None:
        if source.actual_graph is not None:
            raise ProjectionIntegrityError("Run collection contains an unreferenced actual graph")
        graph = None
        tasks: tuple[object, ...] = ()
        known_task_ids: tuple[str, ...] = ()
    else:
        if source.actual_graph is None:
            raise ProjectionIntegrityError("Run collection is missing its exact actual graph")
        graph = project_graph(
            source.actual_graph,
            expected_run_id=detail.run_id,
            expected_graph_id=graph_id,
        )
        tasks = _sequence(_field(source.actual_graph, "tasks"), "Graph.tasks")
        known_task_ids = tuple(item.task_id for item in graph.tasks)

    if source.latest_event is None:
        if detail.projection_sequence != 0:
            raise ProjectionIntegrityError(
                "Run collection event watermark lacks its exact latest RuntimeEvent"
            )
        activity = None
    else:
        activity = project_event(
            source.latest_event,
            expected_run_id=detail.run_id,
            known_task_ids=known_task_ids,
            projection_sequence=detail.projection_sequence,
        )
        if activity.sequence != detail.projection_sequence:
            raise ProjectionIntegrityError(
                "Run collection latest activity does not equal its event watermark"
            )
        if activity.timestamp > detail.updated_at:
            raise ProjectionIntegrityError(
                "Run collection activity is newer than durable updated_at"
            )
        if activity.timestamp < detail.created_at:
            raise ProjectionIntegrityError("Run collection activity precedes durable created_at")

    if detail.created_at > detail.updated_at:
        raise ProjectionIntegrityError("Run collection updated_at precedes created_at")
    if detail.started_at is not None and detail.started_at < detail.created_at:
        raise ProjectionIntegrityError("Run collection started_at precedes created_at")
    if detail.started_at is not None and detail.started_at > detail.updated_at:
        raise ProjectionIntegrityError("Run collection started_at exceeds updated_at")
    if detail.completed_at is not None:
        lower_bound = detail.started_at or detail.created_at
        if detail.completed_at < lower_bound:
            raise ProjectionIntegrityError(
                "Run collection completed_at precedes its lifecycle start"
            )
        if detail.completed_at > detail.updated_at:
            raise ProjectionIntegrityError("Run collection completed_at exceeds updated_at")

    status = project_run_status(detail.status)
    if status.terminal != (detail.completed_at is not None):
        raise ProjectionIntegrityError("Run collection terminal status and completed_at disagree")
    if status.terminal:
        expected_terminal_type = "run.completed" if status.status == "RELEASED" else "run.failed"
        if activity is None or activity.type != expected_terminal_type:
            raise ProjectionIntegrityError(
                "Run collection terminal activity is not the final matching event"
            )
        if activity.status != status.status:
            raise ProjectionIntegrityError(
                "Run collection terminal activity status disagrees with the Run"
            )
        if expected_terminal_type == "run.failed":
            terminal_payload = _model_mapping(_field(source.latest_event, "payload"))
            failure_code = _required_nonblank(
                terminal_payload.get("failure_code"),
                "RuntimeEvent.payload.failure_code",
            )
            if status.status == "CANCELLED" and failure_code != "RUN_CANCELLED":
                raise ProjectionIntegrityError(
                    "cancelled Run requires the frozen RUN_CANCELLED failure code"
                )
    elif activity is not None and activity.type in {"run.completed", "run.failed"}:
        raise ProjectionIntegrityError(
            "nonterminal Run collection item cannot end in a terminal event"
        )
    if activity is not None and activity.type == "run.status_changed":
        if activity.status is None:
            raise ProjectionIntegrityError("run.status_changed requires a status payload")
        activity_status = project_run_status(activity.status)
        if activity_status.terminal or activity_status.status != status.status:
            raise ProjectionIntegrityError(
                "run.status_changed does not match the current nonterminal Run"
            )
    if activity is not None and activity.type == "run.started":
        if (
            status.status != "RUNNING"
            or detail.started_at is None
            or detail.started_at != activity.timestamp
        ):
            raise ProjectionIntegrityError(
                "run.started activity does not match the current Run start"
            )
    _validate_public_availability(
        source.result_availability,
        context="RunCollectionItem.result",
    )
    result_status = source.result_availability.status
    if status.status == "RELEASED":
        if not source.release_closure_valid or result_status is not AvailabilityStatus.AVAILABLE:
            raise ProjectionIntegrityError(
                "RELEASED Run collection item requires valid available release closure"
            )
    else:
        if source.release_closure_valid:
            raise ProjectionIntegrityError("non-RELEASED Run cannot assert valid release closure")
        if result_status is AvailabilityStatus.AVAILABLE:
            raise ProjectionIntegrityError(
                "non-RELEASED Run collection item cannot expose an available result"
            )
        if status.terminal and result_status is AvailabilityStatus.PENDING:
            raise ProjectionIntegrityError(
                "terminal Run collection item cannot retain pending result availability"
            )
        if not status.terminal and result_status is not AvailabilityStatus.PENDING:
            raise ProjectionIntegrityError(
                "nonterminal Run collection item requires pending result availability"
            )

    progress = calculate_run_progress(
        tasks,
        run_status=status.status,
        release_closure_valid=source.release_closure_valid,
    )
    return RunCollectionItemV1(
        run_id=detail.run_id,
        object=RunCollectionObjectV1(
            object_id=object_projection.object_id,
            symbol=object_projection.symbol,
            company_name=object_projection.company_name,
        ),
        status=detail.status,
        stage=detail.stage,
        progress=progress,
        activity=(
            None
            if activity is None
            else RunCollectionActivityV1(
                event_id=activity.event_id,
                type=activity.type,
                sequence=activity.sequence,
                timestamp=activity.timestamp,
                task_id=activity.task_id,
                message_code=activity.message_code,
            )
        ),
        graph_version=None if graph is None else graph.version,
        projection_revision=detail.projection_revision,
        projection_sequence=detail.projection_sequence,
        as_of=detail.as_of,
        created_at=detail.created_at,
        updated_at=detail.updated_at,
        started_at=detail.started_at,
        completed_at=detail.completed_at,
        terminal=detail.terminal,
        result_availability=source.result_availability,
    )


def build_run_collection(
    *,
    sources: Sequence[RunCollectionSource],
    cursor_signing_key: bytes,
    limit: int = 50,
    object_id: str | None = None,
    statuses: Sequence[object] = (),
    result_availability: AvailabilityStatus | str | None = None,
    cursor: str | None = None,
) -> ResearchRunCollectionV1:
    """Filter, keyset-page, and project an authoritative Run snapshot.

    Cursors are versioned canonical JSON authenticated with HMAC-SHA256.  The
    token binds the normalized filter set and the final ordering tuple from
    the previous page.  The previous tuple must still exist in the supplied
    filtered snapshot, so a removed/unknown (expired) cursor fails closed
    instead of degrading to an offset or first-page read.
    """

    checked_limit = _positive_int(limit, context="Run collection limit")
    if checked_limit > 100:
        raise ProjectionIntegrityError("Run collection limit must be within 1..100")
    key = _run_collection_cursor_key(cursor_signing_key)
    filters = _normalize_run_collection_filters(
        object_id=object_id,
        statuses=statuses,
        result_availability=result_availability,
    )
    marker = (
        _decode_run_collection_cursor(
            cursor,
            signing_key=key,
            filters=filters,
        )
        if cursor is not None
        else None
    )

    filtered_sources = tuple(
        source for source in sources if _run_collection_source_matches(source, filters)
    )
    projected = tuple(project_run_collection_item(source) for source in filtered_sources)
    if any(not _run_collection_item_matches(item, filters) for item in projected):
        raise ProjectionIntegrityError("Run collection source filtering is inconsistent")
    run_ids = tuple(item.run_id for item in projected)
    if len(set(run_ids)) != len(run_ids):
        raise ProjectionIntegrityError("Run collection contains duplicate Run identities")
    ordered = tuple(
        sorted(
            projected,
            key=_run_collection_order_key,
            reverse=True,
        )
    )

    start = 0
    if marker is not None:
        matching_positions = tuple(
            index for index, item in enumerate(ordered) if _run_collection_order_key(item) == marker
        )
        if len(matching_positions) != 1:
            _raise_invalid_run_collection_cursor()
        start = matching_positions[0] + 1

    page = ordered[start : start + checked_limit]
    has_more = start + len(page) < len(ordered)
    next_cursor = (
        _encode_run_collection_cursor(
            item=page[-1],
            signing_key=key,
            filters=filters,
        )
        if has_more and page
        else None
    )
    return ResearchRunCollectionV1(items=page, next_cursor=next_cursor)


def project_task(task: object, *, expected_run_id: str) -> TaskProjectionV1:
    run_id = _required_string(task, "run_id", "Task")
    if run_id != expected_run_id:
        raise ProjectionIntegrityError("Task belongs to another Run")
    project_task_status(_field(task, "status"))
    try:
        coverage = safe_json_object(
            _field(task, "evidence_source_coverage"),
            allowed_keys=_TASK_COVERAGE_ALLOWLIST,
            context="Task.evidence_source_coverage",
        )
    except UnsafeProjectionData as exc:
        raise ProjectionIntegrityError(str(exc)) from exc
    return TaskProjectionV1(
        task_id=_required_string(task, "task_id", "Task"),
        run_id=run_id,
        parent_task_id=_optional_string(
            _field(task, "parent_task_id", None), context="Task.parent_task_id"
        ),
        task_type=_required_string(task, "task_type", "Task"),
        goal=safe_text(_field(task, "goal"), context="Task.goal"),
        assigned_agent=_required_string(task, "assigned_agent", "Task"),
        skill_id=_required_string(task, "skill_id", "Task"),
        dependencies=_unique_string_tuple(_field(task, "dependencies"), "Task.dependencies"),
        origin=_enum_text(_field(task, "origin"), context="Task.origin"),
        reason_code=_optional_string(_field(task, "reason_code", None), context="Task.reason_code"),
        status=_enum_text(_field(task, "status"), context="Task.status"),
        progress=_ratio(_field(task, "progress"), context="Task.progress"),
        attempt_count=_nonnegative_int(_field(task, "attempt_count"), context="Task.attempt_count"),
        task_input_evidence_ids=_unique_string_tuple(
            _field(task, "task_input_evidence_ids"),
            "Task.task_input_evidence_ids",
        ),
        task_output_evidence_ids=_unique_string_tuple(
            _field(task, "task_output_evidence_ids"),
            "Task.task_output_evidence_ids",
        ),
        evidence_acquisition_status=(
            None
            if _field(task, "evidence_acquisition_status", None) is None
            else _enum_text(
                _field(task, "evidence_acquisition_status"),
                context="Task.evidence_acquisition_status",
            )
        ),
        evidence_source_coverage=coverage,
        created_at=_required_datetime(task, "created_at", "Task"),
    )


def project_graph(
    graph: object,
    *,
    expected_run_id: str,
    expected_graph_id: str | None = None,
) -> GraphProjectionV1:
    run_id = _required_string(graph, "run_id", "Graph")
    graph_id = _required_string(graph, "graph_id", "Graph")
    if run_id != expected_run_id:
        raise ProjectionIntegrityError("Graph belongs to another Run")
    if expected_graph_id is not None and graph_id != expected_graph_id:
        raise ProjectionIntegrityError("Graph does not match the Run graph reference")
    raw_tasks = _sequence(_field(graph, "tasks"), "Graph.tasks")
    tasks = tuple(project_task(task, expected_run_id=run_id) for task in raw_tasks)
    task_ids = tuple(task.task_id for task in tasks)
    if len(set(task_ids)) != len(task_ids):
        raise ProjectionIntegrityError("Graph contains duplicate Task identities")
    known = set(task_ids)
    for task in tasks:
        if task.parent_task_id is not None and task.parent_task_id not in known:
            raise ProjectionIntegrityError("Task parent does not resolve inside its Run graph")
        if any(dependency not in known for dependency in task.dependencies):
            raise ProjectionIntegrityError("Task dependency does not resolve inside its Run graph")
        if task.task_id in task.dependencies:
            raise ProjectionIntegrityError("Task cannot depend on itself")
    return GraphProjectionV1(
        graph_id=graph_id,
        run_id=run_id,
        version=_positive_int(_field(graph, "version"), context="Graph.version"),
        tasks=tasks,
    )


def project_path_change(source: object, *, expected_run_id: str) -> PathChangeProjectionV1:
    run_id = _required_string(source, "run_id", "PathChange source")
    if run_id != expected_run_id:
        raise ProjectionIntegrityError("PathChange source belongs to another Run")

    correction_id = _field(source, "correction_id", None)
    if correction_id is not None:
        source_id = _required_nonblank(correction_id, "Correction.correction_id")
        task_id = _required_string(source, "task_id", "Correction")
        return PathChangeProjectionV1(
            path_change_id=source_id,
            source_kind="CORRECTION",
            source_id=source_id,
            change_kind="SELF_CORRECTION",
            status=_enum_text(_field(source, "status"), context="Correction.status"),
            decision=None,
            reason_code=_required_string(source, "problem_code", "Correction"),
            task_refs=(task_id,),
            operations=(),
            graph_version_before=_optional_positive_int(
                _field(source, "graph_version_before", None),
                "Correction.graph_version_before",
            ),
            graph_version_after=_optional_positive_int(
                _field(source, "graph_version_after", None),
                "Correction.graph_version_after",
            ),
            created_at=_required_datetime(source, "created_at", "Correction"),
            resolved_at=_optional_datetime(
                _field(source, "resolved_at", None), "Correction.resolved_at"
            ),
        )

    source_kind = _enum_text(_field(source, "source_kind"), context="PathChange.source_kind")
    if source_kind != "REPLAN":
        raise ProjectionIntegrityError("PathChange requires an exact Correction or Replan source")
    source_id = _required_string(source, "source_id", "PathChange")
    replan_id = _required_string(source, "replan_id", "Replan")
    if source_id != replan_id:
        raise ProjectionIntegrityError("Replan path_change_id/source_id must be identical")
    change_kind = _enum_text(_field(source, "change_kind"), context="Replan.change_kind")
    operations = tuple(
        _project_graph_operation(item, expected_run_id=run_id)
        for item in _sequence(_field(source, "operations"), "Replan.operations")
    )
    decision = _optional_enum_text(_field(source, "decision", None), "Replan.decision")
    if decision == "APPROVED" and not operations:
        raise ProjectionIntegrityError("approved Replan requires durable typed operations")
    if decision != "APPROVED" and operations:
        raise ProjectionIntegrityError("unapproved Replan cannot carry graph operations")
    task_refs = _unique_string_tuple(_field(source, "task_refs"), "Replan.task_refs")
    operation_tasks = {
        task_id
        for operation in operations
        for task_id in (operation.task_id, operation.dependency_task_id)
        if task_id is not None
    }
    if not operation_tasks.issubset(set(task_refs)):
        raise ProjectionIntegrityError("Replan operations reference an unbound Task")
    return PathChangeProjectionV1(
        path_change_id=replan_id,
        source_kind="REPLAN",
        source_id=replan_id,
        change_kind=change_kind,
        status=_enum_text(_field(source, "status"), context="Replan.status"),
        decision=decision,
        reason_code=_optional_string(
            _field(source, "reason_code", None), context="Replan.reason_code"
        ),
        task_refs=task_refs,
        operations=operations,
        graph_version_before=_optional_positive_int(
            _field(source, "graph_version_before", None), "Replan.graph_version_before"
        ),
        graph_version_after=_optional_positive_int(
            _field(source, "graph_version_after", None), "Replan.graph_version_after"
        ),
        created_at=_required_datetime(source, "created_at", "Replan"),
        resolved_at=_optional_datetime(_field(source, "resolved_at", None), "Replan.resolved_at"),
    )


def project_event(
    event: object,
    *,
    expected_run_id: str,
    known_task_ids: Collection[str],
    projection_sequence: int | None = None,
) -> SafeRuntimeActivityV1:
    run_id = _required_string(event, "run_id", "RuntimeEvent")
    if run_id != expected_run_id:
        raise ProjectionIntegrityError("RuntimeEvent belongs to another Run")
    event_type = _enum_text(_field(event, "type"), context="RuntimeEvent.type")
    allowed_keys = _EVENT_PAYLOAD_KEYS.get(event_type)
    if allowed_keys is None:
        raise ProjectionIntegrityError(f"unsupported RuntimeEvent type: {event_type}")
    sequence = _positive_int(_field(event, "sequence"), context="RuntimeEvent.sequence")
    if projection_sequence is not None and sequence > projection_sequence:
        raise ProjectionIntegrityError("RuntimeEvent is ahead of the projection watermark")
    task_id = _optional_string(_field(event, "task_id", None), context="RuntimeEvent.task_id")
    if task_id is not None and task_id not in set(known_task_ids):
        raise ProjectionIntegrityError("RuntimeEvent names a Task outside the Run graph")
    try:
        payload = safe_json_object(
            _field(event, "payload"),
            allowed_keys=allowed_keys,
            context=f"RuntimeEvent[{event_type}].payload",
        )
    except UnsafeProjectionData as exc:
        raise ProjectionIntegrityError(str(exc)) from exc

    message_code_value = payload.get("message_code")
    message_code = (
        safe_text(message_code_value, context="RuntimeEvent.message_code")
        if message_code_value is not None
        else f"EVENT_{event_type.replace('.', '_').upper()}"
    )
    actor_id, actor_type = _event_actor(payload)
    status = payload.get("status")
    status_text = (
        None if status is None else _required_nonblank(status, "RuntimeEvent.payload.status")
    )
    return SafeRuntimeActivityV1(
        event_id=_required_string(event, "event_id", "RuntimeEvent"),
        type=event_type,
        sequence=sequence,
        timestamp=_required_datetime(event, "timestamp", "RuntimeEvent"),
        task_id=task_id,
        message_code=message_code,
        status=status_text,
        actor_id=actor_id,
        actor_type=actor_type,
        input_refs=(),
        output_refs=_event_output_refs(payload),
        evidence_refs=_single_ref(payload, "evidence_id"),
        calculation_refs=_single_ref(payload, "calculation_id"),
        review_refs=_single_ref(payload, "review_id"),
        proof_refs=_single_ref(payload, "proof_id"),
        artifact_refs=(),
        trace_bundle_refs=(),
    )


def build_released_metric(
    *,
    expected_object_id: str,
    expected_run_id: str,
    metric: object,
    claims: Sequence[object],
    calculation: object,
    evidence: Sequence[object],
    proof_policy_decisions: Sequence[object],
    proof_records: Sequence[object] = (),
    proof_verifications: Sequence[object] = (),
    proof_commitments: Sequence[object] = (),
) -> ReleasedFinancialMetricProjectionV1:
    """Project one lossless released metric with exact Claim/K/E/Proof joins."""

    metric_id = _required_string(metric, "metric_id", "ReleasedMetric")
    calculation_id = _required_string(metric, "calculation_id", "ReleasedMetric")
    if (
        _required_string(calculation, "calculation_id", "Calculation") != calculation_id
        or _required_string(calculation, "run_id", "Calculation") != expected_run_id
    ):
        raise ProjectionIntegrityError("released metric Calculation closure failed")
    if _enum_text(_field(calculation, "status"), context="Calculation.status") != "PASS":
        raise ProjectionIntegrityError("released metric requires a PASS Calculation")
    if _required_string(calculation, "formula_id", "Calculation") != _required_string(
        metric, "formula_id", "ReleasedMetric"
    ) or _required_string(calculation, "capability_id", "Calculation") != _required_string(
        metric, "capability_id", "ReleasedMetric"
    ):
        raise ProjectionIntegrityError("released metric formula/capability closure failed")

    metric_evidence_ids = _unique_string_tuple(
        _field(metric, "evidence_ids"), "ReleasedMetric.evidence_ids"
    )
    if not metric_evidence_ids:
        raise ProjectionIntegrityError("released metric requires Evidence")
    calculation_evidence_ids = _unique_string_tuple(
        _field(calculation, "input_evidence_ids"), "Calculation.input_evidence_ids"
    )
    if calculation_evidence_ids != metric_evidence_ids:
        raise ProjectionIntegrityError("metric and Calculation Evidence order/identity disagree")
    evidence_by_id = _unique_index(evidence, "evidence_id", context="Evidence")
    if set(evidence_by_id) != set(metric_evidence_ids):
        raise ProjectionIntegrityError("metric Evidence input is incomplete or contaminated")
    for evidence_id in metric_evidence_ids:
        record = evidence_by_id[evidence_id]
        if (
            _required_string(record, "run_id", "Evidence") != expected_run_id
            or _required_string(record, "object_id", "Evidence") != expected_object_id
            or _enum_text(_field(record, "status"), context="Evidence.status") != "ACCEPTED"
        ):
            raise ProjectionIntegrityError("released metric Evidence closure failed")

    canonical_value = _canonical_decimal(
        _field(metric, "canonical_value"), context="ReleasedMetric.canonical_value"
    )
    calculation_value = _canonical_decimal(
        _field(calculation, "output_value"), context="Calculation.output_value"
    )
    if calculation_value != canonical_value:
        raise ProjectionIntegrityError("released metric value differs from its Calculation")
    canonical_unit = _enum_text(_field(metric, "canonical_unit"), context="metric unit")
    calculation_unit = _enum_text(
        _field(calculation, "output_unit"), context="Calculation.output_unit"
    ).upper()
    metric_currency = _optional_raw_string(_field(metric, "currency", None))
    unit_matches = calculation_unit == canonical_unit.upper()
    if canonical_unit.upper() == "CURRENCY" and metric_currency is not None:
        unit_matches = calculation_unit == metric_currency.upper()
    elif canonical_unit.upper() == "INDEX":
        unit_matches = calculation_unit in {"INDEX", "INDEX_POINTS"}
    if not unit_matches:
        raise ProjectionIntegrityError("released metric unit differs from its Calculation")

    matching_claims = tuple(
        claim
        for claim in claims
        if _optional_raw_string(_field(claim, "metric_id", None)) == metric_id
    )
    if len(matching_claims) != 1:
        raise ProjectionIntegrityError("released metric requires exactly one exact material Claim")
    claim_ids: list[str] = []
    for claim in matching_claims:
        _validate_claim_metric_closure(
            claim,
            metric=metric,
            expected_run_id=expected_run_id,
            evidence_ids=metric_evidence_ids,
        )
        claim_ids.append(_required_string(claim, "claim_id", "Claim"))
    if len(set(claim_ids)) != len(claim_ids):
        raise ProjectionIntegrityError("released metric has duplicate Claim identities")

    proof_join = join_metric_proof(
        expected_run_id=expected_run_id,
        calculation=calculation,
        metric=metric,
        proof_policy_decisions=proof_policy_decisions,
        proof_records=proof_records,
        proof_verifications=proof_verifications,
        proof_commitments=proof_commitments,
    )
    method = _project_method_metadata(_field(metric, "method_metadata", None))
    return ReleasedFinancialMetricProjectionV1(
        run_id=expected_run_id,
        metric_id=metric_id,
        name=_required_string(metric, "name", "ReleasedMetric"),
        canonical_value=canonical_value,
        canonical_unit=canonical_unit,
        display_value=_required_string(metric, "display_value", "ReleasedMetric"),
        display_unit=_required_string(metric, "display_unit", "ReleasedMetric"),
        period=_required_string(metric, "period", "ReleasedMetric"),
        period_basis=_enum_text(_field(metric, "period_basis"), context="metric period_basis"),
        actuality=_enum_text(_field(metric, "actuality"), context="metric actuality"),
        as_of=_required_date(metric, "as_of", "ReleasedMetric"),
        currency=_optional_string(_field(metric, "currency", None), context="metric.currency"),
        formula_id=_required_string(metric, "formula_id", "ReleasedMetric"),
        capability_id=_required_string(metric, "capability_id", "ReleasedMetric"),
        calculation_id=calculation_id,
        evidence_refs=metric_evidence_ids,
        claim_refs=tuple(claim_ids),
        proof=proof_join.projection,
        method_metadata=method,
        technical_price_basis=_optional_enum_text(
            _field(metric, "technical_price_basis", None), "metric.technical_price_basis"
        ),
        corporate_action_status=_optional_enum_text(
            _field(metric, "corporate_action_status", None),
            "metric.corporate_action_status",
        ),
        corporate_action_guard_refs=_unique_string_tuple(
            _field(metric, "corporate_action_guard_refs"),
            "metric.corporate_action_guard_refs",
        ),
        limitations=_string_tuple(_field(metric, "limitations"), "metric.limitations"),
    )


def join_metric_proof(
    *,
    expected_run_id: str,
    calculation: object,
    metric: object,
    proof_policy_decisions: Sequence[object],
    proof_records: Sequence[object] = (),
    proof_verifications: Sequence[object] = (),
    proof_commitments: Sequence[object] = (),
) -> MetricProofJoin:
    """Join an explicit policy to exact Run/Calculation proof and verification facts."""

    calculation_id = _required_string(calculation, "calculation_id", "Calculation")
    if _required_string(calculation, "run_id", "Calculation") != expected_run_id:
        raise ProjectionIntegrityError("proof Calculation belongs to another Run")
    policies = tuple(
        policy
        for policy in proof_policy_decisions
        if _optional_raw_string(_field(policy, "calculation_id", None)) == calculation_id
    )
    if len(policies) != 1:
        raise ProjectionIntegrityError("metric requires exactly one durable ProofPolicyDecision")
    policy = policies[0]
    if _required_string(policy, "run_id", "ProofPolicyDecision") != expected_run_id:
        raise ProjectionIntegrityError("ProofPolicyDecision belongs to another Run")
    formula_id = _required_string(metric, "formula_id", "ReleasedMetric")
    if _required_string(policy, "formula_id", "ProofPolicyDecision") != formula_id:
        raise ProjectionIntegrityError("ProofPolicyDecision formula closure failed")
    requirement = _enum_text(
        _field(policy, "requirement"), context="ProofPolicyDecision.requirement"
    )
    if requirement not in {"NOT_REQUIRED", "MUST_PROVE"}:
        raise ProjectionIntegrityError("unknown proof requirement")
    policy_id = _required_string(policy, "policy_id", "ProofPolicyDecision")

    records = tuple(
        proof
        for proof in proof_records
        if _optional_raw_string(_field(proof, "calculation_id", None)) == calculation_id
    )
    for proof in records:
        if _required_string(proof, "run_id", "ProofRecord") != expected_run_id:
            raise ProjectionIntegrityError("ProofRecord belongs to another Run")
    if requirement == "NOT_REQUIRED":
        if records:
            raise ProjectionIntegrityError("NOT_REQUIRED calculation has an unexpected ProofRecord")
        return MetricProofJoin(
            projection=MetricProofProjectionV1(
                policy_id=policy_id,
                requirement="NOT_REQUIRED",
                status="NOT_REQUIRED",
                proof_refs=(),
            ),
            trace_refs=(),
        )

    if len(records) > 1:
        raise ProjectionIntegrityError("MUST_PROVE calculation has ambiguous ProofRecords")
    if not records:
        return MetricProofJoin(
            projection=MetricProofProjectionV1(
                policy_id=policy_id,
                requirement="MUST_PROVE",
                status="PENDING",
                proof_refs=(),
            ),
            trace_refs=(),
        )

    proof = records[0]
    proof_id = _required_string(proof, "proof_id", "ProofRecord")
    commitment = _exact_commitment(
        proof,
        calculation=calculation,
        metric=metric,
        commitments=proof_commitments,
        expected_run_id=expected_run_id,
    )
    del commitment
    verification_id = _verified_proof_id(
        proof,
        verifications=proof_verifications,
    )
    raw_status = _enum_text(_field(proof, "status"), context="ProofRecord.status")
    if verification_id is not None:
        projected_status = "VERIFIED"
    elif raw_status in {"REQUIRED_PENDING", "PENDING"}:
        projected_status = "PENDING"
    elif raw_status == "PROVING":
        projected_status = "PROVING"
    elif raw_status in {"VALID", "VERIFIED"}:
        projected_status = "GENERATED_UNVERIFIED"
    elif raw_status in {"INVALID", "FAILED"}:
        projected_status = "INVALID"
    elif raw_status == "ERROR":
        projected_status = "ERROR"
    elif raw_status in {"UNSUPPORTED", "NOT_IMPLEMENTED"}:
        projected_status = "UNSUPPORTED"
    else:
        raise ProjectionIntegrityError(f"unknown proof status: {raw_status}")

    availability = AvailabilityV1.available()
    trace_ref = ProofTraceRefV1(
        proof_id=proof_id,
        calculation_id=calculation_id,
        requirement="MUST_PROVE",
        status=projected_status,
        verification_id=verification_id,
        availability=availability,
    )
    return MetricProofJoin(
        projection=MetricProofProjectionV1(
            policy_id=policy_id,
            requirement="MUST_PROVE",
            status=projected_status,
            proof_refs=(proof_id,),
        ),
        trace_refs=(trace_ref,),
    )


def build_released_result_projection(
    *,
    expected_object_id: str,
    expected_run_id: str,
    run: object,
    canonical_record: object,
    released_result: object,
    calculations: Sequence[object],
    evidence: Sequence[object],
    proof_policy_decisions: Sequence[object],
    proof_records: Sequence[object] = (),
    proof_verifications: Sequence[object] = (),
    proof_commitments: Sequence[object] = (),
) -> ReleasedResultProjectionV1:
    """Build the released result only after full typed material closure succeeds."""

    if (
        _required_string(run, "run_id", "Run") != expected_run_id
        or _required_string(run, "research_object_id", "Run") != expected_object_id
        or _enum_text(_field(run, "status"), context="Run.status") != "RELEASED"
    ):
        raise ProjectionIntegrityError("ReleasedResult requires its exact RELEASED Run")
    canonical_id = _required_string(canonical_record, "record_id", "CanonicalRecord")
    if (
        _required_string(canonical_record, "run_id", "CanonicalRecord") != expected_run_id
        or _required_string(canonical_record, "object_snapshot_ref", "CanonicalRecord")
        != expected_object_id
    ):
        raise ProjectionIntegrityError("CanonicalRecord does not close to the Run/Object")
    result_id = _required_string(released_result, "result_id", "ReleasedResult")
    if (
        _required_string(released_result, "run_id", "ReleasedResult") != expected_run_id
        or _required_string(released_result, "canonical_record_id", "ReleasedResult")
        != canonical_id
    ):
        raise ProjectionIntegrityError("ReleasedResult does not close to CanonicalRecord")

    raw_metrics = _sequence(_field(released_result, "released_metrics"), "released metrics")
    raw_claims = _sequence(_field(released_result, "material_claims"), "material claims")
    if not raw_metrics or not raw_claims:
        raise ProjectionIntegrityError("released result requires typed material metrics and Claims")
    calculations_by_id = _unique_index(calculations, "calculation_id", context="Calculation")
    evidence_by_id = _unique_index(evidence, "evidence_id", context="Evidence")
    metrics = tuple(
        build_released_metric(
            expected_object_id=expected_object_id,
            expected_run_id=expected_run_id,
            metric=metric,
            claims=raw_claims,
            calculation=_required_index_item(
                calculations_by_id,
                _required_string(metric, "calculation_id", "ReleasedMetric"),
                "Calculation",
            ),
            evidence=tuple(
                _required_index_item(evidence_by_id, evidence_id, "Evidence")
                for evidence_id in _unique_string_tuple(
                    _field(metric, "evidence_ids"), "ReleasedMetric.evidence_ids"
                )
            ),
            proof_policy_decisions=proof_policy_decisions,
            proof_records=proof_records,
            proof_verifications=proof_verifications,
            proof_commitments=proof_commitments,
        )
        for metric in raw_metrics
    )
    if len(metrics) != len(MATERIAL_FORMULAS) or {item.formula_id for item in metrics} != set(
        MATERIAL_FORMULAS
    ):
        raise ProjectionIntegrityError("released result does not contain the exact FULL set")
    if len({metric.metric_id for metric in metrics}) != len(metrics):
        raise ProjectionIntegrityError("released result has duplicate metric identities")
    if len({metric.calculation_id for metric in metrics}) != len(metrics):
        raise ProjectionIntegrityError("released result has duplicate metric Calculations")
    claims = tuple(_project_typed_claim(claim, expected_run_id) for claim in raw_claims)
    if len({claim.claim_id for claim in claims}) != len(claims):
        raise ProjectionIntegrityError("released result has duplicate Claim identities")
    if {claim.metric_id for claim in claims} != {metric.metric_id for metric in metrics}:
        raise ProjectionIntegrityError("released result Claim/metric closure is incomplete")

    _validate_canonical_release_refs(
        canonical_record,
        metrics=metrics,
        claims=claims,
        proof_records=proof_records,
        expected_run_id=expected_run_id,
    )
    dispositions = tuple(
        _project_disposition(item)
        for item in _sequence(
            _field(released_result, "material_calculation_dispositions"),
            "material calculation dispositions",
        )
    )
    if len({item["calculation_id"] for item in dispositions}) != len(dispositions):
        raise ProjectionIntegrityError("material dispositions contain duplicate Calculations")
    metric_by_calculation = {metric.calculation_id: metric.metric_id for metric in metrics}
    if {item["calculation_id"] for item in dispositions} != set(metric_by_calculation):
        raise ProjectionIntegrityError("material disposition closure is incomplete")
    if any(
        item["status"] != "REPORTABLE"
        or item["metric_id"] != metric_by_calculation[item["calculation_id"]]
        or item["reason"] is not None
        for item in dispositions
    ):
        raise ProjectionIntegrityError("released material disposition is not REPORTABLE")
    source_coverage_value = _field(released_result, "research_source_coverage", None)
    source_coverage = (
        None
        if source_coverage_value is None
        else _safe_model_json(
            source_coverage_value,
            allowed_keys=_SOURCE_COVERAGE_ALLOWLIST,
            context="ReleasedResult.research_source_coverage",
        )
    )
    return ReleasedResultProjectionV1(
        object_id=expected_object_id,
        run_id=expected_run_id,
        released_result_id=result_id,
        canonical_record_id=canonical_id,
        released_at=_required_datetime(released_result, "released_at", "ReleasedResult"),
        metrics=metrics,
        claims=claims,
        material_calculation_dispositions=dispositions,
        research_source_coverage=source_coverage,
        limitations=_string_tuple(
            _field(released_result, "limitations"), "ReleasedResult.limitations"
        ),
        availability=AvailabilityV1.available(),
    )


def build_released_object_core(
    *,
    projection_revision: int,
    generated_at: datetime,
    research_object: object,
    runs: Sequence[RunCollectionItemV1],
    eligible_releases: Sequence[EligibleReleasedObjectCandidate],
    authoritative_run_ids: Collection[str] | None = None,
    release_ineligibility: Mapping[str, str] | None = None,
) -> ReleasedObjectCoreV1:
    """Select the latest eligible release using `(released_at, run_id)` only.

    ``authoritative_run_ids`` and ``release_ineligibility`` are the explicit
    repository snapshot membership/assessment proof. Requiring both prevents
    a filtered caller from silently omitting a newer eligible release while
    allowing a retained RELEASED Run whose current closure became unavailable
    to remain outside the eligible set. The Parent PostgreSQL adapter must
    obtain all inputs in the same Object snapshot.
    """

    revision = _positive_int(projection_revision, context="projection_revision")
    generated_at = _aware_datetime(generated_at, "generated_at")
    object_projection = project_object(research_object)
    object_id = object_projection.object_id
    history = tuple(sorted(runs, key=lambda item: (item.updated_at, item.run_id), reverse=True))
    if len({item.run_id for item in history}) != len(history):
        raise ProjectionIntegrityError("Released Object history contains duplicate Runs")
    if any(item.object.object_id != object_id for item in history):
        raise ProjectionIntegrityError("Released Object history contains a foreign Run")
    history_by_id = {item.run_id: item for item in history}
    if authoritative_run_ids is None:
        raise ProjectionIntegrityError(
            "Released Object requires authoritative full-Run snapshot membership"
        )
    authoritative_ids = tuple(
        _required_nonblank(item, f"authoritative_run_ids[{index}]")
        for index, item in enumerate(authoritative_run_ids)
    )
    if len(set(authoritative_ids)) != len(authoritative_ids):
        raise ProjectionIntegrityError("authoritative Run snapshot contains duplicate identities")
    if set(authoritative_ids) != set(history_by_id):
        raise ProjectionIntegrityError(
            "Released Object history is filtered or torn from authoritative snapshot membership"
        )
    if release_ineligibility is None:
        raise ProjectionIntegrityError(
            "Released Object requires an authoritative eligibility assessment"
        )
    ineligible: dict[str, str] = {}
    for run_id, reason_code in release_ineligibility.items():
        checked_run_id = _required_nonblank(run_id, "release_ineligibility.run_id")
        checked_reason = _required_nonblank(
            reason_code,
            f"release_ineligibility[{checked_run_id}]",
        )
        if _SAFE_REASON_CODE.fullmatch(checked_reason) is None:
            raise ProjectionIntegrityError("release ineligibility reason is not a stable code")
        if checked_run_id in ineligible:
            raise ProjectionIntegrityError("duplicate release ineligibility assessment")
        ineligible[checked_run_id] = checked_reason

    candidates: list[EligibleReleasedObjectCandidate] = []
    validation_ids: set[str] = set()
    for candidate in eligible_releases:
        if (
            candidate.run.run_id not in history_by_id
            or candidate.run != history_by_id[candidate.run.run_id]
        ):
            raise ProjectionIntegrityError("eligible release does not bind exact object history")
        validation_id = _validate_released_object_candidate(candidate, object_id=object_id)
        if validation_id in validation_ids:
            raise ProjectionIntegrityError(
                "Released Object candidates reuse a ReleaseValidation identity"
            )
        validation_ids.add(validation_id)
        candidates.append(candidate)
    if len({item.run.run_id for item in candidates}) != len(candidates):
        raise ProjectionIntegrityError("Released Object has duplicate eligibility candidates")
    released_history_ids = {item.run_id for item in history if item.status == "RELEASED"}
    candidate_ids = {item.run.run_id for item in candidates}
    ineligible_ids = set(ineligible)
    if candidate_ids & ineligible_ids:
        raise ProjectionIntegrityError(
            "release assessment marks one Run both eligible and ineligible"
        )
    if candidate_ids | ineligible_ids != released_history_ids:
        raise ProjectionIntegrityError(
            "every authoritative RELEASED Run requires one exact eligibility assessment"
        )

    if not candidates:
        return ReleasedObjectCoreV1(
            projection_revision=revision,
            generated_at=generated_at,
            object=object_projection,
            latest_released_run_id=None,
            current_released_result_availability=AvailabilityV1.unavailable(
                AvailabilityStatus.NOT_RELEASED,
                "NO_RELEASED_RUN",
            ),
            source_run_id=None,
            released_result_id=None,
            canonical_record_id=None,
            released_at=None,
            metrics=(),
            claim_refs=(),
            report_artifacts=None,
            runs=history,
            run_count=len(history),
        )

    selected = max(
        candidates,
        key=lambda item: (item.result.released_at, item.run.run_id),
    )
    return ReleasedObjectCoreV1(
        projection_revision=revision,
        generated_at=generated_at,
        object=object_projection,
        latest_released_run_id=selected.run.run_id,
        current_released_result_availability=AvailabilityV1.available(),
        source_run_id=selected.run.run_id,
        released_result_id=selected.result.released_result_id,
        canonical_record_id=selected.result.canonical_record_id,
        released_at=selected.result.released_at,
        metrics=selected.result.metrics,
        claim_refs=tuple(item.claim_id for item in selected.result.claims),
        report_artifacts=selected.artifacts,
        runs=history,
        run_count=len(history),
    )


def build_financial_review(
    *,
    expected_object_id: str,
    expected_run_id: str,
    projection_revision: int,
    projection_sequence: int,
    run: object,
    review: object | None,
    canonical_record: object | None = None,
    released_result: object | None = None,
    tasks: Sequence[object] | None = None,
    proof_records: Sequence[object] | None = None,
    correction_records: Sequence[object] | None = None,
    evidence_records: Sequence[object] | None = None,
    calculation_records: Sequence[object] | None = None,
    metric_records: Sequence[object] | None = None,
    claim_records: Sequence[object] | None = None,
    judgment_records: Sequence[object] | None = None,
    proof_policy_decisions: Sequence[object] | None = None,
    json_allowlist: JsonAllowlist = _REVIEW_JSON_KEYS,
) -> FinancialReviewProjectionV1:
    """Build Review B only from the exact independently reviewed input snapshot."""

    if (
        _required_string(run, "run_id", "Run") != expected_run_id
        or _required_string(run, "research_object_id", "Run") != expected_object_id
    ):
        raise ProjectionIntegrityError("Financial Review Run/Object closure failed")
    run_status = project_run_status(_field(run, "status"))
    revision = _positive_int(projection_revision, context="projection_revision")
    sequence = _nonnegative_int(projection_sequence, context="projection_sequence")

    if review is None:
        if canonical_record is not None or released_result is not None:
            raise ProjectionIntegrityError("absent Review cannot bind Canonical/Result records")
        if run_status.status == "RELEASED":
            raise ProjectionIntegrityError("RELEASED Run cannot lack Financial Review")
        availability = (
            AvailabilityV1.unavailable(
                AvailabilityStatus.NOT_GENERATED,
                "REVIEW_NOT_GENERATED",
            )
            if run_status.terminal
            else AvailabilityV1.unavailable(
                AvailabilityStatus.PENDING,
                "REVIEW_PENDING",
            )
        )
        return FinancialReviewProjectionV1(
            projection_revision=revision,
            projection_sequence=sequence,
            object_id=expected_object_id,
            run_id=expected_run_id,
            canonical_record_id=None,
            released_result_id=None,
            review_id=None,
            status=None,
            reviewer=None,
            input_snapshot_hash=None,
            availability=availability,
        )

    if _required_string(review, "run_id", "Review") != expected_run_id:
        raise ProjectionIntegrityError("Review belongs to another Run")
    review_id = _required_string(review, "review_id", "Review")
    review_inputs = _validate_review_input_snapshot(
        expected_object_id=expected_object_id,
        expected_run_id=expected_run_id,
        run_as_of=_required_date(run, "as_of", "Run"),
        review=review,
        evidence_records=evidence_records,
        calculation_records=calculation_records,
        metric_records=metric_records,
        claim_records=claim_records,
        judgment_records=judgment_records,
        proof_policy_decisions=proof_policy_decisions,
    )
    task_index = _optional_owned_index(
        tasks,
        id_field="task_id",
        expected_run_id=expected_run_id,
        context="Task",
    )
    proof_index = _optional_owned_index(
        proof_records,
        id_field="proof_id",
        expected_run_id=expected_run_id,
        context="ProofRecord",
    )
    correction_index = _optional_owned_index(
        correction_records,
        id_field="correction_id",
        expected_run_id=expected_run_id,
        context="CorrectionRecord",
    )
    checks = tuple(
        sorted(
            (
                _project_review_check(
                    item,
                    expected_run_id=expected_run_id,
                    json_allowlist=json_allowlist,
                )
                for item in _sequence(_field(review, "checks"), "Review.checks")
            ),
            key=lambda item: (item.created_at, item.check_id),
        )
    )
    if not checks:
        raise ProjectionIntegrityError("retained Financial Review requires durable checks")
    if len({item.check_id for item in checks}) != len(checks):
        raise ProjectionIntegrityError("Financial Review has duplicate durable check IDs")
    _validate_review_corrections(
        checks,
        correction_index=correction_index,
        task_index=task_index,
    )

    expected_status = _aggregate_review_status(checks)
    stored_status = _enum_text(_field(review, "status"), context="Review.status")
    if stored_status != expected_status:
        raise ProjectionIntegrityError("Review status disagrees with durable exception states")

    canonical_subject_ids = (
        set()
        if canonical_record is None
        else {_required_string(canonical_record, "record_id", "CanonicalRecord")}
    )
    result_subject_ids = (
        set()
        if released_result is None
        else {_required_string(released_result, "result_id", "ReleasedResult")}
    )
    reference_sets: dict[str, set[str] | None] = {
        "EVIDENCE": set(review_inputs["evidence"]),
        "CALCULATION": set(review_inputs["calculations"]),
        "METRIC": set(review_inputs["metrics"]),
        "CLAIM": set(review_inputs["claims"]),
        "JUDGMENT": set(review_inputs["judgments"]),
        "TASK": None if task_index is None else set(task_index),
        "PROOF": None if proof_index is None else set(proof_index),
        "RUN": {expected_run_id},
        "CANONICAL_RECORD": canonical_subject_ids,
        "RELEASED_RESULT": result_subject_ids,
    }
    for check in checks:
        for subject in check.subjects:
            allowed = reference_sets[subject.subject_type]
            if allowed is None:
                raise ProjectionIntegrityError(
                    f"Review Check {subject.subject_type} subject lacks exact retained records"
                )
            if subject.subject_id not in allowed:
                raise ProjectionIntegrityError("Review Check subject lacks an exact reviewed ref")

    canonical_id: str | None = None
    result_id: str | None = None
    if run_status.status == "RELEASED":
        if canonical_record is None or released_result is None:
            raise ProjectionIntegrityError("released Review requires Canonical and Result closure")
        canonical_id = _required_string(canonical_record, "record_id", "CanonicalRecord")
        result_id = _required_string(released_result, "result_id", "ReleasedResult")
        if (
            _required_string(canonical_record, "run_id", "CanonicalRecord") != expected_run_id
            or _required_string(canonical_record, "object_snapshot_ref", "CanonicalRecord")
            != expected_object_id
            or review_id
            not in _unique_string_tuple(
                _field(canonical_record, "review_refs"), "CanonicalRecord.review_refs"
            )
            or _required_string(released_result, "run_id", "ReleasedResult") != expected_run_id
            or _required_string(released_result, "canonical_record_id", "ReleasedResult")
            != canonical_id
        ):
            raise ProjectionIntegrityError("released Review Canonical/Result closure failed")
        if stored_status != "PASS":
            raise ProjectionIntegrityError("released Review must be PASS")
    elif canonical_record is not None or released_result is not None:
        raise ProjectionIntegrityError("live pre-release Review must keep X/L identities null")

    input_hash = review_inputs["input_hash"]
    return FinancialReviewProjectionV1(
        projection_revision=revision,
        projection_sequence=sequence,
        object_id=expected_object_id,
        run_id=expected_run_id,
        canonical_record_id=canonical_id,
        released_result_id=result_id,
        review_id=review_id,
        status=stored_status,
        reviewer=_required_string(review, "reviewer", "Review"),
        input_snapshot_hash=input_hash,
        reviewed_evidence_refs=_unique_string_tuple(
            _field(review, "reviewed_evidence_refs"), "Review.reviewed_evidence_refs"
        ),
        reviewed_calculation_refs=_unique_string_tuple(
            _field(review, "reviewed_calculation_refs"),
            "Review.reviewed_calculation_refs",
        ),
        reviewed_metric_refs=_unique_string_tuple(
            _field(review, "reviewed_metric_refs"), "Review.reviewed_metric_refs"
        ),
        reviewed_claim_refs=_unique_string_tuple(
            _field(review, "reviewed_claim_refs"), "Review.reviewed_claim_refs"
        ),
        reviewed_judgment_refs=_unique_string_tuple(
            _field(review, "reviewed_judgment_refs"),
            "Review.reviewed_judgment_refs",
        ),
        required_proof_calculation_refs=_unique_string_tuple(
            _field(review, "required_proof_calculation_refs"),
            "Review.required_proof_calculation_refs",
        ),
        checks=checks,
        availability=AvailabilityV1.available(),
    )


def _validate_review_input_snapshot(
    *,
    expected_object_id: str,
    expected_run_id: str,
    run_as_of: date,
    review: object,
    evidence_records: Sequence[object] | None,
    calculation_records: Sequence[object] | None,
    metric_records: Sequence[object] | None,
    claim_records: Sequence[object] | None,
    judgment_records: Sequence[object] | None,
    proof_policy_decisions: Sequence[object] | None,
) -> dict[str, Any]:
    """Rebind a Review to its exact retained Phase 3 hash preimage.

    The historical review hash is intentionally recomputed with its original
    algorithm.  RFC 8785 release hashes are a separate Phase 4 contract and
    must not silently redefine this already-persisted identity.
    """

    required_inputs = {
        "Evidence": evidence_records,
        "Calculation": calculation_records,
        "Metric": metric_records,
        "Claim": claim_records,
        "Judgment": judgment_records,
        "ProofPolicyDecision": proof_policy_decisions,
    }
    missing = [name for name, records in required_inputs.items() if records is None]
    if missing:
        raise ProjectionIntegrityError(
            "Financial Review requires exact retained input records: " + ", ".join(missing)
        )

    assert evidence_records is not None
    assert calculation_records is not None
    assert metric_records is not None
    assert claim_records is not None
    assert judgment_records is not None
    assert proof_policy_decisions is not None
    try:
        evidence = tuple(
            EvidenceRecord.model_validate(_model_mapping(item)) for item in evidence_records
        )
        calculations = tuple(
            CalculationRecord.model_validate(_model_mapping(item)) for item in calculation_records
        )
        metrics = tuple(
            ReleasedFinancialMetric.model_validate(_model_mapping(item)) for item in metric_records
        )
        claims = tuple(
            MaterialFinancialClaim.model_validate(_model_mapping(item)) for item in claim_records
        )
        judgments = tuple(_model_mapping(item) for item in judgment_records)
        decisions = tuple(
            ProofPolicyDecision.model_validate(_model_mapping(item))
            for item in proof_policy_decisions
        )
    except (TypeError, ValueError) as exc:
        raise ProjectionIntegrityError(
            "Financial Review retained input record failed exact domain validation"
        ) from exc

    evidence_index = _unique_index(evidence, "evidence_id", context="Review Evidence")
    calculation_index = _unique_index(
        calculations,
        "calculation_id",
        context="Review Calculation",
    )
    metric_index = _unique_index(metrics, "metric_id", context="Review Metric")
    claim_index = _unique_index(claims, "claim_id", context="Review Claim")
    judgment_index = _unique_index(judgments, "judgment_id", context="Review Judgment")
    decision_index = _unique_index(
        decisions,
        "decision_id",
        context="Review ProofPolicyDecision",
    )
    decisions_by_calculation = _unique_index(
        decisions,
        "calculation_id",
        context="Review ProofPolicyDecision Calculation",
    )

    if any(
        record.run_id != expected_run_id or record.object_id != expected_object_id
        for record in evidence
    ):
        raise ProjectionIntegrityError("Review Evidence belongs to another Run/Object")
    if any(record.run_id != expected_run_id for record in calculations):
        raise ProjectionIntegrityError("Review Calculation belongs to another Run")
    if any(record.run_id != expected_run_id for record in claims):
        raise ProjectionIntegrityError("Review Claim belongs to another Run")
    if any(
        _required_string(record, "run_id", "Review Judgment") != expected_run_id
        for record in judgments
    ):
        raise ProjectionIntegrityError("Review Judgment belongs to another Run")
    if any(record.run_id != expected_run_id for record in decisions):
        raise ProjectionIntegrityError("Review ProofPolicyDecision belongs to another Run")

    for calculation in calculations:
        if not set(calculation.input_evidence_ids).issubset(evidence_index):
            raise ProjectionIntegrityError(
                "Review Calculation inputs lack exact retained Evidence records"
            )
    for metric in metrics:
        calculation = calculation_index.get(metric.calculation_id)
        if (
            calculation is None
            or metric.formula_id != calculation.formula_id
            or metric.capability_id != calculation.capability_id
            or not set(metric.evidence_ids).issubset(evidence_index)
        ):
            raise ProjectionIntegrityError(
                "Review Metric lacks an exact retained Calculation/Evidence binding"
            )
    for claim in claims:
        metric = next((item for item in metrics if item.metric_id == claim.metric_id), None)
        if (
            metric is None
            or not set(claim.calculation_refs).issubset(calculation_index)
            or not set(claim.evidence_refs).issubset(evidence_index)
            or not set(claim.judgment_refs).issubset(judgment_index)
        ):
            raise ProjectionIntegrityError(
                "Review Claim lacks exact retained Metric/Calculation/Evidence/Judgment support"
            )
    if set(decisions_by_calculation) != set(calculation_index):
        raise ProjectionIntegrityError(
            "Review requires exactly one ProofPolicyDecision per retained Calculation"
        )
    for calculation_id, decision in decisions_by_calculation.items():
        if decision.formula_id != calculation_index[calculation_id].formula_id:
            raise ProjectionIntegrityError(
                "Review ProofPolicyDecision formula does not match its Calculation"
            )

    expected_ref_sets = {
        "reviewed_evidence_refs": set(evidence_index),
        "reviewed_calculation_refs": set(calculation_index),
        "reviewed_metric_refs": set(metric_index),
        "reviewed_claim_refs": set(claim_index),
        "reviewed_judgment_refs": set(judgment_index),
    }
    for field_name, expected_ids in expected_ref_sets.items():
        retained_ids = set(_unique_string_tuple(_field(review, field_name), f"Review.{field_name}"))
        if retained_ids != expected_ids:
            raise ProjectionIntegrityError(
                f"Review.{field_name} does not equal the exact retained input set"
            )

    proof_requirements = {
        calculation_id: decision.requirement
        for calculation_id, decision in decisions_by_calculation.items()
    }
    required_proof_ids = {
        calculation_id
        for calculation_id, requirement in proof_requirements.items()
        if requirement is ProofRequirement.MUST_PROVE
    }
    retained_required_ids = set(
        _unique_string_tuple(
            _field(review, "required_proof_calculation_refs"),
            "Review.required_proof_calculation_refs",
        )
    )
    if retained_required_ids != required_proof_ids:
        raise ProjectionIntegrityError(
            "Review.required_proof_calculation_refs does not match exact Proof policy"
        )

    persisted_hash = _required_string(review, "input_snapshot_hash", "Review")
    try:
        require_sha256_identity(persisted_hash, field_name="Review.input_snapshot_hash")
        computed_hash = financial_review_input_snapshot_hash(
            run_id=expected_run_id,
            run_as_of=run_as_of,
            evidence=evidence,
            calculations=calculations,
            metrics=metrics,
            claims=claims,
            judgments=judgments,
            proof_requirements=proof_requirements,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProjectionIntegrityError(
            "Financial Review input snapshot hash could not be recomputed"
        ) from exc
    if not hmac.compare_digest(computed_hash, persisted_hash):
        raise ProjectionIntegrityError(
            "Review.input_snapshot_hash does not bind the exact retained inputs"
        )

    return {
        "evidence": evidence_index,
        "calculations": calculation_index,
        "metrics": metric_index,
        "claims": claim_index,
        "judgments": judgment_index,
        "decisions": decision_index,
        "input_hash": persisted_hash,
    }


def build_execution_projection(
    *,
    expected_object_id: str,
    expected_run_id: str,
    projection_revision: int,
    projection_sequence: int,
    canonical_record: object,
    released_result: object | None = None,
    events: Sequence[object] = (),
    next_cursor: str | None = None,
) -> ExecutionProjectionV1:
    """Build Canonical Execution C with safe graph snapshots and ordered events."""

    canonical_id = _required_string(canonical_record, "record_id", "CanonicalRecord")
    if (
        _required_string(canonical_record, "run_id", "CanonicalRecord") != expected_run_id
        or _required_string(canonical_record, "object_snapshot_ref", "CanonicalRecord")
        != expected_object_id
    ):
        raise ProjectionIntegrityError("Canonical Execution Run/Object closure failed")
    revision = _positive_int(projection_revision, context="projection_revision")
    sequence = _nonnegative_int(projection_sequence, context="projection_sequence")

    planned = project_graph(
        _field(canonical_record, "planned_graph"),
        expected_run_id=expected_run_id,
    )
    actual = project_graph(
        _field(canonical_record, "actual_graph"),
        expected_run_id=expected_run_id,
    )
    task_refs = _unique_string_tuple(
        _field(canonical_record, "task_refs"), "CanonicalRecord.task_refs"
    )
    if set(task_refs) != {task.task_id for task in actual.tasks}:
        raise ProjectionIntegrityError("Canonical task refs do not equal actual graph Tasks")

    projected_events = tuple(
        sorted(
            (
                project_event(
                    event,
                    expected_run_id=expected_run_id,
                    known_task_ids=task_refs,
                    projection_sequence=sequence,
                )
                for event in events
            ),
            key=lambda item: item.sequence,
        )
    )
    if len({item.sequence for item in projected_events}) != len(projected_events):
        raise ProjectionIntegrityError("Execution event page contains duplicate sequences")
    if len({item.event_id for item in projected_events}) != len(projected_events):
        raise ProjectionIntegrityError("Execution event page contains duplicate event IDs")

    result_id: str | None = None
    if released_result is not None:
        result_id = _required_string(released_result, "result_id", "ReleasedResult")
        if (
            _required_string(released_result, "run_id", "ReleasedResult") != expected_run_id
            or _required_string(released_result, "canonical_record_id", "ReleasedResult")
            != canonical_id
        ):
            raise ProjectionIntegrityError("Execution ReleasedResult closure failed")
    if next_cursor is not None:
        safe_text(next_cursor, context="Execution.next_cursor", max_length=256)

    cost = _nonnegative_number(_field(canonical_record, "cost"), context="CanonicalRecord.cost")
    return ExecutionProjectionV1(
        projection_revision=revision,
        projection_sequence=sequence,
        object_id=expected_object_id,
        run_id=expected_run_id,
        canonical_record_id=canonical_id,
        released_result_id=result_id,
        object_snapshot_ref=expected_object_id,
        planned_graph=planned.model_dump(mode="json"),
        actual_graph=actual.model_dump(mode="json"),
        task_refs=task_refs,
        evidence_refs=_unique_string_tuple(
            _field(canonical_record, "evidence_refs"), "CanonicalRecord.evidence_refs"
        ),
        calculation_refs=_unique_string_tuple(
            _field(canonical_record, "calculation_refs"),
            "CanonicalRecord.calculation_refs",
        ),
        metric_refs=_unique_string_tuple(
            _field(canonical_record, "metric_refs"), "CanonicalRecord.metric_refs"
        ),
        claim_refs=_unique_string_tuple(
            _field(canonical_record, "claim_refs"), "CanonicalRecord.claim_refs"
        ),
        judgment_refs=_unique_string_tuple(
            _field(canonical_record, "judgment_refs"), "CanonicalRecord.judgment_refs"
        ),
        decision_refs=_unique_string_tuple(
            _field(canonical_record, "decision_refs"), "CanonicalRecord.decision_refs"
        ),
        correction_refs=_unique_string_tuple(
            _field(canonical_record, "correction_refs"),
            "CanonicalRecord.correction_refs",
        ),
        replan_refs=_unique_string_tuple(
            _field(canonical_record, "replan_refs"), "CanonicalRecord.replan_refs"
        ),
        generated_capability_refs=_unique_string_tuple(
            _field(canonical_record, "generated_capability_refs"),
            "CanonicalRecord.generated_capability_refs",
        ),
        review_refs=_unique_string_tuple(
            _field(canonical_record, "review_refs"), "CanonicalRecord.review_refs"
        ),
        proof_refs=_unique_string_tuple(
            _field(canonical_record, "proof_refs"), "CanonicalRecord.proof_refs"
        ),
        trace_refs=_unique_string_tuple(
            _field(canonical_record, "trace_refs"), "CanonicalRecord.trace_refs"
        ),
        token_usage=_nonnegative_int(
            _field(canonical_record, "token_usage"), context="CanonicalRecord.token_usage"
        ),
        cost=cost,
        latency_ms=_nonnegative_int(
            _field(canonical_record, "latency_ms"), context="CanonicalRecord.latency_ms"
        ),
        runtime_outcome=_required_string(canonical_record, "runtime_outcome", "CanonicalRecord"),
        events=projected_events,
        next_cursor=next_cursor,
        availability=AvailabilityV1.available(),
    )


def build_claim_detail(
    *,
    expected_object_id: str,
    expected_run_id: str,
    claim_id: str,
    projection_revision: int,
    projection_sequence: int,
    run: object,
    canonical_record: object,
    released_result: object,
    calculations: Sequence[object],
    evidence: Sequence[object],
    tasks: Sequence[object],
    proof_policy_decisions: Sequence[object],
    anchor_manifest: object,
    artifact_group: ReportArtifactGroupV1,
    review_projections: Sequence[FinancialReviewProjectionV1],
    proof_records: Sequence[object] = (),
    proof_verifications: Sequence[object] = (),
    proof_commitments: Sequence[object] = (),
    judgments: Sequence[object] = (),
    events: Sequence[object] = (),
    primary_task_id: str | None = None,
    calculation_input_allowlist: JsonAllowlist = _CALCULATION_INPUT_KEYS,
    calculation_parameter_allowlist: JsonAllowlist = _CALCULATION_PARAMETER_KEYS,
) -> ClaimDetailV1:
    """Build exact Claim detail; the persisted anchor manifest is mandatory."""

    assembly = _assemble_claim(
        expected_object_id=expected_object_id,
        expected_run_id=expected_run_id,
        claim_id=claim_id,
        run=run,
        canonical_record=canonical_record,
        released_result=released_result,
        calculations=calculations,
        evidence=evidence,
        tasks=tasks,
        proof_policy_decisions=proof_policy_decisions,
        proof_records=proof_records,
        proof_verifications=proof_verifications,
        proof_commitments=proof_commitments,
        judgments=judgments,
        review_projections=review_projections,
        anchor_manifest=anchor_manifest,
        artifact_group=artifact_group,
        events=events,
        primary_task_id=primary_task_id,
        calculation_input_allowlist=calculation_input_allowlist,
        calculation_parameter_allowlist=calculation_parameter_allowlist,
    )
    anchors = {
        "anchor_manifest_id": assembly.manifest.anchor_manifest_id,
        "anchor_manifest_sha256": assembly.manifest.anchor_manifest_sha256,
        "representations": [
            item.model_dump(mode="json") for item in assembly.manifest.representations
        ],
        "review_anchors": [
            item.model_dump(mode="json") for item in assembly.manifest.review_anchors
        ],
        "task_anchors": [item.model_dump(mode="json") for item in assembly.manifest.task_anchors],
        "execution_anchors": [
            item.model_dump(mode="json") for item in assembly.manifest.execution_anchors
        ],
    }
    return ClaimDetailV1(
        projection_revision=_positive_int(projection_revision, context="projection_revision"),
        projection_sequence=_nonnegative_int(projection_sequence, context="projection_sequence"),
        object_id=expected_object_id,
        run_id=expected_run_id,
        claim_id=assembly.claim.claim_id,
        claim=assembly.claim,
        released_metric=assembly.metric,
        task_refs=assembly.task_refs,
        primary_task_id=assembly.primary_task_id,
        evidence=assembly.evidence,
        calculations=assembly.calculations,
        judgment_refs=assembly.judgment_refs,
        review_refs=assembly.review_refs,
        proof_refs=assembly.proof_refs,
        canonical_record_id=assembly.canonical_record_id,
        released_result_id=assembly.released_result_id,
        anchors=anchors,
        availability=AvailabilityV1.available(),
    )


def build_trace_bundle(
    *,
    expected_object_id: str,
    expected_run_id: str,
    claim_id: str,
    projection_revision: int,
    projection_sequence: int,
    run: object,
    canonical_record: object,
    released_result: object,
    calculations: Sequence[object],
    evidence: Sequence[object],
    tasks: Sequence[object],
    proof_policy_decisions: Sequence[object],
    anchor_manifest: object,
    artifact_group: ReportArtifactGroupV1,
    review_projections: Sequence[FinancialReviewProjectionV1],
    proof_records: Sequence[object] = (),
    proof_verifications: Sequence[object] = (),
    proof_commitments: Sequence[object] = (),
    judgments: Sequence[object] = (),
    events: Sequence[object] = (),
    primary_task_id: str | None = None,
    calculation_input_allowlist: JsonAllowlist = _CALCULATION_INPUT_KEYS,
    calculation_parameter_allowlist: JsonAllowlist = _CALCULATION_PARAMETER_KEYS,
) -> TraceBundleV1:
    """Build an exact Claim Trace from one immutable persisted anchor manifest."""

    assembly = _assemble_claim(
        expected_object_id=expected_object_id,
        expected_run_id=expected_run_id,
        claim_id=claim_id,
        run=run,
        canonical_record=canonical_record,
        released_result=released_result,
        calculations=calculations,
        evidence=evidence,
        tasks=tasks,
        proof_policy_decisions=proof_policy_decisions,
        proof_records=proof_records,
        proof_verifications=proof_verifications,
        proof_commitments=proof_commitments,
        judgments=judgments,
        review_projections=review_projections,
        anchor_manifest=anchor_manifest,
        artifact_group=artifact_group,
        events=events,
        primary_task_id=primary_task_id,
        calculation_input_allowlist=calculation_input_allowlist,
        calculation_parameter_allowlist=calculation_parameter_allowlist,
    )
    return TraceBundleV1(
        projection_revision=_positive_int(projection_revision, context="projection_revision"),
        projection_sequence=_nonnegative_int(projection_sequence, context="projection_sequence"),
        anchor_manifest_id=assembly.manifest.anchor_manifest_id,
        anchor_manifest_sha256=assembly.manifest.anchor_manifest_sha256,
        object_id=expected_object_id,
        run_id=expected_run_id,
        claim_id=assembly.claim.claim_id,
        metric_id=assembly.metric.metric_id,
        calculation_id=assembly.metric.calculation_id,
        claim=assembly.claim,
        released_metric=assembly.metric,
        task_refs=assembly.task_refs,
        primary_task_id=assembly.primary_task_id,
        evidence_refs=assembly.evidence_refs,
        calculation_refs=assembly.calculation_refs,
        judgment_refs=assembly.judgment_refs,
        review_refs=assembly.review_refs,
        proof_refs=assembly.proof_refs,
        canonical_record_id=assembly.canonical_record_id,
        released_result_id=assembly.released_result_id,
        report=assembly.report,
        review_anchors=assembly.manifest.review_anchors,
        task_anchors=assembly.manifest.task_anchors,
        execution_anchors=assembly.manifest.execution_anchors,
        availability=AvailabilityV1.available(),
    )


def build_atomic_run_projection(
    *,
    expected_object_id: str,
    expected_run_id: str,
    projection_revision: int,
    projection_sequence: int,
    generated_at: datetime,
    research_object: object,
    run: object,
    goal: object,
    confirmed_scheme: object,
    planned_graph: object,
    actual_graph: object | None,
    proof_summary: ProofSummaryV1,
    review_availability: AvailabilityV1,
    result_availability: AvailabilityV1,
    artifact_availability: AvailabilityV1,
    execution_availability: AvailabilityV1,
    path_changes: Sequence[object] = (),
    events: Sequence[object] = (),
    review_projection: FinancialReviewProjectionV1 | None = None,
    released_result_projection: ReleasedResultProjectionV1 | None = None,
    artifact_group: ReportArtifactGroupV1 | None = None,
    execution_projection: ExecutionProjectionV1 | None = None,
    release_validations: Sequence[object] = (),
    release_candidate_source: ReleaseCandidateSourceV1 | None = None,
    terminal_event: object | None = None,
    safe_failure: Mapping[str, object] | None = None,
) -> AtomicRunProjectionV1:
    """Compose the one-shot browser bootstrap from a single durable snapshot."""

    revision = _positive_int(projection_revision, context="projection_revision")
    sequence = _nonnegative_int(projection_sequence, context="projection_sequence")
    generated_at = _aware_datetime(generated_at, "generated_at")
    object_projection = project_object(research_object)
    if object_projection.object_id != expected_object_id:
        raise ProjectionIntegrityError("requested ResearchObject does not match exact object")
    run_projection = project_run_detail(
        run,
        projection_revision=revision,
        projection_sequence=sequence,
    )
    if (
        run_projection.run_id != expected_run_id
        or run_projection.research_object_id != expected_object_id
    ):
        raise ProjectionIntegrityError("requested Run/Object tuple does not close")
    status = project_run_status(run_projection.status)
    goal_projection = project_goal(goal, expected_object_id=expected_object_id)
    if goal_projection.goal_id != run_projection.goal_id:
        raise ProjectionIntegrityError("Run Goal reference does not close")
    scheme_projection = project_scheme(
        confirmed_scheme,
        expected_object_id=expected_object_id,
        expected_goal_id=goal_projection.goal_id,
    )
    if scheme_projection.scheme_id != run_projection.scheme_id:
        raise ProjectionIntegrityError("Run Scheme reference does not close")
    if run_projection.planned_graph_id is None:
        raise ProjectionIntegrityError("admitted Run is missing its planned graph reference")
    planned_projection = project_graph(
        planned_graph,
        expected_run_id=expected_run_id,
        expected_graph_id=run_projection.planned_graph_id,
    )
    actual_projection: GraphProjectionV1 | None = None
    if actual_graph is not None:
        if run_projection.actual_graph_id is None:
            raise ProjectionIntegrityError("actual graph exists without a Run reference")
        actual_projection = project_graph(
            actual_graph,
            expected_run_id=expected_run_id,
            expected_graph_id=run_projection.actual_graph_id,
        )
    elif run_projection.actual_graph_id is not None:
        raise ProjectionIntegrityError("Run references an unavailable actual graph")
    tasks = actual_projection.tasks if actual_projection is not None else planned_projection.tasks
    task_ids = {item.task_id for item in tasks}

    changes = tuple(
        sorted(
            (project_path_change(item, expected_run_id=expected_run_id) for item in path_changes),
            key=lambda item: (item.created_at, item.path_change_id),
        )
    )
    if len({item.path_change_id for item in changes}) != len(changes):
        raise ProjectionIntegrityError("path_changes contains duplicate source identities")
    if any(not set(item.task_refs).issubset(task_ids) for item in changes):
        raise ProjectionIntegrityError("PathChange references a Task outside the actual graph")

    activity = tuple(
        sorted(
            (
                project_event(
                    event,
                    expected_run_id=expected_run_id,
                    known_task_ids=task_ids,
                    projection_sequence=sequence,
                )
                for event in events
            ),
            key=lambda item: item.sequence,
        )
    )
    if len({item.sequence for item in activity}) != len(activity):
        raise ProjectionIntegrityError("activity contains duplicate RuntimeEvent sequences")
    if len({item.event_id for item in activity}) != len(activity):
        raise ProjectionIntegrityError("activity contains duplicate RuntimeEvent identities")

    _availability_body(review_availability, review_projection, "Review")
    _availability_body(result_availability, released_result_projection, "ReleasedResult")
    _availability_body(artifact_availability, artifact_group, "ReportArtifactGroup")
    _availability_body(execution_availability, execution_projection, "Execution")
    if review_projection is not None and (
        review_projection.object_id != expected_object_id
        or review_projection.run_id != expected_run_id
        or review_projection.projection_revision != revision
        or review_projection.projection_sequence != sequence
    ):
        raise ProjectionIntegrityError("Review projection is torn or cross-Run")
    if released_result_projection is not None and (
        released_result_projection.object_id != expected_object_id
        or released_result_projection.run_id != expected_run_id
    ):
        raise ProjectionIntegrityError("ReleasedResult projection is cross-Run")
    if artifact_group is not None and (
        artifact_group.object_id != expected_object_id or artifact_group.run_id != expected_run_id
    ):
        raise ProjectionIntegrityError("ReportArtifactGroup is cross-Run")
    if execution_projection is not None and (
        execution_projection.object_id != expected_object_id
        or execution_projection.run_id != expected_run_id
        or execution_projection.projection_revision != revision
        or execution_projection.projection_sequence != sequence
    ):
        raise ProjectionIntegrityError("Execution projection is torn or cross-Run")

    _validate_atomic_release_validation(
        status=status,
        object_id=expected_object_id,
        run_id=expected_run_id,
        validations=release_validations,
        review=review_projection,
        result=released_result_projection,
        artifacts=artifact_group,
        proof=proof_summary,
        execution=execution_projection,
        source=release_candidate_source,
    )
    release_closure_valid = _release_projection_closes(
        status=status,
        review=review_projection,
        result=released_result_projection,
        artifacts=artifact_group,
        proof=proof_summary,
        execution=execution_projection,
    )
    if status.status != "RELEASED" and any(
        item is not None for item in (released_result_projection, artifact_group)
    ):
        raise ProjectionIntegrityError("non-RELEASED Run cannot expose released output")
    progress = calculate_run_progress(
        tasks,
        run_status=status.status,
        release_closure_valid=release_closure_valid,
    )

    safe_failure_projection = None if safe_failure is None else _project_safe_failure(safe_failure)
    terminal = _terminal_state(
        status=status,
        terminal_event=terminal_event,
        activity=activity,
        projection_sequence=sequence,
        safe_failure=safe_failure_projection,
    )
    if status.terminal != (run_projection.completed_at is not None):
        raise ProjectionIntegrityError("Run terminal state and completed_at disagree")

    review_summary = ReviewSummaryV1(
        availability=review_availability,
        review_id=review_projection.review_id if review_projection is not None else None,
        status=review_projection.status if review_projection is not None else None,
    )
    result_summary = ResultSummaryV1(
        availability=result_availability,
        released_result_id=(
            released_result_projection.released_result_id
            if released_result_projection is not None
            else None
        ),
        canonical_record_id=(
            released_result_projection.canonical_record_id
            if released_result_projection is not None
            else None
        ),
        released_at=(
            released_result_projection.released_at
            if released_result_projection is not None
            else None
        ),
    )
    artifact_summary = ArtifactSummaryV1(
        availability=artifact_availability,
        report_id=artifact_group.report_id if artifact_group is not None else None,
        representation_ids=tuple(
            item.artifact_id
            for item in artifact_group.representations
            if item.artifact_id is not None
        )
        if artifact_group is not None
        else (),
    )
    execution_summary = ExecutionSummaryV1(
        availability=execution_availability,
        canonical_record_id=(
            execution_projection.canonical_record_id if execution_projection is not None else None
        ),
    )
    return AtomicRunProjectionV1(
        projection_revision=revision,
        projection_sequence=sequence,
        generated_at=generated_at,
        object=object_projection,
        run=run_projection,
        goal=goal_projection,
        confirmed_scheme=scheme_projection,
        planned_graph=planned_projection,
        actual_graph=actual_projection,
        graph_version=actual_projection.version if actual_projection is not None else None,
        tasks=tasks,
        path_changes=changes,
        activity=activity,
        lifecycle=RunLifecycleV1(
            status=status.status,
            stage=status.stage,
            progress=progress,
            terminal=status.terminal,
            terminal_outcome=status.terminal_outcome,
            safe_failure=safe_failure_projection,
        ),
        review=review_summary,
        result=result_summary,
        artifacts=artifact_summary,
        proof=proof_summary,
        execution=execution_summary,
        terminal=terminal,
    )


def _assemble_claim(
    *,
    expected_object_id: str,
    expected_run_id: str,
    claim_id: str,
    run: object,
    canonical_record: object,
    released_result: object,
    calculations: Sequence[object],
    evidence: Sequence[object],
    tasks: Sequence[object],
    proof_policy_decisions: Sequence[object],
    proof_records: Sequence[object],
    proof_verifications: Sequence[object],
    proof_commitments: Sequence[object],
    judgments: Sequence[object],
    review_projections: Sequence[FinancialReviewProjectionV1],
    anchor_manifest: object,
    artifact_group: ReportArtifactGroupV1,
    events: Sequence[object],
    primary_task_id: str | None,
    calculation_input_allowlist: JsonAllowlist,
    calculation_parameter_allowlist: JsonAllowlist,
) -> _ClaimAssembly:
    claim_id = _required_nonblank(claim_id, "claim_id")
    if (
        _required_string(run, "run_id", "Run") != expected_run_id
        or _required_string(run, "research_object_id", "Run") != expected_object_id
        or _enum_text(_field(run, "status"), context="Run.status") != "RELEASED"
    ):
        raise ProjectionIntegrityError("Claim detail requires its exact RELEASED Run")
    canonical_id = _required_string(canonical_record, "record_id", "CanonicalRecord")
    result_id = _required_string(released_result, "result_id", "ReleasedResult")
    if (
        _required_string(canonical_record, "run_id", "CanonicalRecord") != expected_run_id
        or _required_string(canonical_record, "object_snapshot_ref", "CanonicalRecord")
        != expected_object_id
        or _required_string(released_result, "run_id", "ReleasedResult") != expected_run_id
        or _required_string(released_result, "canonical_record_id", "ReleasedResult")
        != canonical_id
    ):
        raise ProjectionIntegrityError("Claim Canonical/ReleasedResult closure failed")

    raw_claims = _sequence(_field(released_result, "material_claims"), "material claims")
    matching_claims = tuple(
        item
        for item in raw_claims
        if _optional_raw_string(_field(item, "claim_id", None)) == claim_id
    )
    if len(matching_claims) != 1:
        raise ProjectionIntegrityError("requested Claim is absent or ambiguous in this Run")
    raw_claim = matching_claims[0]
    claim = _project_typed_claim(raw_claim, expected_run_id)

    raw_metrics = _sequence(_field(released_result, "released_metrics"), "released metrics")
    matching_metrics = tuple(
        item
        for item in raw_metrics
        if _optional_raw_string(_field(item, "metric_id", None)) == claim.metric_id
    )
    if len(matching_metrics) != 1:
        raise ProjectionIntegrityError("Claim has no exact released metric")
    raw_metric = matching_metrics[0]

    calculation_by_id = _unique_index(calculations, "calculation_id", context="Calculation")
    calculation_records = tuple(
        _required_index_item(calculation_by_id, item, "Calculation")
        for item in claim.calculation_refs
    )
    metric_calculation = _required_index_item(
        calculation_by_id,
        _required_string(raw_metric, "calculation_id", "ReleasedMetric"),
        "Calculation",
    )
    evidence_by_id = _unique_index(evidence, "evidence_id", context="Evidence")
    evidence_records = tuple(
        _required_index_item(evidence_by_id, item, "Evidence") for item in claim.evidence_refs
    )
    metric = build_released_metric(
        expected_object_id=expected_object_id,
        expected_run_id=expected_run_id,
        metric=raw_metric,
        claims=matching_claims,
        calculation=metric_calculation,
        evidence=evidence_records,
        proof_policy_decisions=proof_policy_decisions,
        proof_records=proof_records,
        proof_verifications=proof_verifications,
        proof_commitments=proof_commitments,
    )

    task_by_id = _unique_index(tasks, "task_id", context="Task")
    ordered_task_ids: list[str] = []
    for calculation in calculation_records:
        if _required_string(calculation, "run_id", "Calculation") != expected_run_id:
            raise ProjectionIntegrityError("Claim Calculation belongs to another Run")
        task_id = _required_string(calculation, "task_id", "Calculation")
        task = _required_index_item(task_by_id, task_id, "Task")
        if _required_string(task, "run_id", "Task") != expected_run_id:
            raise ProjectionIntegrityError("Claim supporting Task belongs to another Run")
        if task_id not in ordered_task_ids:
            ordered_task_ids.append(task_id)
    if primary_task_id is not None:
        primary_task_id = _required_nonblank(primary_task_id, "primary_task_id")
        if primary_task_id not in ordered_task_ids:
            raise ProjectionIntegrityError("persisted primary Task is not a supporting Task")
    task_refs = tuple(
        TaskAvailabilityRefV1(task_id=item, availability=AvailabilityV1.available())
        for item in ordered_task_ids
    )

    evidence_details = tuple(
        _project_evidence(item, expected_object_id, expected_run_id) for item in evidence_records
    )
    evidence_refs = tuple(
        EvidenceAvailabilityRefV1(
            evidence_id=_required_string(item, "evidence_id", "Evidence"),
            availability=AvailabilityV1.available(),
        )
        for item in evidence_records
    )
    calculation_details = tuple(
        _project_calculation(
            item,
            expected_run_id=expected_run_id,
            input_allowlist=calculation_input_allowlist,
            parameter_allowlist=calculation_parameter_allowlist,
        )
        for item in calculation_records
    )
    calculation_refs = tuple(
        CalculationAvailabilityRefV1(
            calculation_id=_required_string(item, "calculation_id", "Calculation"),
            availability=AvailabilityV1.available(),
        )
        for item in calculation_records
    )
    judgment_refs = _project_judgments(
        claim.judgment_refs,
        judgments=judgments,
        expected_run_id=expected_run_id,
    )
    review_refs = _claim_review_refs(
        claim_id,
        review_projections=review_projections,
        canonical_record=canonical_record,
        expected_object_id=expected_object_id,
        expected_run_id=expected_run_id,
    )
    proof_join = join_metric_proof(
        expected_run_id=expected_run_id,
        calculation=metric_calculation,
        metric=raw_metric,
        proof_policy_decisions=proof_policy_decisions,
        proof_records=proof_records,
        proof_verifications=proof_verifications,
        proof_commitments=proof_commitments,
    )

    if artifact_group.object_id != expected_object_id or artifact_group.run_id != expected_run_id:
        raise ProjectionIntegrityError("artifact group belongs to another Run/Object")
    _validate_public_availability(artifact_group.availability, context="artifact group")
    for slot in artifact_group.representations:
        _validate_public_availability(
            slot.availability,
            context=f"artifact {slot.format}",
        )
    if (
        artifact_group.canonical_record_id != canonical_id
        or artifact_group.released_result_id != result_id
        or artifact_group.report_id != result_id
    ):
        raise ProjectionIntegrityError("artifact group release identity closure failed")
    manifest = validate_anchor_manifest(
        anchor_manifest,
        expected_object_id=expected_object_id,
        expected_run_id=expected_run_id,
        expected_canonical_record_id=canonical_id,
        expected_released_result_id=result_id,
        expected_claim_id=claim_id,
        expected_metric_id=claim.metric_id,
    )
    if (
        artifact_group.anchor_manifest_id != manifest.anchor_manifest_id
        or artifact_group.anchor_manifest_sha256 != manifest.anchor_manifest_sha256
    ):
        raise ProjectionIntegrityError("artifact group and Claim manifest disagree")
    _validate_claim_anchors(
        manifest,
        task_refs=task_refs,
        review_refs=review_refs,
        events=events,
        expected_run_id=expected_run_id,
    )

    report_representations: list[TraceRepresentationV1] = []
    for slot, anchor in zip(
        artifact_group.representations,
        manifest.representations,
        strict=True,
    ):
        if (
            slot.format != anchor.format
            or slot.artifact_id != anchor.artifact_id
            or _availability_value(slot.availability) != _availability_value(anchor.availability)
        ):
            raise ProjectionIntegrityError("report representation and Claim anchor disagree")
        report_representations.append(
            TraceRepresentationV1(
                format=slot.format,
                artifact_id=slot.artifact_id,
                availability=slot.availability,
                claim_anchor=anchor,
            )
        )
    report = TraceReportV1(
        report_id=result_id,
        representations=(report_representations[0], report_representations[1]),
    )
    return _ClaimAssembly(
        claim=claim,
        metric=metric,
        task_refs=task_refs,
        primary_task_id=primary_task_id,
        evidence=evidence_details,
        evidence_refs=evidence_refs,
        calculations=calculation_details,
        calculation_refs=calculation_refs,
        judgment_refs=judgment_refs,
        review_refs=review_refs,
        proof_refs=proof_join.trace_refs,
        canonical_record_id=canonical_id,
        released_result_id=result_id,
        manifest=manifest,
        report=report,
    )


def _project_graph_operation(
    operation: object,
    *,
    expected_run_id: str,
) -> TypedGraphOperationV1:
    operation_run = _field(operation, "run_id", expected_run_id)
    if operation_run != expected_run_id:
        raise ProjectionIntegrityError("graph operation belongs to another Run")
    kind = _enum_text(_field(operation, "operation"), context="graph operation")
    if kind not in {"add_node", "add_edge", "remove_edge"}:
        raise ProjectionIntegrityError("unsupported graph operation")
    task_id = _required_string(operation, "task_id", "graph operation")
    dependency = _optional_string(
        _field(operation, "dependency_task_id", None),
        context="graph operation dependency_task_id",
    )
    if kind == "add_node" and dependency is not None:
        raise ProjectionIntegrityError("add_node cannot carry a dependency Task")
    if kind != "add_node" and dependency is None:
        raise ProjectionIntegrityError("edge operation requires a dependency Task")
    return TypedGraphOperationV1(
        operation=kind,
        task_id=task_id,
        dependency_task_id=dependency,
    )


def _event_actor(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    candidates = (
        ("requested_by", "REQUESTER"),
        ("approved_by", "APPROVER"),
        ("decided_by", "DECIDER"),
        ("generated_by", "GENERATOR"),
    )
    selected = tuple(
        (_required_nonblank(payload[key], f"event {key}"), role)
        for key, role in candidates
        if payload.get(key) is not None
    )
    if len(selected) > 1:
        raise ProjectionIntegrityError("RuntimeEvent has ambiguous public actor identity")
    return selected[0] if selected else (None, None)


def _event_output_refs(payload: Mapping[str, Any]) -> tuple[str, ...]:
    ordered_keys = (
        "gap_id",
        "build_id",
        "generated_capability_id",
        "registration_id",
        "correction_id",
        "replan_id",
        "scheme_id",
        "graph_id",
        "canonical_record_id",
        "result_id",
    )
    result: list[str] = []
    for key in ordered_keys:
        value = payload.get(key)
        if value is not None:
            text = _required_nonblank(value, f"RuntimeEvent.payload.{key}")
            if text not in result:
                result.append(text)
    return tuple(result)


def _single_ref(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    return () if value is None else (_required_nonblank(value, f"event {key}"),)


def _project_method_metadata(value: object) -> MethodMetadataV1 | None:
    if value is None:
        return None
    raw_parameters = _sequence(_field(value, "parameters"), "method parameters")
    parameters: list[MethodParameterV1] = []
    for item in raw_parameters:
        if isinstance(item, Mapping):
            name = _required_string(item, "name", "method parameter")
            parameter_value = _required_string(item, "value", "method parameter")
        elif isinstance(item, Sequence) and not isinstance(item, str | bytes) and len(item) == 2:
            name = _required_nonblank(item[0], "method parameter name")
            parameter_value = _required_nonblank(item[1], "method parameter value")
        else:
            raise ProjectionIntegrityError("method parameters require ordered name/value pairs")
        parameters.append(MethodParameterV1(name=name, value=parameter_value))
    if len({item.name for item in parameters}) != len(parameters):
        raise ProjectionIntegrityError("method parameter names must be unique")
    return MethodMetadataV1(
        method=_required_string(value, "method", "MethodMetadata"),
        parameters=tuple(parameters),
        observation_count=_optional_positive_int(
            _field(value, "observation_count", None), "MethodMetadata.observation_count"
        ),
        warmup_required=_optional_positive_int(
            _field(value, "warmup_required", None), "MethodMetadata.warmup_required"
        ),
        warmup_satisfied=_optional_bool(
            _field(value, "warmup_satisfied", None), "MethodMetadata.warmup_satisfied"
        ),
        first_as_of=_optional_date(
            _field(value, "first_as_of", None), "MethodMetadata.first_as_of"
        ),
        last_as_of=_optional_date(_field(value, "last_as_of", None), "MethodMetadata.last_as_of"),
        is_wilder=_optional_bool(_field(value, "is_wilder", None), "MethodMetadata.is_wilder"),
        ema_adjust=_optional_bool(_field(value, "ema_adjust", None), "MethodMetadata.ema_adjust"),
    )


def _validate_claim_metric_closure(
    claim: object,
    *,
    metric: object,
    expected_run_id: str,
    evidence_ids: tuple[str, ...],
) -> None:
    if _required_string(claim, "run_id", "Claim") != expected_run_id:
        raise ProjectionIntegrityError("Claim belongs to another Run")
    comparisons = (
        (
            _required_string(claim, "metric_id", "Claim"),
            _required_string(metric, "metric_id", "Metric"),
        ),
        (
            _canonical_decimal(_field(claim, "value"), context="Claim.value"),
            _canonical_decimal(_field(metric, "canonical_value"), context="Metric.value"),
        ),
        (
            _enum_text(_field(claim, "unit"), context="Claim.unit"),
            _enum_text(_field(metric, "canonical_unit"), context="Metric.unit"),
        ),
        (_required_string(claim, "period", "Claim"), _required_string(metric, "period", "Metric")),
        (
            _enum_text(_field(claim, "period_basis"), context="Claim.period_basis"),
            _enum_text(_field(metric, "period_basis"), context="Metric.period_basis"),
        ),
        (
            _enum_text(_field(claim, "actuality"), context="Claim.actuality"),
            _enum_text(_field(metric, "actuality"), context="Metric.actuality"),
        ),
        (_required_date(claim, "as_of", "Claim"), _required_date(metric, "as_of", "Metric")),
        (
            _optional_string(_field(claim, "currency", None), context="Claim.currency"),
            _optional_string(_field(metric, "currency", None), context="Metric.currency"),
        ),
    )
    if any(left != right for left, right in comparisons):
        raise ProjectionIntegrityError("Claim canonical semantics differ from released metric")
    if _unique_string_tuple(_field(claim, "calculation_refs"), "Claim.calculation_refs") != (
        _required_string(metric, "calculation_id", "Metric"),
    ):
        raise ProjectionIntegrityError("Claim Calculation refs differ from released metric")
    if _unique_string_tuple(_field(claim, "evidence_refs"), "Claim.evidence_refs") != evidence_ids:
        raise ProjectionIntegrityError("Claim Evidence refs differ from released metric")


def _project_typed_claim(claim: object, expected_run_id: str) -> TypedReleasedClaimV1:
    if _required_string(claim, "run_id", "Claim") != expected_run_id:
        raise ProjectionIntegrityError("Claim belongs to another Run")
    return TypedReleasedClaimV1(
        claim_id=_required_string(claim, "claim_id", "Claim"),
        run_id=expected_run_id,
        claim_type=_required_string(claim, "claim_type", "Claim"),
        statement=safe_text(_field(claim, "statement"), context="Claim.statement"),
        metric_id=_required_string(claim, "metric_id", "Claim"),
        value=_canonical_decimal(_field(claim, "value"), context="Claim.value"),
        unit=_enum_text(_field(claim, "unit"), context="Claim.unit"),
        period=_required_string(claim, "period", "Claim"),
        period_basis=_enum_text(_field(claim, "period_basis"), context="Claim.period_basis"),
        actuality=_enum_text(_field(claim, "actuality"), context="Claim.actuality"),
        as_of=_required_date(claim, "as_of", "Claim"),
        currency=_optional_string(_field(claim, "currency", None), context="Claim.currency"),
        calculation_refs=_unique_string_tuple(
            _field(claim, "calculation_refs"), "Claim.calculation_refs"
        ),
        evidence_refs=_unique_string_tuple(_field(claim, "evidence_refs"), "Claim.evidence_refs"),
        judgment_refs=_unique_string_tuple(_field(claim, "judgment_refs"), "Claim.judgment_refs"),
    )


def _exact_commitment(
    proof: object,
    *,
    calculation: object,
    metric: object,
    commitments: Sequence[object],
    expected_run_id: str,
) -> object:
    calculation_id = _required_string(calculation, "calculation_id", "Calculation")
    matching = tuple(
        item
        for item in commitments
        if _optional_raw_string(_field(item, "calculation_id", None)) == calculation_id
    )
    if len(matching) != 1:
        raise ProjectionIntegrityError("MUST_PROVE record requires exactly one input commitment")
    commitment = matching[0]
    if (
        _required_string(commitment, "run_id", "ProofInputCommitment") != expected_run_id
        or _required_string(commitment, "formula_id", "ProofInputCommitment")
        != _required_string(metric, "formula_id", "Metric")
        or _required_string(commitment, "capability_id", "ProofInputCommitment")
        != _required_string(metric, "capability_id", "Metric")
        or _required_string(commitment, "implementation_hash", "ProofInputCommitment")
        != _required_string(proof, "implementation_hash", "ProofRecord")
        or _required_string(commitment, "input_commitment", "ProofInputCommitment")
        != _required_string(proof, "input_commitment", "ProofRecord")
        or _unique_string_tuple(
            _field(commitment, "input_evidence_refs"),
            "ProofInputCommitment.input_evidence_refs",
        )
        != _unique_string_tuple(
            _field(calculation, "input_evidence_ids"), "Calculation.input_evidence_ids"
        )
    ):
        raise ProjectionIntegrityError("Proof input commitment closure failed")
    return commitment


def _verified_proof_id(proof: object, *, verifications: Sequence[object]) -> str | None:
    proof_id = _required_string(proof, "proof_id", "ProofRecord")
    matching = tuple(
        item
        for item in verifications
        if _optional_raw_string(_field(item, "proof_id", None)) == proof_id
    )
    verified = tuple(
        item
        for item in matching
        if _field(item, "verified", False) is True
        and _enum_text(_field(item, "status"), context="ProofVerification.status") == "VERIFIED"
    )
    if len(verified) > 1:
        raise ProjectionIntegrityError("ProofRecord has ambiguous VERIFIED records")
    if not verified:
        return None
    item = verified[0]
    for field_name in ("image_id", "receipt_hash", "journal_hash"):
        if _required_string(item, field_name, "ProofVerification") != _required_string(
            proof, field_name, "ProofRecord"
        ):
            raise ProjectionIntegrityError("Proof verification cryptographic closure failed")
    return _required_string(item, "verification_id", "ProofVerification")


def _validate_canonical_release_refs(
    canonical_record: object,
    *,
    metrics: Sequence[ReleasedFinancialMetricProjectionV1],
    claims: Sequence[TypedReleasedClaimV1],
    proof_records: Sequence[object],
    expected_run_id: str,
) -> None:
    expected = {
        "metric_refs": {item.metric_id for item in metrics},
        "claim_refs": {item.claim_id for item in claims},
    }
    for field_name, expected_refs in expected.items():
        actual = set(
            _unique_string_tuple(_field(canonical_record, field_name), f"Canonical.{field_name}")
        )
        if actual != expected_refs:
            raise ProjectionIntegrityError(f"Canonical {field_name} do not match released output")
    calculation_refs = set(
        _unique_string_tuple(
            _field(canonical_record, "calculation_refs"), "Canonical.calculation_refs"
        )
    )
    evidence_refs = set(
        _unique_string_tuple(_field(canonical_record, "evidence_refs"), "Canonical.evidence_refs")
    )
    if {item.calculation_id for item in metrics} - calculation_refs:
        raise ProjectionIntegrityError("Canonical record omits a released Calculation")
    if {ref for item in metrics for ref in item.evidence_refs} - evidence_refs:
        raise ProjectionIntegrityError("Canonical record omits released Evidence")
    exact_proofs = {
        _required_string(item, "proof_id", "ProofRecord")
        for item in proof_records
        if _optional_raw_string(_field(item, "run_id", None)) == expected_run_id
        and _optional_raw_string(_field(item, "calculation_id", None))
        in {metric.calculation_id for metric in metrics}
    }
    canonical_proofs = set(
        _unique_string_tuple(_field(canonical_record, "proof_refs"), "Canonical.proof_refs")
    )
    if exact_proofs != canonical_proofs:
        raise ProjectionIntegrityError("Canonical Proof refs do not match released calculations")


def _project_disposition(value: object) -> SafeJsonObject:
    raw = {
        "calculation_id": _required_string(value, "calculation_id", "Disposition"),
        "metric_id": _optional_string(
            _field(value, "metric_id", None), context="Disposition.metric_id"
        ),
        "status": _enum_text(_field(value, "status"), context="Disposition.status"),
        "reason": _optional_string(_field(value, "reason", None), context="Disposition.reason"),
    }
    try:
        return safe_json_object(
            raw,
            allowed_keys={"calculation_id", "metric_id", "status", "reason"},
            context="material calculation disposition",
        )
    except UnsafeProjectionData as exc:
        raise ProjectionIntegrityError(str(exc)) from exc


def _project_review_check(
    check: object,
    *,
    expected_run_id: str,
    json_allowlist: JsonAllowlist,
) -> FinancialReviewCheckProjectionV1:
    check_id = _required_string(check, "check_id", "ReviewCheck")
    subjects = tuple(
        ReviewSubjectV1.model_validate(_model_mapping(item))
        for item in _sequence(_field(check, "subjects"), "ReviewCheck.subjects")
    )
    if not subjects or any(item.run_id != expected_run_id for item in subjects):
        raise ProjectionIntegrityError("ReviewCheck requires typed same-Run subjects")
    correction_refs = tuple(
        ReviewCorrectionRefV1.model_validate(_model_mapping(item))
        for item in _sequence(_field(check, "correction_refs"), "ReviewCheck.correction_refs")
    )
    if any(item.run_id != expected_run_id for item in correction_refs):
        raise ProjectionIntegrityError("Review correction belongs to another Run")
    try:
        expected = safe_json_object(
            _field(check, "expected"),
            allowed_keys=json_allowlist,
            context=f"ReviewCheck[{check_id}].expected",
        )
        actual = safe_json_object(
            _field(check, "actual"),
            allowed_keys=json_allowlist,
            context=f"ReviewCheck[{check_id}].actual",
        )
    except UnsafeProjectionData as exc:
        raise ProjectionIntegrityError(str(exc)) from exc
    detail_value = _field(check, "detail", None)
    detail = (
        None
        if detail_value is None
        else safe_text(
            detail_value,
            context=f"ReviewCheck[{check_id}].detail",
        )
    )
    return FinancialReviewCheckProjectionV1(
        check_id=check_id,
        check_code=_required_string(check, "check_code", "ReviewCheck"),
        status=_enum_text(_field(check, "status"), context="ReviewCheck.status"),
        subjects=subjects,
        expected=expected,
        actual=actual,
        detail=detail,
        exception_state=_enum_text(
            _field(check, "exception_state"), context="ReviewCheck.exception_state"
        ),
        correction_refs=tuple(
            sorted(
                correction_refs,
                key=lambda item: (
                    item.resolved_at.isoformat() if item.resolved_at is not None else "",
                    item.correction_id,
                ),
            )
        ),
        created_at=_required_datetime(check, "created_at", "ReviewCheck"),
        resolved_at=_optional_datetime(
            _field(check, "resolved_at", None), "ReviewCheck.resolved_at"
        ),
    )


def _aggregate_review_status(
    checks: Sequence[FinancialReviewCheckProjectionV1],
) -> str:
    if any(item.status == "BLOCK" and item.exception_state == "OPEN" for item in checks):
        return "BLOCK"
    if any(item.status == "REVIEW" and item.exception_state == "OPEN" for item in checks):
        return "REVIEW"
    return "PASS"


def _project_evidence(
    evidence: object,
    expected_object_id: str,
    expected_run_id: str,
) -> SafeJsonObject:
    if (
        _required_string(evidence, "run_id", "Evidence") != expected_run_id
        or _required_string(evidence, "object_id", "Evidence") != expected_object_id
    ):
        raise ProjectionIntegrityError("Evidence belongs to another Run/Object")
    value = _public_json_value(_field(evidence, "normalized_value"))
    try:
        safe_value = safe_json(
            value,
            allowed_keys=_CALCULATION_INPUT_KEYS,
            context="Evidence.normalized_value",
        )
    except UnsafeProjectionData as exc:
        raise ProjectionIntegrityError(str(exc)) from exc
    return {
        "evidence_id": _required_string(evidence, "evidence_id", "Evidence"),
        "run_id": expected_run_id,
        "object_id": expected_object_id,
        "provider": _required_string(evidence, "provider", "Evidence"),
        "producer_task_id": _optional_string(
            _field(evidence, "producer_task_id", None), context="Evidence.producer_task_id"
        ),
        "evidence_purpose": _optional_string(
            _field(evidence, "evidence_purpose", None), context="Evidence.evidence_purpose"
        ),
        "evidence_category": _enum_text(
            _field(evidence, "evidence_category"), context="Evidence.evidence_category"
        ),
        "retrieved_at": _required_datetime(evidence, "retrieved_at", "Evidence").isoformat(),
        "observed_at": _optional_datetime(
            _field(evidence, "observed_at", None), "Evidence.observed_at"
        ).isoformat()
        if _field(evidence, "observed_at", None) is not None
        else None,
        "provider_timestamp": _optional_datetime(
            _field(evidence, "provider_timestamp", None), "Evidence.provider_timestamp"
        ).isoformat()
        if _field(evidence, "provider_timestamp", None) is not None
        else None,
        "period": _required_string(evidence, "period", "Evidence"),
        "period_basis": _optional_enum_text(
            _field(evidence, "period_basis", None), "Evidence.period_basis"
        ),
        "actuality": _enum_text(_field(evidence, "actuality"), context="Evidence.actuality"),
        "as_of": _required_date(evidence, "as_of", "Evidence").isoformat(),
        "normalized_field": _required_string(evidence, "normalized_field", "Evidence"),
        "normalized_value": safe_value,
        "unit": _required_string(evidence, "unit", "Evidence"),
        "currency": _optional_string(
            _field(evidence, "currency", None), context="Evidence.currency"
        ),
        "snapshot_hash": _required_string(evidence, "snapshot_hash", "Evidence"),
        "status": _enum_text(_field(evidence, "status"), context="Evidence.status"),
    }


def _project_calculation(
    calculation: object,
    *,
    expected_run_id: str,
    input_allowlist: JsonAllowlist,
    parameter_allowlist: JsonAllowlist,
) -> SafeJsonObject:
    if _required_string(calculation, "run_id", "Calculation") != expected_run_id:
        raise ProjectionIntegrityError("Calculation belongs to another Run")
    try:
        inputs = safe_json_object(
            _public_json_value(_field(calculation, "input_values_snapshot")),
            allowed_keys=input_allowlist,
            context="Calculation.input_values_snapshot",
        )
        parameters = safe_json_object(
            _public_json_value(_field(calculation, "parameters")),
            allowed_keys=parameter_allowlist,
            context="Calculation.parameters",
        )
        output = safe_json(
            _public_json_value(_field(calculation, "output_value")),
            allowed_keys=set(),
            context="Calculation.output_value",
        )
    except UnsafeProjectionData as exc:
        raise ProjectionIntegrityError(str(exc)) from exc
    return {
        "calculation_id": _required_string(calculation, "calculation_id", "Calculation"),
        "run_id": expected_run_id,
        "task_id": _required_string(calculation, "task_id", "Calculation"),
        "capability_id": _required_string(calculation, "capability_id", "Calculation"),
        "capability_version": _required_string(calculation, "capability_version", "Calculation"),
        "formula_id": _required_string(calculation, "formula_id", "Calculation"),
        "input_evidence_ids": list(
            _unique_string_tuple(
                _field(calculation, "input_evidence_ids"),
                "Calculation.input_evidence_ids",
            )
        ),
        "input_values_snapshot": inputs,
        "parameters": parameters,
        "output_value": output,
        "output_unit": _required_string(calculation, "output_unit", "Calculation"),
        "status": _enum_text(_field(calculation, "status"), context="Calculation.status"),
        "review_status": _optional_enum_text(
            _field(calculation, "review_status", None), "Calculation.review_status"
        ),
        "implementation_hash": _optional_string(
            _field(calculation, "implementation_hash", None),
            context="Calculation.implementation_hash",
        ),
        "runtime_version": _optional_string(
            _field(calculation, "runtime_version", None),
            context="Calculation.runtime_version",
        ),
        "review_record_id": _optional_string(
            _field(calculation, "review_record_id", None),
            context="Calculation.review_record_id",
        ),
        "canonical_record_id": _optional_string(
            _field(calculation, "canonical_record_id", None),
            context="Calculation.canonical_record_id",
        ),
        "proof_id": _optional_string(
            _field(calculation, "proof_ref", None), context="Calculation.proof_ref"
        ),
        "created_at": _required_datetime(calculation, "created_at", "Calculation").isoformat(),
    }


def _project_judgments(
    judgment_ids: Sequence[str],
    *,
    judgments: Sequence[object],
    expected_run_id: str,
) -> tuple[JudgmentAvailabilityV1, ...]:
    index = _unique_index(judgments, "judgment_id", context="Judgment", allow_missing=True)
    result: list[JudgmentAvailabilityV1] = []
    detail_keys = {
        "schema_version": None,
        "judgment_id": None,
        "run_id": None,
        "task_id": None,
        "judgment_type": None,
        "value": None,
        "evidence_refs": None,
        "calculation_refs": None,
        "policy_id": None,
        "skill_version": None,
        "confidence": None,
        "limitations": None,
        "requires_review": None,
    }
    for judgment_id in judgment_ids:
        record = index.get(judgment_id)
        if record is None:
            result.append(
                JudgmentAvailabilityV1(
                    judgment_id=judgment_id,
                    run_id=expected_run_id,
                    availability=AvailabilityV1.unavailable(
                        AvailabilityStatus.UNAVAILABLE,
                        "DETAIL_NOT_RETAINED",
                    ),
                    detail=None,
                )
            )
            continue
        record_run = _field(record, "run_id", None)
        if record_run is not None and record_run != expected_run_id:
            raise ProjectionIntegrityError("Judgment belongs to another Run")
        if _field(record, "schema_version", None) != "phase4-technical-judgment/v1":
            result.append(
                JudgmentAvailabilityV1(
                    judgment_id=judgment_id,
                    run_id=expected_run_id,
                    availability=AvailabilityV1.unavailable(
                        AvailabilityStatus.UNAVAILABLE,
                        "JUDGMENT_DETAIL_NOT_TYPED",
                    ),
                    detail=None,
                )
            )
            continue
        detail = _safe_model_json(
            record,
            allowed_keys=detail_keys,
            context=f"Judgment[{judgment_id}]",
        )
        if (
            detail.get("judgment_id") != judgment_id
            or detail.get("run_id") != expected_run_id
            or detail.get("requires_review") is not True
        ):
            raise ProjectionIntegrityError("typed Judgment identity/Review closure failed")
        result.append(
            JudgmentAvailabilityV1(
                judgment_id=judgment_id,
                run_id=expected_run_id,
                availability=AvailabilityV1.available(),
                detail=detail,
            )
        )
    return tuple(result)


def _claim_review_refs(
    claim_id: str,
    *,
    review_projections: Sequence[FinancialReviewProjectionV1],
    canonical_record: object,
    expected_object_id: str,
    expected_run_id: str,
) -> tuple[ReviewAvailabilityRefV1, ...]:
    canonical_review_refs = _unique_string_tuple(
        _field(canonical_record, "review_refs"), "Canonical.review_refs"
    )
    by_id: dict[str, FinancialReviewProjectionV1] = {}
    for projection in review_projections:
        if projection.review_id is None:
            raise ProjectionIntegrityError("Claim Review input cannot be an absent Review")
        if projection.review_id in by_id:
            raise ProjectionIntegrityError("duplicate Review projection identity")
        if projection.object_id != expected_object_id or projection.run_id != expected_run_id:
            raise ProjectionIntegrityError("Review projection belongs to another Run/Object")
        by_id[projection.review_id] = projection
    if set(by_id) != set(canonical_review_refs):
        raise ProjectionIntegrityError("Claim Review inputs do not equal Canonical Review refs")

    result: list[ReviewAvailabilityRefV1] = []
    for review_id in canonical_review_refs:
        review = by_id[review_id]
        subject_check_ids = tuple(
            check.check_id
            for check in review.checks
            if any(
                subject.subject_type == "CLAIM" and subject.subject_id == claim_id
                for subject in check.subjects
            )
        )
        if claim_id not in review.reviewed_claim_refs and not subject_check_ids:
            continue
        result.append(
            ReviewAvailabilityRefV1(
                review_id=review_id,
                check_ids=subject_check_ids,
                availability=AvailabilityV1.available(),
            )
        )
    if not result:
        raise ProjectionIntegrityError("Claim has no explicit Financial Review association")
    return tuple(result)


def _validate_claim_anchors(
    manifest: ValidatedAnchorManifest,
    *,
    task_refs: Sequence[TaskAvailabilityRefV1],
    review_refs: Sequence[ReviewAvailabilityRefV1],
    events: Sequence[object],
    expected_run_id: str,
) -> None:
    expected_task_ids = tuple(item.task_id for item in task_refs)
    if tuple(item.task_id for item in manifest.task_anchors) != expected_task_ids:
        raise ProjectionIntegrityError("manifest Task anchors do not follow exact Task refs")
    expected_review_pairs = tuple(
        (review.review_id, check_id) for review in review_refs for check_id in review.check_ids
    )
    actual_review_pairs = tuple(
        (anchor.review_id, anchor.check_id) for anchor in manifest.review_anchors
    )
    if actual_review_pairs != expected_review_pairs:
        raise ProjectionIntegrityError("manifest Review anchors do not follow Review/Check refs")

    event_by_id = _unique_index(events, "event_id", context="RuntimeEvent", allow_missing=True)
    task_order = {task_id: index for index, task_id in enumerate(expected_task_ids)}
    previous_task_index = -1
    for anchor in manifest.execution_anchors:
        if anchor.task_id not in task_order:
            raise ProjectionIntegrityError("execution anchor names an unsupported Task")
        current_task_index = task_order[anchor.task_id]
        if current_task_index < previous_task_index:
            raise ProjectionIntegrityError("execution anchors do not follow Task order")
        previous_task_index = current_task_index
        sequences: list[int] = []
        for event_id in anchor.event_refs:
            event = event_by_id.get(event_id)
            if event is None:
                raise ProjectionIntegrityError("execution anchor event relation is not retained")
            if (
                _required_string(event, "run_id", "RuntimeEvent") != expected_run_id
                or _required_string(event, "event_id", "RuntimeEvent") != event_id
                or _required_string(event, "task_id", "RuntimeEvent") != anchor.task_id
            ):
                raise ProjectionIntegrityError("execution anchor event closure failed")
            sequences.append(
                _positive_int(_field(event, "sequence"), context="RuntimeEvent.sequence")
            )
        if sequences != sorted(sequences) or len(set(sequences)) != len(sequences):
            raise ProjectionIntegrityError("execution anchor events are not in original order")


def _safe_model_json(
    value: object,
    *,
    allowed_keys: JsonAllowlist,
    context: str,
) -> SafeJsonObject:
    raw = _model_mapping(value)
    try:
        return safe_json_object(
            _public_json_value(raw),
            allowed_keys=allowed_keys,
            context=context,
        )
    except UnsafeProjectionData as exc:
        raise ProjectionIntegrityError(str(exc)) from exc


def _public_json_value(value: object) -> Any:
    if isinstance(value, BaseModel):
        return _public_json_value(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return _public_json_value(value.value)
    if isinstance(value, Decimal):
        return _canonical_decimal(value, context="decimal JSON value")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Mapping):
        return {key: _public_json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | memoryview | str):
        return [_public_json_value(item) for item in value]
    raise ProjectionIntegrityError(f"non-public JSON value: {type(value).__name__}")


def _normalize_run_collection_filters(
    *,
    object_id: str | None,
    statuses: Sequence[object],
    result_availability: AvailabilityStatus | str | None,
) -> _RunCollectionFilterSet:
    normalized_object_id = (
        None if object_id is None else _required_nonblank(object_id, "object_id filter")
    )
    raw_statuses = _sequence(statuses, "Run collection status filters")
    normalized_statuses: set[str] = set()
    for value in raw_statuses:
        status = project_run_status(value).status
        normalized_statuses.add(status)
    ordered_statuses = tuple(sorted(normalized_statuses, key=lambda value: value.encode("utf-8")))

    if result_availability is None:
        availability = None
    else:
        raw_availability = _enum_text(
            result_availability,
            context="result_availability filter",
        )
        try:
            availability = AvailabilityStatus(raw_availability).value
        except ValueError as exc:
            raise ProjectionIntegrityError("unsupported result_availability filter") from exc
    return _RunCollectionFilterSet(
        object_id=normalized_object_id,
        statuses=ordered_statuses,
        result_availability=availability,
    )


def _run_collection_item_matches(
    item: RunCollectionItemV1,
    filters: _RunCollectionFilterSet,
) -> bool:
    return (
        (filters.object_id is None or item.object.object_id == filters.object_id)
        and (not filters.statuses or item.status in filters.statuses)
        and (
            filters.result_availability is None
            or item.result_availability.status.value == filters.result_availability
        )
    )


def _run_collection_source_matches(
    source: RunCollectionSource,
    filters: _RunCollectionFilterSet,
) -> bool:
    """Apply exact query predicates before projecting unrelated source rows."""

    if not isinstance(source, RunCollectionSource):
        raise ProjectionIntegrityError("Run collection source must be an exact record set")
    run_object_id = _required_string(source.run, "research_object_id", "Run")
    if filters.object_id is not None and run_object_id != filters.object_id:
        return False
    raw_status = _enum_text(_field(source.run, "status"), context="Run.status")
    if filters.statuses and raw_status not in filters.statuses:
        return False
    if filters.result_availability is not None:
        if not isinstance(source.result_availability, AvailabilityV1):
            raise ProjectionIntegrityError(
                "result_availability must be an exact AvailabilityV1 projection"
            )
        if source.result_availability.status.value != filters.result_availability:
            return False
    return True


def _run_collection_order_key(item: RunCollectionItemV1) -> tuple[datetime, bytes]:
    return (item.updated_at, item.run_id.encode("utf-8"))


def _run_collection_cursor_key(value: object) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ProjectionIntegrityError(
            "Run collection cursor signing key must contain at least 32 bytes"
        )
    return value


def _canonical_cursor_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProjectionIntegrityError(
            "Run collection cursor payload is not canonical JSON"
        ) from exc


def _encode_run_collection_cursor(
    *,
    item: RunCollectionItemV1,
    signing_key: bytes,
    filters: _RunCollectionFilterSet,
) -> str:
    payload = _canonical_cursor_json(
        {
            "filters": filters.cursor_value(),
            "last": {
                "run_id": item.run_id,
                "updated_at": item.updated_at.isoformat(),
            },
            "version": _RUN_COLLECTION_CURSOR_VERSION,
        }
    )
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    signature = hmac.new(signing_key, payload, hashlib.sha256).hexdigest()
    token = f"{_RUN_COLLECTION_CURSOR_PREFIX}.{encoded}.{signature}"
    if len(token) > _RUN_COLLECTION_CURSOR_MAX_LENGTH:
        raise ProjectionIntegrityError("Run collection cursor exceeds its bounded encoding")
    return token


def _decode_run_collection_cursor(
    cursor: object,
    *,
    signing_key: bytes,
    filters: _RunCollectionFilterSet,
) -> tuple[datetime, bytes]:
    if (
        not isinstance(cursor, str)
        or not cursor
        or len(cursor) > _RUN_COLLECTION_CURSOR_MAX_LENGTH
        or any(ord(character) < 0x21 or ord(character) > 0x7E for character in cursor)
    ):
        _raise_invalid_run_collection_cursor()
    parts = cursor.split(".")
    if (
        len(parts) != 3
        or parts[0] != _RUN_COLLECTION_CURSOR_PREFIX
        or re.fullmatch(r"[A-Za-z0-9_-]+", parts[1]) is None
        or re.fullmatch(r"[0-9a-f]{64}", parts[2]) is None
    ):
        _raise_invalid_run_collection_cursor()

    encoded_payload = parts[1]
    try:
        padding = "=" * (-len(encoded_payload) % 4)
        payload = base64.b64decode(
            encoded_payload + padding,
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError):
        _raise_invalid_run_collection_cursor()
    if base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii") != encoded_payload:
        _raise_invalid_run_collection_cursor()
    expected_signature = hmac.new(signing_key, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(parts[2], expected_signature):
        _raise_invalid_run_collection_cursor()

    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _raise_invalid_run_collection_cursor()
    if _canonical_cursor_json(decoded) != payload:
        _raise_invalid_run_collection_cursor()
    if not isinstance(decoded, dict) or set(decoded) != {"filters", "last", "version"}:
        _raise_invalid_run_collection_cursor()
    if decoded["version"] != _RUN_COLLECTION_CURSOR_VERSION:
        _raise_invalid_run_collection_cursor()
    if decoded["filters"] != filters.cursor_value():
        _raise_invalid_run_collection_cursor()

    last = decoded["last"]
    if not isinstance(last, dict) or set(last) != {"run_id", "updated_at"}:
        _raise_invalid_run_collection_cursor()
    run_id = last["run_id"]
    timestamp = last["updated_at"]
    if not isinstance(run_id, str) or not run_id or not isinstance(timestamp, str):
        _raise_invalid_run_collection_cursor()
    try:
        checked_run_id = safe_text(run_id, context="cursor run_id", max_length=512)
        updated_at = datetime.fromisoformat(timestamp)
        updated_at = _aware_datetime(updated_at, "cursor updated_at")
    except (ProjectionIntegrityError, UnsafeProjectionData, ValueError):
        _raise_invalid_run_collection_cursor()
    if updated_at.isoformat() != timestamp:
        _raise_invalid_run_collection_cursor()
    return (updated_at, checked_run_id.encode("utf-8"))


def _raise_invalid_run_collection_cursor() -> None:
    raise ProductError(
        code=ErrorCodeV1.INVALID_CURSOR,
        message="Run collection cursor is invalid",
    )


def _model_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    if isinstance(value, Mapping):
        return dict(value)
    raise ProjectionIntegrityError(f"expected a retained mapping, got {type(value).__name__}")


def _availability_value(value: AvailabilityV1) -> tuple[str, str | None, bool]:
    return (
        _enum_text(value.status, context="Availability.status"),
        value.reason_code,
        value.retryable,
    )


def _field(record: object, name: str, default: object = _MISSING) -> Any:
    if isinstance(record, Mapping):
        value = record.get(name, default)
    else:
        value = getattr(record, name, default)
    if value is _MISSING and default is _MISSING:
        raise ProjectionIntegrityError(f"retained record is missing required field {name}")
    return value


def _required_string(record: object, name: str, context: str) -> str:
    return _required_nonblank(_field(record, name), f"{context}.{name}")


def _required_nonblank(value: object, context: str) -> str:
    try:
        return safe_text(value, context=context)
    except UnsafeProjectionData as exc:
        raise ProjectionIntegrityError(str(exc)) from exc


def _optional_raw_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_string(value: object, *, context: str) -> str | None:
    if value is None:
        return None
    return _required_nonblank(value, context)


def _enum_text(value: object, *, context: str) -> str:
    if isinstance(value, Enum):
        value = value.value
    return _required_nonblank(value, context)


def _optional_enum_text(value: object, context: str) -> str | None:
    return None if value is None else _enum_text(value, context=context)


def _ratio(value: object, *, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        raise ProjectionIntegrityError(f"{context} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ProjectionIntegrityError(f"{context} must be within 0..1")
    return result


def _nonnegative_number(value: object, *, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        raise ProjectionIntegrityError(f"{context} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ProjectionIntegrityError(f"{context} must be finite and nonnegative")
    return result


def _positive_int(value: object, *, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ProjectionIntegrityError(f"{context} must be a positive integer")
    return value


def _nonnegative_int(value: object, *, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProjectionIntegrityError(f"{context} must be a nonnegative integer")
    return value


def _optional_positive_int(value: object, context: str) -> int | None:
    return None if value is None else _positive_int(value, context=context)


def _optional_bool(value: object, context: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ProjectionIntegrityError(f"{context} must be boolean")
    return value


def _canonical_decimal(value: object, *, context: str) -> str:
    if isinstance(value, bool) or value is None:
        raise ProjectionIntegrityError(f"{context} must be decimal-compatible")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ProjectionIntegrityError(f"{context} must be decimal-compatible") from exc
    if not result.is_finite():
        raise ProjectionIntegrityError(f"{context} must be finite")
    return format(result, "f")


def _sequence(value: object, context: str) -> tuple[Any, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray | memoryview):
        raise ProjectionIntegrityError(f"{context} must be a sequence")
    return tuple(value)


def _string_tuple(value: object, context: str) -> tuple[str, ...]:
    return tuple(
        _required_nonblank(item, f"{context}[{index}]")
        for index, item in enumerate(_sequence(value, context))
    )


def _unique_string_tuple(value: object, context: str) -> tuple[str, ...]:
    result = _string_tuple(value, context)
    if len(set(result)) != len(result):
        raise ProjectionIntegrityError(f"{context} must contain unique identities")
    return result


def _unique_index(
    records: Sequence[object],
    id_field: str,
    *,
    context: str,
    allow_missing: bool = False,
) -> dict[str, object]:
    result: dict[str, object] = {}
    for index, record in enumerate(records):
        value = _field(record, id_field, None if allow_missing else _MISSING)
        if value is None and allow_missing:
            continue
        identity = _required_nonblank(value, f"{context}[{index}].{id_field}")
        if identity in result:
            raise ProjectionIntegrityError(f"duplicate {context} identity: {identity}")
        result[identity] = record
    return result


def _optional_owned_index(
    records: Sequence[object] | None,
    *,
    id_field: str,
    expected_run_id: str,
    context: str,
) -> dict[str, object] | None:
    if records is None:
        return None
    index = _unique_index(records, id_field, context=context)
    for identity, record in index.items():
        if _required_string(record, "run_id", context) != expected_run_id:
            raise ProjectionIntegrityError(f"{context} {identity} belongs to another Run")
    return index


def _validate_review_corrections(
    checks: Sequence[FinancialReviewCheckProjectionV1],
    *,
    correction_index: Mapping[str, object] | None,
    task_index: Mapping[str, object] | None,
) -> None:
    for check in checks:
        correction_ids = tuple(item.correction_id for item in check.correction_refs)
        if len(set(correction_ids)) != len(correction_ids):
            raise ProjectionIntegrityError("Review Check repeats a Correction relation")
        if not correction_ids:
            continue
        if correction_index is None or task_index is None:
            raise ProjectionIntegrityError(
                "Review corrections require exact retained Correction and Task records"
            )
        for reference in check.correction_refs:
            record = _required_index_item(
                correction_index,
                reference.correction_id,
                "CorrectionRecord",
            )
            task_id = _required_string(record, "task_id", "CorrectionRecord")
            if (
                task_id != reference.task_id
                or task_id not in task_index
                or _enum_text(_field(record, "status"), context="CorrectionRecord.status")
                != reference.status
                or _optional_datetime(
                    _field(record, "resolved_at", None),
                    "CorrectionRecord.resolved_at",
                )
                != reference.resolved_at
            ):
                raise ProjectionIntegrityError(
                    "Review correction relation does not match exact Correction/Task state"
                )


def _required_index_item(index: Mapping[str, object], identity: str, context: str) -> object:
    try:
        return index[identity]
    except KeyError as exc:
        raise ProjectionIntegrityError(f"missing exact {context}: {identity}") from exc


def _required_datetime(record: object, name: str, context: str) -> datetime:
    value = _field(record, name)
    if not isinstance(value, datetime):
        raise ProjectionIntegrityError(f"{context}.{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ProjectionIntegrityError(f"{context}.{name} must be an RFC3339 UTC instant")
    return value


def _optional_datetime(value: object, context: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ProjectionIntegrityError(f"{context} must be an RFC3339 UTC instant")
    return value


def _required_date(record: object, name: str, context: str) -> date:
    value = _field(record, name)
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ProjectionIntegrityError(f"{context}.{name} must be a date")
    return value


def _optional_date(value: object, context: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ProjectionIntegrityError(f"{context} must be a date")
    return value


def _aware_datetime(value: object, context: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ProjectionIntegrityError(f"{context} must be an RFC3339 UTC instant")
    return value


def _availability_body(
    availability: AvailabilityV1,
    body: object | None,
    context: str,
) -> None:
    _validate_public_availability(availability, context=context)
    available = _enum_text(availability.status, context=f"{context}.availability") == "AVAILABLE"
    if available != (body is not None):
        raise ProjectionIntegrityError(
            f"{context} availability and retained projection body disagree"
        )


def _validate_release_candidate_source(
    *,
    object_id: str,
    run_id: str,
    review: FinancialReviewProjectionV1,
    result: ReleasedResultProjectionV1,
    execution: ExecutionProjectionV1,
    artifacts: ReportArtifactGroupV1,
    source: ReleaseCandidateSourceV1 | None,
) -> None:
    """Rederive B/L/X from exact retained records instead of trusting DTOs."""

    if source is None:
        raise ProjectionIntegrityError(
            "released candidate lacks its exact retained Review/Result/Proof preimage"
        )
    if (
        _required_string(source.run, "run_id", "Release source Run") != run_id
        or _required_string(
            source.run,
            "research_object_id",
            "Release source Run",
        )
        != object_id
        or _enum_text(_field(source.run, "status"), context="Release source Run.status")
        != "RELEASED"
    ):
        raise ProjectionIntegrityError("release source belongs to another Run/Object")

    authoritative_result = build_released_result_projection(
        expected_object_id=object_id,
        expected_run_id=run_id,
        run=source.run,
        canonical_record=source.canonical_record,
        released_result=source.released_result,
        calculations=source.calculation_records,
        evidence=source.evidence_records,
        proof_policy_decisions=source.proof_policy_decisions,
        proof_records=source.proof_records,
        proof_verifications=source.proof_verifications,
        proof_commitments=source.proof_commitments,
    )
    if authoritative_result != result:
        raise ProjectionIntegrityError(
            "ReleasedResult projection differs from its exact authoritative records"
        )

    authoritative_review = build_financial_review(
        expected_object_id=object_id,
        expected_run_id=run_id,
        projection_revision=review.projection_revision,
        projection_sequence=review.projection_sequence,
        run=source.run,
        review=source.review,
        canonical_record=source.canonical_record,
        released_result=source.released_result,
        tasks=source.tasks,
        proof_records=source.proof_records,
        correction_records=source.correction_records,
        evidence_records=source.evidence_records,
        calculation_records=source.calculation_records,
        metric_records=source.metric_records,
        claim_records=source.claim_records,
        judgment_records=source.judgment_records,
        proof_policy_decisions=source.proof_policy_decisions,
    )
    if authoritative_review != review:
        raise ProjectionIntegrityError(
            "FinancialReview projection differs from its exact authoritative preimage"
        )

    authoritative_execution = build_execution_projection(
        expected_object_id=object_id,
        expected_run_id=run_id,
        projection_revision=execution.projection_revision,
        projection_sequence=execution.projection_sequence,
        canonical_record=source.canonical_record,
        released_result=source.released_result,
    )
    transport_fields = {"events", "next_cursor"}
    if authoritative_execution.model_dump(
        mode="python",
        exclude=transport_fields,
    ) != execution.model_dump(mode="python", exclude=transport_fields):
        raise ProjectionIntegrityError(
            "CanonicalExecution projection differs from its exact authoritative record"
        )

    try:
        authoritative_artifacts = build_report_artifact_group(
            expected_object_id=object_id,
            expected_run_id=run_id,
            run=source.run,
            canonical_record=source.canonical_record,
            released_result=source.released_result,
            anchor_manifest=source.anchor_manifest,
            html=source.html_artifact,
            pdf=source.pdf_artifact,
            availability=source.artifact_availability,
        )
    except ArtifactProjectionError as exc:
        raise ProjectionIntegrityError(
            "ReportArtifactGroup source records fail exact integrity validation"
        ) from exc
    if authoritative_artifacts != artifacts:
        raise ProjectionIntegrityError(
            "ReportArtifactGroup projection differs from its exact authoritative records"
        )

    for slot, source_slot, payload in (
        (
            authoritative_artifacts.representations[0],
            source.html_artifact,
            source.html_payload,
        ),
        (
            authoritative_artifacts.representations[1],
            source.pdf_artifact,
            source.pdf_payload,
        ),
    ):
        if slot.availability.status is not AvailabilityStatus.AVAILABLE:
            continue
        verified = verify_artifact_bytes(
            requested_run_id=run_id,
            requested_artifact_id=slot.artifact_id,
            research_object={"object_id": object_id},
            run=source.run,
            canonical_record=source.canonical_record,
            released_result=source.released_result,
            artifact=source_slot.artifact,
            representation=slot,
            anchor_manifest=source.anchor_manifest,
            payload=payload,
        )
        if not verified.ok:
            raise ProjectionIntegrityError(
                "release artifact bytes fail exact content integrity validation"
            )


def _validate_atomic_release_validation(
    *,
    status: RunStatusProjection,
    object_id: str,
    run_id: str,
    validations: Sequence[object],
    review: FinancialReviewProjectionV1 | None,
    result: ReleasedResultProjectionV1 | None,
    artifacts: ReportArtifactGroupV1 | None,
    proof: ProofSummaryV1,
    execution: ExecutionProjectionV1 | None,
    source: ReleaseCandidateSourceV1 | None = None,
) -> None:
    rows = _sequence(validations, "ReleaseValidation persisted rows")
    _validate_terminal_artifact_slots(status=status, artifacts=artifacts)
    if status.status != "RELEASED":
        decisions = tuple(
            _release_validation_decision(row, object_id=object_id, run_id=run_id) for row in rows
        )
        if "ALLOWED" in decisions:
            raise ProjectionIntegrityError(
                "non-RELEASED atomic projection cannot carry an ALLOWED ReleaseValidation"
            )
        if "BLOCKED" in decisions:
            raise ProjectionIntegrityError(
                "BLOCKED ReleaseValidation preimage is unavailable for integrity verification"
            )
        return
    validation = _one_allowed_release_validation(rows, object_id=object_id, run_id=run_id)
    if validation is None:
        raise ProjectionIntegrityError(
            "RELEASED atomic projection requires exactly one ALLOWED ReleaseValidation"
        )
    if any(item is None for item in (review, result, artifacts, execution)):
        raise ProjectionIntegrityError(
            "RELEASED atomic projection cannot validate an incomplete release closure"
        )
    assert review is not None
    assert result is not None
    assert artifacts is not None
    assert execution is not None
    _validate_release_candidate_source(
        object_id=object_id,
        run_id=run_id,
        review=review,
        result=result,
        execution=execution,
        artifacts=artifacts,
        source=source,
    )
    validation_id = _required_string(validation, "validation_id", "ReleaseValidation")
    if (
        _enum_text(_field(validation, "decision"), context="ReleaseValidation.decision")
        != "ALLOWED"
        or _string_tuple(_field(validation, "reason_codes"), "ReleaseValidation.reason_codes")
        or _required_string(validation, "object_id", "ReleaseValidation") != object_id
        or _required_string(validation, "run_id", "ReleaseValidation") != run_id
        or _required_string(validation, "review_id", "ReleaseValidation") != review.review_id
        or _required_string(validation, "canonical_record_id", "ReleaseValidation")
        != execution.canonical_record_id
        or _required_string(validation, "released_result_id", "ReleaseValidation")
        != result.released_result_id
        or _required_string(validation, "release_policy_version", "ReleaseValidation")
        != _RELEASE_POLICY_VERSION
        or _required_string(validation, "review_policy_version", "ReleaseValidation")
        != _REVIEW_POLICY_VERSION
        or _required_string(validation, "material_output_policy_version", "ReleaseValidation")
        != _MATERIAL_OUTPUT_POLICY_VERSION
        or _required_string(validation, "artifact_policy_version", "ReleaseValidation")
        != _ARTIFACT_POLICY_VERSION
        or _required_string(validation, "review_input_snapshot_hash", "ReleaseValidation")
        != review.input_snapshot_hash
        or _required_datetime(validation, "released_at", "ReleaseValidation") != result.released_at
    ):
        raise ProjectionIntegrityError(
            "ReleaseValidation does not bind the atomic release projection"
        )
    policy_ids = {item.proof.policy_id for item in result.metrics}
    if policy_ids != {_required_string(validation, "proof_policy_id", "ReleaseValidation")}:
        raise ProjectionIntegrityError("ReleaseValidation Proof policy does not bind metrics")
    _validate_release_material_projection(
        run_id=run_id,
        review=review,
        result=result,
        execution=execution,
        proof=proof,
    )
    expected_hashes = _compute_release_validation_hashes(
        review=review,
        result=result,
        execution=execution,
        artifacts=artifacts,
        proof=proof,
        validation_id=validation_id,
    )
    for field_name in (
        "proof_policy_hash",
        "material_output_manifest_hash",
        "artifact_manifest_hash",
        "closure_hash",
    ):
        if _required_string(validation, field_name, "ReleaseValidation") != getattr(
            expected_hashes, field_name
        ):
            raise ProjectionIntegrityError(
                f"ReleaseValidation.{field_name} does not bind its canonical preimage"
            )
    evaluated_at = _required_datetime(validation, "evaluated_at", "ReleaseValidation")
    if evaluated_at > result.released_at:
        raise ProjectionIntegrityError("ReleaseValidation cannot be evaluated after release")


def _validate_released_object_candidate(
    candidate: EligibleReleasedObjectCandidate,
    *,
    object_id: str,
) -> str:
    run_id = candidate.run.run_id
    canonical_id = candidate.execution.canonical_record_id
    result_id = candidate.result.released_result_id
    if (
        candidate.run.object.object_id != object_id
        or candidate.run.status != "RELEASED"
        or not candidate.run.terminal
        or candidate.run.result_availability.status is not AvailabilityStatus.AVAILABLE
        or candidate.result.object_id != object_id
        or candidate.result.run_id != run_id
        or candidate.result.canonical_record_id != canonical_id
        or candidate.review.object_id != object_id
        or candidate.review.run_id != run_id
        or candidate.review.status != "PASS"
        or candidate.review.review_id is None
        or candidate.review.canonical_record_id != canonical_id
        or candidate.review.released_result_id != result_id
        or candidate.execution.object_id != object_id
        or candidate.execution.run_id != run_id
        or candidate.execution.released_result_id != result_id
        or candidate.execution.object_snapshot_ref != object_id
        or candidate.execution.runtime_outcome != "RELEASED"
        or candidate.review.projection_revision != candidate.run.projection_revision
        or candidate.review.projection_sequence != candidate.run.projection_sequence
        or candidate.execution.projection_revision != candidate.run.projection_revision
        or candidate.execution.projection_sequence != candidate.run.projection_sequence
        or candidate.artifacts.object_id != object_id
        or candidate.artifacts.run_id != run_id
        or candidate.artifacts.canonical_record_id != canonical_id
        or candidate.artifacts.released_result_id != result_id
        or candidate.artifacts.report_id != result_id
        or _enum_text(
            candidate.artifacts.representations[0].availability.status,
            context="HTML availability",
        )
        != "AVAILABLE"
    ):
        raise ProjectionIntegrityError("Released Object candidate identity/gate closure failed")
    if candidate.source is None:
        raise ProjectionIntegrityError(
            "released candidate lacks its exact retained Review/Result/Proof preimage"
        )
    if (
        _required_date(candidate.source.run, "as_of", "Release source Run") != candidate.run.as_of
        or _required_datetime(candidate.source.run, "created_at", "Release source Run")
        != candidate.run.created_at
        or _optional_datetime(
            _field(candidate.source.run, "started_at", None),
            "Release source Run.started_at",
        )
        != candidate.run.started_at
        or _optional_datetime(
            _field(candidate.source.run, "completed_at", None),
            "Release source Run.completed_at",
        )
        != candidate.run.completed_at
    ):
        raise ProjectionIntegrityError(
            "Released Object candidate differs from its exact authoritative Run"
        )
    _validate_release_candidate_source(
        object_id=object_id,
        run_id=run_id,
        review=candidate.review,
        result=candidate.result,
        execution=candidate.execution,
        artifacts=candidate.artifacts,
        source=candidate.source,
    )
    _release_projection_closes(
        status=project_run_status(candidate.run.status),
        review=candidate.review,
        result=candidate.result,
        artifacts=candidate.artifacts,
        proof=candidate.proof,
        execution=candidate.execution,
    )
    _validate_release_material_closure(candidate)

    validations = _sequence(candidate.validation, "ReleaseValidation persisted rows")
    validation = _one_allowed_release_validation(
        validations,
        object_id=object_id,
        run_id=run_id,
    )
    if validation is None:
        raise ProjectionIntegrityError(
            "RELEASED candidate requires exactly one ALLOWED ReleaseValidation"
        )
    validation_id = _required_string(validation, "validation_id", "ReleaseValidation")
    if (
        _required_string(validation, "run_id", "ReleaseValidation") != run_id
        or _required_string(validation, "object_id", "ReleaseValidation") != object_id
        or _enum_text(_field(validation, "decision"), context="ReleaseValidation.decision")
        != "ALLOWED"
        or _required_string(validation, "review_id", "ReleaseValidation")
        != candidate.review.review_id
        or _required_string(validation, "canonical_record_id", "ReleaseValidation") != canonical_id
        or _required_string(validation, "released_result_id", "ReleaseValidation") != result_id
        or _required_string(validation, "release_policy_version", "ReleaseValidation")
        != _RELEASE_POLICY_VERSION
        or _required_string(validation, "review_policy_version", "ReleaseValidation")
        != _REVIEW_POLICY_VERSION
        or _required_string(validation, "material_output_policy_version", "ReleaseValidation")
        != _MATERIAL_OUTPUT_POLICY_VERSION
        or _required_string(validation, "artifact_policy_version", "ReleaseValidation")
        != _ARTIFACT_POLICY_VERSION
        or _required_string(validation, "review_input_snapshot_hash", "ReleaseValidation")
        != candidate.review.input_snapshot_hash
        or _required_datetime(validation, "released_at", "ReleaseValidation")
        != candidate.result.released_at
    ):
        raise ProjectionIntegrityError("ReleaseValidation does not bind the selected release")
    if _string_tuple(_field(validation, "reason_codes"), "ReleaseValidation.reason_codes"):
        raise ProjectionIntegrityError("ALLOWED ReleaseValidation cannot carry blocking reasons")
    metric_policy_ids = {item.proof.policy_id for item in candidate.result.metrics}
    if metric_policy_ids != {_required_string(validation, "proof_policy_id", "ReleaseValidation")}:
        raise ProjectionIntegrityError("ReleaseValidation proof policy does not match metrics")
    hashes = compute_release_validation_hashes(candidate, validation_id=validation_id)
    for field_name in (
        "proof_policy_hash",
        "material_output_manifest_hash",
        "artifact_manifest_hash",
        "closure_hash",
    ):
        persisted = _required_string(validation, field_name, "ReleaseValidation")
        try:
            require_sha256_identity(persisted, field_name=f"ReleaseValidation.{field_name}")
        except ValueError as exc:
            raise ProjectionIntegrityError(str(exc)) from exc
        if persisted != getattr(hashes, field_name):
            raise ProjectionIntegrityError(
                f"ReleaseValidation.{field_name} does not bind its canonical preimage"
            )
    evaluated_at = _required_datetime(validation, "evaluated_at", "ReleaseValidation")
    if evaluated_at > candidate.result.released_at:
        raise ProjectionIntegrityError("ReleaseValidation cannot be evaluated after release")
    return validation_id


def _release_validation_decision(
    validation: object,
    *,
    object_id: str,
    run_id: str,
) -> str:
    """Validate row identity and the frozen ALLOWED/BLOCKED lifecycle."""

    _required_string(validation, "validation_id", "ReleaseValidation")
    if (
        _required_string(validation, "run_id", "ReleaseValidation") != run_id
        or _required_string(validation, "object_id", "ReleaseValidation") != object_id
    ):
        raise ProjectionIntegrityError("ReleaseValidation belongs to another Run/Object")
    decision = _enum_text(_field(validation, "decision"), context="ReleaseValidation.decision")
    if decision not in {"ALLOWED", "BLOCKED"}:
        raise ProjectionIntegrityError("unknown ReleaseValidation decision")
    reasons = _string_tuple(_field(validation, "reason_codes"), "ReleaseValidation.reason_codes")
    if any(_SAFE_REASON_CODE.fullmatch(reason) is None for reason in reasons):
        raise ProjectionIntegrityError("ReleaseValidation reason is not a stable code")
    for field_name in (
        "review_id",
        "canonical_record_id",
        "released_result_id",
        "proof_policy_id",
    ):
        _required_string(validation, field_name, "ReleaseValidation")
    policy_versions = {
        "release_policy_version": _RELEASE_POLICY_VERSION,
        "review_policy_version": _REVIEW_POLICY_VERSION,
        "material_output_policy_version": _MATERIAL_OUTPUT_POLICY_VERSION,
        "artifact_policy_version": _ARTIFACT_POLICY_VERSION,
    }
    for field_name, expected in policy_versions.items():
        if _required_string(validation, field_name, "ReleaseValidation") != expected:
            raise ProjectionIntegrityError("ReleaseValidation uses an unsupported policy family")
    for field_name in (
        "proof_policy_hash",
        "material_output_manifest_hash",
        "artifact_manifest_hash",
        "review_input_snapshot_hash",
        "closure_hash",
    ):
        value = _required_string(validation, field_name, "ReleaseValidation")
        try:
            require_sha256_identity(value, field_name=f"ReleaseValidation.{field_name}")
        except ValueError as exc:
            raise ProjectionIntegrityError(str(exc)) from exc
    _required_datetime(validation, "evaluated_at", "ReleaseValidation")
    released_at = _field(validation, "released_at", None)
    if decision == "ALLOWED":
        if reasons or released_at is None:
            raise ProjectionIntegrityError(
                "ALLOWED ReleaseValidation requires released_at and no blocking reasons"
            )
    elif not reasons or released_at is not None:
        raise ProjectionIntegrityError(
            "BLOCKED ReleaseValidation requires reasons and no released_at"
        )
    return decision


def _one_allowed_release_validation(
    rows: Sequence[object],
    *,
    object_id: str,
    run_id: str,
) -> object | None:
    validation_ids: set[str] = set()
    allowed: list[object] = []
    for row in rows:
        validation_id = _required_string(row, "validation_id", "ReleaseValidation")
        if validation_id in validation_ids:
            raise ProjectionIntegrityError("duplicate ReleaseValidation identity")
        validation_ids.add(validation_id)
        decision = _release_validation_decision(row, object_id=object_id, run_id=run_id)
        if decision == "BLOCKED":
            # A BLOCKED row was evaluated against an earlier release candidate.
            # The current candidate cannot reproduce that historical preimage,
            # so accepting its hashes by shape alone would create false
            # integrity authority.  Parent persistence must supply the frozen
            # decision-aware preimage before mixed history can be consumed
            # safely.
            raise ProjectionIntegrityError(
                "BLOCKED ReleaseValidation preimage is unavailable for integrity verification"
            )
        if decision == "ALLOWED":
            allowed.append(row)
    return allowed[0] if len(allowed) == 1 else None


def compute_release_validation_hashes(
    candidate: EligibleReleasedObjectCandidate,
    *,
    validation_id: str,
) -> ReleaseValidationHashes:
    """Recompute the four validation hashes from explicit versioned preimages.

    This gives both the release writer and read-side selector one deterministic
    implementation-local algorithm.  The Parent migration must persist the
    returned values atomically with the exact rows represented by ``candidate``.
    """

    return _compute_release_validation_hashes(
        review=candidate.review,
        result=candidate.result,
        execution=candidate.execution,
        artifacts=candidate.artifacts,
        proof=candidate.proof,
        validation_id=validation_id,
    )


def _compute_release_validation_hashes(
    *,
    review: FinancialReviewProjectionV1,
    result: ReleasedResultProjectionV1,
    execution: ExecutionProjectionV1,
    artifacts: ReportArtifactGroupV1,
    proof: ProofSummaryV1,
    validation_id: str,
) -> ReleaseValidationHashes:
    validation_id = _required_nonblank(validation_id, "ReleaseValidation.validation_id")
    metric_policy_ids = {item.proof.policy_id for item in result.metrics}
    if len(metric_policy_ids) != 1:
        raise ProjectionIntegrityError("material metrics require one exact Proof policy")
    proof_policy_id = next(iter(metric_policy_ids))
    proof_policy_hash = canonical_json_sha256(
        {
            "preimage_version": _PROOF_POLICY_PREIMAGE_VERSION,
            "proof_policy_id": proof_policy_id,
            "proof_summary": proof.model_dump(mode="json"),
            "metric_proof_bindings": [
                {
                    "metric_id": metric.metric_id,
                    "calculation_id": metric.calculation_id,
                    "formula_id": metric.formula_id,
                    "proof": metric.proof.model_dump(mode="json"),
                }
                for metric in result.metrics
            ],
        }
    )
    material_output_manifest_hash = canonical_json_sha256(
        {
            "preimage_version": _MATERIAL_OUTPUT_PREIMAGE_VERSION,
            "material_output_policy_version": _MATERIAL_OUTPUT_POLICY_VERSION,
            "released_result": result.model_dump(mode="json"),
        }
    )
    artifact_manifest_hash = canonical_json_sha256(
        {
            "preimage_version": _ARTIFACT_PREIMAGE_VERSION,
            "artifact_policy_version": _ARTIFACT_POLICY_VERSION,
            "report_artifacts": artifacts.model_dump(mode="json"),
        }
    )
    closure_hash = canonical_json_sha256(
        {
            "preimage_version": _RELEASE_CLOSURE_PREIMAGE_VERSION,
            "validation_id": validation_id,
            "release_policy_version": _RELEASE_POLICY_VERSION,
            "review_policy_version": _REVIEW_POLICY_VERSION,
            "proof_policy_id": proof_policy_id,
            "proof_policy_hash": proof_policy_hash,
            "material_output_policy_version": _MATERIAL_OUTPUT_POLICY_VERSION,
            "material_output_manifest_hash": material_output_manifest_hash,
            "artifact_policy_version": _ARTIFACT_POLICY_VERSION,
            "artifact_manifest_hash": artifact_manifest_hash,
            "release_identity": {
                "object_id": result.object_id,
                "run_id": result.run_id,
                "review_id": review.review_id,
                "canonical_record_id": execution.canonical_record_id,
                "released_result_id": result.released_result_id,
                "released_at": result.released_at.isoformat().replace("+00:00", "Z"),
                "run_status": "RELEASED",
            },
            "review": review.model_dump(mode="json"),
            "execution": {
                "preimage_version": _CANONICAL_EXECUTION_PREIMAGE_VERSION,
                **execution.model_dump(
                    mode="json",
                    exclude={"events", "next_cursor"},
                ),
            },
        }
    )
    return ReleaseValidationHashes(
        proof_policy_hash=proof_policy_hash,
        material_output_manifest_hash=material_output_manifest_hash,
        artifact_manifest_hash=artifact_manifest_hash,
        closure_hash=closure_hash,
    )


def _validate_release_material_closure(candidate: EligibleReleasedObjectCandidate) -> None:
    """Validate the frozen FULL material set and its reciprocal references."""

    _validate_release_material_projection(
        run_id=candidate.run.run_id,
        review=candidate.review,
        result=candidate.result,
        execution=candidate.execution,
        proof=candidate.proof,
    )


def _validate_release_material_projection(
    *,
    run_id: str,
    review: FinancialReviewProjectionV1,
    result: ReleasedResultProjectionV1,
    execution: ExecutionProjectionV1,
    proof: ProofSummaryV1,
) -> None:
    """Validate the frozen FULL material set without relying on a list-row wrapper."""

    metrics = result.metrics
    claims = result.claims
    for availability, context in (
        (review.availability, "FinancialReview"),
        (result.availability, "ReleasedResult"),
        (execution.availability, "CanonicalExecution"),
        (proof.availability, "ProofSummary"),
    ):
        _validate_public_availability(availability, context=context)
        if availability.status is not AvailabilityStatus.AVAILABLE:
            raise ProjectionIntegrityError(f"released candidate requires AVAILABLE {context}")
    if review.status != "PASS" or _aggregate_review_status(review.checks) != "PASS":
        raise ProjectionIntegrityError("release Review contains an unresolved REVIEW/BLOCK Check")
    review_subject_refs: dict[str, set[str]] = {
        "RUN": {run_id},
        "TASK": set(execution.task_refs),
        "EVIDENCE": set(review.reviewed_evidence_refs),
        "CALCULATION": set(review.reviewed_calculation_refs),
        "METRIC": {item.metric_id for item in metrics},
        "CLAIM": {item.claim_id for item in claims},
        "JUDGMENT": set(review.reviewed_judgment_refs),
        "PROOF": set(proof.proof_refs),
        "CANONICAL_RECORD": {execution.canonical_record_id},
        "RELEASED_RESULT": {result.released_result_id},
    }
    for check in review.checks:
        for subject in check.subjects:
            if (
                subject.run_id != run_id
                or subject.subject_id not in review_subject_refs[subject.subject_type]
            ):
                raise ProjectionIntegrityError(
                    "release Review Check subject lacks exact same-Run membership"
                )
        if any(
            correction.run_id != run_id or correction.task_id not in review_subject_refs["TASK"]
            for correction in check.correction_refs
        ):
            raise ProjectionIntegrityError(
                "release Review correction lacks exact same-Run Task membership"
            )
    if len(metrics) != len(MATERIAL_FORMULAS) or {item.formula_id for item in metrics} != set(
        MATERIAL_FORMULAS
    ):
        raise ProjectionIntegrityError("released candidate does not contain the exact FULL set")
    metric_by_id = {item.metric_id: item for item in metrics}
    claim_by_metric = {item.metric_id: item for item in claims}
    if len(metric_by_id) != len(metrics) or len(claim_by_metric) != len(claims):
        raise ProjectionIntegrityError("released candidate repeats a material Metric or Claim")
    if len({item.calculation_id for item in metrics}) != len(metrics):
        raise ProjectionIntegrityError(
            "released candidate must bind one unique Calculation per material Metric"
        )
    if len({item.claim_id for item in claims}) != len(claims):
        raise ProjectionIntegrityError("released candidate repeats a material Claim identity")
    if set(metric_by_id) != set(claim_by_metric):
        raise ProjectionIntegrityError("released candidate Metric/Claim closure is incomplete")
    for metric_id, metric in metric_by_id.items():
        claim = claim_by_metric[metric_id]
        if (
            metric.run_id != run_id
            or metric.claim_refs != (claim.claim_id,)
            or claim.run_id != run_id
            or claim.value != metric.canonical_value
            or claim.unit != metric.canonical_unit
            or claim.period != metric.period
            or claim.period_basis != metric.period_basis
            or claim.actuality != metric.actuality
            or claim.as_of != metric.as_of
            or claim.currency != metric.currency
            or claim.calculation_refs != (metric.calculation_id,)
            or claim.evidence_refs != metric.evidence_refs
        ):
            raise ProjectionIntegrityError("released candidate Metric/Claim semantics disagree")

    calculation_ids = {item.calculation_id for item in metrics}
    metric_ids = set(metric_by_id)
    claim_ids = {item.claim_id for item in claims}
    material_evidence_ids = {evidence_id for item in metrics for evidence_id in item.evidence_refs}
    dispositions = tuple(
        _project_disposition(item) for item in result.material_calculation_dispositions
    )
    if any(
        set(_model_mapping(item)) != {"calculation_id", "metric_id", "status", "reason"}
        for item in result.material_calculation_dispositions
    ):
        raise ProjectionIntegrityError("released candidate disposition schema is not exact")
    if len(dispositions) != len(calculation_ids) or len(
        {item["calculation_id"] for item in dispositions}
    ) != len(dispositions):
        raise ProjectionIntegrityError("released candidate repeats a material disposition")
    metric_by_calculation = {item.calculation_id: item.metric_id for item in metrics}
    disposition_calculations = {item["calculation_id"] for item in dispositions}
    if disposition_calculations != calculation_ids:
        raise ProjectionIntegrityError("released candidate disposition closure is incomplete")
    if any(
        item["status"] != "REPORTABLE"
        or item["metric_id"] != metric_by_calculation[item["calculation_id"]]
        or item["reason"] is not None
        for item in dispositions
    ):
        raise ProjectionIntegrityError("released material disposition is not REPORTABLE")
    if not calculation_ids.issubset(set(review.reviewed_calculation_refs)):
        raise ProjectionIntegrityError("release Review omits a material Calculation")
    if not material_evidence_ids.issubset(set(review.reviewed_evidence_refs)):
        raise ProjectionIntegrityError("release Review omits material Evidence")
    if metric_ids != set(review.reviewed_metric_refs):
        raise ProjectionIntegrityError("release Review Metric refs are not exact")
    if claim_ids != set(review.reviewed_claim_refs):
        raise ProjectionIntegrityError("release Review Claim refs are not exact")
    must_prove = {item.calculation_id for item in metrics if item.proof.requirement == "MUST_PROVE"}
    for metric in metrics:
        metric_proof = metric.proof
        if metric_proof.requirement == "MUST_PROVE":
            if metric_proof.status != "VERIFIED" or len(metric_proof.proof_refs) != 1:
                raise ProjectionIntegrityError(
                    "release requires exact VERIFIED Proof closure for every MUST_PROVE Metric"
                )
        elif metric_proof.status != "NOT_REQUIRED" or metric_proof.proof_refs:
            raise ProjectionIntegrityError(
                "NOT_REQUIRED release Metric cannot carry Proof state or references"
            )
    if must_prove != set(review.required_proof_calculation_refs):
        raise ProjectionIntegrityError("release Review required-Proof refs are not exact")
    if metric_ids != set(execution.metric_refs):
        raise ProjectionIntegrityError("release Execution Metric refs are not exact")
    if claim_ids != set(execution.claim_refs):
        raise ProjectionIntegrityError("release Execution Claim refs are not exact")
    if not calculation_ids.issubset(set(execution.calculation_refs)):
        raise ProjectionIntegrityError("release Execution omits a material Calculation")
    metric_proof_refs = {proof_id for item in metrics for proof_id in item.proof.proof_refs}
    all_metric_proof_refs = tuple(
        proof_id for item in metrics for proof_id in item.proof.proof_refs
    )
    if len(metric_proof_refs) != len(all_metric_proof_refs):
        raise ProjectionIntegrityError("release reuses one Proof across material Metrics")
    if len(proof.proof_refs) != len(set(proof.proof_refs)):
        raise ProjectionIntegrityError("release Proof summary repeats a Proof identity")
    if metric_proof_refs != set(proof.proof_refs):
        raise ProjectionIntegrityError("release Proof summary refs are not exact")
    expected_proof_policy = (
        "NOT_REQUIRED"
        if not must_prove
        else "MUST_PROVE"
        if len(must_prove) == len(metrics)
        else "MIXED"
    )
    expected_proof_status = "NOT_REQUIRED" if not must_prove else "VERIFIED"
    if proof.policy != expected_proof_policy or proof.status != expected_proof_status:
        raise ProjectionIntegrityError(
            "release Proof summary does not match the exact material Proof requirements"
        )


def _release_projection_closes(
    *,
    status: RunStatusProjection,
    review: FinancialReviewProjectionV1 | None,
    result: ReleasedResultProjectionV1 | None,
    artifacts: ReportArtifactGroupV1 | None,
    proof: ProofSummaryV1,
    execution: ExecutionProjectionV1 | None,
) -> bool:
    _validate_public_availability(proof.availability, context="ProofSummary")
    for body, context in (
        (review, "FinancialReview"),
        (result, "ReleasedResult"),
        (execution, "CanonicalExecution"),
    ):
        if body is not None:
            _validate_public_availability(body.availability, context=context)
    if artifacts is not None:
        _validate_public_availability(artifacts.availability, context="ReportArtifactGroup")
        for slot in artifacts.representations:
            _validate_public_availability(
                slot.availability,
                context=f"ReportArtifactGroup.{slot.format}",
            )
    _validate_terminal_artifact_slots(status=status, artifacts=artifacts)
    proof_policy = _enum_text(proof.policy, context="ProofSummary.policy")
    proof_status = proof.status
    proof_satisfied = (proof_policy == "NOT_REQUIRED" and proof_status == "NOT_REQUIRED") or (
        proof_policy in {"MUST_PROVE", "MIXED"} and proof_status == "VERIFIED"
    )
    bodies_close = (
        review is not None
        and review.status == "PASS"
        and result is not None
        and artifacts is not None
        and execution is not None
        and proof_satisfied
        and review.availability.status is AvailabilityStatus.AVAILABLE
        and result.availability.status is AvailabilityStatus.AVAILABLE
        and execution.availability.status is AvailabilityStatus.AVAILABLE
        and _enum_text(artifacts.availability.status, context="artifact availability")
        == "AVAILABLE"
        and _enum_text(proof.availability.status, context="proof availability") == "AVAILABLE"
        and artifacts.representations[0].format == "HTML"
        and _enum_text(
            artifacts.representations[0].availability.status,
            context="HTML availability",
        )
        == "AVAILABLE"
        and result.canonical_record_id == execution.canonical_record_id
        and artifacts.canonical_record_id == execution.canonical_record_id
        and artifacts.released_result_id == result.released_result_id
    )
    if status.status == "RELEASED" and not bodies_close:
        raise ProjectionIntegrityError("RELEASED Run lacks complete Review/Proof/X/L/HTML closure")
    return bool(bodies_close)


def _validate_terminal_artifact_slots(
    *,
    status: RunStatusProjection,
    artifacts: ReportArtifactGroupV1 | None,
) -> None:
    if (
        status.terminal
        and artifacts is not None
        and any(
            slot.availability.status is AvailabilityStatus.PENDING
            for slot in artifacts.representations
        )
    ):
        raise ProjectionIntegrityError("terminal Run artifact slot cannot remain PENDING")


def _validate_public_availability(
    availability: AvailabilityV1,
    *,
    context: str,
) -> None:
    if availability.status is AvailabilityStatus.AVAILABLE:
        return
    try:
        reason = safe_text(
            availability.reason_code,
            context=f"{context}.availability.reason_code",
            max_length=128,
        )
    except UnsafeProjectionData as exc:
        raise ProjectionIntegrityError(str(exc)) from exc
    if _SAFE_REASON_CODE.fullmatch(reason) is None:
        raise ProjectionIntegrityError(
            f"{context}.availability.reason_code must be a stable uppercase code"
        )


def _project_safe_failure(value: Mapping[str, object]) -> SafeJsonObject:
    try:
        copied = safe_json_object(
            value,
            allowed_keys=_SAFE_FAILURE_ALLOWLIST,
            context="TerminalFailure",
        )
    except UnsafeProjectionData as exc:
        raise ProjectionIntegrityError(str(exc)) from exc
    required = {"status", "failure_stage", "failure_code"}
    missing = required - set(copied)
    if missing:
        raise ProjectionIntegrityError(
            f"TerminalFailure is missing required fields: {sorted(missing)}"
        )
    status = _enum_text(copied["status"], context="TerminalFailure.status")
    failure_stage = _enum_text(copied["failure_stage"], context="TerminalFailure.failure_stage")
    failure_code = _required_nonblank(copied["failure_code"], "TerminalFailure.failure_code")
    if status not in {"FAILED", "CANCELLED"}:
        raise ProjectionIntegrityError("TerminalFailure.status must be FAILED or CANCELLED")
    if status == "CANCELLED":
        if failure_stage != "CANCELLATION" or failure_code != "RUN_CANCELLED":
            raise ProjectionIntegrityError("CANCELLED TerminalFailure tuple is invalid")
    elif (
        failure_stage not in _SAFE_FAILURE_CODES_BY_STAGE
        or failure_code not in _SAFE_FAILURE_CODES_BY_STAGE[failure_stage]
    ):
        raise ProjectionIntegrityError("FAILED TerminalFailure tuple is invalid")
    safe_message = copied.get("safe_message")
    if safe_message is not None:
        try:
            safe_message = safe_text(
                safe_message,
                context="TerminalFailure.safe_message",
                max_length=4096,
            )
        except UnsafeProjectionData as exc:
            raise ProjectionIntegrityError(str(exc)) from exc
    return {
        "status": status,
        "failure_stage": failure_stage,
        "failure_code": failure_code,
        "safe_message": safe_message,
    }


def _terminal_state(
    *,
    status: RunStatusProjection,
    terminal_event: object | None,
    activity: Sequence[SafeRuntimeActivityV1],
    projection_sequence: int,
    safe_failure: SafeJsonObject | None,
) -> TerminalStateV1:
    if not status.terminal:
        if terminal_event is not None or safe_failure is not None:
            raise ProjectionIntegrityError("nonterminal Run carries terminal facts")
        return TerminalStateV1(
            is_terminal=False,
            outcome=None,
            event_id=None,
            sequence=None,
        )
    if terminal_event is None:
        raise ProjectionIntegrityError("terminal Run requires one exact terminal event")
    event_id = _required_string(terminal_event, "event_id", "terminal RuntimeEvent")
    event_type = _enum_text(_field(terminal_event, "type"), context="terminal event type")
    event_sequence = _positive_int(
        _field(terminal_event, "sequence"), context="terminal event sequence"
    )
    if (
        event_sequence != projection_sequence
        or not activity
        or activity[-1].event_id != event_id
        or activity[-1].sequence != event_sequence
    ):
        raise ProjectionIntegrityError("terminal event is not the final projection event")
    payload = _model_mapping(_field(terminal_event, "payload"))
    payload_status = _optional_raw_string(payload.get("status"))
    if status.status == "RELEASED":
        if (
            event_type != "run.completed"
            or payload_status != "RELEASED"
            or safe_failure is not None
        ):
            raise ProjectionIntegrityError("RELEASED terminal event closure failed")
    else:
        if event_type != "run.failed" or payload_status != status.status or safe_failure is None:
            raise ProjectionIntegrityError("unsuccessful terminal event closure failed")
        expected_safe_failure = {
            "status": payload_status,
            "failure_stage": payload.get("failure_stage"),
            "failure_code": payload.get("failure_code"),
            "safe_message": payload.get("safe_message"),
        }
        if safe_failure != expected_safe_failure:
            raise ProjectionIntegrityError("TerminalFailure and run.failed payload disagree")
    return TerminalStateV1(
        is_terminal=True,
        outcome=status.terminal_outcome,
        event_id=event_id,
        sequence=event_sequence,
    )


DEFAULT_REVIEW_JSON_ALLOWLIST = _REVIEW_JSON_KEYS
DEFAULT_CALCULATION_INPUT_ALLOWLIST = _CALCULATION_INPUT_KEYS
DEFAULT_CALCULATION_PARAMETER_ALLOWLIST = _CALCULATION_PARAMETER_KEYS

__all__ = [
    "DEFAULT_CALCULATION_INPUT_ALLOWLIST",
    "DEFAULT_CALCULATION_PARAMETER_ALLOWLIST",
    "DEFAULT_REVIEW_JSON_ALLOWLIST",
    "EligibleReleasedObjectCandidate",
    "MetricProofJoin",
    "ProjectionIntegrityError",
    "ReleaseValidationHashes",
    "RunCollectionSource",
    "RunStatusProjection",
    "TaskStatusProjection",
    "build_atomic_run_projection",
    "build_claim_detail",
    "build_execution_projection",
    "build_financial_review",
    "build_run_collection",
    "build_released_metric",
    "build_released_object_core",
    "build_released_result_projection",
    "build_trace_bundle",
    "calculate_run_progress",
    "compute_release_validation_hashes",
    "join_metric_proof",
    "project_event",
    "project_goal",
    "project_graph",
    "project_object",
    "project_path_change",
    "project_run_detail",
    "project_run_collection_item",
    "project_run_status",
    "project_scheme",
    "project_task",
    "project_task_status",
]
