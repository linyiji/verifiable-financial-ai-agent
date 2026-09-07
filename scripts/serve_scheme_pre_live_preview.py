"""Read-only browser harness: local validated prepare response; ALL other writes blocked."""

from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from apps.api.main import create_app
from src.phase4_product.admission import prepare_request_hash
from src.phase4_product.contracts import PrepareResearchRunRequestV1, ResearchRunDraftV1
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend


async def no_runtime_start(self):
    """This harness never starts scheduler workers, even if a database Run is nonterminal."""


PostgreSQLPhase4ProductBackend.start = no_runtime_start
app = create_app()
draft = ResearchRunDraftV1.model_validate_json(
    Path("artifacts/phase5b_scheme_repair/local-preview-draft.json").read_text()
)
receipt = {"preview_prepares": 0, "blocked_writes": 0, "provider_calls": 0, "r2_created": False}
headers = {
    "Content-Type": "application/json; charset=utf-8",
    "X-Phase4-Contract-Version": "phase4-core/v1",
    "Access-Control-Allow-Origin": "http://127.0.0.1:4173",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": (
        "Content-Type,Idempotency-Key,X-Phase4-Contract-Version,Accept,X-Request-ID"
    ),
    "Access-Control-Expose-Headers": "X-Phase4-Contract-Version",
}


@app.middleware("http")
async def pre_live_firewall(request: Request, call_next):
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=headers)
    if request.url.path == "/__pre_live_receipt":
        return JSONResponse(receipt)
    if request.method not in {"GET", "HEAD"}:
        if request.method == "POST" and request.url.path == "/api/research-runs/prepare":
            payload = PrepareResearchRunRequestV1.model_validate(await request.json())
            if prepare_request_hash(payload) != draft.prepare_request_hash:
                return JSONResponse(
                    {"error": "LOCAL_PREVIEW_REQUEST_MISMATCH"}, status_code=409, headers=headers
                )
            receipt["preview_prepares"] += 1
            return JSONResponse(draft.model_dump(mode="json"), status_code=201, headers=headers)
        receipt["blocked_writes"] += 1
        return JSONResponse({"error": "PRE_LIVE_R2_FIREWALL"}, status_code=403, headers=headers)
    return await call_next(request)
