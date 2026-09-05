from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from src.adapters.risc0 import PendingProofAdapter
from src.agentic import DeterministicSchemeGenerator, ResearchLeadPlanner, SchemeGenerator
from src.application.errors import ApplicationError, NotFoundError
from src.application.evidence_collection import EvidenceCollector, FixtureEvidenceCollector
from src.application.evidence_routing import (
    EvidenceTaskRouter,
    RunEvidenceStore,
    TaskEvidenceRoutingResult,
)
from src.application.execution import IntegratedTaskExecutor
from src.application.extensions import (
    ProofWorkflow,
    ProofWorkflowOutcome,
    TaskCalculationExtension,
)
from src.application.models import ResearchRunDraft, RunAggregate
from src.application.repository import ApplicationRepository, InMemoryApplicationRepository
from src.assurance import DeterministicReviewer, IndependentFinancialReviewer, ReleaseGate
from src.assurance.proof_policy import ProofPolicy
from src.capabilities.calculation_lineage import link_calculation_lineage
from src.capabilities.financial.growth import RevenueGrowthCapability
from src.capabilities.financial.profitability import EbitdaMarginCapability
from src.capabilities.registry import CapabilityRegistry
from src.data.ingestion import EvidenceIngestionResult
from src.data.repository import EvidenceRepository, InMemoryEvidenceRepository
from src.domain.enums import CapabilityBackend, ProofRequirement, ProofStatus, RunStatus
from src.domain.proof import ProofRecord, ProofRequest
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.domain.research_run import ResearchRun
from src.domain.runtime_event import RuntimeEventType
from src.domain.task import Task
from src.observability import NoopTraceAdapter
from src.observability.instrumentation import RuntimeInstrumentation
from src.observability.references import TraceReferenceRepository
from src.output import (
    CanonicalExecutionRecordBuilder,
    FinancialReportRenderer,
    ObjectWritebackItem,
    ObjectWritebackProposalBuilder,
    ReleasedResearchResultBuilder,
    ReleaseGateSnapshot,
    ValueType,
    WritebackTarget,
    build_canonical_record_projections,
)
from src.output.calculation_taxonomy import partition_material_calculation_refs
from src.output.financial_metrics import (
    MATERIAL_FORMULAS,
    build_material_financial_release,
    build_research_source_coverage,
)
from src.runtime import (
    CheckpointStore,
    DependencyScheduler,
    InMemoryCheckpointStore,
    InMemoryRuntimeEventStore,
    RuntimeEventStore,
    RuntimeState,
)
from src.tooling.native import NativeToolBackend
from src.tooling.runtime import ToolRuntime


