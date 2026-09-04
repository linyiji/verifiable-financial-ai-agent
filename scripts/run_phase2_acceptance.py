"""Run the credentialed Phase-2 NVDA backend chain and save sanitized evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

from src.adapters.fmp import FinancialProviderMode, FMPProvider, select_financial_provider
from src.adapters.llm import TeamoRouterClient
from src.agentic.llm_integration import (
    TeamoRouterResearchLeadPlanner,
    TeamoRouterSchemeGenerator,
)
from src.application.evidence_collection import LiveFMPEvidenceCollector
from src.application.service import ResearchApplicationService
from src.data.repository import InMemoryEvidenceRepository
from src.infrastructure.config import Settings
from src.observability import create_langfuse_trace_adapter


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


async def run(output: Path) -> dict[str, Any]:
    await asyncio.to_thread(output.mkdir, parents=True, exist_ok=True)
    settings = Settings()
    if not settings.fmp.enabled or not settings.llm.enabled:
        raise RuntimeError("Phase-2 acceptance requires configured FMP and TeamoRouter credentials")

    selection = select_financial_provider(
        mode=FinancialProviderMode.FMP,
        fmp_settings=settings.fmp,
        fixture_path=Path("tests/fixtures/nvda_financials.json"),
    )
    if not isinstance(selection.provider, FMPProvider):
        raise RuntimeError("Phase-2 acceptance did not select the live FMP provider")

    evidence_repository = InMemoryEvidenceRepository()
    collector = LiveFMPEvidenceCollector.with_local_artifacts(
        provider=selection.provider,
        repository=evidence_repository,
        artifact_root=output / "raw",
    )
    llm_client = TeamoRouterClient(settings.llm, timeout_seconds=60.0)
    scheme_generator = TeamoRouterSchemeGenerator(llm_client, max_validation_attempts=2)
    planner = TeamoRouterResearchLeadPlanner(llm_client, max_validation_attempts=3)
    trace_build = create_langfuse_trace_adapter(
        settings.langfuse,
        additional_sensitive_values={
            "FMP_API_KEY": settings.fmp.api_key.get_secret_value(),
            "TEAMOROUTER_API_KEY": settings.llm.api_key.get_secret_value(),
        },
    )
    service = ResearchApplicationService(
        trace_adapter=trace_build.adapter,
        evidence_repository=evidence_repository,
        evidence_collector=collector,
        scheme_generator=scheme_generator,
        planner=planner,
    )

    research_object = await service.create_object(
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
        idempotency_key="phase2-live-object-nvda",
    )
    draft = await service.prepare_run(
        research_object_id=research_object.object_id,
        research_goal="Assess NVDA fundamentals, evidence quality, material risks, and limitations",
        as_of=date(2026, 9, 4),
        preferences={"depth": "standard", "provider": "live_fmp"},
    )
    aggregate = await service.confirm_run(
        draft_id=draft.draft_id,
        confirm_scheme=True,
        idempotency_key="phase2-live-run-nvda",
    )
    _write_json(output / "scheme_snapshot.json", aggregate.scheme.model_dump(mode="json"))
    _write_json(
        output / "planned_graph.json",
        aggregate.runtime.planned_graph.model_dump(mode="json"),
    )
    aggregate = await service.execute_run(aggregate.run.run_id)

    artifacts = aggregate.artifacts
    assert artifacts.canonical_record is not None
    assert artifacts.released_result is not None
    assert artifacts.review is not None
    events = await service.event_store.replay(aggregate.run.run_id)
    scheme_audit = scheme_generator.last_audit
    planner_audit = planner.last_audit

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
    calculations = [item.model_dump(mode="json") for item in artifacts.calculations]
    _write_json(
        output / "accepted_evidence.json",
        [item.model_dump(mode="json") for item in artifacts.evidence],
    )
    _write_json(output / "calculation_records.json", calculations)
    _write_json(output / "runtime_events.json", [item.model_dump(mode="json") for item in events])
    _write_json(output / "task_outputs.json", artifacts.task_outputs)
    _write_json(
        output / "canonical_execution_record.json",
        artifacts.canonical_record.model_dump(mode="json"),
    )
    _write_json(
        output / "released_research_result.json",
        artifacts.released_result.model_dump(mode="json"),
    )

    summary = {
        "run_id": aggregate.run.run_id,
        "run_status": aggregate.run.status.value,
        "symbol": "NVDA",
        "frontend": "DEFERRED_PENDING_FINAL_UX_BASELINE",
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
            "enabled": trace_build.enabled,
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
        "evidence_event_count": sum(event.type.value == "evidence.accepted" for event in events),
        "graph_edge_event_count": sum(
            event.type.value in {"graph.edge_added", "graph.edge_removed"} for event in events
        ),
        "calculations": [
            {
                "calculation_id": item.calculation_id,
                "capability_id": item.capability_id,
                "capability_version": item.capability_version,
                "formula_id": item.formula_id,
                "code_hash": item.code_hash,
                "source_ref": item.source_ref,
                "runtime_version": item.runtime_version,
                "input_evidence_ids": item.input_evidence_ids,
                "output_value": str(item.output_value),
                "output_unit": item.output_unit,
                "review_record_id": item.review_record_id,
                "canonical_record_id": item.canonical_record_id,
            }
            for item in artifacts.calculations
        ],
        "review_status": artifacts.review.status.value,
        "canonical_record_id": artifacts.canonical_record.record_id,
        "released_result_id": artifacts.released_result.result_id,
        "runtime_event_count": len(events),
        "runtime_event_sequences_contiguous": [item.sequence for item in events]
        == list(range(1, len(events) + 1)),
        "secret_values_included": False,
    }
    _write_json(output / "acceptance_summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase2/acceptance/latest"),
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.output)), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
