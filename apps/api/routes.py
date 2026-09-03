from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Header, Request
from fastapi.responses import StreamingResponse

from contracts.api.models import (
    ConfirmResearchRunRequest,
    CreateResearchObjectRequest,
    PrepareResearchRunRequest,
)
from src.application.errors import ApplicationError
from src.application.events import completed_run_event_stream
from src.application.service import ResearchApplicationService

router = APIRouter(prefix="/api")


def _service(request: Request) -> ResearchApplicationService:
    return request.app.state.research_service


@router.post("/objects", status_code=201)
async def create_object(
    payload: CreateResearchObjectRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return await _service(request).create_object(
        **payload.model_dump(), idempotency_key=idempotency_key
    )


@router.get("/objects")
async def list_objects(request: Request):
    return await _service(request).repository.list_objects()


@router.get("/objects/{object_id}")
async def get_object(object_id: str, request: Request):
    return await _service(request).get_object(object_id)


@router.get("/objects/{object_id}/state")
async def get_object_state(object_id: str, request: Request):
    service = _service(request)
    await service.get_object(object_id)
    runs = await service.repository.list_runs_for_object(object_id)
    proposals = [run.artifacts.writeback for run in runs if run.artifacts.writeback is not None]
    return {"research_object_id": object_id, "writeback_proposals": proposals}


@router.get("/objects/{object_id}/financials")
async def get_object_financials(object_id: str, request: Request):
    service = _service(request)
    await service.get_object(object_id)
    runs = await service.repository.list_runs_for_object(object_id)
    values = [
        run.artifacts.released_result.structured_financial_results.get("financial_summary", {})
        for run in runs
        if run.artifacts.released_result is not None
    ]
    return {"research_object_id": object_id, "versions": values}


@router.get("/objects/{object_id}/runs")
async def list_object_runs(object_id: str, request: Request):
    service = _service(request)
    await service.get_object(object_id)
    return [run.run for run in await service.repository.list_runs_for_object(object_id)]


@router.post("/research-runs/prepare", status_code=201)
async def prepare_run(payload: PrepareResearchRunRequest, request: Request):
    return await _service(request).prepare_run(**payload.model_dump())


@router.post("/research-runs", status_code=201)
async def confirm_run(
    payload: ConfirmResearchRunRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    service = _service(request)
    aggregate = await service.confirm_run(**payload.model_dump(), idempotency_key=idempotency_key)
    background_tasks.add_task(service.execute_run, aggregate.run.run_id)
    return {"run_id": aggregate.run.run_id, "status": "planning"}


@router.get("/research-runs/{run_id}")
async def get_run(run_id: str, request: Request):
    return (await _service(request).get_run(run_id)).run


@router.get("/research-runs/{run_id}/tasks")
async def get_tasks(run_id: str, request: Request):
    return (await _service(request).get_run(run_id)).runtime.actual_graph.tasks


@router.get("/research-runs/{run_id}/graph")
async def get_graph(run_id: str, request: Request):
    runtime = (await _service(request).get_run(run_id)).runtime
    return {
        "planned_graph": runtime.planned_graph,
        "actual_graph": runtime.actual_graph,
    }


@router.get("/research-runs/{run_id}/result")
async def get_result(run_id: str, request: Request):
    artifacts = (await _service(request).get_run(run_id)).artifacts
    if artifacts.released_result is None:
        raise ApplicationError("RESULT_NOT_RELEASED", "run result is not released", status_code=409)
    return {"result": artifacts.released_result, "report": artifacts.report}


@router.get("/research-runs/{run_id}/review-view")
async def get_review_view(run_id: str, request: Request):
    artifacts = (await _service(request).get_run(run_id)).artifacts
    if artifacts.projections is None:
        raise ApplicationError(
            "RESULT_NOT_RELEASED", "review view is not released", status_code=409
        )
    return artifacts.projections.financial_review


@router.get("/research-runs/{run_id}/execution-view")
async def get_execution_view(run_id: str, request: Request):
    artifacts = (await _service(request).get_run(run_id)).artifacts
    if artifacts.projections is None:
        raise ApplicationError(
            "RESULT_NOT_RELEASED", "execution view is not released", status_code=409
        )
    return artifacts.projections.execution_details


@router.get("/research-runs/{run_id}/events")
async def stream_events(
    run_id: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    service = _service(request)
    await service.get_run(run_id)
    return StreamingResponse(
        completed_run_event_stream(
            store=service.event_store,
            run_id=run_id,
            last_event_id=last_event_id,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.post("/reviews/{review_id}/resolve")
async def resolve_review(review_id: str):
    raise ApplicationError(
        "NOT_IMPLEMENTED",
        f"manual review resolution is not implemented in Phase 1: {review_id}",
        status_code=501,
    )


@router.post("/research-runs/{run_id}/capability-gaps/{gap_id}/generate")
@router.post("/research-runs/{run_id}/capability-gaps/{gap_id}/skip")
async def capability_gap_action(run_id: str, gap_id: str):
    raise ApplicationError(
        "NOT_IMPLEMENTED",
        "generated capability workflow is deferred; no capability is faked",
        status_code=501,
        details={"run_id": run_id, "gap_id": gap_id},
    )
