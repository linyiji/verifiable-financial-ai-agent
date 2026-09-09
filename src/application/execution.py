from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from src.agentic.decisions import ResearchLeadReplanDecider
from src.agentic.registry import RegistrationNotFoundError
from src.agentic.research_agent import ResearchAgentInvocationError
from src.agentic.specialist import SpecialistExecutionContext, SpecialistResult
from src.application.research_outputs import (
    availability_map,
    configure_output_contracts,
    publish_output,
)
from src.data.peers import PeerCompanyFacts, PeerSelectionService
from src.domain.agent_output import ResearchAgentOutputRecord
from src.domain.capability import CapabilityContext
from src.domain.correction import CorrectionRecord
from src.domain.decision import StructuredAgentDecision
from src.domain.enums import (
    CorrectionStatus,
    EvidenceAcquisitionStatus,
    EvidenceCategory,
    ReplanDecision,
    TaskOrigin,
)
from src.domain.financial_branch import BranchRequirement
from src.domain.output_dependency import LocalOutputFailure, OutputStatus
from src.domain.runtime_event import RuntimeEventType
from src.domain.task import ReplanRequest, Task
from src.observability.instrumentation import ObservationStage
from src.observability.performance import observe
from src.runtime.graph import (
    GraphMutationActor,
    GraphMutationRole,
    GraphMutationService,
)
from src.runtime.scheduler import TaskExecutionContext, TaskExecutionResult


