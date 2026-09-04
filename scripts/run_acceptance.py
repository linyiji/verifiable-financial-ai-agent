"""Run the controlled Phase-1 vertical slice and save reviewable evidence artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

from src.application.service import ResearchApplicationService


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


async def run(output: Path) -> dict[str, Any]:
    await asyncio.to_thread(output.mkdir, parents=True, exist_ok=True)
    service = ResearchApplicationService()
    research_object = await service.create_object(
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
        idempotency_key="acceptance-object-nvda",
    )
    draft = await service.prepare_run(
        research_object_id=research_object.object_id,
        research_goal="Assess fundamentals, valuation limitations, and material risks",
        as_of=date(2026, 9, 3),
        preferences={"depth": "standard"},
    )
    aggregate = await service.confirm_run(
        draft_id=draft.draft_id,
        confirm_scheme=True,
        idempotency_key="acceptance-run-nvda",
    )
    await service.execute_run(aggregate.run.run_id)

    artifacts = aggregate.artifacts
    assert artifacts.canonical_record is not None
    assert artifacts.released_result is not None
    assert artifacts.report is not None
    assert artifacts.projections is not None
    assert artifacts.writeback is not None
    assert artifacts.review is not None
    events = await service.event_store.replay(aggregate.run.run_id)

    _write_json(output / "runtime_events.json", [item.model_dump(mode="json") for item in events])
    _write_json(
        output / "calculation_records.json",
        [item.model_dump(mode="json") for item in artifacts.calculations],
    )
    _write_json(
        output / "canonical_execution_record.json",
        artifacts.canonical_record.model_dump(mode="json"),
    )
    _write_json(
        output / "released_research_result.json",
        artifacts.released_result.model_dump(mode="json"),
    )
    _write_json(output / "financial_report.json", artifacts.report.model_dump(mode="json"))
    _write_json(output / "writeback_proposal.json", artifacts.writeback.model_dump(mode="json"))

    summary = {
        "run_id": aggregate.run.run_id,
        "run_status": aggregate.run.status.value,
        "planned_task_count": len(aggregate.runtime.planned_graph.tasks),
        "actual_task_count": len(aggregate.runtime.actual_graph.tasks),
        "parallel_task_peak": artifacts.parallel_task_peak,
        "accepted_evidence_count": len(artifacts.evidence),
        "fixture_snapshot_hashes": sorted({item.snapshot_hash for item in artifacts.evidence}),
        "calculation_count": len(artifacts.calculations),
        "correction_count": len(artifacts.corrections),
        "replan_count": len(artifacts.replans),
        "review_status": artifacts.review.status.value,
        "proof_statuses": [item.status.value for item in artifacts.proofs],
        "canonical_record_id": artifacts.canonical_record.record_id,
        "financial_review_record_id": (artifacts.projections.financial_review.canonical_record_id),
        "execution_details_record_id": (
            artifacts.projections.execution_details.canonical_record_id
        ),
        "runtime_event_count": len(events),
        "runtime_event_sequences_contiguous": [item.sequence for item in events]
        == list(range(1, len(events) + 1)),
    }
    _write_json(output / "acceptance_summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/acceptance/latest"),
        help="Directory for generated acceptance evidence",
    )
    args = parser.parse_args()
    summary = asyncio.run(run(args.output))
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
