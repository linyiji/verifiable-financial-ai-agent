from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from src.application.evidence_collection import (
    EndpointCollectionStatus,
    EvidenceAcquisitionScope,
    EvidenceTaskAcquisitionResult,
)
from src.domain.enums import EvidenceAcquisitionStatus, EvidenceCategory, EvidenceStatus
from src.domain.evidence import EvidenceRecord
from src.domain.runtime_event import RuntimeEventType
from src.domain.task import Task


class ScopedEvidenceCollector(Protocol):
    async def collect_scope(
        self,
        *,
        task_id: str,
        scope: EvidenceAcquisitionScope,
        symbol: str,
        run_id: str,
        object_id: str,
        as_of: date,
    ) -> EvidenceTaskAcquisitionResult: ...


@dataclass(frozen=True, slots=True)
class EvidenceEventIntent:
    """An unsequenced event request for the coordinator-owned runtime event stream."""

    run_id: str
    task_id: str
    type: RuntimeEventType
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class EvidenceLineage:
    evidence_id: str
    producer_task_id: str | None
    source_endpoint: str | None
    evidence_purpose: str | None
    evidence_category: EvidenceCategory
    referenced_by_task_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TaskEvidenceRoutingResult:
    task_id: str
    acquisition_status: EvidenceAcquisitionStatus | None
    input_evidence_ids: tuple[str, ...]
    output_evidence_ids: tuple[str, ...]
    event_intents: tuple[EvidenceEventIntent, ...]
    endpoint_statuses: tuple[EndpointCollectionStatus, ...] = ()

    def apply_to(self, task: Task) -> Task:
        """Apply references to a task without coupling collection to execution.py."""

        if task.task_id != self.task_id:
            raise ValueError("routing result belongs to a different task")
        task.task_input_evidence_ids = list(self.input_evidence_ids)
        task.task_output_evidence_ids = list(self.output_evidence_ids)
        task.evidence_acquisition_status = self.acquisition_status
        task.evidence_source_coverage = {
            item.endpoint.value: {
                "status": _source_coverage_status(item),
                "http_status": item.http_status,
                "error_code": item.error_code,
                "accepted_count": item.accepted_count,
            }
            for item in self.endpoint_statuses
            if item.endpoint.value in {"news", "transcript"}
        }
        return task


