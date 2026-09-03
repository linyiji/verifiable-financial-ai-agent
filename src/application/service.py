from __future__ import annotations

import inspect
from collections.abc import Callable
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
from src.application.execution import IntegratedTaskExecutor, decimal_as_float
from src.application.models import ResearchRunDraft, RunAggregate
from src.application.repository import ApplicationRepository, InMemoryApplicationRepository
from src.assurance import DeterministicReviewer, ReleaseGate
from src.assurance.proof_policy import ProofPolicy
from src.capabilities.calculation_lineage import link_calculation_lineage
from src.capabilities.financial.growth import RevenueGrowthCapability
from src.capabilities.financial.profitability import EbitdaMarginCapability
from src.capabilities.registry import CapabilityRegistry
from src.data.ingestion import EvidenceIngestionResult
from src.data.repository import EvidenceRepository, InMemoryEvidenceRepository
from src.domain.enums import CapabilityBackend, ProofStatus, RunStatus
from src.domain.proof import ProofRequest
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

        registry = CapabilityRegistry()
        registry.register(RevenueGrowthCapability())
        registry.register(EbitdaMarginCapability())
        self.capability_registry = registry
        self.tool_runtime = ToolRuntime(
            registry,
            {CapabilityBackend.NATIVE: NativeToolBackend(registry)},
        )

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
        async with self.instrumentation.scheme(run_id=f"DRAFT:{goal_id}"):
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

    async def execute_run(self, run_id: str) -> RunAggregate:
        aggregate = await self._aggregate(run_id)
        if aggregate.run.status is RunStatus.RELEASED:
            return aggregate
        aggregate.run.status = RunStatus.RUNNING
        aggregate.run.started_at = datetime.now(UTC)
        try:
            async with self.instrumentation.run(run_id=run_id):
                executor = IntegratedTaskExecutor(self, aggregate)
                scheduler = DependencyScheduler(
                    event_store=self.event_store,
                    checkpoint_store=self.checkpoint_store,
                )
                await scheduler.execute(state=aggregate.runtime, executor=executor)
                aggregate.artifacts.parallel_task_peak = executor.parallel_peak
                await self._assure_and_release(aggregate)
        except Exception:
            aggregate.run.status = RunStatus.FAILED
            aggregate.run.completed_at = datetime.now(UTC)
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
        async with self.instrumentation.review(
            run_id=run_id,
            attributes={"review_id": f"REVIEW-{run_id}"},
        ):
            await self.event_store.emit(
                run_id=run_id,
                event_type=RuntimeEventType.REVIEW_STARTED,
            )
            review = DeterministicReviewer().review(
                review_id=f"REVIEW-{run_id}",
                run_id=run_id,
                evidence=aggregate.artifacts.evidence,
                calculations=aggregate.artifacts.calculations,
            )
            aggregate.artifacts.review = review
            aggregate.runtime.review_state = review.model_dump(mode="json")
            await self.event_store.emit(
                run_id=run_id,
                event_type=RuntimeEventType.REVIEW_RESOLVED,
                payload={"review_id": review.review_id, "status": review.status.value},
            )

        proof_policy = ProofPolicy(require_material_calculations=False)
        proof_requirements = {
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
        aggregate.artifacts.proofs = [proof]
        aggregate.runtime.proof_state = {
            "status": proof.status.value,
            "semantics": "No ZK proof is claimed; Phase 1 policy is NOT_REQUIRED.",
        }
        release_decision = ReleaseGate().evaluate(
            review=review,
            proof_requirements=proof_requirements,
            proofs={first.calculation_id: proof},
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
            correction_refs=[item.correction_id for item in aggregate.artifacts.corrections],
            replan_refs=[item.replan_id for item in aggregate.artifacts.replans],
            review_refs=[review.review_id],
            proof_refs=[proof.proof_id],
            trace_refs=[reference.reference_id for reference in trace_references],
            runtime_outcome=RunStatus.RELEASED.value,
        )
        aggregate.artifacts.calculations = link_calculation_lineage(
            aggregate.artifacts.calculations,
            review=review,
            canonical_record=record,
        )
        calculations = {item.capability_id: item for item in aggregate.artifacts.calculations}
        live_evidence = any(item.provider == "fmp" for item in aggregate.artifacts.evidence)
        research_news_result = next(
            (
                output
                for task_id, output in aggregate.artifacts.task_outputs.items()
                if ":analyze-research-news" in task_id or task_id.endswith(":research-news")
            ),
            {"status": "not_available", "limitation": True},
        )
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
                "revenue_growth": decimal_as_float(calculations["revenue_growth"].output_value),
                "ebitda_margin": decimal_as_float(calculations["ebitda_margin"].output_value),
            },
            "fundamental_result": {"calculation_refs": record.calculation_refs},
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
        limitations = [
            "RISC Zero proof is NOT_IMPLEMENTED and no proof claim is made.",
        ]
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
            release_gate=ReleaseGateSnapshot(review_status=review.status),
            structured_financial_results=structured,
            released_claims=[{"type": "CALCULATION", "refs": record.calculation_refs}],
            judgments=[
                {
                    "judgment_ref": f"JUDGMENT-{run_id}-V1",
                    "version": 1,
                    "text": "Evidence-backed research execution; not investment advice.",
                }
            ],
            risk_output=risk_result,
            limitations=limitations,
        )
        object_id = aggregate.run.research_object_id
        report = FinancialReportRenderer.render(result, research_object=object_id)
        projections = build_canonical_record_projections(record)
        evidence = aggregate.artifacts.evidence
        current_revenue = next(
            item
            for item in evidence
            if item.normalized_field == "revenue" and item.period == "FY2026"
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
                    period="FY2026",
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
            aggregate.run.status = RunStatus.RELEASED
            aggregate.runtime.run_status = RunStatus.RELEASED
            aggregate.run.completed_at = datetime.now(UTC)
            await self.event_store.emit(
                run_id=run_id,
                event_type=RuntimeEventType.RELEASE_COMPLETED,
                payload={
                    "canonical_record_id": record.record_id,
                    "result_id": result.result_id,
                },
            )
            await self.event_store.emit(
                run_id=run_id,
                event_type=RuntimeEventType.RUN_COMPLETED,
                payload={"status": RunStatus.RELEASED.value},
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