class ResearchApplicationService:
    """The single Phase-1 orchestration boundary used by API and acceptance tests."""

    def __init__(
        self,
        *,
        repository: ApplicationRepository | None = None,
        fixture_path: Path | None = None,
        trace_adapter: object | None = None,
        evidence_repository: EvidenceRepository | None = None,
        scheme_generator: SchemeGenerator | None = None,
        planner: object | None = None,
        evidence_collector: EvidenceCollector | None = None,
        event_store: RuntimeEventStore | None = None,
        checkpoint_store: CheckpointStore | None = None,
        instrumentation: RuntimeInstrumentation | None = None,
        trace_reference_repository: TraceReferenceRepository | None = None,
        run_id_factory: Callable[[], str] | None = None,
        calculation_extensions: Sequence[TaskCalculationExtension] = (),
        proof_workflow: ProofWorkflow | None = None,
    ) -> None:
        self.repository = repository or InMemoryApplicationRepository()
        self.event_store = event_store or InMemoryRuntimeEventStore()
        self.checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self.evidence_repository = evidence_repository or InMemoryEvidenceRepository()
        self.fixture_path = fixture_path or (
            Path(__file__).resolve().parents[2] / "tests/fixtures/nvda_financials.json"
        )
        self.trace_adapter = trace_adapter or NoopTraceAdapter()
        self.trace_reference_repository = trace_reference_repository
        self.instrumentation = instrumentation or RuntimeInstrumentation(
            self.trace_adapter,
            reference_repository=trace_reference_repository,
        )
        self._run_id_factory = run_id_factory or (lambda: f"RUN-{uuid4()}")
        self.scheme_generator = scheme_generator or DeterministicSchemeGenerator()
        self.planner = planner or ResearchLeadPlanner()
        self.evidence_collector = evidence_collector or FixtureEvidenceCollector(
            repository=self.evidence_repository,
            fixture_path=self.fixture_path,
        )
        self._evidence_stores: dict[str, RunEvidenceStore] = {}
        self._idempotency: dict[tuple[str, str], object] = {}
        self.calculation_extensions = list(calculation_extensions)
        self.proof_workflow = proof_workflow

        registry = CapabilityRegistry()
        registry.register(RevenueGrowthCapability())
        registry.register(EbitdaMarginCapability())
        self.capability_registry = registry
        self.tool_runtime = ToolRuntime(
            registry,
            {CapabilityBackend.NATIVE: NativeToolBackend(registry)},
        )

    def add_calculation_extension(self, extension: TaskCalculationExtension) -> None:
        if not isinstance(extension, TaskCalculationExtension):
            raise TypeError("extension must implement TaskCalculationExtension")
        self.calculation_extensions.append(extension)

    async def create_object(
        self,
        *,
        symbol: str,
        company_name: str,
        exchange: str,
        sector: str | None = None,
        currency: str = "USD",
        idempotency_key: str | None = None,
    ) -> ResearchObject:
        cached = self._idempotent("create_object", idempotency_key)
        if isinstance(cached, ResearchObject):
            return cached
        normalized = symbol.strip().upper()
        existing = next(
            (item for item in await self.repository.list_objects() if item.symbol == normalized),
            None,
        )
        if existing is not None:
            if idempotency_key:
                self._remember("create_object", idempotency_key, existing)
                return existing
            raise ApplicationError(
                "OBJECT_ALREADY_EXISTS",
                f"research object already exists for symbol {normalized}",
                status_code=409,
                details={"object_id": existing.object_id},
            )
        entity = ResearchObject(
            object_id=f"OBJ-{normalized}",
            symbol=normalized,
            company_name=company_name,
            exchange=exchange,
            sector=sector,
            currency=currency,
        )
        await self.repository.add_object(entity)
        self._remember("create_object", idempotency_key, entity)
        return entity

    async def prepare_run(
        self,
        *,
        research_object_id: str,
        research_goal: str,
        as_of,
        preferences: dict[str, object],
        observation_run_id: str | None = None,
    ) -> ResearchRunDraft:
        research_object = await self._object(research_object_id)
        goal_id = f"GOAL-{uuid4()}"
        goal = ResearchGoal(
            goal_id=goal_id,
            research_object_id=research_object_id,
            goal_text=research_goal,
            as_of=as_of,
            preferences=preferences,
        )
        if observation_run_id is not None and not observation_run_id.strip():
            raise ValueError("observation_run_id must not be blank")
        trace_run_id = observation_run_id or f"DRAFT:{goal_id}"
        async with self.instrumentation.scheme(run_id=trace_run_id):
            scheme = await self.scheme_generator.generate(
                research_object=research_object,
                goal=goal,
            )
        draft = ResearchRunDraft(
            draft_id=f"DRAFT-{uuid4()}",
            goal=goal,
            scheme_snapshot=scheme,
        )
        await self.repository.add_draft(draft)
        return draft

    async def confirm_run(
        self,
        *,
        draft_id: str,
        confirm_scheme: bool,
        idempotency_key: str | None = None,
    ) -> RunAggregate:
        cached = self._idempotent("confirm_run", idempotency_key)
        if isinstance(cached, RunAggregate):
            return cached
        if not confirm_scheme:
            raise ApplicationError(
                "SCHEME_CONFIRMATION_REQUIRED",
                "confirm_scheme must be true before a Research Run is created",
            )
        draft = await self.repository.get_draft(draft_id)
        if draft is None:
            raise NotFoundError("draft", draft_id)
        run_id = self._run_id_factory()
        if not run_id.strip():
            raise ValueError("run_id_factory returned a blank run id")
        scheme = draft.scheme_snapshot.model_copy(update={"confirmed_at": datetime.now(UTC)})
        async with self.instrumentation.planning(run_id=run_id):
            planned = self.planner.plan(run_id=run_id, goal=draft.goal, scheme=scheme)
            plan = await planned if inspect.isawaitable(planned) else planned
        runtime = RuntimeState.create(run_id=run_id, planned_graph=plan)
        run = ResearchRun(
            run_id=run_id,
            research_object_id=draft.goal.research_object_id,
            goal_id=draft.goal.goal_id,
            scheme_id=scheme.scheme_id,
            status=RunStatus.PLANNING,
            as_of=draft.goal.as_of,
            planned_graph_id=plan.graph_id,
            actual_graph_id=runtime.actual_graph.graph_id,
        )
        aggregate = RunAggregate(run=run, goal=draft.goal, scheme=scheme, runtime=runtime)
        await self.repository.add_run(aggregate)
        await self.event_store.emit(
            run_id=run_id,
            event_type=RuntimeEventType.RUN_CREATED,
            payload={"object_id": run.research_object_id},
        )
        await self.event_store.emit(
            run_id=run_id,
            event_type=RuntimeEventType.SCHEME_GENERATED,
            payload={
                "scheme_id": scheme.scheme_id,
                "generated_by": scheme.generated_by,
                "generated_at": scheme.created_at.isoformat(),
                "generation_stage": "prepare",
                "retrospective": True,
            },
        )
        await self.event_store.emit(
            run_id=run_id,
            event_type=RuntimeEventType.SCHEME_CONFIRMED,
            payload={"scheme_id": scheme.scheme_id},
        )
        await self.event_store.emit(
            run_id=run_id,
            event_type=RuntimeEventType.PLAN_GENERATED,
            payload={"graph_id": plan.graph_id, "task_count": len(plan.tasks)},
        )
        for task in plan.tasks:
            await self.event_store.emit(
                run_id=run_id,
                task_id=task.task_id,
                event_type=RuntimeEventType.TASK_CREATED,
                payload={"task_type": task.task_type},
            )
        self._remember("confirm_run", idempotency_key, aggregate)
        return aggregate

    async def execute_run(
        self,
        run_id: str,
        *,
        emit_run_started: bool = True,
    ) -> RunAggregate:
        aggregate = await self._aggregate(run_id)
        if aggregate.run.status is RunStatus.RELEASED:
            return aggregate
        aggregate.run.status = RunStatus.RUNNING
        if aggregate.run.started_at is None:
            aggregate.run.started_at = datetime.now(UTC)
            if aggregate.run.updated_at < aggregate.run.started_at:
                aggregate.run.updated_at = aggregate.run.started_at
        try:
            async with self.instrumentation.run(run_id=run_id):
                executor = IntegratedTaskExecutor(self, aggregate)
                scheduler = DependencyScheduler(
                    event_store=self.event_store,
                    checkpoint_store=self.checkpoint_store,
                )
                await scheduler.execute(
                    state=aggregate.runtime,
                    executor=executor,
                    emit_run_started=emit_run_started,
                )
                aggregate.artifacts.parallel_task_peak = executor.parallel_peak
                await self._assure_and_release(aggregate)
        except Exception as exc:
            durable_events = list(await self.event_store.replay(run_id))
            terminal_event = (
                durable_events[-1]
                if durable_events and durable_events[-1].type is RuntimeEventType.RUN_FAILED
                else None
            )
            if terminal_event is None:
                terminal_at = datetime.now(UTC)
                self._apply_terminal_lifecycle(
                    aggregate,
                    status=RunStatus.FAILED,
                    terminal_at=terminal_at,
                )
                terminal_event = await self.event_store.emit(
                    run_id=run_id,
                    event_type=RuntimeEventType.RUN_FAILED,
                    payload={
                        "status": RunStatus.FAILED.value,
                        "failure_stage": "POST_SCHEDULER",
                        "failure_code": type(exc).__name__.upper(),
                        "safe_message": "The Run could not complete its release checks.",
                    },
                    timestamp=terminal_at,
                )
            terminal_status = RunStatus(str(terminal_event.payload.get("status", "")))
            self._apply_terminal_lifecycle(
                aggregate,
                status=terminal_status,
                terminal_at=terminal_event.timestamp,
            )
            await self.repository.save_run(aggregate)
            await self.repository.save_runtime_events(list(await self.event_store.replay(run_id)))
            raise
        await self.repository.save_run(aggregate)
        await self.repository.save_runtime_events(list(await self.event_store.replay(run_id)))
        return aggregate

    async def get_object(self, object_id: str) -> ResearchObject:
        return await self._object(object_id)

    async def get_run(self, run_id: str) -> RunAggregate:
        return await self._aggregate(run_id)

    async def ingest_fixture_evidence(self, aggregate: RunAggregate) -> EvidenceIngestionResult:
        """Backward-compatible alias for Phase-1 callers."""

        return await self.ingest_research_evidence(aggregate)

    async def ingest_research_evidence(self, aggregate: RunAggregate) -> EvidenceIngestionResult:
        research_object = await self._object(aggregate.run.research_object_id)
        return await self.evidence_collector.collect(
            symbol=research_object.symbol,
            run_id=aggregate.run.run_id,
            object_id=research_object.object_id,
            as_of=aggregate.run.as_of,
        )

    async def route_task_evidence(
        self,
        aggregate: RunAggregate,
        task: Task,
        *,
        acquire: bool,
    ) -> TaskEvidenceRoutingResult:
        """Route run-global evidence while persisting only references on each Task."""

        research_object = await self._object(aggregate.run.research_object_id)
        store = self._evidence_stores.setdefault(
            aggregate.run.run_id, RunEvidenceStore(aggregate.run.run_id)
        )
        router = EvidenceTaskRouter(collector=self.evidence_collector, store=store)  # type: ignore[arg-type]
        routing = await router.route(
            task,
            symbol=research_object.symbol,
            object_id=research_object.object_id,
            as_of=aggregate.run.as_of,
            acquire=acquire,
        )
        routing.apply_to(task)
        routing.apply_to(aggregate.runtime.task(task.task_id))
        accepted_ids = set(store.select_ids())
        aggregate.artifacts.evidence = [
            record for record in store.records if record.evidence_id in accepted_ids
        ]
        aggregate.runtime.evidence_refs = list(store.select_ids())
        return routing

    async def _assure_and_release(self, aggregate: RunAggregate) -> None:
        run_id = aggregate.run.run_id
        calculations_before_review = list(aggregate.artifacts.calculations)
        judgments = list(aggregate.artifacts.judgments)
        strict_financial_release = any(
            calculation.formula_id in set(MATERIAL_FORMULAS[2:])
            for calculation in calculations_before_review
        )
        released_metrics = ()
        material_claims = ()
        material_dispositions = ()
        research_news_result = next(
            (
                output
                for task_id, output in aggregate.artifacts.task_outputs.items()
                if ":analyze-research-news" in task_id or task_id.endswith(":research-news")
            ),
            {"status": "not_available", "limitation": True},
        )
        source_coverage = None
        if strict_financial_release:
            (
                released_metrics,
                material_claims,
                material_dispositions,
            ) = build_material_financial_release(
                run_id=run_id,
                evidence=aggregate.artifacts.evidence,
                calculations=calculations_before_review,
                judgments=judgments,
            )
            source_coverage = build_research_source_coverage(research_news_result)

        proof_policy = ProofPolicy(require_material_calculations=self.proof_workflow is not None)
        proof_requirements = {
            calculation.calculation_id: proof_policy.requirement_for(calculation)
            for calculation in calculations_before_review
        }
        async with self.instrumentation.review(
            run_id=run_id,
            attributes={"review_id": f"REVIEW-{run_id}"},
        ):
            await self.event_store.emit(
                run_id=run_id,
                event_type=RuntimeEventType.REVIEW_STARTED,
            )
            if strict_financial_release:
                review = IndependentFinancialReviewer().review(
                    review_id=f"REVIEW-{run_id}",
                    run_id=run_id,
                    run_as_of=aggregate.run.as_of,
                    evidence=aggregate.artifacts.evidence,
                    calculations=calculations_before_review,
                    metrics=released_metrics,
                    claims=material_claims,
                    judgments=judgments,
                    proof_requirements=proof_requirements,
                )
            else:
                review = DeterministicReviewer().review(
                    review_id=f"REVIEW-{run_id}",
                    run_id=run_id,
                    evidence=aggregate.artifacts.evidence,
                    calculations=calculations_before_review,
                )
            aggregate.artifacts.review = review
            aggregate.runtime.review_state = review.model_dump(mode="json")
            await self.event_store.emit(
                run_id=run_id,
                event_type=RuntimeEventType.REVIEW_RESOLVED,
                payload={"review_id": review.review_id, "status": review.status.value},
            )

        if review.status.value != "PASS":
            raise ApplicationError(
                "REVIEW_BLOCKED",
                "independent review did not pass",
                details={"review_id": review.review_id, "status": review.status.value},
            )

        proof_outcome = await self._execute_proof_workflow(aggregate)
        if proof_outcome.requirements != proof_requirements:
            raise ApplicationError(
                "PROOF_POLICY_CHANGED_AFTER_REVIEW",
                "proof requirements changed after independent review",
            )
        aggregate.artifacts.proofs = list(proof_outcome.proofs.values())
        aggregate.runtime.proof_state = proof_outcome.runtime_state

        release_decision = ReleaseGate().evaluate(
            review=review,
            proof_requirements=proof_outcome.requirements,
            proofs=proof_outcome.proofs,
            calculations={item.calculation_id: item for item in calculations_before_review},
            evidence=(aggregate.artifacts.evidence if strict_financial_release else None),
            metrics=(released_metrics if strict_financial_release else None),
            claims=(material_claims if strict_financial_release else None),
            judgments=(judgments if strict_financial_release else None),
            run_as_of=(aggregate.run.as_of if strict_financial_release else None),
            input_commitments=(
                proof_outcome.input_commitments
                if strict_financial_release
                else proof_outcome.input_commitments or None
            ),
            verifications=(
                proof_outcome.verifications
                if strict_financial_release
                else proof_outcome.verifications or None
            ),
            artifacts=(
                proof_outcome.artifacts
                if strict_financial_release
                else proof_outcome.artifacts or None
            ),
        )
        if not release_decision.allowed:
            raise ApplicationError(
                "RELEASE_GATE_BLOCKED",
                "assurance requirements were not satisfied",
                details={"reason_codes": list(release_decision.reason_codes)},
            )

        trace_references = (
            await self.trace_reference_repository.list_by_run(run_id)
            if self.trace_reference_repository is not None
            else []
        )
        record = CanonicalExecutionRecordBuilder.build(
            record_id=f"CER-{run_id}",
            run_id=run_id,
            object_snapshot_ref=aggregate.run.research_object_id,
            goal_ref=aggregate.goal.goal_id,
            scheme_ref=aggregate.scheme.scheme_id,
            planned_graph=aggregate.runtime.planned_graph.model_dump(mode="json"),
            actual_graph=aggregate.runtime.actual_graph.model_dump(mode="json"),
            task_refs=[task.task_id for task in aggregate.runtime.actual_graph.tasks],
            evidence_refs=[record.evidence_id for record in aggregate.artifacts.evidence],
            calculation_refs=[
                calculation.calculation_id for calculation in aggregate.artifacts.calculations
            ],
            metric_refs=[metric.metric_id for metric in released_metrics],
            claim_refs=[claim.claim_id for claim in material_claims],
            judgment_refs=[
                str(judgment["judgment_id"])
                for judgment in judgments
                if isinstance(judgment.get("judgment_id"), str)
            ],
            generated_capability_refs=aggregate.artifacts.generated_capability_refs,
            correction_refs=[item.correction_id for item in aggregate.artifacts.corrections],
            replan_refs=[item.replan_id for item in aggregate.artifacts.replans],
            review_refs=[review.review_id],
            proof_refs=[proof.proof_id for proof in proof_outcome.proofs.values()],
            trace_refs=[reference.reference_id for reference in trace_references],
            runtime_outcome=RunStatus.RELEASED.value,
        )
        aggregate.artifacts.calculations = link_calculation_lineage(
            aggregate.artifacts.calculations,
            review=review,
            canonical_record=record,
            proofs=[
                proof for proof in proof_outcome.proofs.values() if isinstance(proof, ProofRecord)
            ],
        )
        fundamental_calculation_refs = list(record.calculation_refs)
        technical_calculation_refs: list[str] = []
        if strict_financial_release:
            (
                fundamental_calculation_refs,
                technical_calculation_refs,
            ) = partition_material_calculation_refs(aggregate.artifacts.calculations)
            if set(fundamental_calculation_refs) | set(technical_calculation_refs) != set(
                record.calculation_refs
            ):
                raise ApplicationError(
                    "MATERIAL_CALCULATION_TAXONOMY_MISMATCH",
                    "structured report calculation taxonomy does not close to the canonical record",
                )
        calculations = {item.capability_id: item for item in aggregate.artifacts.calculations}
        live_evidence = any(item.provider == "fmp" for item in aggregate.artifacts.evidence)
        risk_result = next(
            (
                output
                for task_id, output in aggregate.artifacts.task_outputs.items()
                if task_id.endswith(":risk-follow-up")
            ),
            {"finding": "No additional quantified risk conclusion is available."},
        )
        structured = {
            "research_object": aggregate.run.research_object_id,
            "financial_summary": {
                "revenue_growth": str(calculations["revenue_growth"].output_value),
                "ebitda_margin": str(calculations["ebitda_margin"].output_value),
            },
            "fundamental_result": {"calculation_refs": fundamental_calculation_refs},
            "peer_result": next(
                (
                    output
                    for task_id, output in aggregate.artifacts.task_outputs.items()
                    if ":analyze-peers" in task_id or task_id.endswith(":peers")
                ),
                {"status": "not_available"},
            ),
            "research_news_result": research_news_result,
            "valuation_result": {"status": "not_quantified_in_current_scope"},
            "investment_thesis": {"status": "reviewed_execution"},
        }
        if strict_financial_release:
            structured["technical_result"] = {
                "calculation_refs": technical_calculation_refs,
            }
        limitations = list(proof_outcome.limitations)
        if not live_evidence:
            limitations.insert(0, "Offline controlled fixture only.")
        if research_news_result.get("limitation"):
            limitations.append(
                "Research-news analysis is limited because no accepted licensed news or "
                "transcript evidence was available."
            )
        result = ReleasedResearchResultBuilder.build(
            result_id=f"RESULT-{run_id}",
            canonical_record=record,
            release_gate=ReleaseGateSnapshot(
                review_status=review.status,
                must_prove_statuses=[
                    proof_outcome.proofs[calculation_id].status
                    for calculation_id, requirement in proof_outcome.requirements.items()
                    if requirement is ProofRequirement.MUST_PROVE
                ],
            ),
            structured_financial_results=structured,
            released_claims=(
                []
                if strict_financial_release
                else [{"type": "CALCULATION", "refs": record.calculation_refs}]
            ),
            released_metrics=released_metrics,
            material_claims=material_claims,
            material_calculation_dispositions=material_dispositions,
            research_source_coverage=source_coverage,
            judgments=judgments,
            risk_output=risk_result,
            limitations=limitations,
        )
        object_id = aggregate.run.research_object_id
        report = FinancialReportRenderer.render(result, research_object=object_id)
        projections = build_canonical_record_projections(record)
        evidence = aggregate.artifacts.evidence
        current_revenue = max(
            (item for item in evidence if item.normalized_field == "revenue"),
            key=lambda item: (item.as_of, item.period, item.evidence_id),
        )
        growth = calculations["revenue_growth"]
        writeback = ObjectWritebackProposalBuilder.build(
            proposal_id=f"WRITEBACK-{run_id}",
            object_id=object_id,
            run_id=run_id,
            items=[
                ObjectWritebackItem(
                    metric_code="revenue",
                    period=current_revenue.period,
                    as_of=current_revenue.as_of,
                    definition_version="1",
                    value=current_revenue.normalized_value,
                    unit=current_revenue.unit,
                    currency=current_revenue.currency,
                    value_type=ValueType.FACT,
                    writeback_target=WritebackTarget.CANONICAL_STATE,
                    source_evidence_ids=[current_revenue.evidence_id],
                ),
                ObjectWritebackItem(
                    metric_code="revenue_growth",
                    period=current_revenue.period,
                    as_of=aggregate.run.as_of,
                    definition_version="revenue_growth_v1",
                    value=str(growth.output_value),
                    unit=growth.output_unit,
                    value_type=ValueType.CALCULATION,
                    writeback_target=WritebackTarget.VERSIONED_METRIC,
                    calculation_id=growth.calculation_id,
                ),
            ],
        )
        async with self.instrumentation.release(
            run_id=run_id,
            attributes={
                "review_id": review.review_id,
                "canonical_record_id": record.record_id,
                "released_result_id": result.result_id,
                "runtime_status": RunStatus.RELEASED.value,
            },
        ):
            aggregate.artifacts.canonical_record = record
            aggregate.artifacts.released_result = result
            aggregate.artifacts.projections = projections
            aggregate.artifacts.report = report
            aggregate.artifacts.writeback = writeback
            await self.event_store.emit(
                run_id=run_id,
                event_type=RuntimeEventType.RELEASE_COMPLETED,
                payload={
                    "canonical_record_id": record.record_id,
                    "result_id": result.result_id,
                },
            )
            terminal_at = datetime.now(UTC)
            self._apply_terminal_lifecycle(
                aggregate,
                status=RunStatus.RELEASED,
                terminal_at=terminal_at,
            )
            await self.event_store.emit(
                run_id=run_id,
                event_type=RuntimeEventType.RUN_COMPLETED,
                payload={"status": RunStatus.RELEASED.value},
                timestamp=terminal_at,
            )

    @staticmethod
    def _apply_terminal_lifecycle(
        aggregate: RunAggregate,
        *,
        status: RunStatus,
        terminal_at: datetime,
    ) -> None:
        if status not in {RunStatus.RELEASED, RunStatus.FAILED, RunStatus.CANCELLED}:
            raise ValueError("terminal lifecycle requires a terminal Run status")
        aggregate.run.status = status
        aggregate.runtime.run_status = status
        aggregate.run.completed_at = terminal_at
        if aggregate.run.updated_at < terminal_at:
            aggregate.run.updated_at = terminal_at

    async def _execute_proof_workflow(
        self,
        aggregate: RunAggregate,
    ) -> ProofWorkflowOutcome:
        run_id = aggregate.run.run_id
        if self.proof_workflow is not None:
            return await self.proof_workflow.execute(
                run_id=run_id,
                calculations=aggregate.artifacts.calculations,
            )
        proof_policy = ProofPolicy(require_material_calculations=False)
        requirements = {
            calculation.calculation_id: proof_policy.requirement_for(calculation)
            for calculation in aggregate.artifacts.calculations
        }
        first = aggregate.artifacts.calculations[0]
        proof = await PendingProofAdapter().prove(
            ProofRequest(
                proof_id=f"PROOF-{run_id}-PHASE1",
                run_id=run_id,
                calculation_id=first.calculation_id,
                program_id="risc0-financial-v1-not-implemented",
                input_commitments=first.input_evidence_ids,
            )
        )
        assert proof.status is ProofStatus.NOT_IMPLEMENTED
        return ProofWorkflowOutcome(
            requirements=requirements,
            proofs={first.calculation_id: proof},
            runtime_state={
                "status": proof.status.value,
                "semantics": "No ZK proof is claimed; Phase 1 policy is NOT_REQUIRED.",
            },
            limitations=("RISC Zero proof is NOT_IMPLEMENTED and no proof claim is made.",),
        )

    async def _object(self, object_id: str) -> ResearchObject:
        entity = await self.repository.get_object(object_id)
        if entity is None:
            raise NotFoundError("research_object", object_id)
        return entity

    async def _aggregate(self, run_id: str) -> RunAggregate:
        aggregate = await self.repository.get_run(run_id)
        if aggregate is None:
            raise NotFoundError("research_run", run_id)
        return aggregate

    def _idempotent(self, operation: str, key: str | None) -> object | None:
        return self._idempotency.get((operation, key)) if key else None

    def _remember(self, operation: str, key: str | None, value: object) -> None:
        if key:
            self._idempotency[(operation, key)] = value