class RunEvidenceStore:
    """Run-global evidence identity store with task-local produced/reference indexes."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._records: dict[str, EvidenceRecord] = {}
        self._task_inputs: dict[str, list[str]] = {}
        self._task_outputs: dict[str, list[str]] = {}
        self._announced_ids: set[str] = set()

    def register_acquisition(
        self, acquisition: EvidenceTaskAcquisitionResult
    ) -> TaskEvidenceRoutingResult:
        if not acquisition.task_id.startswith(f"{self.run_id}:"):
            raise ValueError("acquisition task does not belong to this run")

        accepted = acquisition.ingestion.accepted.records
        for record in acquisition.ingestion.created_records:
            if record.producer_task_id != acquisition.task_id:
                raise ValueError("new evidence producer_task_id must match the acquisition task")
        for record in acquisition.ingestion.records:
            self._register_record(record)

        inputs: list[str] = []
        outputs: list[str] = []
        intents: list[EvidenceEventIntent] = []
        created_ids = {record.evidence_id for record in acquisition.ingestion.created_records}
        for record in accepted:
            if record.producer_task_id == acquisition.task_id:
                _append_unique(outputs, record.evidence_id)
            else:
                _append_unique(inputs, record.evidence_id)
            if record.evidence_id not in created_ids or record.evidence_id in self._announced_ids:
                continue
            self._announced_ids.add(record.evidence_id)
            intents.append(
                EvidenceEventIntent(
                    run_id=self.run_id,
                    task_id=acquisition.task_id,
                    type=RuntimeEventType.EVIDENCE_ACCEPTED,
                    payload={
                        "evidence_id": record.evidence_id,
                        "field": record.normalized_field,
                        "producer_task_id": record.producer_task_id,
                        "source_endpoint": record.source_endpoint,
                        "evidence_purpose": record.evidence_purpose,
                        "evidence_category": record.evidence_category.value,
                    },
                )
            )

        self._task_inputs[acquisition.task_id] = inputs
        self._task_outputs[acquisition.task_id] = outputs
        return TaskEvidenceRoutingResult(
            task_id=acquisition.task_id,
            acquisition_status=acquisition.status,
            input_evidence_ids=tuple(inputs),
            output_evidence_ids=tuple(outputs),
            event_intents=tuple(intents),
            endpoint_statuses=acquisition.endpoint_statuses,
        )

    def link_inputs(
        self, task_id: str, evidence_ids: tuple[str, ...] | list[str]
    ) -> tuple[str, ...]:
        self._validate_task_id(task_id)
        target = self._task_inputs.setdefault(task_id, [])
        for evidence_id in evidence_ids:
            if evidence_id not in self._records:
                raise KeyError(f"unknown evidence reference: {evidence_id}")
            _append_unique(target, evidence_id)
        return tuple(target)

    def select_ids(
        self,
        *,
        categories: frozenset[EvidenceCategory] | None = None,
        purposes: frozenset[str] | None = None,
    ) -> tuple[str, ...]:
        return tuple(
            evidence_id
            for evidence_id, record in self._records.items()
            if record.status is EvidenceStatus.ACCEPTED
            and (categories is None or record.evidence_category in categories)
            and (purposes is None or record.evidence_purpose in purposes)
        )

    def lineage(self, evidence_id: str) -> EvidenceLineage:
        record = self._records.get(evidence_id)
        if record is None:
            raise KeyError(f"unknown evidence: {evidence_id}")
        consumers = tuple(
            task_id
            for task_id, references in self._task_inputs.items()
            if evidence_id in references
        )
        return EvidenceLineage(
            evidence_id=evidence_id,
            producer_task_id=record.producer_task_id,
            source_endpoint=record.source_endpoint,
            evidence_purpose=record.evidence_purpose,
            evidence_category=record.evidence_category,
            referenced_by_task_ids=consumers,
        )

    @property
    def records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(self._records.values())

    def task_inputs(self, task_id: str) -> tuple[str, ...]:
        return tuple(self._task_inputs.get(task_id, ()))

    def task_outputs(self, task_id: str) -> tuple[str, ...]:
        return tuple(self._task_outputs.get(task_id, ()))

    def _register_record(self, record: EvidenceRecord) -> None:
        if record.run_id != self.run_id:
            raise ValueError("evidence record does not belong to this run")
        existing = self._records.get(record.evidence_id)
        if existing is not None and existing != record:
            raise ValueError(f"run-global evidence collision: {record.evidence_id}")
        self._records.setdefault(record.evidence_id, record)

    def _validate_task_id(self, task_id: str) -> None:
        if not task_id.startswith(f"{self.run_id}:"):
            raise ValueError("task does not belong to this run")


class EvidenceTaskRouter:
    """Map planned tasks to evidence acquisition or run-global evidence references."""

    _ACQUISITION_SCOPES = {
        "evidence_collection": EvidenceAcquisitionScope.COMPANY,
        "peer_analysis": EvidenceAcquisitionScope.PEER,
        "research_news_analysis": EvidenceAcquisitionScope.RESEARCH_NEWS,
    }
    _INPUT_CATEGORIES = {
        "fundamental_analysis": frozenset(
            {
                EvidenceCategory.COMPANY_PROFILE,
                EvidenceCategory.FINANCIAL_STATEMENT,
                EvidenceCategory.MARKET,
                EvidenceCategory.ANALYST,
            }
        ),
        "peer_analysis": frozenset(
            {
                EvidenceCategory.COMPANY_PROFILE,
                EvidenceCategory.MARKET,
                EvidenceCategory.PEER,
            }
        ),
        "research_news_analysis": frozenset(
            {
                EvidenceCategory.COMPANY_PROFILE,
                EvidenceCategory.MARKET,
                EvidenceCategory.ANALYST,
                EvidenceCategory.NEWS,
                EvidenceCategory.TRANSCRIPT,
            }
        ),
        "valuation_analysis": frozenset(
            {
                EvidenceCategory.FINANCIAL_STATEMENT,
                EvidenceCategory.MARKET,
                EvidenceCategory.PEER,
                EvidenceCategory.ANALYST,
            }
        ),
        "risk_analysis": frozenset(EvidenceCategory),
        "report_synthesis": frozenset(EvidenceCategory),
    }

    def __init__(self, *, collector: ScopedEvidenceCollector, store: RunEvidenceStore) -> None:
        self._collector = collector
        self._store = store

    async def route(
        self,
        task: Task,
        *,
        symbol: str,
        object_id: str,
        as_of: date,
        acquire: bool = True,
    ) -> TaskEvidenceRoutingResult:
        if task.run_id != self._store.run_id:
            raise ValueError("task and evidence store belong to different runs")

        acquisition_result: TaskEvidenceRoutingResult | None = None
        scope = self._acquisition_scope(task) if acquire else None
        if scope is not None:
            acquisition = await self._collector.collect_scope(
                task_id=task.task_id,
                scope=scope,
                symbol=symbol,
                run_id=task.run_id,
                object_id=object_id,
                as_of=as_of,
            )
            acquisition_result = self._store.register_acquisition(acquisition)

        categories = self._INPUT_CATEGORIES.get(task.task_type)
        selected = self._store.select_ids(categories=categories) if categories else ()
        if acquisition_result is not None:
            produced = set(acquisition_result.output_evidence_ids)
            selected = tuple(evidence_id for evidence_id in selected if evidence_id not in produced)
        inputs = self._store.link_inputs(task.task_id, list(selected))
        if acquisition_result is None:
            return TaskEvidenceRoutingResult(
                task_id=task.task_id,
                acquisition_status=None,
                input_evidence_ids=inputs,
                output_evidence_ids=(),
                event_intents=(),
            )
        return TaskEvidenceRoutingResult(
            task_id=task.task_id,
            acquisition_status=acquisition_result.acquisition_status,
            input_evidence_ids=inputs,
            output_evidence_ids=acquisition_result.output_evidence_ids,
            event_intents=acquisition_result.event_intents,
            endpoint_statuses=acquisition_result.endpoint_statuses,
        )

    def _acquisition_scope(self, task: Task) -> EvidenceAcquisitionScope | None:
        """Resolve specialized collection tasks without changing the shared Task contract."""

        if task.task_type != "evidence_collection":
            return self._ACQUISITION_SCOPES.get(task.task_type)
        semantic_hint = f"{task.task_id} {task.goal}".lower().replace("_", "-")
        if "peer" in semantic_hint or "comparable" in semantic_hint:
            return EvidenceAcquisitionScope.PEER
        if "news" in semantic_hint or "transcript" in semantic_hint:
            return EvidenceAcquisitionScope.RESEARCH_NEWS
        return EvidenceAcquisitionScope.COMPANY


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _source_coverage_status(item: EndpointCollectionStatus) -> str:
    if item.accepted_count > 0:
        return "AVAILABLE"
    if item.status.value == "ENTITLEMENT_DENIED":
        return "BLOCKED"
    if item.status.value in {"AVAILABLE", "NO_DATA"}:
        return "EMPTY"
    return "ERROR"
