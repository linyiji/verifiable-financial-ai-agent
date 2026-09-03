from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from src.agentic.decisions import ResearchLeadReplanDecider
from src.agentic.specialist import SpecialistResult
from src.domain.capability import CapabilityContext
from src.domain.correction import CorrectionRecord
from src.domain.decision import StructuredAgentDecision
from src.domain.enums import CorrectionStatus, ReplanDecision, TaskOrigin
from src.domain.runtime_event import RuntimeEventType
from src.domain.task import ReplanRequest, Task
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
        self._has_specialized_collection_tasks = sum(
            task.task_type == "evidence_collection"
            for task in aggregate.runtime.actual_graph.tasks
        ) > 1
        self._active = 0
        self.parallel_peak = 0

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
            routing = await self._service.route_task_evidence(
                self._aggregate,
                task,
                acquire=self._should_acquire_evidence(task),
            )
            for intent in routing.event_intents:
                await self._service.event_store.emit(
                    run_id=intent.run_id,
                    task_id=intent.task_id,
                    event_type=intent.type,
                    payload=intent.payload,
                )
            handler = self._handler_for(task)
            return await handler(task)
        finally:
            self._active -= 1

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
        growth = await self._service.tool_runtime.execute(
            "revenue_growth",
            {"prior": prior, "current": current, "calculation_id": f"CALC-{task.run_id}-GROWTH"},
            context,
        )
        await self._service.event_store.emit(
            run_id=task.run_id,
            task_id=task.task_id,
            event_type=RuntimeEventType.CALCULATION_COMPLETED,
            payload={"calculation_id": growth.calculation_id},
        )

        # The fixture intentionally presents a quarterly revenue candidate first.
        # The real capability rejects its period mismatch and the same task corrects it.
        try:
            await self._service.tool_runtime.execute(
                "ebitda_margin",
                {
                    "ebitda": ebitda,
                    "revenue": mismatch,
                    "calculation_id": f"CALC-{task.run_id}-MARGIN-BAD",
                },
                context,
            )
        except ValueError as exc:
            await self._service.event_store.emit(
                run_id=task.run_id,
                task_id=task.task_id,
                event_type=RuntimeEventType.TASK_SELF_CORRECTING,
                payload={"problem_code": "PERIOD_MISMATCH", "error": type(exc).__name__},
            )
            correction = CorrectionRecord(
                correction_id=f"CORR-{task.run_id}-PERIOD",
                run_id=task.run_id,
                task_id=task.task_id,
                problem_code="PERIOD_MISMATCH",
                detected_by="ebitda_margin",
                attempt=1,
                action="SELECT_PERIOD_ALIGNED_REVENUE",
                input_refs=[ebitda.evidence_id, mismatch.evidence_id],
                output_refs=[current.evidence_id],
                status=CorrectionStatus.RESOLVED,
                resolved_at=datetime.now(UTC),
            )
            self._aggregate.artifacts.corrections.append(correction)
            await self._service.event_store.emit(
                run_id=task.run_id,
                task_id=task.task_id,
                event_type=RuntimeEventType.TASK_CORRECTION_RESOLVED,
                payload={"correction_id": correction.correction_id},
            )

        margin = await self._service.tool_runtime.execute(
            "ebitda_margin",
            {
                "ebitda": ebitda,
                "revenue": current,
                "calculation_id": f"CALC-{task.run_id}-MARGIN",
            },
            context,
        )
        self._aggregate.artifacts.calculations.extend([growth, margin])
        await self._service.event_store.emit(
            run_id=task.run_id,
            task_id=task.task_id,
            event_type=RuntimeEventType.CALCULATION_COMPLETED,
            payload={"calculation_id": margin.calculation_id},
        )
        self._aggregate.artifacts.task_outputs[task.task_id] = {
            "revenue_growth": str(growth.output_value),
            "ebitda_margin": str(margin.output_value),
        }
        return TaskExecutionResult(
            result_ref=f"analysis://{task.task_id}",
            output_refs=(growth.calculation_id, margin.calculation_id),
        )

    async def _execute_risk_analysis(self, task: Task) -> TaskExecutionResult:
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
        await self._service.event_store.emit(
            run_id=task.run_id,
            task_id=task.task_id,
            event_type=RuntimeEventType.REPLAN_REQUESTED,
            payload={"replan_id": pending.replan_id, "decision": pending.decision.value},
        )
        decision = ResearchLeadReplanDecider().decide(
            pending,
            outcome=ReplanDecision.APPROVED,
            decision_id=f"DEC-{task.run_id}-REPLAN-APPROVED",
            reason_code="LEAD_APPROVED_FOCUSED_FOLLOW_UP",
            summary="Research Lead approved the bounded child task.",
        )
        await self._service.event_store.emit(
            run_id=task.run_id,
            task_id=task.task_id,
            event_type=RuntimeEventType.REPLAN_APPROVED,
            payload={"replan_id": pending.replan_id, "decided_by": decision.request.decided_by},
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
        await GraphMutationService(self._service.event_store).insert_node_between(
            state=self._aggregate.runtime,
            request=decision.request,
            task=child,
            predecessor_task_id=task.task_id,
            successor_task_id=synthesis.task_id,
            actor=GraphMutationActor("research_lead", GraphMutationRole.RESEARCH_LEAD),
        )
        self._aggregate.artifacts.replans.append(
            decision.request.model_copy(update={"created_task_ids": [child.task_id]})
        )
        self._aggregate.artifacts.task_outputs[task.task_id] = specialist_result.output
        return TaskExecutionResult(result_ref=f"analysis://{task.task_id}")

    async def _execute_risk_follow_up(self, task: Task) -> TaskExecutionResult:
        self._aggregate.artifacts.task_outputs[task.task_id] = {
            "finding": "No additional quantified risk can be supported by the offline fixture.",
            "limitation": True,
        }
        return TaskExecutionResult(result_ref=f"analysis://{task.task_id}")

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
            "risk_analysis_v1": self._execute_risk_analysis,
        }
        if task.origin is TaskOrigin.PLAN and task.skill_id in by_skill:
            return by_skill[task.skill_id]
        return getattr(self, f"_execute_{task.task_type}", self._execute_generic)

    def _should_acquire_evidence(self, task: Task) -> bool:
        if task.task_type == "evidence_collection":
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