class IntegratedTaskExecutor:
    """Adapter from runtime Tasks to application capabilities and Agent decisions."""

    def __init__(self, service: object, aggregate: object) -> None:
        self._service = service
        self._aggregate = aggregate
        configure_output_contracts(aggregate.runtime)
        self._has_specialized_collection_tasks = (
            sum(
                task.task_type == "evidence_collection"
                for task in aggregate.runtime.actual_graph.tasks
            )
            > 1
        )
        self._active = 0
        self.parallel_peak = 0
        self._calculation_commit_lock = asyncio.Lock()

    @observe("task.execution", task="task")
    async def execute(
        self,
        task: Task,
        context: TaskExecutionContext,
    ) -> TaskExecutionResult:
        del context
        self._active += 1
        self.parallel_peak = max(self.parallel_peak, self._active)
        try:
            # Yield once so independent READY tasks demonstrably overlap in the runtime.
            await asyncio.sleep(0)
            async with self._service.instrumentation.task(
                run_id=task.run_id,
                task_id=task.task_id,
                attributes={"task_type": task.task_type},
            ):
                async with self._service.instrumentation.agent(
                    run_id=task.run_id,
                    task_id=task.task_id,
                    attributes={"agent": task.assigned_agent},
                ):
                    async with self._service.instrumentation.skill(
                        run_id=task.run_id,
                        task_id=task.task_id,
                        attributes={"skill": task.skill_id},
                    ):
                        return await self._execute_instrumented_task(task)
        finally:
            self._active -= 1

    async def _execute_instrumented_task(self, task: Task) -> TaskExecutionResult:
        await self._service.event_store.emit(
            run_id=task.run_id,
            task_id=task.task_id,
            event_type=RuntimeEventType.TASK_PROGRESS,
            payload={
                "progress": 0.1,
                "stage": "dispatched",
                "message": "Task dispatched to its application execution adapter.",
            },
        )
        acquire = self._should_acquire_evidence(task)
        async with self._service.instrumentation.tool(
            run_id=task.run_id,
            task_id=task.task_id,
            attributes={
                "tool_name": "evidence_router",
                "capability": "live_or_fixture_evidence_collection" if acquire else "evidence_link",
            },
        ):
            routing = await self._service.route_task_evidence(
                self._aggregate,
                task,
                acquire=acquire,
            )
        if routing.acquisition_status is not None:
            produced = set(routing.output_evidence_ids)
            records = [
                record
                for record in self._aggregate.artifacts.evidence
                if record.evidence_id in produced
            ]
            authoritative = self._aggregate.runtime.task(task.task_id)
            for endpoint, coverage in authoritative.evidence_source_coverage.items():
                refs = [
                    record.evidence_id
                    for record in records
                    if record.source_endpoint == endpoint and record.status.value == "ACCEPTED"
                ]
                status = OutputStatus(coverage["outcome"])
                if status is OutputStatus.COMPLETED and not refs:
                    status = OutputStatus.INSUFFICIENT_EVIDENCE
                publish_output(
                    authoritative,
                    "source." + endpoint,
                    status,
                    refs=refs,
                    reason=coverage.get("error_code"),
                )
                await self._service.event_store.emit(
                    run_id=task.run_id,
                    task_id=task.task_id,
                    event_type=RuntimeEventType.TASK_PROGRESS,
                    payload={
                        "progress": authoritative.progress,
                        "message_code": f"SOURCE_OUTCOME:{endpoint}:{status.value}:{len(refs)}",
                    },
                )
            status_counts: dict[str, int] = {}
            for record in records:
                status_counts[record.status.value] = status_counts.get(record.status.value, 0) + 1
            if not records:
                status_counts[routing.acquisition_status.value] = 1
            async with self._service.instrumentation.observe(
                ObservationStage.EVIDENCE,
                run_id=task.run_id,
                task_id=task.task_id,
                attributes={
                    "evidence_count": len(records),
                    "providers": sorted({record.provider for record in records}),
                    "periods": sorted({record.period for record in records}),
                    "normalized_fields": sorted({record.normalized_field for record in records}),
                    "status_counts": status_counts,
                },
            ):
                pass
        for intent in routing.event_intents:
            await self._service.event_store.emit(
                run_id=intent.run_id,
                task_id=intent.task_id,
                event_type=intent.type,
                payload=intent.payload,
            )
        handler = self._handler_for(task)
        return await handler(task)

    async def _execute_evidence_collection(self, task: Task) -> TaskExecutionResult:
        routed = self._aggregate.runtime.task(task.task_id)
        acquisition = routed.evidence_acquisition_status
        status = acquisition.value.lower() if acquisition is not None else "not_requested"
        return TaskExecutionResult(
            result_ref=f"evidence://{task.run_id}/{task.task_id.rsplit(':', 1)[-1]}/{status}",
            output_refs=tuple(routed.task_output_evidence_ids),
        )

    async def _execute_fundamental_analysis(self, task: Task) -> TaskExecutionResult:
        input_ids = set(self._aggregate.runtime.task(task.task_id).task_input_evidence_ids)
        evidence = [
            record
            for record in self._aggregate.artifacts.evidence
            if record.evidence_id in input_ids
        ]
        prior, current, mismatch, ebitda = _select_financial_inputs(evidence)
        context = CapabilityContext(
            run_id=task.run_id,
            task_id=task.task_id,
            accepted_evidence_ids=[record.evidence_id for record in evidence],
        )
        await self._service.event_store.emit(
            run_id=task.run_id,
            task_id=task.task_id,
            event_type=RuntimeEventType.CALCULATION_STARTED,
            payload={"capability_id": "revenue_growth"},
        )
        growth = await self._execute_calculation(
            task=task,
            capability_id="revenue_growth",
            inputs={
                "prior": prior,
                "current": current,
                "calculation_id": f"CALC-{task.run_id}-GROWTH",
            },
            context=context,
        )
        await self._commit_calculation(task, growth)

        # The fixture intentionally presents a quarterly revenue candidate first.
        # The real capability rejects its period mismatch and the same task corrects it.
        correction = None
        try:
            await self._execute_calculation(
                task=task,
                capability_id="ebitda_margin",
                inputs={
                    "ebitda": ebitda,
                    "revenue": mismatch,
                    "calculation_id": f"CALC-{task.run_id}-MARGIN-BAD",
                },
                context=context,
            )
        except ValueError as exc:
            from src.capabilities.financial.common import PeriodMismatchError

            if not isinstance(exc, PeriodMismatchError):
                raise
            correction_id = f"CORR-{task.run_id}-PERIOD"
            # Awaited event publication, not presentation dwell, defines the
            # durable correction boundaries. Slow consumers reconstruct by replay.
            async with self._service.instrumentation.self_correction(
                run_id=task.run_id,
                task_id=task.task_id,
                attributes={
                    "correction_id": correction_id,
                    "problem_code": "PERIOD_MISMATCH",
                    "error_type": type(exc).__name__,
                },
            ):
                await self._service.event_store.emit(
                    run_id=task.run_id,
                    task_id=task.task_id,
                    event_type=RuntimeEventType.TASK_SELF_CORRECTING,
                    payload={"problem_code": "PERIOD_MISMATCH", "error": type(exc).__name__},
                )
                correction_timestamp = datetime.now(UTC)
                correction = CorrectionRecord(
                    correction_id=correction_id,
                    run_id=task.run_id,
                    task_id=task.task_id,
                    problem_code="PERIOD_MISMATCH",
                    detected_by="ebitda_margin",
                    attempt=1,
                    action="SELECT_PERIOD_ALIGNED_REVENUE",
                    input_refs=[ebitda.evidence_id, mismatch.evidence_id],
                    output_refs=[current.evidence_id],
                    status=CorrectionStatus.RESOLVED,
                    created_at=correction_timestamp,
                    resolved_at=correction_timestamp,
                )

        margin = await self._execute_calculation(
            task=task,
            capability_id="ebitda_margin",
            inputs={
                "ebitda": ebitda,
                "revenue": current,
                "calculation_id": f"CALC-{task.run_id}-MARGIN",
            },
            context=context,
        )
        await self._commit_calculation(task, margin)
        if correction is not None:
            correction.resolved_at = datetime.now(UTC)
            self._aggregate.artifacts.corrections.append(correction)
            await self._service.event_store.emit(
                run_id=task.run_id,
                task_id=task.task_id,
                event_type=RuntimeEventType.TASK_CORRECTION_RESOLVED,
                payload={"correction_id": correction.correction_id},
            )
        extension_calculations = []
        extension_refs: list[str] = []
        extension_judgments: list[dict[str, object]] = []
        extension_output: dict[str, object] = {}
        for extension in self._service.calculation_extensions:

            async def commit(part):
                async with self._calculation_commit_lock:
                    for calculation in part.calculations:
                        await self._commit_calculation(task, calculation)
                    self._aggregate.artifacts.generated_capability_refs.extend(
                        part.generated_capability_refs
                    )
                    self._aggregate.artifacts.judgments.extend(part.judgments)

            async def publish(outcome):
                async with self._calculation_commit_lock:
                    self._aggregate.artifacts.financial_branches.append(outcome)
                    if outcome.status.value != "NOT_APPLICABLE":
                        publish_output(
                            self._aggregate.runtime.task(task.task_id),
                            outcome.calculation_type,
                            OutputStatus(outcome.status.value),
                            refs=outcome.calculation_ids,
                            reason=outcome.reason_code,
                        )
                    await self._service.repository.save_runtime_events(
                        list(await self._service.event_store.replay(task.run_id))
                    )

            incremental = getattr(extension, "execute_incremental", None)
            if incremental is not None:
                scheme = getattr(self._aggregate, "scheme", None)
                required = getattr(scheme, "calculation_requirements", [])
                result = await incremental(
                    task=task,
                    state=self._aggregate.runtime,
                    evidence=evidence,
                    context=context,
                    commit=commit,
                    publish=publish,
                    requirements={key: BranchRequirement.REQUIRED for key in required},
                )
            else:
                result = await extension.execute(
                    task=task, state=self._aggregate.runtime, evidence=evidence, context=context
                )
                await commit(result)
            for calculation in result.calculations:
                if calculation.run_id != task.run_id or calculation.task_id != task.task_id:
                    raise ValueError("calculation extension returned cross-task lineage")
            extension_calculations.extend(result.calculations)
            extension_refs.extend(result.generated_capability_refs)
            extension_judgments.extend(result.judgments)
            extension_output.update(result.task_output)
        supporting_output = {
            "revenue_growth": str(growth.output_value),
            "ebitda_margin": str(margin.output_value),
            **extension_output,
        }
        calculation_refs = (
            growth.calculation_id,
            margin.calculation_id,
            *(item.calculation_id for item in extension_calculations),
        )
        agent_result = await self._invoke_research_agent(
            task,
            supporting_output=supporting_output,
            additional_input_refs=calculation_refs,
        )
        if agent_result is not None:
            return self._accept_research_agent_output(
                task,
                agent_result,
                supporting_output=supporting_output,
                additional_output_refs=calculation_refs,
            )
        self._aggregate.artifacts.task_outputs[task.task_id] = supporting_output
        return TaskExecutionResult(
            result_ref=f"analysis://{task.task_id}",
            output_refs=calculation_refs,
        )

    async def _execute_calculation(
        self,
        *,
        task: Task,
        capability_id: str,
        inputs: dict[str, object],
        context: CapabilityContext,
    ):
        calculation_id = str(inputs.get("calculation_id", ""))
        async with self._service.instrumentation.calculation(
            run_id=task.run_id,
            task_id=task.task_id,
            attributes={
                "calculation_id": calculation_id,
                "capability": capability_id,
            },
        ):
            async with self._service.instrumentation.tool(
                run_id=task.run_id,
                task_id=task.task_id,
                attributes={"tool_name": "native_financial_code", "capability": capability_id},
            ):
                return await self._service.tool_runtime.execute(
                    capability_id,
                    inputs,
                    context,
                )

    async def _commit_calculation(self, task, calculation):
        if calculation.run_id != task.run_id or calculation.task_id != task.task_id:
            raise ValueError("calculation commit returned cross-task lineage")
        existing = next(
            (
                item
                for item in self._aggregate.artifacts.calculations
                if item.calculation_id == calculation.calculation_id
            ),
            None,
        )
        if existing is not None:
            if existing != calculation:
                raise ValueError("calculation identity is immutable")
            return
        await self._service.repository.save_calculation(calculation)
        self._aggregate.artifacts.calculations.append(calculation)
        # Technical MACD has multiple records; branch-level publication owns that
        # compound output. Single native anchors are published only after durable save.
        if calculation.capability_id in {"revenue_growth", "ebitda_margin"}:
            publish_output(
                self._aggregate.runtime.task(task.task_id),
                calculation.capability_id,
                OutputStatus.COMPLETED,
                refs=[calculation.calculation_id],
            )
        await self._service.event_store.emit(
            run_id=task.run_id,
            task_id=task.task_id,
            event_type=RuntimeEventType.CALCULATION_COMPLETED,
            payload={
                "calculation_id": calculation.calculation_id,
                "capability_id": calculation.capability_id,
            },
        )

    async def _execute_risk_analysis(self, task: Task) -> TaskExecutionResult:
        agent_result = await self._invoke_research_agent(
            task,
            supporting_output={"status": "agent_assessment_required"},
        )
        if agent_result is not None:
            execution = self._accept_research_agent_output(
                task,
                agent_result,
                supporting_output={},
            )
            if agent_result.replan_request is not None:
                await self._apply_risk_replan(task, agent_result.replan_request)
            return execution

        return await self._execute_deterministic_risk_analysis(task)

    async def _execute_deterministic_risk_analysis(self, task: Task) -> TaskExecutionResult:
        synthesis = next(
            candidate
            for candidate in self._aggregate.runtime.actual_graph.tasks
            if candidate.task_type == "report_synthesis"
        )
        request = ReplanRequest(
            replan_id=f"REPLAN-{task.run_id}-RISK",
            run_id=task.run_id,
            requesting_task_id=task.task_id,
            requested_by=task.assigned_agent,
            reason_code="MATERIAL_RISK_FOLLOW_UP",
            reason_detail="Specialist requests a focused risk follow-up child task.",
            proposed_graph_change={
                "operation": "insert_task_between",
                "add_child_task_type": "risk_follow_up",
                "remove_edge": [task.task_id, synthesis.task_id],
                "add_edges": [
                    [task.task_id, f"{task.run_id}:risk-follow-up"],
                    [f"{task.run_id}:risk-follow-up", synthesis.task_id],
                ],
            },
        )
        specialist_result = SpecialistResult(
            output={"risk_signal": "requires_follow_up"},
            decision=StructuredAgentDecision(
                decision_id=f"DEC-{task.run_id}-RISK",
                run_id=task.run_id,
                task_id=task.task_id,
                decision_type="REQUEST_REPLAN",
                reason_code=request.reason_code,
                summary=request.reason_detail,
                evidence_ids=list(
                    self._aggregate.runtime.task(task.task_id).task_input_evidence_ids
                ),
                requires_review=True,
            ),
            replan_request=request,
        )
        pending = specialist_result.replan_request
        assert pending is not None and pending.decision is ReplanDecision.PENDING
        self._aggregate.artifacts.task_outputs[task.task_id] = specialist_result.output
        await self._apply_risk_replan(task, pending)
        return TaskExecutionResult(result_ref=f"analysis://{task.task_id}")

    async def _apply_risk_replan(self, task: Task, pending: ReplanRequest) -> None:
        synthesis = next(
            candidate
            for candidate in self._aggregate.runtime.actual_graph.tasks
            if candidate.task_type == "report_synthesis"
        )
        if (
            pending.run_id != task.run_id
            or pending.requesting_task_id != task.task_id
            or pending.requested_by != task.assigned_agent
            or pending.decision is not ReplanDecision.PENDING
        ):
            raise ValueError("risk replan request does not close to its authoritative task")
        self._aggregate.artifacts.replans.append(pending)
        async with self._service.instrumentation.replan(
            run_id=task.run_id,
            task_id=task.task_id,
            attributes={"replan_id": pending.replan_id, "reason_code": pending.reason_code},
        ):
            await self._service.event_store.emit(
                run_id=task.run_id,
                task_id=task.task_id,
                event_type=RuntimeEventType.REPLAN_REQUESTED,
                payload={"replan_id": pending.replan_id, "decision": pending.decision.value},
            )
            # Requested and approved remain separate awaited durable events;
            # browser presentation must not impose a minimum runtime dwell.
            decision = ResearchLeadReplanDecider().decide(
                pending,
                outcome=ReplanDecision.APPROVED,
                decision_id=f"DEC-{task.run_id}-REPLAN-APPROVED",
                reason_code="LEAD_APPROVED_FOCUSED_FOLLOW_UP",
                summary="Research Lead approved the bounded child task.",
            )
            child = Task(
                task_id=f"{task.run_id}:risk-follow-up",
                run_id=task.run_id,
                parent_task_id=task.task_id,
                task_type="risk_follow_up",
                goal="Validate the material risk signal as a bounded child task",
                assigned_agent="risk_analyst",
                skill_id="risk_analysis_v1",
                dependencies=[],
                origin=TaskOrigin.REPLAN,
                reason_code=pending.reason_code,
            )
            approved = decision.request.model_copy(update={"created_task_ids": [child.task_id]})
            self._aggregate.artifacts.replans[-1] = approved
            await self._service.event_store.emit(
                run_id=task.run_id,
                task_id=task.task_id,
                event_type=RuntimeEventType.REPLAN_APPROVED,
                payload={
                    "replan_id": pending.replan_id,
                    "decided_by": approved.decided_by,
                },
            )
            await GraphMutationService(self._service.event_store).insert_node_between(
                state=self._aggregate.runtime,
                request=approved,
                task=child,
                predecessor_task_id=task.task_id,
                successor_task_id=synthesis.task_id,
                actor=GraphMutationActor("research_lead", GraphMutationRole.RESEARCH_LEAD),
            )

    async def _execute_peer_analysis(self, task: Task) -> TaskExecutionResult:
        routed_task = self._aggregate.runtime.task(task.task_id)
        input_ids = set(routed_task.task_input_evidence_ids) | set(
            routed_task.task_output_evidence_ids
        )
        evidence = [
            record
            for record in self._aggregate.artifacts.evidence
            if record.evidence_id in input_ids
        ]
        subject = PeerCompanyFacts(
            symbol=str(_evidence_value(evidence, "symbol", "UNKNOWN")),
            industry=_optional_string(_evidence_value(evidence, "industry")),
            sector=_optional_string(_evidence_value(evidence, "sector")),
            market_cap=_optional_decimal(
                _evidence_value(evidence, "provider_reference_market_cap")
            ),
            source_evidence_ids=tuple(
                record.evidence_id
                for record in evidence
                if record.normalized_field
                in {"symbol", "industry", "sector", "provider_reference_market_cap"}
            ),
        )
        selection = PeerSelectionService().select(
            subject=subject,
            stock_peer_evidence=evidence,
            facts_by_symbol={},
            business_relevance={},
            required_metrics=frozenset({"revenue", "ebitda", "provider_reference_pe"}),
        )
        supporting_output = {
            "candidate_source": "fmp.stock_peers",
            "candidates": [item.model_dump(mode="json") for item in selection.candidates],
            "selection_decisions": [item.model_dump(mode="json") for item in selection.decisions],
            "selected_comparables": [
                item.model_dump(mode="json") for item in selection.selected_comparables
            ],
            "status": (
                "selected"
                if selection.selected_comparables
                else "no_selected_comparables_due_missing_enrichment"
            ),
        }
        agent_result = await self._invoke_research_agent(
            task,
            supporting_output=supporting_output,
        )
        if agent_result is not None:
            return self._accept_research_agent_output(
                task,
                agent_result,
                supporting_output=supporting_output,
            )
        self._aggregate.artifacts.task_outputs[task.task_id] = supporting_output
        return TaskExecutionResult(result_ref=f"peer-selection://{task.task_id}")

    async def _execute_risk_follow_up(self, task: Task) -> TaskExecutionResult:
        supporting_output = {
            "finding": (
                "No additional quantified risk can be supported by the available accepted evidence."
            ),
            "limitation": True,
        }
        agent_result = await self._invoke_research_agent(
            task,
            supporting_output=supporting_output,
        )
        if agent_result is not None:
            return self._accept_research_agent_output(
                task,
                agent_result,
                supporting_output=supporting_output,
            )
        self._aggregate.artifacts.task_outputs[task.task_id] = supporting_output
        return TaskExecutionResult(result_ref=f"analysis://{task.task_id}")

    async def _execute_research_news_analysis(self, task: Task) -> TaskExecutionResult:
        """Represent unavailable licensed news as a limitation, never as a success claim."""

        accepted = [
            record
            for record in self._aggregate.artifacts.evidence
            if record.evidence_id
            in self._aggregate.runtime.task(task.task_id).task_input_evidence_ids
            and record.evidence_category in {EvidenceCategory.NEWS, EvidenceCategory.TRANSCRIPT}
        ]
        dependency_statuses = {
            self._aggregate.runtime.task(dependency).evidence_acquisition_status
            for dependency in task.dependencies
        }
        dependency_statuses.add(
            self._aggregate.runtime.task(task.task_id).evidence_acquisition_status
        )
        source_coverage: dict[str, object] = {}
        for dependency in task.dependencies:
            candidate = self._aggregate.runtime.task(dependency).evidence_source_coverage
            if candidate:
                source_coverage.update(candidate)
        source_coverage.update(self._aggregate.runtime.task(task.task_id).evidence_source_coverage)
        source_coverage = {
            key: value for key, value in source_coverage.items() if key in {"news", "transcript"}
        }
        category_by_source = {
            "news": EvidenceCategory.NEWS,
            "transcript": EvidenceCategory.TRANSCRIPT,
        }
        for source, category in category_by_source.items():
            details = source_coverage.setdefault(
                source,
                {
                    "status": "EMPTY",
                    "http_status": 0,
                    "error_code": "NO_ENDPOINT_RESULT",
                    "accepted_count": 0,
                },
            )
            if isinstance(details, dict):
                details["accepted_evidence_ids"] = [
                    record.evidence_id
                    for record in accepted
                    if record.evidence_category is category
                ]
        if accepted and all(
            isinstance(item, dict) and item.get("status") == "AVAILABLE"
            for item in source_coverage.values()
        ):
            status = "completed"
            limitation = False
            reason = None
        elif accepted:
            status = "partial"
            limitation = True
            reason = "PARTIAL_NEWS_TRANSCRIPT_COVERAGE"
        elif EvidenceAcquisitionStatus.ENTITLEMENT_BLOCKED in dependency_statuses:
            status = "entitlement_blocked"
            limitation = True
            reason = "NEWS_TRANSCRIPT_ENTITLEMENT_BLOCKED"
        else:
            status = "insufficient_evidence"
            limitation = True
            reason = "NO_ACCEPTED_NEWS_OR_TRANSCRIPT_EVIDENCE"

        output: dict[str, object] = {
            "status": status,
            "accepted_evidence_ids": [record.evidence_id for record in accepted],
            "limitation": limitation,
            "source_coverage": source_coverage,
        }
        if reason is not None:
            output["reason_code"] = reason
        agent_result = await self._invoke_research_agent(
            task,
            supporting_output=output,
            additional_input_refs=tuple(record.evidence_id for record in accepted),
        )
        if agent_result is not None:
            return self._accept_research_agent_output(
                task,
                agent_result,
                supporting_output=output,
                additional_output_refs=tuple(record.evidence_id for record in accepted),
            )
        self._aggregate.artifacts.task_outputs[task.task_id] = output
        return TaskExecutionResult(
            result_ref=f"research-news://{task.task_id}/{status}",
            output_refs=tuple(record.evidence_id for record in accepted),
        )

    async def _execute_valuation_analysis(self, task: Task) -> TaskExecutionResult:
        supporting_output = {
            "status": "not_quantified_in_current_scope",
            "quantified_valuation_available": False,
        }
        agent_result = await self._invoke_research_agent(
            task,
            supporting_output=supporting_output,
        )
        if agent_result is not None:
            return self._accept_research_agent_output(
                task,
                agent_result,
                supporting_output=supporting_output,
            )
        self._aggregate.artifacts.task_outputs[task.task_id] = supporting_output
        return TaskExecutionResult(result_ref=f"analysis://{task.task_id}")

    async def _execute_report_synthesis(self, task: Task) -> TaskExecutionResult:
        supporting_output = {
            "status": "best_effort_not_released",
            **availability_map(self._aggregate, task),
        }
        agent_result = await self._invoke_research_agent(
            task,
            supporting_output=supporting_output,
        )
        if agent_result is not None:
            required_actors = {output.output_id for output in self._upstream_agent_outputs(task)}
            consumed_actors = {
                output.output_id
                for output in self._upstream_agent_outputs(task)
                if output.output_id in agent_result.agent_output.input_refs
            }
            missing = required_actors - consumed_actors
            if missing:
                raise ValueError(
                    "research synthesis did not consume every available specialist output: "
                    f"{sorted(missing)}"
                )
            return self._accept_research_agent_output(
                task,
                agent_result,
                supporting_output=supporting_output,
            )
        self._aggregate.artifacts.task_outputs[task.task_id] = supporting_output
        return TaskExecutionResult(result_ref=f"analysis://{task.task_id}")

    async def _invoke_research_agent(
        self,
        task: Task,
        *,
        supporting_output: dict[str, object],
        additional_input_refs: tuple[str, ...] = (),
    ) -> SpecialistResult | None:
        try:
            agent = self._service.agent_registry.get(task.assigned_agent)
        except RegistrationNotFoundError:
            if self._service.agent_registry.registered_ids():
                raise
            return None
        if task.task_type not in agent.supported_task_types:
            raise ValueError(
                f"registered research Agent does not support task type {task.task_type}"
            )
        if task.run_id != self._aggregate.run.run_id:
            raise ValueError("research Agent dispatch attempted cross-Run execution")
        current_task = self._aggregate.runtime.task(task.task_id)
        if current_task.run_id != task.run_id or current_task.assigned_agent != task.assigned_agent:
            raise ValueError("research Agent dispatch does not match authoritative Task identity")

        normalized_evidence = self._normalized_evidence_for_task(task)
        upstream_outputs = self._upstream_agent_outputs(task)
        availability = availability_map(self._aggregate, task)
        recovery_store = self._service.recovery_evidence_store
        recovery_scope = {item["task_id"] for item in availability["output_availability"]}
        recovery_scope.add(task.task_id)
        availability["recovery_evidence"] = [
            {
                key: record.model_dump(mode="json")[key]
                for key in (
                    "record_id",
                    "route",
                    "model",
                    "actual_model",
                    "outcome",
                    "failure_class",
                    "capability_check",
                )
            }
            for record in (await recovery_store.records(task.run_id) if recovery_store else [])
            if record.scope.task_id in recovery_scope
        ]
        input_refs = list(
            dict.fromkeys(
                [
                    self._aggregate.goal.goal_id,
                    self._aggregate.scheme.scheme_id,
                    *(item["evidence_id"] for item in normalized_evidence),
                    *(item.output_id for item in upstream_outputs),
                    *additional_input_refs,
                    *(item["calculation_id"] for item in availability["available_calculations"]),
                    *(
                        ref
                        for item in availability["available_calculations"]
                        for ref in item["input_evidence_ids"]
                    ),
                    *(ref for item in availability["output_availability"] for ref in item["refs"]),
                    *(item["record_id"] for item in availability["recovery_evidence"]),
                ]
            )
        )
        supporting_output = {
            **supporting_output,
            **availability,
            "financial_branch_availability": availability["financial_branches"],
            "availability_rule": (
                "Use only COMPLETED calculations as numeric findings. Do not infer any "
                "numeric result or directional claim for unavailable branches."
                " Never reconstruct failed Agent narratives or absent transcript content. "
                "Every conclusion requires its own accepted evidence/calculation references."
            ),
        }
        context = SpecialistExecutionContext(
            task=task,
            accepted_evidence_ids=[item["evidence_id"] for item in normalized_evidence],
            inputs={
                "research_object_id": self._aggregate.run.research_object_id,
                "goal_id": self._aggregate.goal.goal_id,
                "scheme_id": self._aggregate.scheme.scheme_id,
                "as_of": self._aggregate.run.as_of.isoformat(),
                "research_goal": self._aggregate.goal.goal_text,
                "normalized_evidence": normalized_evidence,
                "deterministic_support": _compact_json_value(
                    _peer_model_support(supporting_output)
                    if task.task_type == "peer_analysis"
                    else supporting_output
                ),
                "upstream_agent_outputs": [
                    {
                        "output_id": output.output_id,
                        "task_id": output.task_id,
                        "actor": output.actor,
                        **output.structured_output.model_dump(mode="json"),
                    }
                    for output in upstream_outputs
                    if output.structured_output is not None
                ],
                "input_refs": input_refs,
            },
        )
        if task.task_type == "risk_follow_up":
            from src.application.risk_follow_up import build_risk_follow_up_context

            context = SpecialistExecutionContext(
                task=task,
                accepted_evidence_ids=current_task.task_input_evidence_ids,
                inputs=build_risk_follow_up_context(self._aggregate, task, normalized_evidence),
            )
        try:
            result = await agent.execute(context)
        except ResearchAgentInvocationError as exc:
            self._append_agent_output(exc.record, task)
            publish_output(
                self._aggregate.runtime.task(task.task_id),
                "agent_output",
                OutputStatus.FAILED,
                refs=[exc.record.output_id],
                reason=exc.record.failure_code,
            )
            # Authorization, unknown preflight and storage errors are NOT localized.
            if exc.record.failure_code in {
                "read_timeout",
                "connect_timeout",
                "provider_unavailable",
                "remote_protocol_error",
                "quota_or_rate_limit",
                "retryable_http_failure",
                "overall_deadline_exceeded",
                "invalid_provider_response",
                "semantic_schema_failure",
                "model_identity_mismatch",
            }:
                raise LocalOutputFailure("Recorded model output failure") from exc
            raise
        record = result.agent_output
        if record is None or record.status != "SUCCESS":
            raise ValueError("research Agent did not return a successful output record")
        self._append_agent_output(record, task)
        if result.decision.run_id != task.run_id or result.decision.task_id != task.task_id:
            raise ValueError("research Agent decision does not match authoritative Task identity")
        return result

    def _accept_research_agent_output(
        self,
        task: Task,
        result: SpecialistResult,
        *,
        supporting_output: dict[str, object],
        additional_output_refs: tuple[str, ...] = (),
    ) -> TaskExecutionResult:
        record = result.agent_output
        if record is None or record.run_id != task.run_id or record.task_id != task.task_id:
            raise ValueError("research Agent output does not close to its authoritative Task")
        self._aggregate.artifacts.task_outputs[task.task_id] = {
            **supporting_output,
            **result.output,
        }
        publish_output(
            self._aggregate.runtime.task(task.task_id),
            "agent_output",
            OutputStatus.COMPLETED,
            refs=[record.output_id],
        )
        return TaskExecutionResult(
            result_ref=record.artifact_ref,
            output_refs=tuple(dict.fromkeys([*additional_output_refs, record.output_id])),
        )

    def _append_agent_output(
        self,
        record: ResearchAgentOutputRecord,
        task: Task,
    ) -> None:
        if (
            record.run_id != self._aggregate.run.run_id
            or record.run_id != task.run_id
            or record.task_id != task.task_id
            or record.actor != task.assigned_agent
        ):
            raise ValueError("research Agent output attempted cross-Run or cross-Task persistence")
        if any(
            candidate.output_id == record.output_id
            for candidate in self._aggregate.artifacts.agent_outputs
        ):
            raise ValueError("research Agent output identity must be unique within a Run")
        self._aggregate.artifacts.agent_outputs.append(record)

    def _upstream_agent_outputs(self, task: Task) -> list[ResearchAgentOutputRecord]:
        upstream_task_ids = self._upstream_task_ids(task)
        outputs = [
            output
            for output in self._aggregate.artifacts.agent_outputs
            if output.status == "SUCCESS" and output.task_id in upstream_task_ids
        ]
        foreign = [output.output_id for output in outputs if output.run_id != task.run_id]
        if foreign:
            raise ValueError(f"upstream research Agent outputs crossed Run identity: {foreign}")
        return sorted(outputs, key=lambda output: (output.created_at, output.output_id))

    def _upstream_task_ids(self, task: Task) -> set[str]:
        dependencies_by_id = {
            candidate.task_id: tuple(candidate.dependencies)
            for candidate in self._aggregate.runtime.actual_graph.tasks
        }
        result: set[str] = set()
        pending = list(task.dependencies)
        while pending:
            task_id = pending.pop()
            if task_id in result:
                continue
            result.add(task_id)
            pending.extend(dependencies_by_id.get(task_id, ()))
        return result

    def _normalized_evidence_for_task(self, task: Task) -> list[dict[str, object]]:
        permitted_ids = set(self._aggregate.runtime.task(task.task_id).task_input_evidence_ids)
        permitted_ids.update(self._aggregate.runtime.task(task.task_id).task_output_evidence_ids)
        candidates = [
            record
            for record in self._aggregate.artifacts.evidence
            if record.evidence_id in permitted_ids
        ]
        if any(
            record.run_id != task.run_id
            or record.object_id != self._aggregate.run.research_object_id
            for record in candidates
        ):
            raise ValueError("research Agent evidence crossed Run or Object identity")
        selected = _select_agent_evidence(task.task_type, candidates)
        return [
            {
                "evidence_id": record.evidence_id,
                "provider": record.provider,
                "category": record.evidence_category.value,
                "field": record.normalized_field,
                "value": _compact_json_value(record.normalized_value),
                "unit": record.unit,
                "currency": record.currency,
                "period": record.period,
                "as_of": record.as_of.isoformat(),
                "actuality": record.actuality.value,
            }
            for record in selected
        ]

    async def _execute_generic(self, task: Task) -> TaskExecutionResult:
        input_ids = list(self._aggregate.runtime.task(task.task_id).task_input_evidence_ids)
        self._aggregate.artifacts.task_outputs[task.task_id] = {
            "status": "completed",
            "accepted_evidence_ids": input_ids,
        }
        return TaskExecutionResult(result_ref=f"analysis://{task.task_id}")

    def _handler_for(self, task: Task):
        by_skill = {
            "evidence_collection_v1": self._execute_evidence_collection,
            "fundamental_analysis_v1": self._execute_fundamental_analysis,
            "peer_analysis_v1": self._execute_peer_analysis,
            "risk_analysis_v1": self._execute_risk_analysis,
        }
        if task.origin is TaskOrigin.PLAN and task.skill_id in by_skill:
            return by_skill[task.skill_id]
        return getattr(self, f"_execute_{task.task_type}", self._execute_generic)

    def _should_acquire_evidence(self, task: Task) -> bool:
        from src.agentic.runtime_bindings import NATIVE_PLANNING_TASK_TYPES

        if task.task_type in NATIVE_PLANNING_TASK_TYPES:
            return True
        return not self._has_specialized_collection_tasks and task.task_type in {
            "peer_analysis",
            "research_news_analysis",
        }


