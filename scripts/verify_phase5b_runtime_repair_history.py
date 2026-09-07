"""Read-only historical safety check. No runtime startup, provider, or admission."""

# Small local forensic fixtures in a single-purpose command, not a serving event loop.
# ruff: noqa: ASYNC240

import asyncio
import hashlib
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from scripts.verify_incremental_planning_invocation import guard
from src.application.persistence import (
    ResearchRunAggregateRow,
    ResearchRunDraftRow,
    RuntimeEventRow,
    TaskRow,
)
from src.infrastructure.config.settings import Settings
from src.infrastructure.database.research_memory import ResearchMemoryRepository

RUN = "RUN-e1b27d55-a58f-428d-b98b-0dc519577bc0"
DRAFT = "DRAFT-036cd4bd-fb8b-4c05-a9ba-25c654588342"
EVIDENCE = Path("artifacts/phase5b_r2_runtime_blocker")


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def main():
    safety = json.loads((EVIDENCE / "memory-safety.json").read_text())
    timeline = json.loads((EVIDENCE / "run-timeline.json").read_text())
    prior_tasks = json.loads((EVIDENCE / "task-state.json").read_text())["tasks"]
    original_draft = json.loads(
        Path("artifacts/mimo_provider_capability/validated-persisted-draft.json").read_text()
    )
    assert guard() == safety["history_guard_after"]
    engine = create_async_engine(
        Settings(_env_file="/Users/mac/Verifiable_Financial_Agent_System/.env.local").database_url
    )
    sessions = async_sessionmaker(engine)
    try:
        async with sessions() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            row = await session.get(ResearchRunAggregateRow, RUN)
            assert row.status == "FAILED"
            assert digest(row.payload) == safety["r2_aggregate_sha256"]
            assert row.payload["run"] == timeline["run"]
            graph = json.loads(
                Path("tests/fixtures/phase5b_failed_r2_planned_graph.json").read_text()
            )
            assert row.payload["runtime"]["planned_graph"] == graph
            tasks = list(
                await session.scalars(
                    select(TaskRow).where(TaskRow.run_id == RUN).order_by(TaskRow.task_id)
                )
            )
            assert len(tasks) == len(prior_tasks) == 9
            for task in tasks:
                prior = next(p for p in prior_tasks if p["task_id"] == task.task_id)
                assert all(task.payload[key] == value for key, value in prior.items())
            events = list(
                await session.scalars(
                    select(RuntimeEventRow)
                    .where(RuntimeEventRow.run_id == RUN)
                    .order_by(RuntimeEventRow.sequence)
                )
            )
            assert len(events) == timeline["total_event_count"] == 606
            assert dict(Counter(e.payload["type"] for e in events)) == timeline["event_type_counts"]
            for prior in timeline["selected_causal_events"]:
                event = next(e for e in events if e.event_id == prior["event_id"])
                # The prior causal receipt intentionally omitted non-causal payload fields.
                assert all(
                    event.payload[key] == value for key, value in prior.items() if key != "payload"
                )
                assert all(
                    event.payload["payload"][key] == value
                    for key, value in prior["payload"].items()
                )
            draft = await session.get(ResearchRunDraftRow, DRAFT)
            assert draft.payload == original_draft
            assert draft.consumed_run_id == RUN
            assert draft.consumed_admission_id == "ADM-315545cb-c617-45bc-ba04-b316a2c1fcf8"
            assert draft.consumed_at.isoformat() == "2026-09-07T10:30:13.187274+00:00"
            for table in ("research_object_versions", "research_view_versions"):
                assert (
                    await session.scalar(
                        text(
                            f"SELECT count(*) FROM {table} WHERE object_id='OBJ-NVDA' AND version>1"
                        )
                    )
                    == 0
                )
            hashes = {
                "r2_aggregate_sha256": digest(row.payload),
                "r2_tasks_sha256": digest([t.payload for t in tasks]),
                "r2_events_sha256": digest([e.payload for e in events]),
                "draft_payload_sha256": digest(draft.payload),
            }
        memory = await ResearchMemoryRepository(sessions).read("OBJ-NVDA")
        assert memory.latest_released_run_id == safety["latest_released_run_id"]
        assert memory.latest_research_view_version == 1
        print(
            json.dumps({"history_safety": "PASS", "production_run_count": 37, **hashes}, indent=2)
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
