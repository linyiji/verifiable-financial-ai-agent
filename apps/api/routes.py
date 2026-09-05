from __future__ import annotations

from fastapi import Header, Request
from fastapi.responses import StreamingResponse

from src.application.events import prepare_completed_run_event_stream
from src.application.service import ResearchApplicationService
from src.phase4_product.api import create_phase4_product_router
from src.phase4_product.contracts import PHASE4_CONTRACT_VERSION
from src.phase4_product.errors import product_error
from src.runtime.events import CursorPreflightError

router = create_phase4_product_router()


def _service(request: Request) -> ResearchApplicationService:
    try:
        return request.app.state.research_service
    except AttributeError as exc:
        raise product_error(
            "TRANSIENT_BACKEND_ERROR",
            "runtime event backend is temporarily unavailable",
        ) from exc


@router.get("/research-runs/{run_id}/events")
async def stream_events(
    run_id: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    requested_contract = request.headers.get("X-Phase4-Contract-Version")
    if requested_contract not in {None, PHASE4_CONTRACT_VERSION}:
        raise product_error(
            "SCHEMA_INCOMPATIBLE",
            "unsupported Phase 4 contract version",
            details={"supported_version": PHASE4_CONTRACT_VERSION},
        )
    service = _service(request)
    try:
        backend = getattr(request.app.state, "phase4_product_backend", None)
        if backend is not None:
            await backend.get_run(run_id)
        else:
            await service.get_run(run_id)
        prepared = await prepare_completed_run_event_stream(
            store=service.event_store,
            run_id=run_id,
            last_event_id=last_event_id,
            heartbeat_seconds=1.0,
        )
    except CursorPreflightError as exc:
        raise product_error(
            exc.code.value,
            str(exc),
            resource_type="research_run",
            resource_id=run_id,
        ) from exc
    return StreamingResponse(
        prepared.body,
        media_type="text/event-stream",
        headers=dict(prepared.response_headers),
    )