def _find(records: list, *, field: str, period: str):
    for record in records:
        if record.normalized_field == field and record.period == period:
            return record
    raise LookupError(f"accepted evidence missing: {field}/{period}")


def _select_financial_inputs(records: list):
    revenues = sorted(
        (
            record
            for record in records
            if record.normalized_field == "revenue" and record.period.startswith("FY")
        ),
        key=lambda record: (record.as_of, record.period),
    )
    if len(revenues) < 2:
        raise LookupError("accepted evidence requires two annual revenue periods")
    prior, current = revenues[-2:]
    ebitda = _find(records, field="ebitda", period=current.period)
    mismatch = next(
        (
            record
            for record in records
            if record.normalized_field == "revenue"
            and record.period != current.period
            and record.period.startswith("Q")
        ),
        prior,
    )
    return prior, current, mismatch, ebitda


def decimal_as_float(value: object) -> float:
    return float(Decimal(str(value)))


def _evidence_value(records: list, field: str, default: object = None) -> object:
    return next(
        (record.normalized_value for record in records if record.normalized_field == field),
        default,
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


_COMMON_AGENT_FIELDS = {
    "symbol",
    "company_name",
    "industry",
    "sector",
    "revenue",
    "ebitda",
    "operating_cash_flow",
    "capital_expenditure",
    "provider_reference_free_cash_flow",
    "total_assets",
    "total_debt",
    "total_stockholders_equity",
    "provider_reference_market_cap",
    "price",
}
_AGENT_FIELDS_BY_TASK = {
    "fundamental_analysis": _COMMON_AGENT_FIELDS - {"price"},
    "peer_analysis": {
        "symbol",
        "company_name",
        "industry",
        "sector",
        "provider_reference_market_cap",
        "price",
    },
    "research_news_analysis": set(),
    "valuation_analysis": _COMMON_AGENT_FIELDS
    | {"buy", "hold", "sell", "strong_buy", "strong_sell"},
    "risk_analysis": _COMMON_AGENT_FIELDS | {"buy", "hold", "sell", "strong_buy", "strong_sell"},
    "risk_follow_up": _COMMON_AGENT_FIELDS,
    "report_synthesis": _COMMON_AGENT_FIELDS | {"buy", "hold", "sell", "strong_buy", "strong_sell"},
}
_FIELD_PRIORITY = {
    field: index
    for index, field in enumerate(
        (
            "symbol",
            "company_name",
            "industry",
            "sector",
            "revenue",
            "ebitda",
            "operating_cash_flow",
            "capital_expenditure",
            "provider_reference_free_cash_flow",
            "total_assets",
            "total_debt",
            "total_stockholders_equity",
            "provider_reference_market_cap",
            "price",
            "strong_buy",
            "buy",
            "hold",
            "sell",
            "strong_sell",
        )
    )
}


def _select_agent_evidence(task_type: str, records: list) -> list:
    """Return a bounded, task-relevant normalized evidence slice for an Agent."""

    allowed = _AGENT_FIELDS_BY_TASK.get(task_type, _COMMON_AGENT_FIELDS)
    if task_type == "research_news_analysis":
        relevant = [
            record
            for record in records
            if record.evidence_category in {EvidenceCategory.NEWS, EvidenceCategory.TRANSCRIPT}
        ]
    else:
        relevant = [
            record
            for record in records
            if record.normalized_field in allowed
            or (task_type == "peer_analysis" and record.normalized_field.startswith("peer_symbol_"))
        ]
    relevant.sort(
        key=lambda record: (
            _FIELD_PRIORITY.get(
                record.normalized_field,
                100 if record.normalized_field.startswith("peer_symbol_") else 200,
            ),
            -record.as_of.toordinal(),
            record.period,
            record.evidence_id,
        )
    )
    selected: list = []
    counts: dict[str, int] = {}
    for record in relevant:
        field = record.normalized_field
        maximum = 9 if field.startswith("peer_symbol_") else 5
        if counts.get(field, 0) >= maximum:
            continue
        counts[field] = counts.get(field, 0) + 1
        selected.append(record)
        if len(selected) == 40:
            break
    return selected


def _peer_model_support(support: dict[str, object]) -> dict[str, object]:
    """Exclude assembly-clock metadata only from the Peer model projection.

    PeerCandidate/PeerSelectionDecision created_at records object construction,
    not an evidence observation date. Preserve original domain/task artifacts and
    all business fields; never strip timestamps from evidence or other inputs.
    """
    return {
        key: [
            {field: value for field, value in item.items() if field != "created_at"}
            for item in rows
        ]
        if key in {"candidates", "selection_decisions", "selected_comparables"}
        and isinstance(rows, list)
        and all(isinstance(item, dict) for item in rows)
        else rows
        for key, rows in support.items()
    }


def _compact_json_value(value: Any, *, depth: int = 0) -> Any:
    """Normalize bounded provider inputs without carrying raw artifacts or payloads."""

    if depth > 4:
        return "[bounded]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, str):
        return value if len(value) <= 1000 else f"{value[:997]}..."
    if isinstance(value, dict):
        return {
            str(key): _compact_json_value(item, depth=depth + 1)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))[:30]
        }
    if isinstance(value, (list, tuple)):
        return [_compact_json_value(item, depth=depth + 1) for item in value[:30]]
    return _compact_json_value(str(value), depth=depth + 1)
