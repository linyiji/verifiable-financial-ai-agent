"""Run the credentialed NVDA chain with PostgreSQL and one Langfuse root trace."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

from scripts.run_phase2_1_acceptance import _evaluate
from src.adapters.fmp import FinancialProviderMode, FMPProvider, select_financial_provider
from src.adapters.llm import TeamoRouterClient
from src.agentic.llm_integration import (
    TeamoRouterResearchLeadPlanner,
    TeamoRouterSchemeGenerator,
)
from src.application.evidence_collection import LiveFMPEvidenceCollector
from src.application.service import ResearchApplicationService
from src.infrastructure.config import Settings
from src.infrastructure.database.artifacts import TaskDependencyGraphKind
from src.infrastructure.database.composition import create_postgresql_persistence
from src.infrastructure.database.migrations import upgrade_postgresql_database
from src.observability import (
    InMemoryTraceReferenceRepository,
    InstrumentedLLMProvider,
    ObservationStage,
    RuntimeInstrumentation,
    create_langfuse_trace_adapter,
)
from src.runtime.sse import runtime_event_stream


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


async def run(output: Path) -> dict[str, Any]:
    await asyncio.to_thread(output.mkdir, parents=True, exist_ok=True)
    settings = Settings()
    if not settings.fmp.enabled or not settings.llm.enabled or not settings.langfuse.enabled:
        raise RuntimeError("FMP, TeamoRouter, and Langfuse must be configured")

    await asyncio.to_thread(upgrade_postgresql_database, settings.database)
    persistence = create_postgresql_persistence(settings.database)
    run_id = f"RUN-{uuid4()}"
    references = InMemoryTraceReferenceRepository()
    trace_build = create_langfuse_trace_adapter(
        settings.langfuse,
        additional_sensitive_values={
            "FMP_API_KEY": settings.fmp.api_key.get_secret_value(),
            "TEAMOROUTER_API_KEY": settings.llm.api_key.get_secret_value(),
        },
    )
    if not trace_build.enabled:
        raise RuntimeError(f"Langfuse adapter is not enabled: {trace_build.classification.value}")
    instrumentation = RuntimeInstrumentation(
        trace_build.adapter,
        reference_repository=references,
    )

    try:
        selection = select_financial_provider(
            mode=FinancialProviderMode.FMP,
            fmp_settings=settings.fmp,
            fixture_path=Path("tests/fixtures/nvda_financials.json"),
        )
        if not isinstance(selection.provider, FMPProvider):
            raise RuntimeError("live FMP provider was not selected")
        collector = LiveFMPEvidenceCollector.with_local_artifacts(
            provider=selection.provider,
            repository=persistence.evidence_repository,
            artifact_root=output / "raw",
        )

        async with instrumentation.research_run(
            run_id=run_id,
            attributes={"object_id": "OBJ-NVDA", "runtime_status": "STARTING"},
        ) as trace:
            llm_client = TeamoRouterClient(settings.llm, timeout_seconds=60.0)
            scheme_provider = InstrumentedLLMProvider(
                llm_client,
                trace=trace,
                stage=ObservationStage.SCHEME_GENERATION,
            )
            planner_provider = InstrumentedLLMProvider(
                llm_client,
                trace=trace,
                stage=ObservationStage.PLANNER_GENERATION,
            )
            scheme_generator = TeamoRouterSchemeGenerator(
                scheme_provider,
                max_validation_attempts=2,
            )
            planner = TeamoRouterResearchLeadPlanner(
                planner_provider,
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
            research_object = await service.create_object(
                symbol="NVDA",
                company_name="NVIDIA Corporation",
                exchange="NASDAQ",
                idempotency_key=f"real-infra-object-{run_id}",
            )
            draft = await service.prepare_run(
                research_object_id=research_object.object_id,
                research_goal=(
                    "Assess NVDA fundamentals, evidence quality, material risks, and limitations"
                ),
                as_of=date(2026, 9, 4),
                preferences={"depth": "standard", "provider": "live_fmp"},
            )
            aggregate = await service.confirm_run(
                draft_id=draft.draft_id,
                confirm_scheme=True,
                idempotency_key=f"real-infra-confirm-{run_id}",
            )
            _write_json(
                output / "scheme_snapshot.json",
                aggregate.scheme.model_dump(mode="json"),
            )
            _write_json(
                output / "planned_graph.json",
                aggregate.runtime.planned_graph.model_dump(mode="json"),
            )
            aggregate = await service.execute_run(run_id)
            trace_id = trace.trace_id

        await instrumentation.flush()
        events = list(await persistence.event_store.replay(run_id))
        checkpoint = await persistence.checkpoint_store.load_latest(run_id)
        if checkpoint is None:
            raise RuntimeError("PostgreSQL checkpoint was not persisted")

        artifacts = aggregate.artifacts
        if artifacts.canonical_record is None or artifacts.released_result is None:
            raise RuntimeError("canonical and released results must exist")
        if not artifacts.canonical_record.trace_refs:
            raise RuntimeError("canonical record does not contain trace reference IDs")

        _write_json(
            output / "accepted_evidence.json",
            [item.model_dump(mode="json") for item in artifacts.evidence],
        )
        _write_json(
            output / "calculation_records.json",
            [item.model_dump(mode="json") for item in artifacts.calculations],
        )
        _write_json(
            output / "runtime_events.json",
            [item.model_dump(mode="json") for item in events],
        )
        _write_json(output / "task_outputs.json", artifacts.task_outputs)
        _write_json(
            output / "canonical_execution_record.json",
            artifacts.canonical_record.model_dump(mode="json"),
        )
        _write_json(
            output / "released_research_result.json",
            artifacts.released_result.model_dump(mode="json"),
        )

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
        scheme_audit = scheme_generator.last_audit
        planner_audit = planner.last_audit
        all_references = await references.list_by_run(run_id)
        summary: dict[str, Any] = {
            "run_id": run_id,
            "run_status": aggregate.run.status.value,
            "symbol": "NVDA",
            "frontend": "DEFERRED",
            "postgresql": {
                "persisted": True,
                "checkpoint_id": checkpoint.checkpoint_id,
                "checkpoint_graph_version": checkpoint.actual_graph_version,
            },
            "fmp": {
                "provider": "fmp",
                "endpoint_status": endpoint_status,
                "accepted_evidence_count": len(artifacts.evidence),
            },
            "llm": {
                "provider": settings.llm.provider,
                "scheme": scheme_audit.model_dump(mode="json") if scheme_audit else None,
                "planner": planner_audit.model_dump(mode="json") if planner_audit else None,
            },
            "langfuse": {
                "classification": trace_build.classification.value,
                "region": settings.langfuse.base_url,
                "trace_id": trace_id,
                "runtime_status": instrumentation.status.value,
                "reference_count": len(all_references),
            },
            "planned_task_count": len(aggregate.runtime.planned_graph.tasks),
            "actual_task_count": len(aggregate.runtime.actual_graph.tasks),
            "actual_graph_version": aggregate.runtime.actual_graph.version,
            "parallel_task_peak": artifacts.parallel_task_peak,
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
                    artifacts.task_outputs.get(task.task_id)
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
                {
                    "calculation_id": item.calculation_id,
                    "capability_id": item.capability_id,
                    "code_hash": item.code_hash,
                    "source_ref": item.source_ref,
                    "input_evidence_ids": item.input_evidence_ids,
                    "review_record_id": item.review_record_id,
                    "canonical_record_id": item.canonical_record_id,
                }
                for item in artifacts.calculations
            ],
            "review_status": artifacts.review.status.value if artifacts.review else None,
            "canonical_record_id": artifacts.canonical_record.record_id,
            "released_result_id": artifacts.released_result.result_id,
            "calculation_ids": [item.calculation_id for item in artifacts.calculations],
            "runtime_event_count": len(events),
            "runtime_event_sequences_contiguous": [item.sequence for item in events]
            == list(range(1, len(events) + 1)),
            "trace_stages": sorted({item.stage for item in all_references}),
            "secret_values_included": False,
        }
        _write_json(output / "acceptance_summary.json", summary)
        semantic_acceptance = _evaluate(output, summary)
        semantic_failed = [
            gate for gate, result in semantic_acceptance.items() if result["status"] != "PASS"
        ]
        _write_json(
            output / "phase2_1_acceptance.json",
            {"acceptance": semantic_acceptance, "failed": semantic_failed},
        )
        if semantic_failed:
            raise RuntimeError(f"Phase-2.1 semantic gates failed: {semantic_failed}")

        await persistence.close()
        persistence = create_postgresql_persistence(settings.database)
        restored = await persistence.application_repository.get_run(run_id)
        restored_canonical = await persistence.run_record_repository.get_canonical(run_id)
        restored_released = await persistence.run_record_repository.get_released(run_id)
        restored_checkpoint = await persistence.checkpoint_store.load_latest(run_id)
        restored_events = list(await persistence.event_store.replay(run_id))
        planned_dependencies = await persistence.run_record_repository.list_task_dependencies(
            run_id,
            graph_kind=TaskDependencyGraphKind.PLANNED,
        )
        actual_dependencies = await persistence.run_record_repository.list_task_dependencies(
            run_id,
            graph_kind=TaskDependencyGraphKind.ACTUAL,
        )
        if (
            restored is None
            or restored_canonical != artifacts.canonical_record
            or restored_released != artifacts.released_result
            or restored_checkpoint != checkpoint
            or restored_events != events
        ):
            raise RuntimeError("PostgreSQL restart/restore round-trip failed")

        stream = runtime_event_stream(
            store=persistence.event_store,
            run_id=run_id,
            last_event_id="0",
            heartbeat_seconds=0.1,
        )
        first_sse = await anext(stream)
        await stream.aclose()
        restore_summary = {
            "aggregate_restored": True,
            "canonical_roundtrip": True,
            "released_roundtrip": True,
            "checkpoint_roundtrip": True,
            "event_replay_roundtrip": True,
            "sse_replay_first_sequence": 1 if first_sse.startswith("id: 1\n") else None,
            "planned_dependency_count": len(planned_dependencies),
            "actual_dependency_count": len(actual_dependencies),
            "event_type_counts": dict(Counter(event.type.value for event in restored_events)),
        }
        _write_json(output / "postgresql_restore_summary.json", restore_summary)
        return {**summary, "restore": restore_summary}
    finally:
        await persistence.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/infrastructure/acceptance/latest"),
    )
    args = parser.parse_args()
    result = asyncio.run(run(args.output))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
