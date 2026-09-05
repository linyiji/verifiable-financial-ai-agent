"""Run the authoritative credentialed NVDA Phase 3 acceptance chain."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import quote_from_bytes
from uuid import uuid4

import httpx
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url

from scripts.run_phase2_1_acceptance import _evaluate as evaluate_phase2_1
from src.adapters.finrobot import FINROBOT_PINNED_COMMIT, PinnedFinRobotAdapter
from src.adapters.finrobot.charts import (
    CanonicalReportChartAdapter,
    DeterministicSVGChartBackend,
)
from src.adapters.finrobot.professional_reporting import (
    UPSTREAM_ATTRIBUTION,
    CanonicalReportMapper,
    ControlledArtifactStore,
    ProfessionalReportPublisher,
)
from src.adapters.finrobot.technical import moving_average_convergence_divergence
from src.adapters.fmp import (
    FinancialProviderMode,
    FMPProvider,
    HttpxFMPTransport,
    select_financial_provider,
)
from src.adapters.fmp.models import FMPEndpoint, FMPResponseEnvelope
from src.adapters.llm import (
    LLMProvider,
    LockedPlannerProvider,
    MimoClient,
    PlannerProviderHealth,
    PlannerWorkload,
    TeamoRouterClient,
    WorkloadProviderRouter,
    WorkloadProviderUnavailableError,
)
from src.adapters.risc0 import (
    EXPECTED_REVENUE_GROWTH_HOST_SHA256,
    EXPECTED_REVENUE_GROWTH_IMAGE_ID,
    CanonicalRevenueInputs,
    RiscZeroProofAdapter,
    build_proof_input,
    load_proof_input,
    write_proof_input,
)
from src.adapters.risc0.models import input_commitment
from src.adapters.risc0.release_manifest import (
    RELEASE_MANIFEST_RELATIVE_PATH,
    load_and_verify_release_manifest,
    release_manifest_sha256,
)
from src.agentic.llm_integration import (
    PlannerProviderResearchLeadPlanner,
    PlannerProviderSchemeGenerator,
)
from src.agentic.scheme import DeterministicSchemeGenerator
from src.application.evidence_collection import LiveFMPEvidenceCollector
from src.application.phase3_financial import (
    FCF_MARGIN_CAPABILITY_ID,
    FreeCashFlowMarginValidationPlanProvider,
    Phase3FinancialCapabilityExtension,
    Phase3ResearchLeadCapabilityAuthority,
    free_cash_flow_margin_requirement,
)
from src.application.phase3_proof import RevenueGrowthRiscZeroProofWorkflow
from src.application.service import ResearchApplicationService
from src.assurance import IndependentFinancialReviewer, ReleaseGate
from src.capabilities.financial.common import NonPositivePriorRevenueError
from src.capabilities.financial.growth import (
    calculate_revenue_growth as calculate_native_revenue_growth,
)
from src.capabilities.generated import (
    CapabilityBuildRequest,
    GeneratedCapabilityArtifactStore,
    GeneratedCapabilityOrchestrator,
    GeneratedCapabilityTrace,
    GeneratedCapabilityValidator,
    PlannerProviderCodeBuilder,
    ResearchLeadCapabilityApproval,
    ScopedCapabilityRegistry,
)
from src.capabilities.generated.contract import GeneratedCapabilityRequestV1
from src.capabilities.generated.spec import (
    GENERATED_CAPABILITY_COMPILER_ID,
    GENERATED_CAPABILITY_COMPILER_VERSION,
)
from src.domain.capability import (
    CapabilityBuildRecord,
    CapabilityGapRecord,
    CapabilityValidationRecord,
    GeneratedCapabilityArtifactRecord,
    GeneratedCapabilityRecord,
    SandboxExecutionRecord,
    ScopedCapabilityRegistration,
)
from src.domain.enums import (
    CapabilityLifecycle,
    CapabilityScope,
    ProofRequirement,
    ProofStatus,
    ReviewStatus,
    RunStatus,
    SourceCoverageStatus,
    TaskStatus,
)
from src.domain.financial_semantics import canonical_decimal, metric_semantics_hash
from src.domain.financial_validation import (
    REVENUE_GROWTH_FORMULA_EXPRESSION,
    REVENUE_GROWTH_PRECONDITION,
    REVENUE_GROWTH_VALIDATION_REASON,
)
from src.domain.macd_policy import MACD_DECIMAL_CONTEXT_POLICY
from src.domain.proof import (
    ProofArtifactReference,
    ProofInputCommitment,
    ProofPolicyDecision,
    ProofRecord,
    ProofRequest,
    ProofResult,
    ProofVerificationRecord,
)
from src.domain.report import (
    CanonicalReportDTO,
    FrozenJsonMapping,
    FrozenJsonSequence,
    ReportArtifactRecord,
)
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.domain.task import Task
from src.infrastructure.config import Settings
from src.infrastructure.database.artifacts import TaskDependencyGraphKind
from src.infrastructure.database.composition import create_postgresql_persistence
from src.infrastructure.database.generated_workflow import (
    PostgreSQLCapabilityWorkflowRecorder,
)
from src.infrastructure.database.migrations import upgrade_postgresql_database
from src.observability import (
    InMemoryTraceReferenceRepository,
    InstrumentedLLMProvider,
    ObservationStage,
    RuntimeInstrumentation,
    TraceRuntimeStatus,
    create_langfuse_trace_adapter,
)
from src.observability.identity_evidence import build_langfuse_identity_set_evidence
from src.observability.reference_ledger import build_trace_reference_ledger
from src.output.calculation_taxonomy import FUNDAMENTAL_FORMULAS, TECHNICAL_FORMULAS
from src.output.financial_metrics import MATERIAL_FORMULAS, build_research_source_coverage
from src.runtime.sse import encode_sse_event, encode_sse_heartbeat, runtime_event_stream
from src.tooling.generated_sandbox import DEFAULT_SANDBOX_IMAGE, DockerSandboxBackend


class CountingFMPTransport:
    """Count requests without retaining params, headers, bodies, or credentials."""

    def __init__(self, delegate: HttpxFMPTransport) -> None:
        self._delegate = delegate
        self.total = 0
        self.by_endpoint: Counter[str] = Counter()

    async def request(
        self,
        *,
        endpoint: FMPEndpoint,
        path: str,
        params: dict[str, str | int],
    ) -> FMPResponseEnvelope:
        self.total += 1
        self.by_endpoint[endpoint.value] += 1
        return await self._delegate.request(endpoint=endpoint, path=path, params=params)


class LLMRequestCounter:
    def __init__(self) -> None:
        self.http_attempts = 0

    async def on_request(self, request: httpx.Request) -> None:
        del request
        self.http_attempts += 1


class CountingLLMProvider:
    """Count structured calls and schema names without retaining prompt content."""

    def __init__(self, delegate: LockedPlannerProvider) -> None:
        self._delegate = delegate
        self.provider_name = delegate.provider_name
        self.model_name = delegate.model_name
        self.logical_calls = 0
        self.schemas: Counter[str] = Counter()

    @property
    def execution_policy(self) -> Any:
        return self._delegate.execution_policy

    async def complete_structured(self, **kwargs: Any) -> Any:
        self.logical_calls += 1
        schema_name = kwargs.get("schema_name")
        if isinstance(schema_name, str):
            self.schemas[schema_name] += 1
        return await self._delegate.complete_structured(**kwargs)


class _PreflightValidationProgress:
    """Non-persisted progress sink for candidate-bound GC qualification."""

    async def static_validated(self, implementation_hash: str) -> None:
        del implementation_hash

    async def sandbox_started(self, implementation_hash: str) -> None:
        del implementation_hash

    async def tests_passed(self, implementation_hash: str) -> None:
        del implementation_hash

    async def financial_validated(self, implementation_hash: str) -> None:
        del implementation_hash


async def _planner_provider_preflight(provider: LLMProvider) -> PlannerProviderHealth:
    """Validate two consecutive owned scheme-and-plan results without creating a Run."""

    provider_name = str(getattr(provider, "provider_name", ""))
    model_name = str(getattr(provider, "model_name", "")) or None
    research_object = ResearchObject(
        object_id="OBJ-NVDA-PREFLIGHT",
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
    )
    goal = ResearchGoal(
        goal_id="GOAL-NVDA-PLANNER-PREFLIGHT",
        research_object_id=research_object.object_id,
        goal_text="Validate the governed NVDA research planner capability.",
        as_of=date(2026, 9, 4),
    )
    actual_models: list[str] = []
    for probe in range(1, 3):
        scheme_result = await PlannerProviderSchemeGenerator(
            provider,
            max_validation_attempts=3,
        ).generate_with_decision(
            research_object=research_object,
            goal=goal,
        )
        scheme_audit = scheme_result.audit
        if (
            scheme_audit.deterministic_fallback
            or scheme_audit.provider != provider_name
            or not scheme_audit.actual_model
        ):
            return PlannerProviderHealth(
                provider=provider_name,
                model=model_name,
                passed=False,
                failure_classification=scheme_audit.failure_classification
                or "owned_scheme_preflight_failed",
            )
        scheme = scheme_result.output
        scheme.confirmed_at = datetime.now(UTC)
        planner = PlannerProviderResearchLeadPlanner(provider, max_validation_attempts=3)
        result = await planner.plan_with_decision(
            run_id=f"PREFLIGHT:{provider_name}:{probe}",
            goal=goal,
            scheme=scheme,
        )
        audit = result.audit
        if (
            audit.deterministic_fallback
            or audit.provider != provider_name
            or not audit.actual_model
        ):
            return PlannerProviderHealth(
                provider=provider_name,
                model=model_name,
                passed=False,
                failure_classification=audit.failure_classification
                or "owned_planner_preflight_failed",
            )
        actual_models.extend((scheme_audit.actual_model, audit.actual_model))
    if len(set(actual_models)) != 1:
        return PlannerProviderHealth(
            provider=provider_name,
            model=None,
            passed=False,
            failure_classification="model_identity_drift",
        )
    return PlannerProviderHealth(
        provider=provider_name,
        model=actual_models[0],
        passed=True,
    )


def _preflight_context() -> tuple[ResearchObject, ResearchGoal]:
    research_object = ResearchObject(
        object_id="OBJ-NVDA-PREFLIGHT",
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
    )
    goal = ResearchGoal(
        goal_id="GOAL-NVDA-PROVIDER-PREFLIGHT",
        research_object_id=research_object.object_id,
        goal_text="Validate one governed NVDA LLM workload without creating a Research Run.",
        as_of=date(2026, 9, 4),
    )
    return research_object, goal


def _failed_workload_health(
    provider: LLMProvider,
    workload: PlannerWorkload,
    error: Exception,
    *,
    attempt: int,
    started: float,
) -> PlannerProviderHealth:
    classification = getattr(error, "failure_classification", None)
    classification_value = getattr(classification, "value", classification)
    if not isinstance(classification_value, str) or not classification_value:
        classification_value = (
            "overall_deadline_exceeded"
            if isinstance(error, TimeoutError)
            else "semantic_schema_failure"
            if isinstance(error, ValueError)
            else "provider_unavailable"
        )
    return PlannerProviderHealth(
        provider=str(getattr(provider, "provider_name", "")),
        model=str(getattr(provider, "model_name", "")) or None,
        passed=False,
        failure_classification=classification_value,
        workload_type=workload,
        attempt=attempt,
        elapsed_seconds=perf_counter() - started,
        retryable=bool(getattr(error, "retryable", False)),
    )


def _fallback_workload_health(
    provider: LLMProvider,
    workload: PlannerWorkload,
    failure_classification: str | None,
    *,
    attempt: int,
    started: float,
) -> PlannerProviderHealth:
    classification = failure_classification or "semantic_schema_failure"
    retryable = classification in {
        "quota_or_rate_limit",
        "retryable_http_failure",
        "provider_unavailable",
        "connect_timeout",
        "read_timeout",
        "overall_deadline_exceeded",
        "remote_protocol_error",
    }
    return PlannerProviderHealth(
        provider=str(getattr(provider, "provider_name", "")),
        model=str(getattr(provider, "model_name", "")) or None,
        passed=False,
        failure_classification=classification,
        workload_type=workload,
        attempt=attempt,
        elapsed_seconds=perf_counter() - started,
        retryable=retryable,
    )


async def _scheme_provider_preflight(provider: LLMProvider) -> PlannerProviderHealth:
    """Require two consecutive exact Scheme planner responses."""

    workload = PlannerWorkload.SCHEME_PLANNER
    provider_name = str(getattr(provider, "provider_name", ""))
    started = perf_counter()
    research_object, goal = _preflight_context()
    actual_models: list[str] = []
    for probe in range(1, 3):
        try:
            result = await PlannerProviderSchemeGenerator(
                provider,
                max_validation_attempts=3,
            ).generate_with_decision(research_object=research_object, goal=goal)
            if result.audit.deterministic_fallback or not result.audit.actual_model:
                return _fallback_workload_health(
                    provider,
                    workload,
                    result.audit.failure_classification,
                    attempt=probe,
                    started=started,
                )
            if result.audit.provider != provider_name:
                raise ValueError("owned Scheme planner provider identity drifted")
            actual_models.append(result.audit.actual_model)
        except Exception as exc:
            return _failed_workload_health(provider, workload, exc, attempt=probe, started=started)
    if len(set(actual_models)) != 1:
        return PlannerProviderHealth(
            provider=provider_name,
            model=None,
            passed=False,
            failure_classification="semantic_schema_failure",
            workload_type=workload,
            attempt=2,
            elapsed_seconds=perf_counter() - started,
            retryable=False,
        )
    return PlannerProviderHealth(
        provider=provider_name,
        model=actual_models[0],
        passed=True,
        workload_type=workload,
        attempt=2,
        elapsed_seconds=perf_counter() - started,
        retryable=False,
    )


async def _lead_provider_preflight(provider: LLMProvider) -> PlannerProviderHealth:
    """Require two consecutive exact Lead planner responses from a fixed owned Scheme."""

    workload = PlannerWorkload.LEAD_PLANNER
    provider_name = str(getattr(provider, "provider_name", ""))
    started = perf_counter()
    research_object, goal = _preflight_context()
    scheme = await DeterministicSchemeGenerator().generate(
        research_object=research_object,
        goal=goal,
    )
    scheme.confirmed_at = datetime.now(UTC)
    actual_models: list[str] = []
    for probe in range(1, 3):
        try:
            result = await PlannerProviderResearchLeadPlanner(
                provider,
                max_validation_attempts=3,
            ).plan_with_decision(
                run_id=f"PREFLIGHT:{provider_name}:LEAD:{probe}",
                goal=goal,
                scheme=scheme,
            )
            if result.audit.deterministic_fallback or not result.audit.actual_model:
                return _fallback_workload_health(
                    provider,
                    workload,
                    result.audit.failure_classification,
                    attempt=probe,
                    started=started,
                )
            if result.audit.provider != provider_name:
                raise ValueError("owned Lead planner provider identity drifted")
            actual_models.append(result.audit.actual_model)
        except Exception as exc:
            return _failed_workload_health(provider, workload, exc, attempt=probe, started=started)
    if len(set(actual_models)) != 1:
        return PlannerProviderHealth(
            provider=provider_name,
            model=None,
            passed=False,
            failure_classification="semantic_schema_failure",
            workload_type=workload,
            attempt=2,
            elapsed_seconds=perf_counter() - started,
            retryable=False,
        )
    return PlannerProviderHealth(
        provider=provider_name,
        model=actual_models[0],
        passed=True,
        workload_type=workload,
        attempt=2,
        elapsed_seconds=perf_counter() - started,
        retryable=False,
    )


async def _generated_capability_provider_preflight(
    provider: LLMProvider,
) -> PlannerProviderHealth:
    """Require two exact, non-persisted Code Builder responses."""

    workload = PlannerWorkload.GENERATED_CAPABILITY
    provider_name = str(getattr(provider, "provider_name", ""))
    started = perf_counter()
    task = Task(
        task_id="TASK-NVDA-GENERATED-CAPABILITY-PREFLIGHT",
        run_id="PREFLIGHT:GENERATED_CAPABILITY",
        task_type="fundamental_analysis",
        goal="Qualify deterministic free cash flow margin generation.",
        assigned_agent="fundamental_analyst",
        skill_id="fundamental_analysis_v1",
        status=TaskStatus.RUNNING,
    )
    gap = CapabilityGapRecord(
        gap_id="GAP-NVDA-GENERATED-CAPABILITY-PREFLIGHT",
        run_id=task.run_id,
        task_id=task.task_id,
        requirement=free_cash_flow_margin_requirement(task),
        requested_by=task.assigned_agent,
        detail="Non-persisted provider stability qualification.",
    )
    approval = ResearchLeadCapabilityApproval(
        decision_id="DEC-NVDA-GENERATED-CAPABILITY-PREFLIGHT",
        run_id=task.run_id,
        task_id=task.task_id,
        gap_id=gap.gap_id,
        phase="SPEC",
        approved=True,
        approved_by="research_lead",
        reason_code="PROVIDER_STABILITY_QUALIFICATION",
        summary="Safe controlled Generated Capability provider qualification.",
    )
    builder = PlannerProviderCodeBuilder(provider)
    validator = GeneratedCapabilityValidator(
        sandbox=DockerSandboxBackend(image=DEFAULT_SANDBOX_IMAGE),
        plans=FreeCashFlowMarginValidationPlanProvider(),
    )
    actual_models: list[str] = []
    for probe in range(1, 3):
        request = CapabilityBuildRequest(
            build_id=f"BUILD-NVDA-GENERATED-CAPABILITY-PREFLIGHT-{probe}",
            gap=gap,
            approval=approval,
            attempt=probe,
            max_attempts=2,
        )
        try:
            candidate = await builder.generate(request)
            if candidate.provider != provider_name or not candidate.actual_model:
                raise ValueError("owned Code Builder provider identity drifted")
            if (
                candidate.compiler_id != GENERATED_CAPABILITY_COMPILER_ID
                or candidate.compiler_version != GENERATED_CAPABILITY_COMPILER_VERSION
            ):
                raise ValueError("owned Generated Capability compiler identity drifted")
            handoff = await validator.validate(
                candidate,
                progress=_PreflightValidationProgress(),
            )
            handoff.assert_ready_for_task_approval(candidate)
            actual_models.append(candidate.actual_model)
        except Exception as exc:
            return _failed_workload_health(provider, workload, exc, attempt=probe, started=started)
    if len(set(actual_models)) != 1:
        return PlannerProviderHealth(
            provider=provider_name,
            model=None,
            passed=False,
            failure_classification="semantic_schema_failure",
            workload_type=workload,
            attempt=2,
            elapsed_seconds=perf_counter() - started,
            retryable=False,
        )
    return PlannerProviderHealth(
        provider=provider_name,
        model=actual_models[0],
        passed=True,
        workload_type=workload,
        attempt=2,
        elapsed_seconds=perf_counter() - started,
        retryable=False,
    )


class AuditedTraceAdapter:
    """Record metadata-only observation identities while delegating real Langfuse I/O."""

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate
        self.observations: list[dict[str, Any]] = []
        self._active_trace_ids: list[str] = []

    @property
    def status(self) -> Any:
        return self._delegate.status

    def mark_degraded(self, operation: str, error: Exception) -> None:
        marker = getattr(self._delegate, "mark_degraded", None)
        if callable(marker):
            marker(operation, error)

    @asynccontextmanager
    async def span(self, name: str, *, attributes: dict[str, Any] | None = None):
        async with self._delegate.span(name, attributes=attributes) as span:
            trace_id = getattr(span, "trace_id", None)
            if isinstance(trace_id, str) and trace_id:
                self._active_trace_ids.append(trace_id)
            try:
                self._record("span", name, attributes, span)
                yield span
            finally:
                if isinstance(trace_id, str) and trace_id:
                    self._active_trace_ids.pop()

    async def event(self, name: str, *, attributes: dict[str, Any] | None = None) -> None:
        handle = await self._delegate.event(name, attributes=attributes)
        self._record("event", name, attributes, handle)

    @asynccontextmanager
    async def generation(
        self,
        name: str,
        *,
        model: str | None = None,
        attributes: dict[str, Any] | None = None,
        usage_details: dict[str, Any] | None = None,
        cost_details: dict[str, Any] | None = None,
    ):
        async with self._delegate.generation(
            name,
            model=model,
            attributes=attributes,
            usage_details=usage_details,
            cost_details=cost_details,
        ) as generation:
            trace_id = getattr(generation, "trace_id", None)
            if isinstance(trace_id, str) and trace_id:
                self._active_trace_ids.append(trace_id)
            try:
                self._record("generation", name, attributes, generation)
                yield generation
            finally:
                if isinstance(trace_id, str) and trace_id:
                    self._active_trace_ids.pop()

    async def complete_generation(self, generation: Any, **kwargs: Any) -> None:
        await self._delegate.complete_generation(generation, **kwargs)

    async def flush(self) -> None:
        flush = getattr(self._delegate, "flush", None)
        if callable(flush):
            await flush()

    def _record(
        self,
        kind: str,
        name: str,
        attributes: dict[str, Any] | None,
        handle: Any,
    ) -> None:
        values = attributes or {}
        trace_id = getattr(handle, "trace_id", None)
        if not trace_id and self._active_trace_ids:
            trace_id = self._active_trace_ids[-1]
        observation_id = getattr(handle, "span_id", None) or getattr(handle, "id", None)
        self.observations.append(
            {
                "kind": kind,
                "name": name,
                "run_id": values.get("run_id"),
                "task_id": values.get("task_id"),
                "tool_name": values.get("tool_name"),
                "trace_id": trace_id,
                "span_id": getattr(handle, "span_id", None),
                "observation_id": observation_id,
            }
        )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _file_hash(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _is_sha256_identity(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _file_starts_with(path: Path, prefix: bytes) -> bool:
    with path.open("rb") as stream:
        return stream.read(len(prefix)) == prefix


def _canonical_hash(value: Any) -> str:
    return _sha256_bytes(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )


def _is_recursively_frozen(value: Any) -> bool:
    if isinstance(value, FrozenJsonMapping):
        return all(_is_recursively_frozen(item) for item in value.values())
    if isinstance(value, FrozenJsonSequence):
        return all(_is_recursively_frozen(item) for item in value)
    return not isinstance(value, (dict, list, set, bytearray))


def _aggregate_snapshot(aggregate: Any) -> dict[str, Any]:
    return {
        "run": aggregate.run.model_dump(mode="json"),
        "goal": aggregate.goal.model_dump(mode="json"),
        "scheme": aggregate.scheme.model_dump(mode="json"),
        "runtime": {
            "planned_graph": aggregate.runtime.planned_graph.model_dump(mode="json"),
            "actual_graph": aggregate.runtime.actual_graph.model_dump(mode="json"),
            "run_status": aggregate.runtime.run_status.value,
            "completed_output_refs": aggregate.runtime.completed_output_refs,
            "evidence_refs": aggregate.runtime.evidence_refs,
            "workspace_refs": aggregate.runtime.workspace_refs,
            "review_state": aggregate.runtime.review_state,
            "proof_state": aggregate.runtime.proof_state,
            "cost": aggregate.runtime.cost,
        },
        "artifacts": aggregate.artifacts.model_dump(mode="json"),
    }


def _tree_snapshot(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): _file_hash(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _resolve_safe_path(path: Path, *, label: str, must_exist: bool = False) -> Path:
    requested = path.expanduser()
    if requested.is_symlink() or requested == Path(requested.anchor):
        raise RuntimeError(f"unsafe {label}")
    return requested.resolve(strict=must_exist)


def _credential_needles(settings: Settings) -> tuple[bytes, ...]:
    values: list[str] = []
    for secret in (
        *settings.fmp.credentials,
        settings.llm.api_key,
        settings.mimo.api_key,
        settings.langfuse.public_key,
        settings.langfuse.secret_key,
    ):
        if secret is not None and secret.get_secret_value():
            values.append(secret.get_secret_value())
    database_password = make_url(settings.database.url).password
    if database_password:
        values.append(database_password)
    needles: set[bytes] = set()
    for value in values:
        raw = value.encode("utf-8")
        if len(raw) < 8:
            raise RuntimeError("configured credential is too short for a reliable secret scan")
        needles.update(
            {
                raw,
                quote_from_bytes(raw, safe="").encode("ascii"),
                base64.b64encode(raw),
                base64.urlsafe_b64encode(raw),
            }
        )
    return tuple(sorted(needles))


def _contains_credential(path: Path, needles: tuple[bytes, ...]) -> bool:
    if not needles:
        return False
    overlap = max(len(needle) for needle in needles) - 1
    previous = b""
    with path.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            candidate = previous + chunk
            if any(needle in candidate for needle in needles):
                return True
            previous = candidate[-overlap:] if overlap else b""
    return False


def _scan_artifacts_for_credentials(
    root: Path,
    *,
    needles: tuple[bytes, ...],
    pending_summary: dict[str, Any],
) -> dict[str, Any]:
    match_count = 0
    scanned_files = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            return {"passed": False, "match_count": 1, "scanned_files": scanned_files}
        if not path.is_file():
            continue
        resolved = path.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError:
            return {"passed": False, "match_count": 1, "scanned_files": scanned_files}
        scanned_files += 1
        match_count += int(_contains_credential(resolved, needles))
    summary_bytes = json.dumps(
        pending_summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    match_count += sum(needle in summary_bytes for needle in needles)
    return {
        "passed": match_count == 0,
        "match_count": match_count,
        "scanned_files": scanned_files,
    }


def _alembic_head(script_location: Path) -> str:
    config = Config()
    config.set_main_option("script_location", str(script_location))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError("Phase 3 requires exactly one Alembic head")
    return heads[0]


def _alembic_location() -> Path:
    return Path(__file__).resolve().parents[1] / "alembic"


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _working_directory() -> Path:
    return Path.cwd().resolve()


def _git(
    repository_root: Path,
    *args: str,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ("git", *args),
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed")
    return completed


def _candidate_preflight(repository_root: Path, expected_head: str) -> dict[str, Any]:
    """Bind acceptance to one clean, tracked, immutable candidate commit."""

    root = repository_root.resolve(strict=True)
    git_root = Path(_git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if git_root != root:
        raise RuntimeError("Phase 3 candidate must be the repository root")
    head = _git(root, "rev-parse", "HEAD^{commit}").stdout.strip()
    if expected_head != head or len(head) != 40:
        raise RuntimeError("declared Phase 3 candidate HEAD does not match current HEAD")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout:
        raise RuntimeError("Phase 3 candidate worktree is not clean")

    required_paths = (
        "alembic/versions/20260904_0004_phase3_capability_proof_artifacts.py",
        "alembic/versions/20260904_0005_financial_evidence_semantics.py",
        "alembic/versions/20260904_0006_generated_capability_artifact_retention.py",
        "scripts/run_phase3_acceptance.py",
        "src/adapters/llm/execution.py",
        "src/adapters/llm/mimo.py",
        "src/adapters/llm/router.py",
        "src/capabilities/generated/artifacts.py",
        "src/domain/financial_validation.py",
        "src/domain/macd_policy.py",
        "src/infrastructure/database/generated_workflow.py",
        "src/adapters/finrobot/technical.py",
        "src/application/service.py",
        "src/observability/identity_evidence.py",
        "src/observability/langfuse_adapter.py",
        "src/observability/reference_ledger.py",
        "src/output/calculation_taxonomy.py",
        "docs/PHASE3_INDEPENDENT_AUDIT_REMEDIATION.md",
        "docs/PHASE3_PLANNER_PROVIDER_ROUTER_REMEDIATION.md",
        "docs/PHASE3_PROVIDER_RELIABILITY_REMEDIATION.md",
        "tests/unit/generated/test_artifact_retention.py",
        "tests/unit/observability/test_langfuse_acceptance_drain_policy.py",
        "tests/unit/observability/test_langfuse_identity_evidence.py",
        "tests/unit/observability/test_trace_reference_ledger.py",
        "tests/unit/output/test_calculation_taxonomy.py",
        "tests/financial/test_volume_ratio_provenance_metadata.py",
        "src/adapters/risc0/release_manifest.py",
        "tests/test_phase3_acceptance_runner.py",
        "tests/unit/llm/test_planner_provider_router.py",
        "tests/unit/llm/test_provider_execution_policy.py",
        "zk/revenue_growth/RISC_ZERO_RELEASE_MANIFEST.json",
        "zk/revenue_growth/build-host.sh",
        "zk/revenue_growth/normalize_macos_host.py",
    )
    tracked = set(_git(root, "ls-files").stdout.splitlines())
    missing = sorted(set(required_paths) - tracked)
    if missing:
        raise RuntimeError(f"Phase 3 candidate is missing tracked release sources: {missing}")
    for relative in required_paths:
        _git(root, "cat-file", "-e", f"{head}:{relative}")

    release_manifest = load_and_verify_release_manifest(root)
    artifacts = release_manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RuntimeError("RISC Zero release artifact identities are missing")
    host_artifact = artifacts.get("host")
    guest_artifact = artifacts.get("guest")
    if not isinstance(host_artifact, dict) or not isinstance(guest_artifact, dict):
        raise RuntimeError("RISC Zero host/guest artifact identities are missing")
    manifest_host_sha256 = host_artifact.get("sha256")
    manifest_image_id = guest_artifact.get("image_id")
    guest_elf_sha256 = guest_artifact.get("elf_sha256")
    guest_binary_sha256 = guest_artifact.get("combined_binary_sha256")
    if manifest_host_sha256 != EXPECTED_REVENUE_GROWTH_HOST_SHA256:
        raise RuntimeError("RISC Zero manifest host pin differs from production")
    if manifest_image_id != EXPECTED_REVENUE_GROWTH_IMAGE_ID:
        raise RuntimeError("RISC Zero manifest image pin differs from production")
    if not _is_sha256_identity(guest_elf_sha256) or not _is_sha256_identity(guest_binary_sha256):
        raise RuntimeError("RISC Zero manifest guest hashes are invalid")
    reproducibility = release_manifest.get("reproducibility")
    if not isinstance(reproducibility, dict) or not (
        int(reproducibility.get("build_count", 0)) >= 2
        and reproducibility.get("cross_absolute_path") is True
        and reproducibility.get("guest_combined_binary_equal") is True
        and reproducibility.get("guest_elf_equal") is True
        and reproducibility.get("host_binary_equal") is True
        and reproducibility.get("image_id_equal") is True
    ):
        raise RuntimeError("RISC Zero reproducibility attestation is incomplete")
    build = release_manifest.get("build")
    if not isinstance(build, dict) or build.get("cargo_locked") is not True:
        raise RuntimeError("RISC Zero locked build identity is missing")
    manifest_path = root / RELEASE_MANIFEST_RELATIVE_PATH
    tree = _git(root, "rev-parse", "HEAD^{tree}").stdout.strip()
    tracked_tree_listing = _git(root, "ls-tree", "-r", "--full-tree", head).stdout.encode("utf-8")
    return {
        "candidate_head": head,
        "candidate_tree": tree,
        "source_fingerprint": _sha256_bytes(tracked_tree_listing),
        "worktree_clean": True,
        "required_release_sources_tracked": True,
        "migration_chain": ["20260904_0004", "20260904_0005", "20260904_0006"],
        "risc0_release_manifest_sha256": release_manifest_sha256(manifest_path),
        "risc0_source_set_sha256": release_manifest["source_closure"]["source_set_sha256"],
        "risc0_manifest_host_sha256": manifest_host_sha256,
        "risc0_manifest_image_id": manifest_image_id,
        "risc0_guest_elf_sha256": guest_elf_sha256,
        "risc0_guest_binary_sha256": guest_binary_sha256,
        "risc0_reproducible_build_count": reproducibility["build_count"],
        "risc0_build_version": build.get("risc0_build_version"),
        "risc0_zkvm_version": build.get("risc0_zkvm_version"),
    }


def _candidate_still_immutable(repository_root: Path, candidate: Mapping[str, Any]) -> bool:
    try:
        current = _candidate_preflight(repository_root, str(candidate["candidate_head"]))
    except RuntimeError:
        return False
    return current == dict(candidate)


def _run_pytest_regression(
    repository_root: Path,
    *,
    suite: str,
    targets: tuple[str, ...],
) -> dict[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(repository_root)
    command = (sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *targets)
    completed = subprocess.run(
        command,
        cwd=repository_root,
        check=False,
        capture_output=True,
        timeout=900,
        env=environment,
    )
    return {
        "suite": suite,
        "targets": list(targets),
        "returncode": completed.returncode,
        "stdout_sha256": _sha256_bytes(completed.stdout),
        "stderr_sha256": _sha256_bytes(completed.stderr),
        "passed": completed.returncode == 0,
    }


def _run_regression_suites(repository_root: Path) -> dict[str, dict[str, Any]]:
    suites = {
        "phase1": (
            "tests/acceptance/test_phase1_acceptance.py",
            "tests/unit/test_foundation_contracts.py",
        ),
        "phase2": (
            "tests/integration/test_phase2_composition.py",
            "tests/unit/data/test_live_fmp_integration.py",
            "tests/unit/llm/test_agentic_llm_integration.py",
            "tests/unit/observability/test_langfuse_integration.py",
        ),
        "phase2_1": (
            "tests/unit/application/test_evidence_semantics.py",
            "tests/unit/data/test_peer_data_semantics.py",
            "tests/unit/assurance/test_review_release.py",
        ),
    }
    return {
        name: _run_pytest_regression(
            repository_root,
            suite=name,
            targets=targets,
        )
        for name, targets in suites.items()
    }


def _require_formal_mode(environment: Mapping[str, str]) -> None:
    if "RISC0_DEV_MODE" in environment:
        raise RuntimeError("RISC0_DEV_MODE is forbidden for formal acceptance")


async def _sse_frames(
    store: Any,
    *,
    run_id: str,
    last_event_id: str,
    expected_events: list[Any],
) -> list[str]:
    stream = runtime_event_stream(
        store=store,
        run_id=run_id,
        last_event_id=last_event_id,
        heartbeat_seconds=0.1,
    )
    try:
        return [await asyncio.wait_for(anext(stream), timeout=2.0) for _ in expected_events]
    finally:
        await stream.aclose()


def _write_exclusive(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _preflight_formal_runtime(host_binary: Path) -> dict[str, Any]:
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError("Phase 3 acceptance requires Python 3.11")
    _require_formal_mode(os.environ)
    if host_binary.is_symlink() or not host_binary.is_file() or not os.access(host_binary, os.X_OK):
        raise RuntimeError("the pinned RISC Zero host binary is not executable")
    host_hash = _file_hash(host_binary)
    if host_hash != EXPECTED_REVENUE_GROWTH_HOST_SHA256:
        raise RuntimeError("the RISC Zero host binary digest does not match the release pin")
    docker = subprocess.run(
        ("docker", "image", "inspect", DEFAULT_SANDBOX_IMAGE),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if docker.returncode != 0:
        raise RuntimeError("the pinned Python 3.11 Docker sandbox image is unavailable")
    image = subprocess.run(
        (str(host_binary), "image-id"),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "RUST_BACKTRACE": "0"},
    )
    if image.returncode != 0:
        raise RuntimeError("the RISC Zero host image-id preflight failed")
    try:
        image_payload = json.loads(image.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("the RISC Zero host returned invalid image metadata") from exc
    if image_payload.get("image_id") != EXPECTED_REVENUE_GROWTH_IMAGE_ID:
        raise RuntimeError("the RISC Zero guest image id does not match the release pin")
    return {
        "python": sys.version.split()[0],
        "docker_image": DEFAULT_SANDBOX_IMAGE,
        "risc0_host_sha256": host_hash,
        "risc0_image_id": image_payload["image_id"],
    }


async def _negative_proof_checks(
    *,
    adapter: RiscZeroProofAdapter,
    host_binary: Path,
    proof_root: Path,
    proof: ProofRecord,
) -> dict[str, bool]:
    safe_id = hashlib.sha256(proof.proof_id.encode("utf-8")).hexdigest()
    input_path = proof_root / "inputs" / f"{safe_id}.json"
    original = load_proof_input(input_path)
    original_result = ProofResult(
        proof_id=proof.proof_id,
        status=ProofStatus.VERIFIED,
        receipt_ref=proof.receipt_artifact_ref,
        verifier_result={
            "proof_input_ref": str(input_path),
            "receipt_hash": proof.receipt_hash,
            "verified": True,
        },
    )
    original_pass = await adapter.verify(original_result)

    tampered_previous_path = proof_root / f"{safe_id}.tampered-previous-revenue.json"
    tampered_previous = build_proof_input(
        run_id=original.run_id,
        calculation_id=original.calculation_id,
        implementation_hash=original.implementation_hash,
        input_evidence_refs=original.input_evidence_refs,
        canonical_inputs=CanonicalRevenueInputs(
            prior_revenue_minor=original.canonical_inputs.prior_revenue_minor + 1,
            current_revenue_minor=original.canonical_inputs.current_revenue_minor,
            currency=original.canonical_inputs.currency,
            scale=original.canonical_inputs.scale,
        ),
    )
    write_proof_input(tampered_previous_path, tampered_previous)
    tampered_previous_result = original_result.model_copy(
        deep=True,
        update={
            "verifier_result": {
                **original_result.verifier_result,
                "proof_input_ref": str(tampered_previous_path),
            }
        },
    )

    tampered_current_path = proof_root / f"{safe_id}.tampered-current-revenue.json"
    tampered_current = build_proof_input(
        run_id=original.run_id,
        calculation_id=original.calculation_id,
        implementation_hash=original.implementation_hash,
        input_evidence_refs=original.input_evidence_refs,
        canonical_inputs=CanonicalRevenueInputs(
            prior_revenue_minor=original.canonical_inputs.prior_revenue_minor,
            current_revenue_minor=original.canonical_inputs.current_revenue_minor + 1,
            currency=original.canonical_inputs.currency,
            scale=original.canonical_inputs.scale,
        ),
    )
    write_proof_input(tampered_current_path, tampered_current)
    tampered_current_result = original_result.model_copy(
        deep=True,
        update={
            "verifier_result": {
                **original_result.verifier_result,
                "proof_input_ref": str(tampered_current_path),
            }
        },
    )

    tampered_result_path = proof_root / f"{safe_id}.tampered-result.json"
    tampered_result = original.model_copy(
        update={"expected_output_commitment": "sha256:" + "0" * 64}
    )
    tampered_result = tampered_result.model_copy(
        update={"input_commitment": input_commitment(tampered_result)}
    )
    write_proof_input(tampered_result_path, tampered_result)
    tampered_expected_result = original_result.model_copy(
        deep=True,
        update={
            "verifier_result": {
                **original_result.verifier_result,
                "proof_input_ref": str(tampered_result_path),
            }
        },
    )

    corrupt_receipt_path = proof_root / f"{safe_id}.corrupt.receipt"
    receipt_bytes = await asyncio.to_thread(Path(str(proof.receipt_artifact_ref)).read_bytes)
    corrupt = bytearray(receipt_bytes)
    corrupt[len(corrupt) // 2] ^= 0x01
    await asyncio.to_thread(_write_exclusive, corrupt_receipt_path, bytes(corrupt))
    corrupt_result = original_result.model_copy(
        deep=True,
        update={"receipt_ref": str(corrupt_receipt_path)},
    )

    wrong_image_adapter = RiscZeroProofAdapter(
        host_binary=host_binary,
        artifact_dir=proof_root,
        expected_image_id="0" * 64,
    )
    files_before_wrong_program = _tree_snapshot(proof_root)
    wrong_program = await adapter.prove(
        ProofRequest(
            proof_id=f"{proof.proof_id}-WRONG-PROGRAM",
            run_id=original.run_id,
            calculation_id=original.calculation_id,
            program_id="unsupported_program_v1",
            input_commitments=[original.input_commitment],
            proof_input_ref=str(input_path),
        )
    )
    wrong_program_failed = (
        wrong_program.status is ProofStatus.ERROR
        and wrong_program.receipt_ref is None
        and _tree_snapshot(proof_root) == files_before_wrong_program
    )
    dev_environment = dict(os.environ)
    dev_environment["RISC0_DEV_MODE"] = "1"
    try:
        _require_formal_mode(dev_environment)
    except RuntimeError:
        dev_mode_presence_fail = True
    else:
        dev_mode_presence_fail = False

    def nonpositive_prior_fails(prior: int) -> bool:
        try:
            CanonicalRevenueInputs(
                prior_revenue_minor=prior,
                current_revenue_minor=original.canonical_inputs.current_revenue_minor,
                currency=original.canonical_inputs.currency,
                scale=original.canonical_inputs.scale,
            )
        except ValueError as exc:
            return REVENUE_GROWTH_VALIDATION_REASON in str(exc)
        return False

    return {
        "original_input_pass": original_pass,
        "zero_prior_fail": nonpositive_prior_fails(0),
        "negative_prior_fail": nonpositive_prior_fails(-1),
        "tampered_previous_revenue_fail": not await adapter.verify(tampered_previous_result),
        "tampered_current_revenue_fail": not await adapter.verify(tampered_current_result),
        "tampered_expected_result_fail": not await adapter.verify(tampered_expected_result),
        "wrong_image_fail": not await wrong_image_adapter.verify(
            original_result.model_copy(deep=True)
        ),
        "wrong_program_fail": wrong_program_failed,
        "corrupted_receipt_fail": not await adapter.verify(corrupt_result),
        "risc0_dev_mode_presence_fail": dev_mode_presence_fail,
    }


def _financial_review_negative_checks(
    *,
    aggregate: Any,
    proof_requirements: Mapping[str, ProofRequirement],
) -> dict[str, bool]:
    evidence = list(aggregate.artifacts.evidence)
    calculations = list(aggregate.artifacts.calculations)
    released = aggregate.artifacts.released_result
    if released is None:
        return {
            "period_mismatch_blocked": False,
            "unit_mismatch_blocked": False,
            "currency_mismatch_blocked": False,
            "cohort_mismatch_blocked": False,
            "calculation_tamper_blocked": False,
            "zero_prior_blocked": False,
            "zero_prior_reason_stable": False,
            "negative_prior_blocked": False,
            "negative_prior_reason_stable": False,
        }
    growth = next(item for item in calculations if item.formula_id == "revenue_growth_v1")
    evidence_by_id = {item.evidence_id: item for item in evidence}
    prior = evidence_by_id[growth.input_evidence_ids[0]]
    current = evidence_by_id[growth.input_evidence_ids[1]]

    def review_with(
        *,
        evidence_update: Any | None = None,
        calculation_update: Any | None = None,
    ) -> Any:
        changed_evidence = [
            evidence_update
            if evidence_update is not None and item.evidence_id == evidence_update.evidence_id
            else item
            for item in evidence
        ]
        changed_calculations = [
            (
                calculation_update
                if calculation_update is not None and item.calculation_id == growth.calculation_id
                else item
            )
            for item in calculations
        ]
        return IndependentFinancialReviewer().review(
            review_id=f"NEGATIVE-{uuid4()}",
            run_id=aggregate.run.run_id,
            run_as_of=aggregate.run.as_of,
            evidence=changed_evidence,
            calculations=changed_calculations,
            metrics=released.released_metrics,
            claims=released.material_claims,
            judgments=aggregate.artifacts.judgments,
            proof_requirements=proof_requirements,
        )

    period_mismatch = current.model_copy(
        update={
            "period": prior.period,
            "statement_cohort": f"NEGATIVE:{prior.period}",
        }
    )
    unit_mismatch = current.model_copy(update={"unit": "COUNT"})
    currency_mismatch = current.model_copy(update={"currency": "EUR"})
    margin = next(item for item in calculations if item.formula_id == "ebitda_margin_v1")
    ebitda = next(
        evidence_by_id[evidence_id]
        for evidence_id in margin.input_evidence_ids
        if evidence_by_id[evidence_id].normalized_field == "ebitda"
    )
    cohort_mismatch = ebitda.model_copy(update={"statement_cohort": "NEGATIVE:COHORT"})
    calculation_tamper = growth.model_copy(
        update={"output_value": Decimal(str(growth.output_value)) + Decimal(1)}
    )
    zero_prior = prior.model_copy(update={"normalized_value": "0"})
    negative_prior = prior.model_copy(update={"normalized_value": "-1"})
    zero_review = review_with(evidence_update=zero_prior)
    negative_review = review_with(evidence_update=negative_prior)

    def has_stable_reason(review_record: Any) -> bool:
        return any(
            getattr(check, "code", None) == "FIN_CALCULATION_RECOMPUTATION"
            and getattr(check, "detail", None) == REVENUE_GROWTH_VALIDATION_REASON
            for check in getattr(review_record, "checks", ())
        )

    return {
        "period_mismatch_blocked": review_with(evidence_update=period_mismatch).status
        is ReviewStatus.BLOCK,
        "unit_mismatch_blocked": review_with(evidence_update=unit_mismatch).status
        is ReviewStatus.BLOCK,
        "currency_mismatch_blocked": review_with(evidence_update=currency_mismatch).status
        is ReviewStatus.BLOCK,
        "cohort_mismatch_blocked": review_with(evidence_update=cohort_mismatch).status
        is ReviewStatus.BLOCK,
        "calculation_tamper_blocked": review_with(calculation_update=calculation_tamper).status
        is ReviewStatus.BLOCK,
        "zero_prior_blocked": zero_review.status is ReviewStatus.BLOCK,
        "zero_prior_reason_stable": has_stable_reason(zero_review),
        "negative_prior_blocked": negative_review.status is ReviewStatus.BLOCK,
        "negative_prior_reason_stable": has_stable_reason(negative_review),
    }


def _financial_semantic_matrix(
    *,
    aggregate: Any,
    dto: CanonicalReportDTO,
    report_artifacts: list[ReportArtifactRecord],
    validations: list[CapabilityValidationRecord],
    proof_inputs: list[ProofInputCommitment],
    proofs: list[ProofRecord],
    review_negative: dict[str, bool],
    cross_view_content_passed: bool,
) -> dict[str, dict[str, Any]]:
    released = aggregate.artifacts.released_result
    review = aggregate.artifacts.review
    if released is None or review is None:
        return {
            f"FS-{index:03d}": _gate(False, {"reason": "release/review missing"})
            for index in range(1, 14)
        }
    metrics = list(released.released_metrics)
    claims = list(released.material_claims)
    calculations = list(aggregate.artifacts.calculations)
    calculation_by_id = {item.calculation_id: item for item in calculations}
    metric_by_id = {item.metric_id: item for item in metrics}
    percent_formulas = set(FUNDAMENTAL_FORMULAS)
    percent_rendering = all(
        item.display_unit == "%"
        and item.display_value
        == format(
            (Decimal(item.canonical_value) * Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            "f",
        )
        for item in metrics
        if item.formula_id in percent_formulas
    )
    decimal_preserved = all(
        item.canonical_value
        == canonical_decimal(calculation_by_id[item.calculation_id].output_value)
        for item in metrics
    ) and [item.model_dump(mode="json") for item in dto.released_metrics] == [
        item.model_dump(mode="json") for item in metrics
    ]
    dispositions = list(released.material_calculation_dispositions)
    calculation_id_by_formula = {item.formula_id: item.calculation_id for item in calculations}
    expected_fundamental_refs = [
        calculation_id_by_formula[formula_id] for formula_id in FUNDAMENTAL_FORMULAS
    ]
    expected_technical_refs = [
        calculation_id_by_formula[formula_id] for formula_id in TECHNICAL_FORMULAS
    ]
    fundamental_section = dto.structured_financial_results.get("fundamental_result")
    technical_section = dto.structured_financial_results.get("technical_result")
    fundamental_refs = (
        fundamental_section.get("calculation_refs")
        if isinstance(fundamental_section, Mapping)
        else None
    )
    technical_refs = (
        technical_section.get("calculation_refs")
        if isinstance(technical_section, Mapping)
        else None
    )
    report_taxonomy = (
        fundamental_refs == expected_fundamental_refs
        and technical_refs == expected_technical_refs
        and set(fundamental_refs).isdisjoint(technical_refs)
        and set(fundamental_refs) | set(technical_refs) == set(dto.calculation_refs)
    )
    material_closure = (
        len(calculations) == len(metrics) == len(dispositions) == len(MATERIAL_FORMULAS)
        and {item.formula_id for item in calculations} == set(MATERIAL_FORMULAS)
        and {item.calculation_id for item in dispositions}
        == {item.calculation_id for item in calculations}
        and all(item.status.value == "REPORTABLE" for item in dispositions)
        and report_taxonomy
    )
    claim_closure = (
        len(claims) == len(metrics)
        and {item.metric_id for item in claims} == set(metric_by_id)
        and all(
            item.calculation_refs == (metric_by_id[item.metric_id].calculation_id,)
            and item.evidence_refs == metric_by_id[item.metric_id].evidence_ids
            and item.value == metric_by_id[item.metric_id].canonical_value
            and item.unit is metric_by_id[item.metric_id].canonical_unit
            for item in claims
        )
    )
    recomputations = [
        item for item in review.checks if item.code == "FIN_CALCULATION_RECOMPUTATION"
    ]
    reviewer_passed = (
        review.reviewer == "independent-financial-review-v2"
        and review.status is ReviewStatus.PASS
        and len(recomputations) == len(MATERIAL_FORMULAS)
        and all(item.status is ReviewStatus.PASS for item in recomputations)
        and review_negative["calculation_tamper_blocked"]
    )
    generated_calculation = next(
        (
            item
            for item in calculations
            if item.formula_id == "operating_cash_flow_plus_signed_capex_divided_by_revenue_v1"
        ),
        None,
    )
    live_validation = generated_calculation.parameters if generated_calculation else {}
    oracle = live_validation.get("owned_oracle_result", {})
    runtime_result = live_validation.get("runtime_result", {})
    generated_oracle_passed = (
        generated_calculation is not None
        and len(validations) == 1
        and validations[0].financial_validation_passed
        and live_validation.get("financial_validation_result") == "PASS"
        and oracle == runtime_result
        and _same_canonical_decimal(oracle.get("value"), generated_calculation.output_value)
    )
    technical = [item for item in metrics if item.formula_id in TECHNICAL_FORMULAS]
    macd_determinism = _macd_ambient_context_check(
        calculations=calculations,
        evidence=aggregate.artifacts.evidence,
    )
    policy = MACD_DECIMAL_CONTEXT_POLICY
    macd_metadata = [
        item.method_metadata for item in technical if item.formula_id.startswith("macd_")
    ]
    technical_passed = (
        len(technical) == 7
        and all(
            item.method_metadata is not None and item.method_metadata.warmup_satisfied is True
            for item in technical
        )
        and all(
            item.technical_price_basis is not None and item.corporate_action_status is not None
            for item in technical
            if item.formula_id != "latest_volume_to_average_volume_20_v1"
        )
        and len(macd_metadata) == 3
        and all(
            method is not None
            and method.decimal_context_policy_id == policy.policy_id
            and method.decimal_precision == policy.precision
            and method.decimal_rounding == policy.rounding
            and method.ema_adjust is policy.ema_adjust
            and method.ema_seed == policy.ema_seed
            and method.fast_span == policy.fast_span
            and method.slow_span == policy.slow_span
            and method.signal_span == policy.signal_span
            and method.warmup_required == policy.warmup_required
            and method.warmup_satisfied is True
            and method.technical_price_basis is not None
            for method in macd_metadata
        )
        and macd_determinism["passed"]
    )
    growth = next((item for item in calculations if item.formula_id == "revenue_growth_v1"), None)
    proof_input = proof_inputs[0] if len(proof_inputs) == 1 else None
    proof = proofs[0] if len(proofs) == 1 else None
    proof_identity = (
        growth is not None
        and proof_input is not None
        and proof is not None
        and growth.implementation_hash
        == proof_input.implementation_hash
        == proof.implementation_hash
        and growth.proof_ref == proof.proof_id
    )
    try:
        revenue_positive_exact = calculate_native_revenue_growth(
            Decimal("100"), Decimal("125")
        ) == Decimal("0.25")
        for invalid_prior in (Decimal("0"), Decimal("-100")):
            try:
                calculate_native_revenue_growth(invalid_prior, Decimal("125"))
            except NonPositivePriorRevenueError as exc:
                if str(exc) != REVENUE_GROWTH_VALIDATION_REASON:
                    raise AssertionError("unstable revenue validation reason") from exc
            else:
                raise AssertionError("nonpositive prior revenue was accepted")
        revenue_nonpositive_rejected = True
    except (ArithmeticError, AssertionError, ValueError):
        revenue_positive_exact = False
        revenue_nonpositive_rejected = False
    revenue_formula_metadata = (
        growth is not None
        and growth.parameters.get("formula_expression") == REVENUE_GROWTH_FORMULA_EXPRESSION
        and growth.parameters.get("semantic_precondition") == REVENUE_GROWTH_PRECONDITION
        and growth.parameters.get("financial_validation_reason") == REVENUE_GROWTH_VALIDATION_REASON
    )
    revenue_semantics_passed = (
        revenue_positive_exact
        and revenue_nonpositive_rejected
        and revenue_formula_metadata
        and review_negative["zero_prior_blocked"]
        and review_negative["zero_prior_reason_stable"]
        and review_negative["negative_prior_blocked"]
        and review_negative["negative_prior_reason_stable"]
    )
    coverage = released.research_source_coverage
    first_partial = build_research_source_coverage(
        {
            "source_coverage": {
                "news": {"status": "AVAILABLE", "accepted_evidence_ids": ["E-NEWS"]},
                "transcript": {"status": "BLOCKED", "error_code": "HTTP_402"},
            }
        }
    )
    second_partial = build_research_source_coverage(
        {
            "source_coverage": {
                "news": {"status": "BLOCKED", "error_code": "HTTP_402"},
                "transcript": {
                    "status": "AVAILABLE",
                    "accepted_evidence_ids": ["E-TRANSCRIPT"],
                },
            }
        }
    )
    partial_coverage = (
        coverage is not None
        and first_partial.news.status is SourceCoverageStatus.AVAILABLE
        and first_partial.transcript.status is SourceCoverageStatus.BLOCKED
        and second_partial.news.status is SourceCoverageStatus.BLOCKED
        and second_partial.transcript.status is SourceCoverageStatus.AVAILABLE
        and dto.research_source_coverage == coverage
    )
    metrics_hash = metric_semantics_hash(tuple(metrics))
    cross_view = (
        tuple(dto.released_metrics) == tuple(metrics)
        and len(report_artifacts) == 3
        and all(item.metric_semantics_hash == metrics_hash for item in report_artifacts)
        and cross_view_content_passed
    )
    return {
        "FS-001": _gate(percent_rendering, {"percent_formula_count": 3}),
        "FS-002": _gate(decimal_preserved, {"decimal_boundary": "string"}),
        "FS-003": _gate(
            material_closure,
            {
                "material_calculation_count": len(calculations),
                "fundamental_calculation_ref_count": (
                    len(fundamental_refs) if fundamental_refs is not None else 0
                ),
                "technical_calculation_ref_count": (
                    len(technical_refs) if technical_refs is not None else 0
                ),
            },
        ),
        "FS-004": _gate(claim_closure, {"typed_claim_count": len(claims)}),
        "FS-005": _gate(
            reviewer_passed and revenue_semantics_passed,
            {
                "recomputation_check_count": len(recomputations),
                "revenue_formula": REVENUE_GROWTH_FORMULA_EXPRESSION,
                "revenue_precondition": REVENUE_GROWTH_PRECONDITION,
                "nonpositive_reason": REVENUE_GROWTH_VALIDATION_REASON,
            },
        ),
        "FS-006": _gate(
            review_negative["period_mismatch_blocked"], {"negative": "period_mismatch"}
        ),
        "FS-007": _gate(
            review_negative["unit_mismatch_blocked"]
            and review_negative["currency_mismatch_blocked"],
            {"negatives": ["unit_mismatch", "currency_mismatch"]},
        ),
        "FS-008": _gate(
            review_negative["cohort_mismatch_blocked"], {"negative": "cohort_mismatch"}
        ),
        "FS-009": _gate(generated_oracle_passed, {"validation_record_count": len(validations)}),
        "FS-010": _gate(
            technical_passed,
            {
                "technical_metric_count": len(technical),
                "macd_decimal_context_policy_id": policy.policy_id,
                "ambient_precisions": macd_determinism["ambient_precisions"],
                "decimal_variant_count": macd_determinism["decimal_variant_count"],
                "byte_variant_count": macd_determinism["byte_variant_count"],
            },
        ),
        "FS-011": _gate(proof_identity, {"proof_id": proof.proof_id if proof else None}),
        "FS-012": _gate(partial_coverage, {"partial_entitlement_directions": 2}),
        "FS-013": _gate(cross_view, {"metric_semantics_hash": metrics_hash}),
    }


def _same_canonical_decimal(left: Any, right: Any) -> bool:
    try:
        return canonical_decimal(left) == canonical_decimal(right)
    except (ArithmeticError, TypeError, ValueError):
        return False


def _macd_ambient_context_check(*, calculations: list[Any], evidence: list[Any]) -> dict[str, Any]:
    formula_ids = (
        "macd_line_close_12_26_adjust_false_v1",
        "macd_signal_close_12_26_9_adjust_false_v1",
        "macd_histogram_close_12_26_9_adjust_false_v1",
    )
    by_formula = {item.formula_id: item for item in calculations if item.formula_id in formula_ids}
    if set(by_formula) != set(formula_ids):
        return {
            "passed": False,
            "ambient_precisions": [10, 28, 50],
            "decimal_variant_count": 0,
            "byte_variant_count": 0,
        }
    line = by_formula[formula_ids[0]]
    if any(
        by_formula[formula_id].input_evidence_ids != line.input_evidence_ids
        for formula_id in formula_ids
    ):
        return {
            "passed": False,
            "ambient_precisions": [10, 28, 50],
            "decimal_variant_count": 0,
            "byte_variant_count": 0,
        }
    evidence_by_id = {item.evidence_id: item for item in evidence}
    try:
        closes = [
            Decimal(str(evidence_by_id[evidence_id].normalized_value))
            for evidence_id in line.input_evidence_ids
        ]
        authoritative = tuple(Decimal(str(by_formula[item].output_value)) for item in formula_ids)
    except (KeyError, TypeError, ValueError):
        return {
            "passed": False,
            "ambient_precisions": [10, 28, 50],
            "decimal_variant_count": 0,
            "byte_variant_count": 0,
        }
    decimal_variants: set[tuple[Any, ...]] = set()
    byte_variants: set[bytes] = set()
    all_match = True
    for precision in (10, 28, 50):
        with localcontext() as ambient:
            ambient.prec = precision
            value = moving_average_convergence_divergence(closes)
        result = (value.line, value.signal, value.histogram)
        all_match = all_match and result == authoritative
        decimal_variants.add(tuple(item.as_tuple() for item in result))
        byte_variants.add(
            json.dumps(
                [canonical_decimal(item) for item in result],
                separators=(",", ":"),
            ).encode("utf-8")
        )
    return {
        "passed": all_match and len(decimal_variants) == len(byte_variants) == 1,
        "ambient_precisions": [10, 28, 50],
        "decimal_variant_count": len(decimal_variants),
        "byte_variant_count": len(byte_variants),
    }


def _report_content_matches_metrics(
    *,
    metrics: tuple[Any, ...],
    chart_path: Path,
    html_path: Path,
    pdf_path: Path,
) -> bool:
    chart_text = chart_path.read_text(encoding="utf-8")
    html_text = html_path.read_text(encoding="utf-8")
    pdf_text = pdf_path.read_text(encoding="latin-1")
    for metric in metrics:
        chart_tokens = (
            metric.metric_id,
            metric.period,
            metric.as_of.isoformat(),
            metric.display_unit,
            format(Decimal(metric.display_value).normalize(), "f"),
        )
        document_tokens = (
            metric.metric_id,
            metric.canonical_value,
            metric.display_value,
            metric.display_unit,
            metric.period,
            metric.as_of.isoformat(),
        )
        if not all(token in chart_text for token in chart_tokens):
            return False
        if not all(token in html_text and token in pdf_text for token in document_tokens):
            return False
    return True


def _gate(passed: bool, evidence: Any) -> dict[str, Any]:
    return {"status": "PASS" if passed else "FAIL", "evidence": evidence}


def _audit_generated_artifact_retention(
    *,
    store: GeneratedCapabilityArtifactStore,
    expected_provider: str,
    expected_model: str,
    gaps: list[CapabilityGapRecord],
    records: list[GeneratedCapabilityArtifactRecord],
    builds: list[CapabilityBuildRecord],
    generated: list[GeneratedCapabilityRecord],
    validations: list[CapabilityValidationRecord],
    sandboxes: list[SandboxExecutionRecord],
) -> dict[str, Any]:
    active = [item for item in generated if item.lifecycle is CapabilityLifecycle.ACTIVE_FOR_SCOPE]
    if not (len(records) == len(active) == len(validations) == len(sandboxes) == 1):
        return {
            "passed": False,
            "binding_count": len(records),
            "active_generated_count": len(active),
        }
    record = records[0]
    generated_record = active[0]
    validation = validations[0]
    sandbox = sandboxes[0]
    retained_builds = [item for item in builds if item.build_id == record.build_id]
    retained_gaps = [item for item in gaps if item.gap_id == generated_record.gap_id]
    try:
        if len(retained_gaps) != 1:
            raise ValueError("accepted Generated Capability gap identity is unavailable")
        owned_request = GeneratedCapabilityRequestV1.from_requirement(
            retained_gaps[0].gap_id,
            retained_gaps[0].requirement,
        )
        reconstructed = store.reconstruct_from_spec(record, owned_request)
        sandbox_input = reconstructed.sandbox_request({"audit_reconstruction": "1"})
    except (OSError, UnicodeError, ValueError):
        return {
            "passed": False,
            "binding_count": 1,
            "build_id": record.build_id,
            "retrieval_verified": False,
            "build_provider_verified": False,
            "source_retrieved": False,
            "tests_retrieved": False,
            "source_hash_verified": False,
            "test_hash_verified": False,
            "sandbox_input_reconstructed": False,
        }
    passed = (
        len(retained_builds) == 1
        and retained_builds[0].provider == expected_provider
        and retained_builds[0].actual_model == expected_model
        and reconstructed.compiler_id == GENERATED_CAPABILITY_COMPILER_ID
        and reconstructed.compiler_version == GENERATED_CAPABILITY_COMPILER_VERSION
        and reconstructed.spec_bytes is not None
        and reconstructed.spec_sha256 is not None
        and record.generated_capability_id == generated_record.generated_capability_id
        and record.capability_id == generated_record.capability_id
        and record.capability_version == generated_record.capability_version
        and record.build_id == validation.build_id == sandbox.build_id
        and record.implementation_hash
        == record.source_sha256
        == generated_record.implementation_hash
        == validation.source_hash
        == validation.implementation_hash
        == sandbox.implementation_hash
        and record.test_sha256 == validation.tests_hash
        and record.runtime_image_identity == sandbox.runtime_image_identity
        and sandbox_input.source.encode("utf-8") == reconstructed.source_bytes
        and sandbox_input.test_source.encode("utf-8") == reconstructed.test_bytes
    )
    return {
        "passed": passed,
        "binding_count": 1,
        "build_id": record.build_id,
        "source_artifact_id": record.source_artifact_id,
        "source_sha256": record.source_sha256,
        "source_size_bytes": record.source_size_bytes,
        "test_artifact_id": record.test_artifact_id,
        "test_sha256": record.test_sha256,
        "test_size_bytes": record.test_size_bytes,
        "implementation_hash": record.implementation_hash,
        "runtime_image_identity": record.runtime_image_identity,
        "spec_sha256": reconstructed.spec_sha256,
        "spec_size_bytes": len(reconstructed.spec_bytes or b""),
        "compiler_id": reconstructed.compiler_id,
        "compiler_version": reconstructed.compiler_version,
        "compiler_runtime_policy": reconstructed.compiler_runtime_policy,
        "spec_compiler_reconstruction_verified": True,
        "build_provider_verified": len(retained_builds) == 1
        and retained_builds[0].provider == expected_provider
        and retained_builds[0].actual_model == expected_model,
        "retrieval_verified": True,
        "source_retrieved": True,
        "tests_retrieved": True,
        "source_hash_verified": True,
        "test_hash_verified": True,
        "sandbox_input_reconstructed": True,
    }


def _acceptance_matrix(
    *,
    aggregate: Any,
    events: list[Any],
    gaps: list[CapabilityGapRecord],
    builds: list[CapabilityBuildRecord],
    generated: list[GeneratedCapabilityRecord],
    generated_artifacts: list[GeneratedCapabilityArtifactRecord],
    validations: list[CapabilityValidationRecord],
    sandboxes: list[SandboxExecutionRecord],
    registrations: list[ScopedCapabilityRegistration],
    proof_policies: list[ProofPolicyDecision],
    proof_inputs: list[ProofInputCommitment],
    proofs: list[ProofRecord],
    verifications: list[ProofVerificationRecord],
    proof_artifacts: list[ProofArtifactReference],
    report_artifacts: list[ReportArtifactRecord],
    negative: dict[str, bool],
    sandbox_backend: DockerSandboxBackend,
    no_refetch: bool,
    chart_provenance_passed: bool,
    finrobot_allowlist_passed: bool,
    finrobot_attribution_passed: bool,
    finrobot_rejected_operations: Mapping[str, bool],
    registry_scope_passed: bool,
    events_integrity_passed: bool,
    dto_immutable_passed: bool,
    artifact_files_passed: bool,
    proof_fail_closed_passed: bool,
    candidate: Mapping[str, Any],
    runtime: Mapping[str, Any],
    generated_retention_audit: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    event_types = [event.type.value for event in events]
    generated_calculations = [
        item
        for item in aggregate.artifacts.calculations
        if item.capability_id == FCF_MARGIN_CAPABILITY_ID
    ]
    active_generated = [
        item for item in generated if item.lifecycle is CapabilityLifecycle.ACTIVE_FOR_SCOPE
    ]
    generated_attempts_classified = len(active_generated) == 1 and all(
        item.lifecycle
        in {
            CapabilityLifecycle.ACTIVE_FOR_SCOPE,
            CapabilityLifecycle.BUILD_FAILED,
        }
        for item in generated
    )
    technical_ids = {
        "technical_sma_50",
        "technical_sma_200",
        "technical_rsi_14",
        "technical_macd_12_26_9",
        "technical_volume_ratio_20",
    }
    technical = [
        item for item in aggregate.artifacts.calculations if item.capability_id in technical_ids
    ]
    accepted_ids = {item.evidence_id for item in aggregate.artifacts.evidence}
    profile = sandbox_backend.security_profile
    attestation = sandboxes[0].security_attestation if len(sandboxes) == 1 else {}
    forbidden_environment_names = {
        "FMP_API_KEY",
        "FMP_API_KEY_1",
        "FMP_API_KEY_2",
        "FMP_API_KEY_3",
        "FMP_API_KEY_4",
        "TEAMOROUTER_API_KEY",
        "MIMO_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "DATABASE_URL",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
    }
    html_record = next(
        (item for item in report_artifacts if item.artifact_type == "text/html"), None
    )
    pdf_record = next(
        (item for item in report_artifacts if item.artifact_type == "application/pdf"), None
    )
    proof = proofs[0] if len(proofs) == 1 else None
    proof_input = proof_inputs[0] if len(proof_inputs) == 1 else None
    verification = verifications[0] if len(verifications) == 1 else None
    growth_calculations = [
        item for item in aggregate.artifacts.calculations if item.capability_id == "revenue_growth"
    ]
    growth = growth_calculations[0] if len(growth_calculations) == 1 else None
    must_prove_policies = [
        item for item in proof_policies if item.requirement is ProofRequirement.MUST_PROVE
    ]
    matrix = {
        "P3-CAP-001": _gate(len(gaps) == 1, "one persisted capability gap"),
        "P3-CAP-002": _gate(
            bool(builds) and all(item.approved_by == "research_lead" for item in builds),
            "Research Lead signed every build attempt",
        ),
        "P3-CAP-003": _gate(
            generated_retention_audit.get("build_provider_verified") is True
            and generated_retention_audit.get("source_retrieved") is True,
            dict(generated_retention_audit),
        ),
        "P3-CAP-004": _gate(
            len(validations) == 1
            and validations[0].static_validation_passed
            and generated_retention_audit.get("source_retrieved") is True
            and generated_retention_audit.get("source_hash_verified") is True,
            dict(generated_retention_audit),
        ),
        "P3-CAP-005": _gate(
            len(sandboxes) == 1
            and sandboxes[0].network_disabled
            and attestation.get("external_connect_blocked") is True,
            "Docker network=none and the runtime network probe was blocked",
        ),
        "P3-CAP-006": _gate(
            profile.get("host_mounts") == []
            and profile.get("read_only_root") is True
            and profile.get("user") == "65534:65534"
            and profile.get("cap_drop") == "ALL"
            and profile.get("no_new_privileges") is True
            and attestation.get("root_write_blocked") is True
            and attestation.get("non_root") is True
            and attestation.get("capabilities_effective") == "0000000000000000"
            and attestation.get("no_new_privileges") is True
            and forbidden_environment_names.isdisjoint(
                set(attestation.get("environment_names", []))
            ),
            "sandbox has no host mounts, read-only root, non-root user, and no privileges",
        ),
        "P3-CAP-007": _gate(
            len(sandboxes) == 1
            and sandboxes[0].passed
            and sandboxes[0].read_only_root
            and sandboxes[0].non_root_user
            and {
                "memory",
                "cpus",
                "pids",
                "wall_timeout_seconds",
            }.issubset(sandboxes[0].resource_limits)
            and all(attestation.get(key) for key in ("memory_max", "cpu_max", "pids_max")),
            "memory/CPU/PID/wall limits persisted",
        ),
        "P3-CAP-008": _gate(
            len(validations) == 1
            and validations[0].unit_tests_passed
            and generated_retention_audit.get("tests_retrieved") is True
            and generated_retention_audit.get("test_hash_verified") is True
            and generated_retention_audit.get("sandbox_input_reconstructed") is True,
            dict(generated_retention_audit),
        ),
        "P3-CAP-009": _gate(
            len(validations) == 1
            and validations[0].financial_invariants_passed
            and validations[0].financial_validation_passed,
            "owned invariants and financial oracle passed",
        ),
        "P3-CAP-010": _gate(
            len(validations) == 1 and validations[0].deterministic_double_run_passed,
            "identical canonical output across deterministic reruns",
        ),
        "P3-CAP-011": _gate(
            generated_attempts_classified
            and len(validations) == len(sandboxes) == 1
            and len(generated_artifacts) == 1
            and generated_retention_audit.get("passed") is True
            and active_generated[0].implementation_hash
            == validations[0].implementation_hash
            == sandboxes[0].implementation_hash,
            dict(generated_retention_audit),
        ),
        "P3-CAP-012": _gate(
            all(
                name in event_types
                for name in (
                    "capability.approved",
                    "capability.registered",
                    "task.resumed",
                )
            )
            and event_types.index("capability.approved")
            < event_types.index("capability.registered")
            < event_types.index("task.resumed")
            and events_integrity_passed,
            "TASK approval precedes registration and resume",
        ),
        "P3-CAP-013": _gate(
            len(registrations) == 1
            and registrations[0].lifecycle is CapabilityLifecycle.ACTIVE_FOR_SCOPE,
            "validated capability active in scoped overlay",
        ),
        "P3-CAP-014": _gate(
            len(registrations) == 1
            and any(
                event.type.value == "task.waiting_for_capability"
                and event.task_id == registrations[0].task_id
                for event in events
            )
            and any(
                event.type.value == "task.resumed" and event.task_id == registrations[0].task_id
                for event in events
            ),
            "original Research Task resumed",
        ),
        "P3-CAP-015": _gate(
            len(generated_calculations) == 1
            and generated_attempts_classified
            and len(registrations) == 1
            and registrations[0].generated_capability_ref
            == active_generated[0].generated_capability_id
            and generated_calculations[0].run_id
            == active_generated[0].run_id
            == aggregate.run.run_id
            and generated_calculations[0].task_id == active_generated[0].task_id
            and generated_calculations[0].capability_id == active_generated[0].capability_id
            and generated_calculations[0].capability_version
            == active_generated[0].capability_version
            == registrations[0].capability_version
            and generated_calculations[0].formula_id == active_generated[0].formula_id
            and generated_calculations[0].implementation_hash
            == active_generated[0].implementation_hash
            and generated_calculations[0].source_ref == active_generated[0].source_ref
            and generated_calculations[0].runtime_version == active_generated[0].runtime_version
            and set(generated_calculations[0].input_evidence_ids).issubset(accepted_ids)
            and generated_calculations[0].output_value is not None
            and bool(generated_calculations[0].output_unit)
            and generated_calculations[0].status.value == "PASS",
            "generated financial CalculationRecord emitted",
        ),
        "P3-CAP-016": _gate(
            len(registrations) == 1
            and registrations[0].scope is CapabilityScope.TASK
            and registry_scope_passed,
            "registration remained TASK-scoped and the global registry was unchanged",
        ),
        "P3-ZK-001": _gate(
            proof is not None and proof.backend == "risc0", "real RISC Zero backend"
        ),
        "P3-ZK-002": _gate(
            proof is not None
            and proof.image_id == EXPECTED_REVENUE_GROWTH_IMAGE_ID
            and runtime.get("risc0_image_id") == EXPECTED_REVENUE_GROWTH_IMAGE_ID
            and runtime.get("risc0_host_sha256") == EXPECTED_REVENUE_GROWTH_HOST_SHA256
            and candidate.get("risc0_manifest_host_sha256") == EXPECTED_REVENUE_GROWTH_HOST_SHA256
            and candidate.get("risc0_manifest_image_id") == EXPECTED_REVENUE_GROWTH_IMAGE_ID
            and _is_sha256_identity(candidate.get("risc0_release_manifest_sha256"))
            and _is_sha256_identity(candidate.get("risc0_source_set_sha256"))
            and _is_sha256_identity(candidate.get("risc0_guest_elf_sha256"))
            and _is_sha256_identity(candidate.get("risc0_guest_binary_sha256"))
            and int(candidate.get("risc0_reproducible_build_count", 0)) >= 2,
            {
                "image_id": EXPECTED_REVENUE_GROWTH_IMAGE_ID,
                "host_sha256": EXPECTED_REVENUE_GROWTH_HOST_SHA256,
                "release_manifest_sha256": candidate.get("risc0_release_manifest_sha256"),
                "source_set_sha256": candidate.get("risc0_source_set_sha256"),
                "guest_elf_sha256": candidate.get("risc0_guest_elf_sha256"),
                "guest_binary_sha256": candidate.get("risc0_guest_binary_sha256"),
                "reproducible_build_count": candidate.get("risc0_reproducible_build_count"),
                "risc0_build_version": candidate.get("risc0_build_version"),
                "risc0_zkvm_version": candidate.get("risc0_zkvm_version"),
            },
        ),
        "P3-ZK-003": _gate(
            proof_input is not None
            and proof is not None
            and growth is not None
            and proof_input.run_id == growth.run_id == proof.run_id
            and proof_input.calculation_id == growth.calculation_id == proof.calculation_id
            and proof_input.formula_id == growth.formula_id
            and proof_input.capability_id == growth.capability_id,
            "proof input commitment binds CalculationRecord",
        ),
        "P3-ZK-004": _gate(
            proof_input is not None
            and proof is not None
            and growth is not None
            and proof_input.implementation_hash
            == proof.implementation_hash
            == growth.implementation_hash,
            "proof binds owned implementation hash",
        ),
        "P3-ZK-005": _gate(
            proof_input is not None
            and proof is not None
            and growth is not None
            and proof_input.input_evidence_refs == growth.input_evidence_ids
            and proof_input.input_commitment == proof.input_commitment,
            "two ordered evidence references bound",
        ),
        "P3-ZK-006": _gate(
            proof is not None
            and proof.receipt_artifact_ref is not None
            and proof.receipt_hash is not None
            and Path(proof.receipt_artifact_ref).is_file()
            and _file_hash(Path(proof.receipt_artifact_ref)) == proof.receipt_hash,
            "real receipt artifact exists",
        ),
        "P3-ZK-007": _gate(
            verification is not None
            and proof is not None
            and verification.proof_id == proof.proof_id
            and verification.image_id == proof.image_id
            and verification.receipt_hash == proof.receipt_hash
            and verification.journal_hash == proof.journal_hash
            and verification.verified
            and verification.status is ProofStatus.VERIFIED,
            "independent verifier passed",
        ),
        "P3-ZK-008": _gate(
            negative["zero_prior_fail"]
            and negative["negative_prior_fail"]
            and negative["tampered_previous_revenue_fail"]
            and negative["tampered_current_revenue_fail"],
            "nonpositive prior and independent previous/current tampering rejected",
        ),
        "P3-ZK-009": _gate(
            negative["tampered_expected_result_fail"], "tampered expected result rejected"
        ),
        "P3-ZK-010": _gate(
            negative["wrong_image_fail"]
            and negative["wrong_program_fail"]
            and negative["corrupted_receipt_fail"],
            "wrong image/program and corrupted receipt rejected",
        ),
        "P3-ZK-011": _gate(
            proof is not None
            and len(proof_artifacts) == 1
            and proof_artifacts[0].proof_id == proof.proof_id
            and proof_artifacts[0].artifact_ref == proof.receipt_artifact_ref
            and proof_artifacts[0].content_hash == proof.receipt_hash,
            "ProofRecord and receipt reference persisted",
        ),
        "P3-ZK-012": _gate(
            proof is not None
            and aggregate.artifacts.canonical_record is not None
            and aggregate.artifacts.canonical_record.proof_refs == [proof.proof_id],
            "CanonicalExecutionRecord references ProofRecord",
        ),
        "P3-ZK-013": _gate(
            proof is not None
            and proof.status is ProofStatus.VERIFIED
            and len(proof_policies) == len(MATERIAL_FORMULAS)
            and {item.calculation_id for item in proof_policies}
            == {item.calculation_id for item in aggregate.artifacts.calculations}
            and len(must_prove_policies) == 1
            and must_prove_policies[0].calculation_id == proof.calculation_id
            and aggregate.run.status is RunStatus.RELEASED
            and proof_fail_closed_passed,
            "MUST_PROVE accepted only VERIFIED proof before release",
        ),
        "P3-ZK-014": _gate(
            "RISC0_DEV_MODE" not in os.environ
            and negative["risc0_dev_mode_presence_fail"]
            and proof is not None
            and negative["original_input_pass"],
            "formal mode valid and RISC0_DEV_MODE presence fails closed",
        ),
        "P3-FIN-001": _gate(
            technical_ids.issubset({item.capability_id for item in technical}),
            "owned technical ports emitted calculations",
        ),
        "P3-FIN-002": _gate(
            bool(technical)
            and all(item.source_ref and "fmp" not in item.source_ref.lower() for item in technical),
            "technical ports contain no provider fetch path",
        ),
        "P3-FIN-003": _gate(
            bool(technical)
            and all(set(item.input_evidence_ids).issubset(accepted_ids) for item in technical),
            "indicator inputs are accepted evidence IDs",
        ),
        "P3-FIN-004": _gate(
            len(technical) == 7
            and {item.formula_id for item in technical} == set(TECHNICAL_FORMULAS)
            and all(
                item.output_value is not None and item.status.value == "PASS" for item in technical
            ),
            "numeric indicator outputs are CalculationRecords",
        ),
        "P3-FIN-005": _gate(chart_provenance_passed, "chart consumed CanonicalReportDTO"),
        "P3-FIN-006": _gate(no_refetch, "chart renderer caused no provider request"),
        "P3-FIN-007": _gate(
            html_record is not None and dto_immutable_passed,
            "HTML consumed a recursively immutable DTO",
        ),
        "P3-FIN-008": _gate(
            html_record is not None
            and pdf_record is not None
            and html_record.semantic_hash == pdf_record.semantic_hash,
            "PDF consumed the same immutable DTO",
        ),
        "P3-FIN-009": _gate(no_refetch, "HTML/PDF caused no FMP or LLM calls"),
        "P3-FIN-010": _gate(
            len(report_artifacts) == 3
            and artifact_files_passed
            and aggregate.artifacts.canonical_record is not None
            and aggregate.artifacts.released_result is not None
            and all(
                item.content_hash
                and item.canonical_record_id == aggregate.artifacts.canonical_record.record_id
                and item.released_result_id == aggregate.artifacts.released_result.result_id
                for item in report_artifacts
            ),
            "three report artifact hashes persisted",
        ),
        "P3-FIN-011": _gate(
            "Apache-2.0" in UPSTREAM_ATTRIBUTION and finrobot_attribution_passed,
            "FinRobot Apache-2.0 attribution retained in SVG, HTML, and PDF",
        ),
        "P3-FIN-012": _gate(
            finrobot_allowlist_passed
            and set(finrobot_rejected_operations)
            == {
                "autogen.run",
                "web.orchestrate",
                "llm.generate_section",
                "valuation.calculate_dcf",
                "sensitivity.run",
            }
            and all(finrobot_rejected_operations.values()),
            {
                "allowlist": ["charts.render", "report.render_pdf"],
                "rejected_operations": dict(sorted(finrobot_rejected_operations.items())),
            },
        ),
    }
    return matrix


def _all_gates_pass(
    matrix: Mapping[str, Mapping[str, Any]],
    *,
    prefix: str,
) -> bool:
    selected = [result for gate, result in matrix.items() if gate.startswith(prefix)]
    return bool(selected) and all(result.get("status") == "PASS" for result in selected)


def _integration_matrix(
    *,
    run_id: str,
    regressions: Mapping[str, Mapping[str, Any]],
    phase2_1_semantic_failed: list[str],
    postgresql: Mapping[str, Any],
    langfuse: Mapping[str, Any],
    capability_matrix: Mapping[str, Mapping[str, Any]],
    proof_matrix: Mapping[str, Mapping[str, Any]],
    financial_matrix: Mapping[str, Mapping[str, Any]],
    proof_ids: list[str],
    report_artifacts: list[ReportArtifactRecord],
    security: Mapping[str, Any],
    restore: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        "P3-INT-001": _gate(bool(regressions["phase1"]["passed"]), dict(regressions["phase1"])),
        "P3-INT-002": _gate(bool(regressions["phase2"]["passed"]), dict(regressions["phase2"])),
        "P3-INT-003": _gate(
            bool(regressions["phase2_1"]["passed"]) and not phase2_1_semantic_failed,
            {
                "regression": dict(regressions["phase2_1"]),
                "semantic_failed": phase2_1_semantic_failed,
            },
        ),
        "P3-INT-004": _gate(bool(postgresql.get("passed")), dict(postgresql)),
        "P3-INT-005": _gate(bool(langfuse.get("passed")), dict(langfuse)),
        "P3-INT-006": _gate(
            _all_gates_pass(capability_matrix, prefix="P3-CAP-"),
            {
                "run_id": run_id,
                "gate_count": len(capability_matrix),
            },
        ),
        "P3-INT-007": _gate(
            _all_gates_pass(proof_matrix, prefix="P3-ZK-"),
            {
                "run_id": run_id,
                "gate_count": len(proof_matrix),
                "real_backend": "risc0",
                "proof_ids": proof_ids,
            },
        ),
        "P3-INT-008": _gate(
            _all_gates_pass(financial_matrix, prefix="P3-FIN-"),
            {
                "run_id": run_id,
                "gate_count": len(financial_matrix),
                "artifacts": [
                    {
                        "artifact_id": item.artifact_id,
                        "content_hash": item.content_hash,
                        "artifact_type": item.artifact_type,
                    }
                    for item in report_artifacts
                ],
            },
        ),
        "P3-INT-009": _gate(bool(security.get("passed")), dict(security)),
        "P3-INT-010": _gate(bool(restore.get("passed")), dict(restore)),
    }


def _expected_core_gate_ids() -> set[str]:
    return {
        *(f"P3-CAP-{index:03d}" for index in range(1, 17)),
        *(f"P3-ZK-{index:03d}" for index in range(1, 15)),
        *(f"P3-FIN-{index:03d}" for index in range(1, 13)),
        *(f"P3-INT-{index:03d}" for index in range(1, 11)),
    }


def _expected_financial_semantic_gate_ids() -> set[str]:
    return {f"FS-{index:03d}" for index in range(1, 14)}


async def _run_authoritative(
    output_root: Path,
    *,
    host_binary: Path,
    candidate_head: str,
    run_id: str,
    audit_state: dict[str, Any],
    fmp_credential_alias: str,
    env_file: Path | None = None,
) -> dict[str, Any]:
    repository_root = await asyncio.to_thread(_repository_root)
    audit_state["failed_stage"] = "repository_preflight"
    if await asyncio.to_thread(_working_directory) != repository_root:
        raise RuntimeError("Phase 3 acceptance must run from the repository root")
    audit_state["failed_stage"] = "candidate_preflight"
    candidate = await asyncio.to_thread(_candidate_preflight, repository_root, candidate_head)
    audit_state["candidate"] = candidate
    audit_state["failed_stage"] = "frozen_regressions"
    regressions = await asyncio.to_thread(_run_regression_suites, repository_root)
    audit_state["regressions"] = regressions
    failed_regressions = [name for name, result in regressions.items() if not result["passed"]]
    if failed_regressions:
        raise RuntimeError(f"frozen regression suites failed: {failed_regressions}")
    if not await asyncio.to_thread(_candidate_still_immutable, repository_root, candidate):
        raise RuntimeError("candidate changed while regression gates executed")
    audit_state["failed_stage"] = "runtime_output_preflight"
    output_root = _resolve_safe_path(output_root, label="Phase 3 acceptance output root")
    allowed_output_root = (repository_root / "artifacts" / "phase3" / "acceptance").resolve()
    try:
        output_root.relative_to(allowed_output_root)
    except ValueError as exc:
        raise RuntimeError("Phase 3 acceptance output must remain in its controlled root") from exc
    output = output_root / run_id
    if output.exists() or output.is_symlink():
        raise RuntimeError("authoritative Phase 3 Run output already exists")
    await asyncio.to_thread(output.mkdir, parents=True, exist_ok=False)
    audit_state["output_created"] = True
    host_binary = _resolve_safe_path(host_binary, label="RISC Zero host binary", must_exist=True)
    runtime = await asyncio.to_thread(_preflight_formal_runtime, host_binary)
    audit_state["runtime"] = runtime
    audit_state["failed_stage"] = "settings_preflight"
    settings = Settings() if env_file is None else Settings(_env_file=env_file)
    if not fmp_credential_alias or any(
        not (character.isalnum() or character in {"-", "_"}) for character in fmp_credential_alias
    ):
        raise RuntimeError("FMP credential alias must be bound before the Run")
    if (
        not settings.fmp.enabled
        or not (settings.mimo.enabled or settings.llm.enabled)
        or not settings.langfuse.enabled
    ):
        raise RuntimeError("FMP, a governed planner provider, and Langfuse must be configured")
    audit_state["fmp_credential_alias"] = fmp_credential_alias

    audit_state["failed_stage"] = "postgresql_migration"
    alembic_location = await asyncio.to_thread(_alembic_location)
    migration_head = await asyncio.to_thread(_alembic_head, alembic_location)
    pre_migration = create_postgresql_persistence(settings.database)
    try:
        async with pre_migration.engine.connect() as connection:
            migration_before = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
    finally:
        await pre_migration.close()
    await asyncio.to_thread(upgrade_postgresql_database, settings.database)
    persistence = create_postgresql_persistence(settings.database)
    async with persistence.engine.connect() as connection:
        migration_current = (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one()
    if migration_current != migration_head:
        raise RuntimeError("PostgreSQL migration current revision does not match Alembic head")
    references = InMemoryTraceReferenceRepository()
    sensitive_values = {
        **{
            f"FMP_API_KEY_SLOT_{index}": secret.get_secret_value()
            for index, secret in enumerate(settings.fmp.credentials, start=1)
        },
        **{
            name: secret.get_secret_value()
            for name, secret in {
                "TEAMOROUTER_API_KEY": settings.llm.api_key,
                "MIMO_API_KEY": settings.mimo.api_key,
            }.items()
            if secret is not None and secret.get_secret_value()
        },
    }
    trace_build = create_langfuse_trace_adapter(
        settings.langfuse,
        additional_sensitive_values=sensitive_values,
    )
    if not trace_build.enabled:
        raise RuntimeError(f"Langfuse adapter is not enabled: {trace_build.classification.value}")
    audited_trace = AuditedTraceAdapter(trace_build.adapter)
    instrumentation = RuntimeInstrumentation(
        audited_trace,
        reference_repository=references,
    )
    llm_http_counter = LLMRequestCounter()
    llm_http_client = httpx.AsyncClient(
        event_hooks={"request": [llm_http_counter.on_request]}, timeout=60.0
    )
    fmp_transport = CountingFMPTransport(HttpxFMPTransport(settings.fmp))
    planner_providers: list[LLMProvider] = []
    if settings.mimo.enabled:
        planner_providers.append(
            MimoClient(settings.mimo, client=llm_http_client, timeout_seconds=60.0)
        )
    if settings.llm.enabled:
        planner_providers.append(
            TeamoRouterClient(settings.llm, client=llm_http_client, timeout_seconds=60.0)
        )
    planner_router = WorkloadProviderRouter(planner_providers)
    audit_state["failed_stage"] = "workload_provider_preflight"
    try:
        provider_bindings = await planner_router.select(
            {
                PlannerWorkload.SCHEME_PLANNER: _scheme_provider_preflight,
                PlannerWorkload.LEAD_PLANNER: _lead_provider_preflight,
                PlannerWorkload.GENERATED_CAPABILITY: (_generated_capability_provider_preflight),
            }
        )
    except WorkloadProviderUnavailableError as exc:
        audit_state["run_provider_bindings"] = {
            "policy_id": "MIMO_PRIMARY_TEAMOROUTER_SECONDARY_V2",
            "failed_workload": exc.workload_type.value,
            "health_checks": [item.safe_evidence() for item in exc.health_checks],
            "binding_map_locked": False,
            "mid_run_failover_enabled": False,
        }
        audit_state["planner_provider_selection"] = audit_state["run_provider_bindings"]
        raise
    provider_bindings_evidence = provider_bindings.safe_evidence()
    provider_bindings_evidence["generated_capability_compiler_id"] = (
        GENERATED_CAPABILITY_COMPILER_ID
    )
    provider_bindings_evidence["generated_capability_compiler_version"] = (
        GENERATED_CAPABILITY_COMPILER_VERSION
    )
    audit_state["run_provider_bindings"] = provider_bindings_evidence
    audit_state["planner_provider_selection"] = provider_bindings_evidence
    _write_json(
        output / "run_provider_bindings.json",
        {
            "run_id": run_id,
            "candidate_head": candidate["candidate_head"],
            "fmp_credential_alias": fmp_credential_alias,
            **provider_bindings_evidence,
        },
    )
    planner_preflight_http_attempts = llm_http_counter.http_attempts
    scheme_binding = provider_bindings.binding_for(PlannerWorkload.SCHEME_PLANNER)
    lead_binding = provider_bindings.binding_for(PlannerWorkload.LEAD_PLANNER)
    generated_binding = provider_bindings.binding_for(PlannerWorkload.GENERATED_CAPABILITY)
    scheme_llm = CountingLLMProvider(scheme_binding.provider)
    lead_llm = CountingLLMProvider(lead_binding.provider)
    generated_llm = CountingLLMProvider(generated_binding.provider)
    workload_llms = (scheme_llm, lead_llm, generated_llm)
    sandbox = DockerSandboxBackend()
    generated_artifact_store = GeneratedCapabilityArtifactStore(
        output / "generated",
        forbidden_values=_credential_needles(settings),
    )
    proof_root = output / "proof"
    adapter = RiscZeroProofAdapter(
        host_binary=host_binary,
        artifact_dir=proof_root,
        timeout_seconds=1_800,
    )

    try:
        selection = select_financial_provider(
            mode=FinancialProviderMode.FMP,
            fmp_settings=settings.fmp,
            fixture_path=repository_root / "tests/fixtures/nvda_financials.json",
            transport=fmp_transport,
        )
        if not isinstance(selection.provider, FMPProvider):
            raise RuntimeError("live FMP provider was not selected")
        collector = LiveFMPEvidenceCollector.with_local_artifacts(
            provider=selection.provider,
            repository=persistence.evidence_repository,
            artifact_root=output / "raw",
        )

        audit_state["failed_stage"] = "authoritative_nvda_chain"
        async with instrumentation.research_run(
            run_id=run_id,
            attributes={
                "object_id": "OBJ-NVDA",
                "phase": "phase3",
                "provider_selection_policy": provider_bindings.policy_id,
                "scheme_planner_provider": scheme_binding.provider_name,
                "scheme_planner_model": scheme_binding.model_name,
                "lead_planner_provider": lead_binding.provider_name,
                "lead_planner_model": lead_binding.model_name,
                "generated_capability_provider": generated_binding.provider_name,
                "generated_capability_model": generated_binding.model_name,
                "generated_capability_compiler_id": GENERATED_CAPABILITY_COMPILER_ID,
                "generated_capability_compiler_version": (GENERATED_CAPABILITY_COMPILER_VERSION),
                "mid_run_failover_enabled": False,
            },
        ) as trace:
            scheme_generator = PlannerProviderSchemeGenerator(
                InstrumentedLLMProvider(
                    scheme_llm,
                    trace=trace,
                    stage=ObservationStage.SCHEME_GENERATION,
                ),
                max_validation_attempts=3,
            )
            planner = PlannerProviderResearchLeadPlanner(
                InstrumentedLLMProvider(
                    lead_llm,
                    trace=trace,
                    stage=ObservationStage.PLANNER_GENERATION,
                ),
                max_validation_attempts=3,
            )
            service = ResearchApplicationService(
                repository=persistence.application_repository,
                evidence_repository=persistence.evidence_repository,
                evidence_collector=collector,
                scheme_generator=scheme_generator,
                planner=planner,
                event_store=persistence.event_store,
                checkpoint_store=persistence.checkpoint_store,
                instrumentation=instrumentation,
                trace_reference_repository=references,
                run_id_factory=lambda: run_id,
            )
            global_registry_before = tuple(
                item.model_dump(mode="json") for item in service.capability_registry.list()
            )
            generated_trace = GeneratedCapabilityTrace(audited_trace)
            scoped_registry = ScopedCapabilityRegistry(service.capability_registry)
            generated_orchestrator = GeneratedCapabilityOrchestrator(
                registry=scoped_registry,
                research_lead=Phase3ResearchLeadCapabilityAuthority(),
                code_builder=PlannerProviderCodeBuilder(
                    generated_llm,
                    trace=generated_trace,
                ),
                validator=GeneratedCapabilityValidator(
                    sandbox=sandbox,
                    plans=FreeCashFlowMarginValidationPlanProvider(),
                ),
                event_store=persistence.event_store,
                recorder=PostgreSQLCapabilityWorkflowRecorder(
                    persistence.phase3_record_repository,
                    artifact_store=generated_artifact_store,
                ),
                trace=generated_trace,
                max_attempts=2,
            )
            service.add_calculation_extension(
                Phase3FinancialCapabilityExtension(
                    generated=generated_orchestrator,
                    event_store=persistence.event_store,
                    instrumentation=instrumentation,
                )
            )
            service.proof_workflow = RevenueGrowthRiscZeroProofWorkflow(
                adapter=adapter,
                artifact_dir=proof_root,
                event_store=persistence.event_store,
                repository=persistence.phase3_record_repository,
                instrumentation=instrumentation,
            )

            research_object = await service.create_object(
                symbol="NVDA",
                company_name="NVIDIA Corporation",
                exchange="NASDAQ",
                idempotency_key=f"phase3-object-{run_id}",
            )
            run_as_of = datetime.now(UTC).date()
            draft = await service.prepare_run(
                research_object_id=research_object.object_id,
                research_goal=(
                    "Assess NVDA fundamentals, deterministic technical context, material risks, "
                    "and verification limitations with governed generated capability execution."
                ),
                as_of=run_as_of,
                preferences={"depth": "standard", "provider": "live_fmp", "phase": 3},
                observation_run_id=run_id,
            )
            aggregate = await service.confirm_run(
                draft_id=draft.draft_id,
                confirm_scheme=True,
                idempotency_key=f"phase3-confirm-{run_id}",
            )
            _write_json(output / "scheme_snapshot.json", aggregate.scheme.model_dump(mode="json"))
            _write_json(
                output / "planned_graph.json",
                aggregate.runtime.planned_graph.model_dump(mode="json"),
            )
            aggregate = await service.execute_run(run_id)
            if aggregate.run.status is not RunStatus.RELEASED:
                raise RuntimeError("Phase 3 run was not released")
            if (
                scheme_generator.last_audit is None
                or scheme_generator.last_audit.deterministic_fallback
            ):
                raise RuntimeError("real selected-provider scheme generation did not pass")
            if planner.last_audit is None or planner.last_audit.deterministic_fallback:
                raise RuntimeError("real selected-provider planner generation did not pass")
            for planner_audit in (scheme_generator.last_audit, planner.last_audit):
                expected_binding = (
                    scheme_binding if planner_audit is scheme_generator.last_audit else lead_binding
                )
                if (
                    planner_audit.provider != expected_binding.provider_name
                    or planner_audit.actual_model != expected_binding.model_name
                ):
                    raise RuntimeError("authoritative workload provider/model lock was violated")
            canonical = aggregate.artifacts.canonical_record
            released = aggregate.artifacts.released_result
            if canonical is None or released is None:
                raise RuntimeError("canonical and released records are required")
            if aggregate.artifacts.review is None:
                raise RuntimeError("review is required before proof release acceptance")
            scoped_runtime_registrations = scoped_registry.registrations()
            if len(scoped_runtime_registrations) != 1:
                raise RuntimeError("expected exactly one runtime scoped registration")
            runtime_registration = scoped_runtime_registrations[0]
            scoped_match = await scoped_registry.lookup(
                runtime_registration.capability_id,
                version=runtime_registration.capability_version,
                run_id=runtime_registration.run_id,
                task_id=runtime_registration.task_id or "",
            )
            sibling_task_match = await scoped_registry.lookup(
                runtime_registration.capability_id,
                version=runtime_registration.capability_version,
                run_id=runtime_registration.run_id,
                task_id="TASK-OUTSIDE-SCOPE",
            )
            sibling_run_match = await scoped_registry.lookup(
                runtime_registration.capability_id,
                version=runtime_registration.capability_version,
                run_id="RUN-OUTSIDE-SCOPE",
                task_id="TASK-OUTSIDE-SCOPE",
            )
            global_registry_after = tuple(
                item.model_dump(mode="json") for item in service.capability_registry.list()
            )
            registry_scope_passed = (
                scoped_match is not None
                and sibling_task_match is None
                and sibling_run_match is None
                and global_registry_after == global_registry_before
                and not service.capability_registry.is_available(
                    runtime_registration.capability_id,
                    runtime_registration.capability_version,
                )
            )

            proof = next(
                item for item in aggregate.artifacts.proofs if isinstance(item, ProofRecord)
            )
            release_gate = ReleaseGate()
            proof_requirements = {proof.calculation_id: ProofRequirement.MUST_PROVE}
            proof_fail_closed_passed = all(
                not release_gate.evaluate(
                    review=aggregate.artifacts.review,
                    proof_requirements=proof_requirements,
                    proofs=proofs,
                ).allowed
                for proofs in (
                    {},
                    {
                        proof.calculation_id: ProofResult(
                            proof_id="PROOF-NEGATIVE-VALID-BUT-UNVERIFIED",
                            status=ProofStatus.VALID,
                        )
                    },
                    {
                        proof.calculation_id: ProofResult(
                            proof_id="PROOF-NEGATIVE-INVALID",
                            status=ProofStatus.INVALID,
                        )
                    },
                    {
                        proof.calculation_id: ProofResult(
                            proof_id="PROOF-NEGATIVE-ERROR",
                            status=ProofStatus.ERROR,
                        )
                    },
                )
            )
            negative = await _negative_proof_checks(
                adapter=adapter,
                host_binary=host_binary,
                proof_root=proof_root,
                proof=proof,
            )
            if not all(negative.values()):
                raise RuntimeError("real RISC Zero negative verification matrix failed")

            external_before = (
                fmp_transport.total,
                sum(item.logical_calls for item in workload_llms),
                llm_http_counter.http_attempts,
            )
            raw_before = _tree_snapshot(output / "raw")
            released_before = _canonical_hash(released.model_dump(mode="json"))
            canonical_before = _canonical_hash(canonical.model_dump(mode="json"))
            dto = CanonicalReportMapper.map(released, canonical)
            if not isinstance(dto, CanonicalReportDTO):
                raise RuntimeError("report mapper did not return CanonicalReportDTO")
            dto_before = _canonical_hash(dto.model_dump(mode="json"))
            try:
                dto.provenance["__mutation_probe__"] = True
            except TypeError:
                dto_immutable_passed = all(
                    _is_recursively_frozen(getattr(dto, field_name))
                    for field_name in (
                        "structured_financial_results",
                        "released_claims",
                        "judgments",
                        "risk_output",
                        "limitations",
                        "calculation_refs",
                        "proof_refs",
                        "provenance",
                    )
                )
            else:  # pragma: no cover - hard acceptance failure
                dto_immutable_passed = False
            report_task_id = next(
                task.task_id
                for task in aggregate.runtime.actual_graph.tasks
                if task.task_type == "report_synthesis"
            )
            async with instrumentation.tool(
                run_id=run_id,
                task_id=report_task_id,
                attributes={
                    "tool_name": "finrobot_owned_svg_chart_port",
                    "upstream_commit": FINROBOT_PINNED_COMMIT,
                },
            ):
                pinned_renderer = PinnedFinRobotAdapter(
                    backend=DeterministicSVGChartBackend(output / "charts"),
                    source_revision=FINROBOT_PINNED_COMMIT,
                )
                chart = await CanonicalReportChartAdapter(pinned_renderer).render(dto)
            report_store = ControlledArtifactStore(output / "professional-reports")
            async with instrumentation.tool(
                run_id=run_id,
                task_id=report_task_id,
                attributes={
                    "tool_name": "finrobot_owned_professional_report_port",
                    "upstream_commit": FINROBOT_PINNED_COMMIT,
                },
            ):
                published = await asyncio.to_thread(
                    ProfessionalReportPublisher(report_store).publish, dto
                )
            report_records = [chart.record, published.html, published.pdf]
            external_after = (
                fmp_transport.total,
                sum(item.logical_calls for item in workload_llms),
                llm_http_counter.http_attempts,
            )
            no_refetch = (
                external_after == external_before
                and _tree_snapshot(output / "raw") == raw_before
                and _canonical_hash(released.model_dump(mode="json")) == released_before
                and _canonical_hash(canonical.model_dump(mode="json")) == canonical_before
                and _canonical_hash(dto.model_dump(mode="json")) == dto_before
            )
            if not no_refetch:
                raise RuntimeError("report rendering crossed the immutable/no-refetch boundary")

            chart_path = Path(chart.record.artifact_ref)
            html_path = report_store.resolve(published.html.artifact_ref)
            pdf_path = report_store.resolve(published.pdf.artifact_ref)
            artifact_paths = {
                chart.record.artifact_id: chart_path,
                published.html.artifact_id: html_path,
                published.pdf.artifact_id: pdf_path,
            }
            for record in report_records:
                path = artifact_paths[record.artifact_id]
                if not path.is_file() or path.stat().st_size != record.size_bytes:
                    raise RuntimeError(
                        f"report artifact is missing or truncated: {record.artifact_id}"
                    )
                if _file_hash(path) != record.content_hash:
                    raise RuntimeError(f"report artifact hash mismatch: {record.artifact_id}")
            artifact_files_passed = True
            if not _file_starts_with(html_path, b"<!doctype html>"):
                raise RuntimeError("professional HTML structure check failed")
            if not _file_starts_with(pdf_path, b"%PDF-"):
                raise RuntimeError("professional PDF structure check failed")
            chart_provenance_passed = (
                chart.upstream_commit == FINROBOT_PINNED_COMMIT
                and chart.license == "Apache-2.0"
                and chart.record.canonical_record_id == dto.canonical_record_id
                and chart.record.released_result_id == dto.released_result_id
                and chart.record.metric_semantics_hash
                == metric_semantics_hash(tuple(dto.released_metrics))
            )
            finrobot_allowlist_passed = set(pinned_renderer.supported_operations) == {
                "charts.render",
                "report.render_pdf",
            }
            finrobot_rejected_operations: dict[str, bool] = {}
            for operation in (
                "autogen.run",
                "web.orchestrate",
                "llm.generate_section",
                "valuation.calculate_dcf",
                "sensitivity.run",
            ):
                try:
                    await pinned_renderer.execute(operation, {})
                except (KeyError, NotImplementedError, RuntimeError, ValueError):
                    finrobot_rejected_operations[operation] = True
                else:
                    finrobot_rejected_operations[operation] = False
            finrobot_attribution_passed = all(
                b"FinRobot" in path.read_bytes() and b"Apache-2.0" in path.read_bytes()
                for path in (chart_path, html_path, pdf_path)
            )
            cross_view_content_passed = _report_content_matches_metrics(
                metrics=tuple(dto.released_metrics),
                chart_path=chart_path,
                html_path=html_path,
                pdf_path=pdf_path,
            )
            if not chart_provenance_passed:
                raise RuntimeError("chart provenance check failed")
            aggregate.artifacts.report_artifacts = report_records
            await persistence.phase3_record_repository.save_many(report_records, run_id=run_id)
            await persistence.application_repository.save_run(aggregate)
            trace_id = trace.trace_id

        await instrumentation.flush()
        if trace_build.drain_barrier is None:
            raise RuntimeError("Langfuse telemetry drain barrier is unavailable")
        expected_observation_identities = tuple(
            str(item.get("observation_id") or "") for item in audited_trace.observations
        )
        local_observation_identities_valid = (
            bool(expected_observation_identities)
            and all(expected_observation_identities)
            and len(set(expected_observation_identities)) == len(expected_observation_identities)
        )
        langfuse_redaction_audit = await asyncio.to_thread(
            trace_build.drain_barrier.audit,
            trace_id,
            expected_observation_identities=expected_observation_identities,
            expected_run_id=run_id,
        )
        identity_set_evidence = build_langfuse_identity_set_evidence(
            run_id=run_id,
            trace_id=trace_id,
            audit=langfuse_redaction_audit,
        )
        events = list(await persistence.event_store.replay(run_id))
        event_sequences = [item.sequence for item in events]
        events_integrity_passed = (
            event_sequences == list(range(1, len(events) + 1))
            and len({item.event_id for item in events}) == len(events)
            and {item.run_id for item in events} == {run_id}
            and bool(events)
            and events[-1].type.value == "run.completed"
            and all(item.type.value not in {"run.failed", "task.failed"} for item in events)
        )
        if not events_integrity_passed:
            raise RuntimeError("RuntimeEvent integrity or terminal ordering failed")
        checkpoint = await persistence.checkpoint_store.load_latest(run_id)
        if checkpoint is None:
            raise RuntimeError("PostgreSQL checkpoint was not persisted")

        repository = persistence.phase3_record_repository
        gaps = await repository.list(CapabilityGapRecord, run_id)
        builds = await repository.list(CapabilityBuildRecord, run_id)
        generated = await repository.list(GeneratedCapabilityRecord, run_id)
        generated_artifacts = await repository.list(GeneratedCapabilityArtifactRecord, run_id)
        validations = await repository.list(CapabilityValidationRecord, run_id)
        sandboxes = await repository.list(SandboxExecutionRecord, run_id)
        registrations = await repository.list(ScopedCapabilityRegistration, run_id)
        proof_policies = await repository.list(ProofPolicyDecision, run_id)
        proof_inputs = await repository.list(ProofInputCommitment, run_id)
        proofs = await repository.list(ProofRecord, run_id)
        verifications = await repository.list(ProofVerificationRecord, run_id)
        proof_artifacts = await repository.list(ProofArtifactReference, run_id)
        report_artifacts = await repository.list(ReportArtifactRecord, run_id)
        generated_retention_audit = _audit_generated_artifact_retention(
            store=generated_artifact_store,
            expected_provider=generated_binding.provider_name,
            expected_model=generated_binding.model_name,
            gaps=gaps,
            records=generated_artifacts,
            builds=builds,
            generated=generated,
            validations=validations,
            sandboxes=sandboxes,
        )
        proof_requirements_by_id = {
            item.calculation_id: item.requirement for item in proof_policies
        }
        review_negative = _financial_review_negative_checks(
            aggregate=aggregate,
            proof_requirements=proof_requirements_by_id,
        )
        audit_state["failed_stage"] = "core_gate_evaluation"
        matrix = _acceptance_matrix(
            aggregate=aggregate,
            events=events,
            gaps=gaps,
            builds=builds,
            generated=generated,
            generated_artifacts=generated_artifacts,
            validations=validations,
            sandboxes=sandboxes,
            registrations=registrations,
            proof_policies=proof_policies,
            proof_inputs=proof_inputs,
            proofs=proofs,
            verifications=verifications,
            proof_artifacts=proof_artifacts,
            report_artifacts=report_artifacts,
            negative=negative,
            sandbox_backend=sandbox,
            no_refetch=no_refetch,
            chart_provenance_passed=chart_provenance_passed,
            finrobot_allowlist_passed=finrobot_allowlist_passed,
            finrobot_attribution_passed=finrobot_attribution_passed,
            finrobot_rejected_operations=finrobot_rejected_operations,
            registry_scope_passed=registry_scope_passed,
            events_integrity_passed=events_integrity_passed,
            dto_immutable_passed=dto_immutable_passed,
            artifact_files_passed=artifact_files_passed,
            proof_fail_closed_passed=proof_fail_closed_passed,
            candidate=candidate,
            runtime=runtime,
            generated_retention_audit=generated_retention_audit,
        )
        financial_semantics = _financial_semantic_matrix(
            aggregate=aggregate,
            dto=dto,
            report_artifacts=report_artifacts,
            validations=validations,
            proof_inputs=proof_inputs,
            proofs=proofs,
            review_negative=review_negative,
            cross_view_content_passed=cross_view_content_passed,
        )
        if set(financial_semantics) != _expected_financial_semantic_gate_ids():
            raise RuntimeError("financial semantic acceptance matrix identity drifted")
        audit_state["capability_matrix"] = {
            key: value for key, value in matrix.items() if key.startswith("P3-CAP-")
        }
        audit_state["proof_matrix"] = {
            key: value for key, value in matrix.items() if key.startswith("P3-ZK-")
        }
        audit_state["financial_matrix"] = {
            key: value for key, value in matrix.items() if key.startswith("P3-FIN-")
        }
        audit_state["financial_semantics"] = financial_semantics

        historical = [
            item
            for item in aggregate.artifacts.evidence
            if item.evidence_purpose == "historical_market_context"
        ]
        close_dates = {item.as_of for item in historical if item.normalized_field == "close"}
        volume_dates = {item.as_of for item in historical if item.normalized_field == "volume"}
        paired_dates = sorted(close_dates & volume_dates)
        endpoint_status = {
            item.endpoint.value: {
                "status": item.status.value,
                "http_status": item.http_status,
                "mapped_record_count": item.mapped_record_count,
                "accepted_count": item.accepted_count,
                "non_accepted_count": item.non_accepted_count,
                "error_code": item.error_code,
            }
            for item in collector.endpoint_statuses
        }
        all_references = await references.list_by_run(run_id)
        trace_ids = {item.trace_id for item in all_references if item.trace_id}
        trace_stages = {item.stage for item in all_references}
        canonical_trace_refs = set(aggregate.artifacts.canonical_record.trace_refs)
        persisted_reference_ids = {item.reference_id for item in all_references}
        trace_reference_ledger = build_trace_reference_ledger(
            run_id=run_id,
            trace_id=trace_id,
            authoritative_reference_ids=[item.reference_id for item in all_references],
            cer_reference_ids=aggregate.artifacts.canonical_record.trace_refs,
            records=all_references,
        )
        audit_state["failed_stage"] = "langfuse_trace_evaluation"
        trace_passed = (
            instrumentation.status is TraceRuntimeStatus.TRACE_HEALTHY
            and isinstance(trace_id, str)
            and bool(trace_id)
            and bool(all_references)
            and trace_ids == {trace_id}
            and {
                "run",
                "scheme_generation",
                "planner_generation",
                "tool",
                "calculation",
                "review",
                "release",
            }.issubset(trace_stages)
            and bool(canonical_trace_refs)
            and canonical_trace_refs.issubset(persisted_reference_ids)
            and trace_reference_ledger.unresolved_count == 0
            and trace_reference_ledger.mapped_reference_count
            == trace_reference_ledger.total_reference_count
            and trace_reference_ledger.same_run_count
            == trace_reference_ledger.total_reference_count
            and trace_reference_ledger.same_trace_count
            == trace_reference_ledger.total_reference_count
            and trace_reference_ledger.cer_resolved_count
            == trace_reference_ledger.cer_reference_count
        )
        event_types = {event.type.value for event in events}
        required_trace_events = {
            "scheme.generated",
            "plan.generated",
            "task.started",
            "capability.gap_detected",
            "capability.build_started",
            "capability.sandbox_started",
            "capability.financial_validated",
            "capability.registered",
            "task.resumed",
            "calculation.completed",
            "review.resolved",
            "proof.verified",
            "release.completed",
        }
        observation_names = {item["name"] for item in audited_trace.observations}
        required_observation_names = {
            "vfas.run",
            "vfas.scheme_generation",
            "vfas.planner_generation",
            "vfas.task",
            "vfas.capability.gap_detected",
            "vfas.capability_generation",
            "vfas.capability.sandbox_started",
            "vfas.capability.financial_validated",
            "vfas.capability.registered",
            "vfas.task.resumed",
            "vfas.calculation",
            "vfas.review",
            "vfas.release",
        }
        required_tool_observations = {
            "risc0_revenue_growth_prover",
            "finrobot_owned_svg_chart_port",
            "finrobot_owned_professional_report_port",
        }
        observed_tool_names = {
            item["tool_name"]
            for item in audited_trace.observations
            if isinstance(item.get("tool_name"), str)
        }
        observation_trace_ids = {
            item["trace_id"] for item in audited_trace.observations if item.get("trace_id")
        }
        trace_observation_passed = (
            required_observation_names.issubset(observation_names)
            and required_tool_observations.issubset(observed_tool_names)
            and observation_trace_ids == {trace_id}
            and all(item.get("run_id") == run_id for item in audited_trace.observations)
            and local_observation_identities_valid
        )
        langfuse_evidence = {
            "passed": trace_passed
            and trace_observation_passed
            and required_trace_events.issubset(set(event_types))
            and langfuse_redaction_audit.passed,
            "trace_id": trace_id,
            "root_trace_count": len(trace_ids),
            "reference_count": len(all_references),
            "trace_stages": sorted(trace_stages),
            "required_runtime_stages_observed": sorted(required_trace_events & set(event_types)),
            "observation_count": len(audited_trace.observations),
            "observation_names": sorted(observation_names),
            "tool_observations": sorted(observed_tool_names),
            "observation_trace_ids": sorted(observation_trace_ids),
            "local_observation_identities_valid": local_observation_identities_valid,
            "expected_observation_count": (langfuse_redaction_audit.expected_observation_count),
            "observed_observation_count": langfuse_redaction_audit.observation_count,
            "missing_observation_identities": list(
                langfuse_redaction_audit.missing_observation_identities
            ),
            "unexpected_observation_identities": list(
                langfuse_redaction_audit.unexpected_observation_identities
            ),
            "unexpected_duplicate_identities": list(
                langfuse_redaction_audit.unexpected_duplicate_identities
            ),
            "one_root_trace": langfuse_redaction_audit.one_root_trace,
            "run_metadata_closure": langfuse_redaction_audit.run_metadata_closure,
            "trace_metadata_closure": langfuse_redaction_audit.trace_metadata_closure,
            "force_flush_succeeded": langfuse_redaction_audit.force_flush_succeeded,
            "attempts": langfuse_redaction_audit.attempts,
            "elapsed_seconds": langfuse_redaction_audit.elapsed_seconds,
            "drain_elapsed_seconds": langfuse_redaction_audit.elapsed_seconds,
            "readback_attempts": [
                {
                    "attempt_number": item.attempt_number,
                    "timestamp": item.timestamp,
                    "elapsed_seconds": item.elapsed_seconds,
                    "expected_count": item.expected_count,
                    "observed_count": item.observed_count,
                    "unique_observed_count": item.unique_observed_count,
                    "missing_observation_identities": list(item.missing_observation_identities),
                    "unexpected_observation_identities": list(
                        item.unexpected_observation_identities
                    ),
                    "duplicate_observation_identities": list(item.duplicate_observation_identities),
                    "root_trace_count": item.root_trace_count,
                    "trace_id": item.trace_id,
                    "run_id": item.run_id,
                    "run_metadata_closure": item.run_metadata_closure,
                    "trace_metadata_closure": item.trace_metadata_closure,
                    "read_succeeded": item.read_succeeded,
                }
                for item in langfuse_redaction_audit.readback_attempts
            ],
            **identity_set_evidence,
            "trace_reference_ledger": {
                "total_reference_count": trace_reference_ledger.total_reference_count,
                "mapped_reference_count": trace_reference_ledger.mapped_reference_count,
                "same_run_count": trace_reference_ledger.same_run_count,
                "same_trace_count": trace_reference_ledger.same_trace_count,
                "unresolved_count": trace_reference_ledger.unresolved_count,
                "cer_reference_count": trace_reference_ledger.cer_reference_count,
                "cer_resolved_count": trace_reference_ledger.cer_resolved_count,
            },
            "credential_redaction": {
                "policy_id": langfuse_redaction_audit.policy_id,
                "passed": langfuse_redaction_audit.passed,
                "read_succeeded": langfuse_redaction_audit.read_succeeded,
                "occurrence_count": langfuse_redaction_audit.occurrence_count,
                "named_occurrence_counts": dict(langfuse_redaction_audit.named_occurrence_counts),
                "serialized_field_count": langfuse_redaction_audit.field_count,
                "observation_count": langfuse_redaction_audit.observation_count,
                "expected_observation_count": (langfuse_redaction_audit.expected_observation_count),
                "attempts": langfuse_redaction_audit.attempts,
                "inspected_surfaces": list(langfuse_redaction_audit.inspected_surfaces),
                "missing_observation_identities": list(
                    langfuse_redaction_audit.missing_observation_identities
                ),
                "unexpected_observation_identities": list(
                    langfuse_redaction_audit.unexpected_observation_identities
                ),
                "unexpected_duplicate_identities": list(
                    langfuse_redaction_audit.unexpected_duplicate_identities
                ),
                "one_root_trace": langfuse_redaction_audit.one_root_trace,
                "run_metadata_closure": langfuse_redaction_audit.run_metadata_closure,
                "trace_metadata_closure": langfuse_redaction_audit.trace_metadata_closure,
                "force_flush_succeeded": langfuse_redaction_audit.force_flush_succeeded,
                "elapsed_seconds": langfuse_redaction_audit.elapsed_seconds,
            },
        }
        audit_state["langfuse"] = langfuse_evidence
        summary: dict[str, Any] = {
            "candidate": candidate,
            "authoritative_phase3_run_id": run_id,
            "run_id": run_id,
            "run_status": aggregate.run.status.value,
            "symbol": "NVDA",
            "run_provider_bindings": provider_bindings_evidence,
            "frontend": "DEFERRED_FROZEN",
            "runtime": runtime,
            "postgresql": {
                "persisted": True,
                "migration_before": migration_before,
                "migration_path": ([migration_head] if migration_before != migration_head else []),
                "migration_head": migration_head,
                "migration_current": migration_current,
                "checkpoint_id": checkpoint.checkpoint_id,
                "checkpoint_graph_version": checkpoint.actual_graph_version,
            },
            "fmp": {
                "provider": "fmp",
                "credential_alias": fmp_credential_alias,
                "request_count": fmp_transport.total,
                "requests_by_endpoint": dict(fmp_transport.by_endpoint),
                "endpoint_status": endpoint_status,
                "accepted_evidence_count": len(aggregate.artifacts.evidence),
                "accepted_historical_pairs": len(paired_dates),
                "historical_range": (
                    [paired_dates[0].isoformat(), paired_dates[-1].isoformat()]
                    if paired_dates
                    else None
                ),
            },
            "llm": {
                "provider_bindings": provider_bindings_evidence,
                "logical_calls": sum(item.logical_calls for item in workload_llms),
                "http_attempts": (llm_http_counter.http_attempts - planner_preflight_http_attempts),
                "preflight_http_attempts": planner_preflight_http_attempts,
                "schemas": {
                    workload.value: dict(counter.schemas)
                    for workload, counter in (
                        (PlannerWorkload.SCHEME_PLANNER, scheme_llm),
                        (PlannerWorkload.LEAD_PLANNER, lead_llm),
                        (PlannerWorkload.GENERATED_CAPABILITY, generated_llm),
                    )
                },
                "scheme": scheme_generator.last_audit.model_dump(mode="json"),
                "planner": planner.last_audit.model_dump(mode="json"),
            },
            "langfuse": {
                "classification": trace_build.classification.value,
                "trace_id": trace_id,
                "runtime_status": instrumentation.status.value,
                "reference_count": len(all_references),
                "trace_stages": sorted(trace_stages),
                "canonical_reference_count": len(canonical_trace_refs),
            },
            "generated_capability": {
                "gap_ids": [item.gap_id for item in gaps],
                "build_ids": [item.build_id for item in builds],
                "generated_ids": [item.generated_capability_id for item in generated],
                "registration_ids": [item.registration_id for item in registrations],
                "sandbox_image": sandbox.image,
                "artifact_retention": generated_retention_audit,
            },
            "proof": {
                "policy_decision_count": len(proof_policies),
                "proof_ids": [item.proof_id for item in proofs],
                "receipt_hashes": [item.receipt_hash for item in proofs],
                "journal_hashes": [item.journal_hash for item in proofs],
                "negative_checks": negative,
            },
            "reports": [item.model_dump(mode="json") for item in report_artifacts],
            "planned_task_count": len(aggregate.runtime.planned_graph.tasks),
            "actual_task_count": len(aggregate.runtime.actual_graph.tasks),
            "actual_graph_version": aggregate.runtime.actual_graph.version,
            "parallel_task_peak": aggregate.artifacts.parallel_task_peak,
            "task_evidence": {
                task.task_id: {
                    "acquisition_status": (
                        task.evidence_acquisition_status.value
                        if task.evidence_acquisition_status
                        else None
                    ),
                    "input_evidence_ids": task.task_input_evidence_ids,
                    "output_evidence_ids": task.task_output_evidence_ids,
                }
                for task in aggregate.runtime.actual_graph.tasks
            },
            "peer_selection": next(
                (
                    aggregate.artifacts.task_outputs.get(task.task_id)
                    for task in aggregate.runtime.actual_graph.tasks
                    if task.task_type == "peer_analysis"
                ),
                None,
            ),
            "evidence_event_count": sum(
                event.type.value == "evidence.accepted" for event in events
            ),
            "graph_edge_event_count": sum(
                event.type.value in {"graph.edge_added", "graph.edge_removed"} for event in events
            ),
            "calculations": [
                item.model_dump(mode="json") for item in aggregate.artifacts.calculations
            ],
            "review_status": (
                aggregate.artifacts.review.status.value if aggregate.artifacts.review else None
            ),
            "canonical_record_id": aggregate.artifacts.canonical_record.record_id,
            "released_result_id": aggregate.artifacts.released_result.result_id,
            "calculation_ids": [item.calculation_id for item in aggregate.artifacts.calculations],
            "runtime_event_count": len(events),
            "runtime_event_sequences_contiguous": events_integrity_passed,
            "no_refetch": no_refetch,
            "acceptance": matrix,
            "financial_semantics": financial_semantics,
            "regressions": regressions,
            "failed": [],
        }
        _write_json(
            output / "accepted_evidence.json",
            [item.model_dump(mode="json") for item in aggregate.artifacts.evidence],
        )
        calculation_payload = [
            item.model_dump(mode="json") for item in aggregate.artifacts.calculations
        ]
        _write_json(output / "calculation_records.json", calculation_payload)
        _write_json(
            output / "generated_capability_artifact_records.json",
            [item.model_dump(mode="json") for item in generated_artifacts],
        )
        _write_json(
            output / "runtime_events.json",
            [item.model_dump(mode="json") for item in events],
        )
        _write_json(output / "task_outputs.json", aggregate.artifacts.task_outputs)
        _write_json(
            output / "canonical_execution_record.json",
            aggregate.artifacts.canonical_record.model_dump(mode="json"),
        )
        _write_json(
            output / "released_research_result.json",
            aggregate.artifacts.released_result.model_dump(mode="json"),
        )
        # The Phase-2.1 evaluator predates extensible calculations and maps every
        # non-growth formula to the original EBITDA source file. Re-run those
        # frozen gates in an isolated view containing exactly their two owned
        # baseline calculations. Never narrow the authoritative Phase-3 artifact.
        baseline_calculation_payload = [
            item
            for item in calculation_payload
            if item["capability_id"] in {"revenue_growth", "ebitda_margin"}
        ]
        if Counter(item["capability_id"] for item in baseline_calculation_payload) != Counter(
            {"revenue_growth": 1, "ebitda_margin": 1}
        ):
            raise RuntimeError("Phase 2.1 baseline requires exactly two owned calculations")
        with tempfile.TemporaryDirectory(prefix="vfas-phase2-1-") as evaluator_dir:
            evaluator_root = Path(evaluator_dir)
            _write_json(
                evaluator_root / "accepted_evidence.json",
                [item.model_dump(mode="json") for item in aggregate.artifacts.evidence],
            )
            _write_json(evaluator_root / "calculation_records.json", baseline_calculation_payload)
            _write_json(
                evaluator_root / "runtime_events.json",
                [item.model_dump(mode="json") for item in events],
            )
            _write_json(evaluator_root / "task_outputs.json", aggregate.artifacts.task_outputs)
            _write_json(
                evaluator_root / "canonical_execution_record.json",
                aggregate.artifacts.canonical_record.model_dump(mode="json"),
            )
            _write_json(
                evaluator_root / "released_research_result.json",
                aggregate.artifacts.released_result.model_dump(mode="json"),
            )
            semantic = evaluate_phase2_1(evaluator_root, summary)
        semantic_failed = [gate for gate, result in semantic.items() if result["status"] != "PASS"]
        _write_json(
            output / "phase2_1_acceptance.json",
            {"acceptance": semantic, "failed": semantic_failed},
        )

        audit_state["failed_stage"] = "postgresql_restart_restore"
        phase3_record_types = (
            CapabilityGapRecord,
            CapabilityBuildRecord,
            GeneratedCapabilityRecord,
            GeneratedCapabilityArtifactRecord,
            CapabilityValidationRecord,
            SandboxExecutionRecord,
            ScopedCapabilityRegistration,
            ProofPolicyDecision,
            ProofInputCommitment,
            ProofRecord,
            ProofVerificationRecord,
            ProofArtifactReference,
            ReportArtifactRecord,
        )
        phase3_before_restart = {
            record_type: await repository.list(record_type, run_id)
            for record_type in phase3_record_types
        }
        planned_before_restart = await persistence.run_record_repository.list_task_dependencies(
            run_id, graph_kind=TaskDependencyGraphKind.PLANNED
        )
        actual_before_restart = await persistence.run_record_repository.list_task_dependencies(
            run_id, graph_kind=TaskDependencyGraphKind.ACTUAL
        )
        aggregate_before_restart = _aggregate_snapshot(aggregate)
        await persistence.close()
        persistence = create_postgresql_persistence(settings.database)
        restored = await persistence.application_repository.get_run(run_id)
        restored_canonical = await persistence.run_record_repository.get_canonical(run_id)
        restored_released = await persistence.run_record_repository.get_released(run_id)
        restored_checkpoint = await persistence.checkpoint_store.load_latest(run_id)
        restored_events = list(await persistence.event_store.replay(run_id))
        phase3_after_restart = {
            record_type: await persistence.phase3_record_repository.list(record_type, run_id)
            for record_type in phase3_record_types
        }
        planned_dependencies = await persistence.run_record_repository.list_task_dependencies(
            run_id, graph_kind=TaskDependencyGraphKind.PLANNED
        )
        actual_dependencies = await persistence.run_record_repository.list_task_dependencies(
            run_id, graph_kind=TaskDependencyGraphKind.ACTUAL
        )
        aggregate_roundtrip = (
            restored is not None and _aggregate_snapshot(restored) == aggregate_before_restart
        )
        same_run_domain_records = (
            restored is not None
            and restored.run.run_id == run_id
            and all(item.run_id == run_id for item in restored.artifacts.evidence)
            and all(item.run_id == run_id for item in restored.artifacts.calculations)
            and restored.artifacts.review is not None
            and restored.artifacts.review.run_id == run_id
            and all(item.run_id == run_id for item in restored.artifacts.report_artifacts)
            and restored_canonical is not None
            and restored_canonical.run_id == run_id
            and restored_released is not None
            and restored_released.run_id == run_id
        )
        records_roundtrip = phase3_after_restart == phase3_before_restart
        dependency_roundtrip = (
            planned_dependencies == planned_before_restart
            and actual_dependencies == actual_before_restart
        )
        if (
            restored is None
            or not aggregate_roundtrip
            or restored.artifacts.report_artifacts != report_artifacts
            or restored_canonical != aggregate.artifacts.canonical_record
            or restored_released != aggregate.artifacts.released_result
            or restored_checkpoint != checkpoint
            or restored_events != events
            or not records_roundtrip
            or not dependency_roundtrip
            or not same_run_domain_records
        ):
            raise RuntimeError("PostgreSQL restart/restore round-trip failed")
        expected_full_frames = [encode_sse_event(event) for event in events]
        full_frames = await _sse_frames(
            persistence.event_store,
            run_id=run_id,
            last_event_id="0",
            expected_events=events,
        )
        midpoint = len(events) // 2
        cursor_event = events[midpoint - 1]
        suffix_events = events[midpoint:]
        numeric_suffix_frames = await _sse_frames(
            persistence.event_store,
            run_id=run_id,
            last_event_id=str(cursor_event.sequence),
            expected_events=suffix_events,
        )
        opaque_suffix_frames = await _sse_frames(
            persistence.event_store,
            run_id=run_id,
            last_event_id=cursor_event.event_id,
            expected_events=suffix_events,
        )
        tail_stream = runtime_event_stream(
            store=persistence.event_store,
            run_id=run_id,
            last_event_id=str(events[-1].sequence),
            heartbeat_seconds=0.1,
        )
        try:
            tail_frame = await asyncio.wait_for(anext(tail_stream), timeout=2.0)
        finally:
            await tail_stream.aclose()
        expected_suffix_frames = [encode_sse_event(event) for event in suffix_events]
        sse_roundtrip = (
            full_frames == expected_full_frames
            and numeric_suffix_frames == expected_suffix_frames
            and opaque_suffix_frames == expected_suffix_frames
            and tail_frame == encode_sse_heartbeat()
        )
        if not sse_roundtrip:
            raise RuntimeError("SSE persisted replay/resume verification failed")
        restore = {
            "passed": True,
            "run_id": run_id,
            "aggregate_restored": True,
            "aggregate_snapshot_roundtrip": aggregate_roundtrip,
            "same_run_domain_records": same_run_domain_records,
            "canonical_roundtrip": True,
            "released_roundtrip": True,
            "checkpoint_roundtrip": True,
            "event_replay_roundtrip": True,
            "evidence_record_count": len(restored.artifacts.evidence),
            "calculation_record_count": len(restored.artifacts.calculations),
            "review_record_id": restored.artifacts.review.review_id,
            "capability_record_type_count": len(phase3_after_restart),
            "proof_record_count": len(phase3_after_restart.get(ProofRecord, [])),
            "report_artifact_count": len(restored.artifacts.report_artifacts),
            "phase3_records_roundtrip": records_roundtrip,
            "report_artifact_roundtrip": True,
            "sse_replay_first_sequence": events[0].sequence,
            "sse_full_count": len(full_frames),
            "sse_numeric_resume_count": len(numeric_suffix_frames),
            "sse_opaque_resume_count": len(opaque_suffix_frames),
            "sse_tail_heartbeat": tail_frame == encode_sse_heartbeat(),
            "planned_dependency_count": len(planned_dependencies),
            "actual_dependency_count": len(actual_dependencies),
            "event_type_counts": dict(Counter(event.type.value for event in restored_events)),
        }
        audit_state["restore"] = restore
        summary["restore"] = restore
        _write_json(output / "postgresql_restore_summary.json", restore)
        secret_scan = _scan_artifacts_for_credentials(
            output,
            needles=_credential_needles(settings),
            pending_summary=summary,
        )
        summary["secret_scan"] = secret_scan
        summary["secret_values_included"] = not secret_scan["passed"]
        candidate_immutable = await asyncio.to_thread(
            _candidate_still_immutable, repository_root, candidate
        )
        postgresql_evidence = {
            "passed": (
                migration_current == migration_head
                and migration_head == "20260904_0006"
                and restore["passed"]
            ),
            "migration_before": migration_before,
            "migration_path": [migration_head] if migration_before != migration_head else [],
            "migration_after": migration_current,
            "repository_roundtrip": restore["passed"],
        }
        audit_state["postgresql"] = postgresql_evidence
        security_evidence = {
            "passed": (
                secret_scan["passed"]
                and negative["risc0_dev_mode_presence_fail"]
                and all(
                    matrix[gate]["status"] == "PASS"
                    for gate in ("P3-CAP-005", "P3-CAP-006", "P3-CAP-007")
                )
                and candidate_immutable
            ),
            "secret_scan": secret_scan,
            "risc0_dev_mode_presence_fail": negative["risc0_dev_mode_presence_fail"],
            "candidate_immutable": candidate_immutable,
        }
        audit_state["security"] = security_evidence
        capability_matrix = {
            key: value for key, value in matrix.items() if key.startswith("P3-CAP-")
        }
        proof_matrix = {key: value for key, value in matrix.items() if key.startswith("P3-ZK-")}
        report_matrix = {key: value for key, value in matrix.items() if key.startswith("P3-FIN-")}
        audit_state["failed_stage"] = "integration_gate_evaluation"
        integration = _integration_matrix(
            run_id=run_id,
            regressions=regressions,
            phase2_1_semantic_failed=semantic_failed,
            postgresql=postgresql_evidence,
            langfuse=langfuse_evidence,
            capability_matrix=capability_matrix,
            proof_matrix=proof_matrix,
            financial_matrix=report_matrix,
            proof_ids=[item.proof_id for item in proofs],
            report_artifacts=report_artifacts,
            security=security_evidence,
            restore=restore,
        )
        matrix.update(integration)
        audit_state["integration_matrix"] = integration
        if set(matrix) != _expected_core_gate_ids():
            raise RuntimeError("formal Phase 3 acceptance matrix identity drifted")
        core_failed = [gate for gate, result in matrix.items() if result["status"] != "PASS"]
        semantic_failed = [
            gate for gate, result in financial_semantics.items() if result["status"] != "PASS"
        ]
        summary["acceptance"] = matrix
        summary["financial_semantics"] = financial_semantics
        summary["failed"] = core_failed
        summary["financial_semantics_failed"] = semantic_failed
        summary["candidate_immutable_at_completion"] = candidate_immutable
        summary["final_status"] = "PASS" if not core_failed and not semantic_failed else "FAIL"
        _write_json(output / "acceptance_matrix.json", matrix)
        _write_json(output / "financial_semantics_matrix.json", financial_semantics)
        _write_json(output / "candidate_identity.json", candidate)
        _write_json(output / "regression_evidence.json", regressions)
        _write_json(output / "langfuse_trace_summary.json", langfuse_evidence)
        _write_json(
            output / "trace_reference_ledger.json",
            trace_reference_ledger.model_dump(mode="json"),
        )
        _write_json(output / "secret_scan_summary.json", secret_scan)
        _write_json(
            output / "review_record.json", aggregate.artifacts.review.model_dump(mode="json")
        )
        _write_json(output / "canonical_report_dto.json", dto.model_dump(mode="json"))
        _write_json(
            output / "typed_claims.json",
            [
                item.model_dump(mode="json")
                for item in aggregate.artifacts.released_result.material_claims
            ],
        )
        _write_json(
            output / "released_metrics.json",
            [
                item.model_dump(mode="json")
                for item in aggregate.artifacts.released_result.released_metrics
            ],
        )
        _write_json(
            output / "report_artifacts.json",
            [item.model_dump(mode="json") for item in report_artifacts],
        )
        _write_json(
            output / "proof_records.json", [item.model_dump(mode="json") for item in proofs]
        )
        _write_json(
            output / "proof_verifications.json",
            [item.model_dump(mode="json") for item in verifications],
        )
        _write_json(
            output / "proof_input_commitments.json",
            [item.model_dump(mode="json") for item in proof_inputs],
        )
        _write_json(
            output / "proof_artifact_references.json",
            [item.model_dump(mode="json") for item in proof_artifacts],
        )
        _write_json(
            output / "generated_capability_records.json",
            {
                "gaps": [item.model_dump(mode="json") for item in gaps],
                "builds": [item.model_dump(mode="json") for item in builds],
                "generated": [item.model_dump(mode="json") for item in generated],
                "validations": [item.model_dump(mode="json") for item in validations],
                "sandboxes": [item.model_dump(mode="json") for item in sandboxes],
                "registrations": [item.model_dump(mode="json") for item in registrations],
            },
        )
        _write_json(
            output / "technical_method_metadata.json",
            {
                item.metric_id: item.method_metadata.model_dump(mode="json")
                for item in aggregate.artifacts.released_result.released_metrics
                if item.method_metadata is not None
            },
        )
        _write_json(
            output / "research_source_coverage.json",
            aggregate.artifacts.released_result.research_source_coverage.model_dump(mode="json"),
        )
        _write_json(
            output / "actual_execution_graph.json",
            aggregate.runtime.actual_graph.model_dump(mode="json"),
        )
        _write_json(
            output / "actual_graph.json",
            aggregate.runtime.actual_graph.model_dump(mode="json"),
        )
        _write_json(
            output / "generated_capability.json",
            (
                generated[0].model_dump(mode="json")
                if len(generated) == 1
                else {
                    "count": len(generated),
                    "records": [item.model_dump(mode="json") for item in generated],
                }
            ),
        )
        _write_json(
            output / "capability_validation.json",
            (
                validations[0].model_dump(mode="json")
                if len(validations) == 1
                else {
                    "count": len(validations),
                    "records": [item.model_dump(mode="json") for item in validations],
                }
            ),
        )
        _write_json(
            output / "sandbox_execution.json",
            (
                sandboxes[0].model_dump(mode="json")
                if len(sandboxes) == 1
                else {
                    "count": len(sandboxes),
                    "records": [item.model_dump(mode="json") for item in sandboxes],
                }
            ),
        )
        _write_json(
            output / "proof_record.json",
            (
                proofs[0].model_dump(mode="json")
                if len(proofs) == 1
                else {
                    "count": len(proofs),
                    "records": [item.model_dump(mode="json") for item in proofs],
                }
            ),
        )
        _write_json(
            output / "proof_verification.json",
            (
                verifications[0].model_dump(mode="json")
                if len(verifications) == 1
                else {
                    "count": len(verifications),
                    "records": [item.model_dump(mode="json") for item in verifications],
                }
            ),
        )
        _write_json(
            output / "proof_release_manifest.json",
            {
                "run_id": run_id,
                "canonical_record_id": aggregate.artifacts.canonical_record.record_id,
                "released_result_id": aggregate.artifacts.released_result.result_id,
                "candidate_head": candidate["candidate_head"],
                "candidate": candidate,
                "policy_decisions": [item.model_dump(mode="json") for item in proof_policies],
                "proof_inputs": [item.model_dump(mode="json") for item in proof_inputs],
                "proofs": [item.model_dump(mode="json") for item in proofs],
                "verifications": [item.model_dump(mode="json") for item in verifications],
                "artifacts": [item.model_dump(mode="json") for item in proof_artifacts],
            },
        )
        final_secret_scan = _scan_artifacts_for_credentials(
            output,
            needles=_credential_needles(settings),
            pending_summary=summary,
        )
        final_candidate_immutable = await asyncio.to_thread(
            _candidate_still_immutable, repository_root, candidate
        )
        if not final_secret_scan["passed"] or not final_candidate_immutable:
            matrix["P3-INT-009"] = _gate(
                False,
                {
                    "secret_scan": final_secret_scan,
                    "candidate_immutable": final_candidate_immutable,
                },
            )
            core_failed = [gate for gate, result in matrix.items() if result["status"] != "PASS"]
            summary["acceptance"] = matrix
            summary["failed"] = core_failed
            summary["final_status"] = "FAIL"
        summary["secret_scan"] = final_secret_scan
        summary["secret_values_included"] = not final_secret_scan["passed"]
        summary["candidate_immutable_at_completion"] = final_candidate_immutable
        _write_json(output / "secret_scan_summary.json", final_secret_scan)
        _write_json(output / "acceptance_matrix.json", matrix)
        _write_json(output / "phase3_acceptance.json", summary)
        _write_json(output / "acceptance_summary.json", summary)
        audit_state["failed_stage"] = "complete"
        if core_failed or semantic_failed:
            raise RuntimeError(
                f"Phase 3 acceptance failed: core={core_failed}; financial={semantic_failed}"
            )
        return summary
    finally:
        await llm_http_client.aclose()
        await persistence.close()


def _failure_matrix(
    *,
    run_id: str,
    audit_state: Mapping[str, Any],
    error_type: str,
) -> dict[str, dict[str, Any]]:
    """Return an exact, fail-closed core matrix for any incomplete authoritative run."""

    stage = str(audit_state.get("failed_stage", "unknown"))
    common = {
        "run_id": run_id,
        "reason": "AUTHORITATIVE_RUN_INCOMPLETE",
        "failed_stage": stage,
        "error_type": error_type,
    }
    matrix = {gate: _gate(False, dict(common)) for gate in _expected_core_gate_ids()}
    regressions = audit_state.get("regressions")
    if isinstance(regressions, Mapping):
        phase_names = {1: "phase1", 2: "phase2", 3: "phase2_1"}
        for index, name in phase_names.items():
            result = regressions.get(name)
            if isinstance(result, Mapping):
                evidence = dict(result)
                evidence["run_id"] = run_id
                matrix[f"P3-INT-{index:03d}"] = _gate(bool(result.get("passed")), evidence)
    state_gate_mapping = {
        "P3-INT-004": "postgresql",
        "P3-INT-005": "langfuse",
        "P3-INT-009": "security",
        "P3-INT-010": "restore",
    }
    for gate, state_key in state_gate_mapping.items():
        value = audit_state.get(state_key)
        if isinstance(value, Mapping):
            evidence = dict(value)
            evidence["run_id"] = run_id
            matrix[gate] = _gate(bool(value.get("passed")), evidence)
    prefix_mapping = {
        "P3-INT-006": ("capability_matrix", "P3-CAP-"),
        "P3-INT-007": ("proof_matrix", "P3-ZK-"),
        "P3-INT-008": ("financial_matrix", "P3-FIN-"),
    }
    for gate, (state_key, prefix) in prefix_mapping.items():
        value = audit_state.get(state_key)
        if isinstance(value, Mapping):
            matrix[gate] = _gate(
                _all_gates_pass(value, prefix=prefix),
                {
                    "run_id": run_id,
                    "gate_count": len(value),
                    "failed_stage": stage,
                },
            )
    if set(matrix) != _expected_core_gate_ids():  # pragma: no cover - construction invariant
        raise RuntimeError("failure matrix identity drifted")
    return matrix


def _write_failure_envelope(
    *,
    output_root: Path,
    run_id: str,
    candidate_head: str,
    audit_state: Mapping[str, Any],
    error_type: str,
) -> None:
    repository_root = _repository_root()
    allowed_output_root = (repository_root / "artifacts" / "phase3" / "acceptance").resolve()
    requested_root = output_root if output_root.is_absolute() else repository_root / output_root
    resolved_root = _resolve_safe_path(requested_root, label="Phase 3 acceptance output root")
    try:
        resolved_root.relative_to(allowed_output_root)
    except ValueError as exc:
        raise RuntimeError("Phase 3 acceptance output must remain in its controlled root") from exc
    output = resolved_root / run_id
    if output.exists() and not audit_state.get("output_created"):
        raise RuntimeError("refusing to overwrite an existing authoritative Run output")
    if not output.exists():
        output.mkdir(parents=True, exist_ok=False)
    matrix_path = output / "acceptance_matrix.json"
    matrix: dict[str, dict[str, Any]]
    preserve_existing_summary = False
    if matrix_path.is_file():
        try:
            existing = json.loads(matrix_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            existing = None
        if isinstance(existing, dict) and set(existing) == _expected_core_gate_ids():
            matrix = existing
            preserve_existing_summary = (output / "phase3_acceptance.json").is_file()
        else:
            matrix = _failure_matrix(
                run_id=run_id,
                audit_state=audit_state,
                error_type=error_type,
            )
    else:
        matrix = _failure_matrix(
            run_id=run_id,
            audit_state=audit_state,
            error_type=error_type,
        )
    failed = [gate for gate, result in matrix.items() if result.get("status") != "PASS"]
    summary = {
        "authoritative_phase3_run_id": run_id,
        "run_id": run_id,
        "candidate_head": candidate_head,
        "candidate": audit_state.get("candidate"),
        "fmp_credential_alias": audit_state.get("fmp_credential_alias"),
        "planner_provider_selection": audit_state.get("planner_provider_selection"),
        "run_provider_bindings": audit_state.get("run_provider_bindings"),
        "final_status": "FAIL",
        "failed_stage": audit_state.get("failed_stage", "unknown"),
        "error_type": error_type,
        "failed": failed,
        "acceptance": matrix,
    }
    _write_json(matrix_path, matrix)
    if not preserve_existing_summary:
        _write_json(output / "phase3_acceptance.json", summary)
        _write_json(output / "acceptance_summary.json", summary)


async def run(
    output_root: Path,
    *,
    host_binary: Path,
    candidate_head: str,
    fmp_credential_alias: str = "",
    env_file: Path | None = None,
) -> dict[str, Any]:
    """Run one authority chain and always emit a complete fail-closed core matrix."""

    run_id = f"RUN-{uuid4()}"
    audit_state: dict[str, Any] = {"failed_stage": "initialization"}
    try:
        return await _run_authoritative(
            output_root,
            host_binary=host_binary,
            candidate_head=candidate_head,
            run_id=run_id,
            audit_state=audit_state,
            fmp_credential_alias=fmp_credential_alias,
            env_file=env_file,
        )
    except Exception as exc:
        await asyncio.to_thread(
            _write_failure_envelope,
            output_root=output_root,
            run_id=run_id,
            candidate_head=candidate_head,
            audit_state=audit_state,
            error_type=type(exc).__name__,
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/phase3/acceptance"),
    )
    parser.add_argument(
        "--risc0-host-binary",
        type=Path,
        default=Path("zk/revenue_growth/target/release/revenue-growth-proof-host"),
    )
    parser.add_argument("--candidate-head", required=True)
    parser.add_argument("--fmp-credential-alias", required=True)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    result = asyncio.run(
        run(
            args.output_root,
            host_binary=args.risc0_host_binary,
            candidate_head=args.candidate_head,
            fmp_credential_alias=args.fmp_credential_alias,
            env_file=args.env_file,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
