"""One opt-in planning-only request. No application backend or Run admission."""

import asyncio
import json
from pathlib import Path

import httpx

from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.provider import LLMProviderError
from src.adapters.llm.teamorouter import TeamoRouterClient
from src.agentic.llm_integration import IncrementalSchemeProposal, _scheme_messages
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.infrastructure.config.settings import Settings
from src.phase4_product.incremental import build_incremental_context
from src.phase4_product.memory_contracts import ResearchMemorySnapshot


async def main():
    out = Path("artifacts/phase5b_scheme_repair")
    await asyncio.to_thread(out.mkdir, parents=True, exist_ok=True)
    memory = ResearchMemorySnapshot.model_validate_json(
        await asyncio.to_thread(
            Path("artifacts/phase5b/memory-after-stopped-prepare.json").read_text
        )
    )
    goal = ResearchGoal(
        goal_id="GOAL-P5B-PREFLIGHT-DIAGNOSTIC",
        research_object_id="OBJ-NVDA",
        goal_text="更新 NVIDIA 营收增长、估值与风险研究；重新取得当前证据并检查期间一致性。",
        as_of="2026-09-07",
    )
    obj = ResearchObject(
        object_id="OBJ-NVDA", symbol="NVDA", company_name="NVIDIA Corporation", exchange="NASDAQ"
    )
    context = build_incremental_context(
        memory.current_view,
        object_id=obj.object_id,
        base_run_id=memory.latest_released_run_id,
        base_view_id=memory.current_view.research_view_version_id,
        target_as_of=goal.as_of,
    )
    result = {"http_attempts": 0, "new_provider_research_runs": 0}

    async def response_hook(response):
        result["http_attempts"] += 1
        result["http_status"] = response.status_code
        if response.status_code >= 400:
            await response.aread()
            try:
                body = response.json()
                error = body.get("error", {})
                message = str(error.get("message", "")) if isinstance(error, dict) else ""
                # Only fixed booleans are retained; never the provider body/message.
                result["mentions_schema"] = "schema" in message.lower()
                result["mentions_additional_properties"] = "additionalProperties" in message
                result["mentions_false"] = "false" in message.lower()
                result["mentions_required"] = "required" in message.lower()
            except (ValueError, TypeError):
                result["error_shape_observed"] = False

    settings = Settings()
    async with httpx.AsyncClient(event_hooks={"response": [response_hook]}) as http:
        client = TeamoRouterClient(
            settings.llm,
            client=http,
            execution_policy=ProviderExecutionPolicyV1(
                max_attempts=1, overall_workload_deadline_seconds=90
            ),
        )
        # Claim the one HTTP allowance only after local configuration validates.
        with (out / "planning-http-attempt.json").open("x") as handle:
            json.dump({"max_http_attempts": 1, "creates_research_run": False}, handle)
        try:
            await client.complete_structured(
                messages=_scheme_messages(obj, goal, context),
                response_model=IncrementalSchemeProposal,
                schema_name="research_scheme_proposal_v2",
                workload_type="SCHEME_PLANNER",
            )
            result["outcome"] = "STRUCTURED_OUTPUT_ACCEPTED"
        except LLMProviderError as error:
            result["outcome"] = "REJECTED"
            result["failure_classification"] = error.failure_classification
            result["attempted_models_count"] = len(error.attempted_models)
    (out / "planning-diagnostic-result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
