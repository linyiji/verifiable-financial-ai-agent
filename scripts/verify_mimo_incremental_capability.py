"""One real MiMo prepare transaction, never confirmation or runtime startup."""

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from scripts.verify_incremental_planning_invocation import BASE, GOAL, OBJECT, VIEW, guard
from src.adapters.llm.routes import configured_incremental_provider, describe_route
from src.agentic.llm_integration import PlannerProviderSchemeGenerator
from src.application.service import ResearchApplicationService
from src.infrastructure.config.settings import Settings
from src.infrastructure.database.research_memory import ResearchMemoryRepository
from src.observability.performance import Recorder, configure
from src.phase4_product.admission import draft_hash_is_valid
from src.phase4_product.contracts import PrepareResearchRunRequestV1
from src.phase4_product.errors import ProductError
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend

OUT = Path("artifacts/mimo_provider_capability")
KEY = "mimo-capability-exact-nvda-v1-20260907"


async def main():
    settings = Settings()
    provider = configured_incremental_provider(settings, route_id="mimo-direct")
    before = await asyncio.to_thread(guard)
    engine = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repo = ResearchMemoryRepository(sessions)
    view = await repo.read_exact(OBJECT, BASE, VIEW)
    memory = await repo.read(OBJECT)
    assert memory.latest_released_run_id == BASE and memory.latest_research_view_version == 1
    assert view.research_view_version_id == VIEW
    backend = PostgreSQLPhase4ProductBackend(
        sessions=sessions,
        service=ResearchApplicationService(),
        incremental_scheme_generator=PlannerProviderSchemeGenerator(
            provider, max_validation_attempts=1
        ),
    )
    # No backend.start(), confirm_run(), planner, scheduler or Run identity allocation.
    await asyncio.to_thread(OUT.mkdir, parents=True, exist_ok=True)
    recorder = Recorder(
        OUT / "attempts.json", forbidden_values=(provider._settings.api_key.get_secret_value(),)
    )
    result = {
        "route": asdict(describe_route(provider)),
        "r2_created": False,
        "new_provider_research_runs": 0,
        "live_scheme_validation": "NOT_REACHED",
    }
    request = PrepareResearchRunRequestV1(
        research_object_id=OBJECT,
        research_goal=GOAL,
        as_of="2026-09-07",
        base_run_id=BASE,
        base_research_view_version=VIEW,
    )
    # Never delete this consumed marker to repeat a failed call.
    with (OUT / "live-call-guard.json").open("x") as handle:
        json.dump({"max_logical_calls": 1, "admission_authorized": False}, handle)
    configure(recorder)
    try:
        draft = await backend.prepare_run(request, idempotency_key=KEY, request_id=None)
        assert draft_hash_is_valid(draft)
        replay = await backend.prepare_run(request, idempotency_key=KEY, request_id=None)
        assert replay == draft
        result.update(
            live_scheme_validation="PASS",
            draft_id=draft.draft_id,
            draft_hash=draft.draft_hash,
            expires_at=draft.expires_at.isoformat(),
            prepare_idempotency_key=KEY,
            persisted_prepare_replay=True,
            counts={
                k: sum(d.decision == k for d in draft.scheme_snapshot.incremental_context.decisions)
                for k in ("REUSE", "REFRESH", "REVALIDATE", "PREVENT", "UNKNOWN")
            },
        )
        await asyncio.to_thread(
            (OUT / "validated-persisted-draft.json").write_text, draft.model_dump_json(indent=2)
        )
    except ProductError as error:
        # Error objects contain only owned classification; never provider exception text.
        result["failure"] = {"code": error.code, "details": error.details}
    finally:
        await recorder.flush()
        configure(None)
        await engine.dispose()
        after = await asyncio.to_thread(guard)
        result["history_unchanged"] = before == after
        result["logical_calls"] = sum(
            r["operation"] == "model.logical_call" for r in recorder.records
        )
        result["attempt_count"] = sum(r["operation"] == "model.attempt" for r in recorder.records)
        await asyncio.to_thread(
            (OUT / "history-guard.json").write_text,
            json.dumps({"before": before, "after": after}, indent=2),
        )
        await asyncio.to_thread((OUT / "result.json").write_text, json.dumps(result, indent=2))
        print(json.dumps(result))
    assert result["history_unchanged"] and result["logical_calls"] <= 1
    if result["live_scheme_validation"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-live", action="store_true", required=True)
    parser.parse_args()
    asyncio.run(main())
