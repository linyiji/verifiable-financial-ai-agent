"""Local HTTP-mocked production-adapter preview. No application DB writes or admission."""

import asyncio
from pathlib import Path

from src.phase4_product.admission import build_prepare_draft
from src.phase4_product.contracts import PrepareResearchRunRequestV1
from src.phase4_product.projections import project_goal, project_scheme
from tests.phase4.backend_product.test_incremental_scheme_repair import (
    generate_through_http,
    real_inputs,
)


async def main():
    view, obj, goal, _ = real_inputs()
    scheme, requests = await generate_through_http()
    # Match PostgreSQLPhase4ProductBackend.prepare's public assurance projection.
    scheme = scheme.model_copy(
        update={
            "assurance_requirements": {
                key: value
                for key, value in scheme.assurance_requirements.items()
                if key in {"financial_review", "proof_policy", "required", "reviewer", "policy_id"}
            }
        }
    )
    draft = build_prepare_draft(
        PrepareResearchRunRequestV1(
            research_object_id=obj.object_id,
            research_goal=goal.goal_text,
            as_of=goal.as_of,
            base_run_id=view.source_run_id,
            base_research_view_version=view.research_view_version_id,
        ),
        draft_id="DRAFT-P5B-LOCAL-PREVIEW",
        goal=project_goal(goal, expected_object_id=obj.object_id),
        scheme_snapshot=project_scheme(
            scheme,
            expected_object_id=obj.object_id,
            expected_goal_id=goal.goal_id,
            require_confirmed=False,
        ),
    )
    out = Path("artifacts/phase5b_scheme_repair")
    await asyncio.to_thread(out.mkdir, parents=True, exist_ok=True)
    (out / "local-preview-draft.json").write_text(draft.model_dump_json(indent=2))
    print("Local HTTP-mocked Scheme draft validated; R2_CREATED=NO; real model calls=0")
    assert len(requests) == 1


if __name__ == "__main__":
    asyncio.run(main())
