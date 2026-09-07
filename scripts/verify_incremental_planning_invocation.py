"""One guarded production-contract planning operation; no admission or app startup.

Retains existing adapter transport retries/fallback. Caps Scheme validation to one
logical provider call for this verification only; invalid output stops, not retries.
No request/response bodies are recorded. Only a validated public draft is retained.
"""

import argparse
import asyncio
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.adapters.llm.teamorouter import TeamoRouterClient
from src.agentic.llm_integration import PlannerProviderSchemeGenerator
from src.agentic.planning_errors import IncrementalSchemeFailure
from src.application.persistence import ResearchObjectRow
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.infrastructure.config.settings import Settings
from src.infrastructure.database.research_memory import ResearchMemoryRepository
from src.observability.performance import Recorder, configure
from src.phase4_product.admission import build_prepare_draft, draft_hash_is_valid
from src.phase4_product.contracts import PrepareResearchRunRequestV1
from src.phase4_product.incremental import build_incremental_context, validate_incremental_scheme
from src.phase4_product.projections import project_goal, project_scheme

OUT = Path("artifacts/phase5b_invocation_repair")
BASE = "RUN-57aed683-75d6-4b47-acc6-a73053ea492e"
VIEW = "RVV-05bec42f-ab9b-55c5-b502-c439b8abe948"
OBJECT = "OBJ-NVDA"
GOAL = (
    "更新 NVIDIA 公司金融研究：基于上次研究的历史背景，使用当前可获得且期间一致的"
    "权威财务证据重新评估营收增长、盈利能力、估值与主要风险，结合最新公司披露和行业事件，"
    "区分已验证事实与尚待确认的信息。"
)


def guard():
    return json.loads(
        subprocess.check_output(
            [".venv/bin/python", "scripts/phase5b_history_guard.py"],
            text=True,
        )
    )


async def main():
    settings = Settings(_env_file="/Users/mac/Verifiable_Financial_Agent_System/.env.local")
    engine = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(engine)
    try:
        repo = ResearchMemoryRepository(sessions)
        view = await repo.read_exact(OBJECT, BASE, VIEW)
        memory = await repo.read(OBJECT)
        assert memory.latest_released_run_id == BASE
        assert memory.latest_research_view_version == 1
        async with sessions() as session:
            row = await session.get(ResearchObjectRow, OBJECT)
            obj = ResearchObject.model_validate(row.payload)
    finally:
        await engine.dispose()
    before = await asyncio.to_thread(guard)
    await asyncio.to_thread(OUT.mkdir, parents=True, exist_ok=True)
    goal = ResearchGoal(
        goal_id="GOAL-P5B-INVOCATION-VERIFY",
        research_object_id=OBJECT,
        goal_text=GOAL,
        as_of="2026-09-07",
    )
    context = build_incremental_context(
        view, object_id=OBJECT, base_run_id=BASE, base_view_id=VIEW, target_as_of=goal.as_of
    )
    provider = TeamoRouterClient(settings.llm)
    generator = PlannerProviderSchemeGenerator(provider, max_validation_attempts=1)
    recorder = Recorder(
        OUT / "attempts.json", forbidden_values=(settings.llm.api_key.get_secret_value(),)
    )
    result = {
        "new_provider_research_runs": 0,
        "r2_created": False,
        "remote_schema_acceptance": "NOT_OBSERVED",
        "live_planning_invocation": "FAIL",
        "live_scheme_validation": "NOT_REACHED",
        "policy": asdict(provider.execution_policy),
    }
    # The marker is permanent, including after failure. No replay bypass exists.
    with (OUT / "verification-attempt.json").open("x") as handle:
        json.dump({"planning_operations_authorized": 1, "run_admission": False}, handle)
    configure(recorder)
    try:
        scheme = await generator.generate(
            research_object=obj, goal=goal, incremental_context=context
        )
        result["remote_schema_acceptance"] = "PASS"
        result["live_scheme_validation"] = "FAIL"
        validate_incremental_scheme(scheme, context)
        # Same public assurance filtering as production prepare_run, no policy change.
        public_scheme = scheme.model_copy(
            update={
                "assurance_requirements": {
                    key: value
                    for key, value in scheme.assurance_requirements.items()
                    if key
                    in {"financial_review", "proof_policy", "required", "reviewer", "policy_id"}
                }
            }
        )
        draft = build_prepare_draft(
            PrepareResearchRunRequestV1(
                research_object_id=OBJECT,
                research_goal=GOAL,
                as_of=goal.as_of,
                base_run_id=BASE,
                base_research_view_version=VIEW,
            ),
            draft_id="DRAFT-P5B-INVOCATION-VERIFY",
            goal=project_goal(goal, expected_object_id=OBJECT),
            scheme_snapshot=project_scheme(
                public_scheme,
                expected_object_id=OBJECT,
                expected_goal_id=goal.goal_id,
                require_confirmed=False,
            ),
        )
        assert draft_hash_is_valid(draft)
        await asyncio.to_thread(
            (OUT / "validated-unadmitted-draft.json").write_text, draft.model_dump_json(indent=2)
        )
        result.update(
            live_planning_invocation="PASS",
            live_scheme_validation="PASS",
            counts={
                kind: sum(d.decision == kind for d in scheme.incremental_context.decisions)
                for kind in ("REUSE", "REFRESH", "REVALIDATE", "PREVENT", "UNKNOWN")
            },
        )
    except IncrementalSchemeFailure as error:
        result.update(reason_code=error.reason_code, attempted_count=error.attempted_count)
    except Exception:
        result["reason_code"] = "LOCAL_VALIDATION_FAILURE"
    finally:
        await recorder.flush()
        configure(None)
        after = await asyncio.to_thread(guard)
        result["history_unchanged"] = before == after
        result["observed_attempt_count"] = sum(
            r["operation"] == "model.attempt" for r in recorder.records
        )
        result["observed_logical_calls"] = sum(
            r["operation"] == "model.logical_call" for r in recorder.records
        )
        await asyncio.to_thread(
            (OUT / "history-guard.json").write_text,
            json.dumps({"before": before, "after": after}, indent=2),
        )
        await asyncio.to_thread((OUT / "result.json").write_text, json.dumps(result, indent=2))
        print(json.dumps(result))
    assert result["history_unchanged"] and result["observed_logical_calls"] == 1
    if result["live_scheme_validation"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-live", action="store_true", required=True)
    parser.parse_args()
    asyncio.run(main())
