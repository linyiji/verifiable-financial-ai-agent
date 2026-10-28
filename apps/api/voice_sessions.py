"""Authenticated voice control and a separate, secret-authenticated Worker plane."""

import asyncio
import hmac
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from contracts.api.voice_session import (
    BindVoiceSession,
    CreateVoiceSession,
    VoiceCredentials,
    VoiceErrorEnvelope,
    VoiceEventsResponse,
    VoiceSessionResponse,
    VoiceProviderAvailability,
    WorkerClaim,
    WorkerConsume,
    WorkerDialogue,
    WorkerPoll,
    WorkerReceipt,
)
from src.adapters.livekit_media import LiveKitMedia
from src.application.voice_sessions import VoiceSessions, fail
from src.application.voice_provider_status import voice_provider_availability, local_test_admitted
from src.infrastructure.config.settings import get_settings
from src.infrastructure.database.voice_tables import VoiceSessionRow

bearer = HTTPBearer(auto_error=False)
LAB_PATH = Path(__file__).resolve().parents[2] / "deploy/voice/client.html"
router = APIRouter(
    prefix="/api/voice-sessions",
    tags=["continuous-voice"],
    responses={code: {"model": VoiceErrorEnvelope} for code in [401, 403, 404, 409, 410, 422, 503]},
)
internal = APIRouter(prefix="/internal/voice", tags=["voice-worker"])


async def principal(
    request: Request,
    auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer),
    ],
):
    mode = os.getenv("VEFIN_VOICE_AUTH_MODE", "disabled")
    if mode == "production":
        resolver = getattr(request.app.state, "voice_identity_resolver", None)
        authorizer = getattr(request.app.state, "voice_task_authorizer", None)
        if not resolver or not authorizer or authorizer is local_task_authorizer:
            fail("VOICE_AUTH_PRODUCTION_BLOCKED", "生产身份认证和 Task 归属校验尚未接入。", 503)
        return await resolver(request)
    if mode != "local":
        fail("VOICE_AUTH_PRODUCTION_BLOCKED", "语音令牌签发默认关闭；尚无生产认证。", 503)
    tokens = json.loads(os.getenv("VEFIN_VOICE_LOCAL_TOKENS", "{}"))
    if auth and auth.scheme.lower() == "bearer":
        for user_id, expected in tokens.items():
            if (
                isinstance(expected, str)
                and len(expected) >= 32
                and hmac.compare_digest(
                    auth.credentials,
                    expected,
                )
            ):
                return user_id
    if auth is None and os.getenv("VEFIN_LOCAL_QA_SESSION_ENABLED") == "1":
        # The product browser uses the same HttpOnly local QA session as the
        # research UI. Its resolver keeps the loopback and token-fingerprint
        # checks; the voice Task authorizer still runs after authentication.
        from apps.api.research_identity import identity

        return await identity(request)
    fail("VOICE_UNAUTHORIZED", "需要有效身份凭证。", 401)


async def local_task_authorizer(user_id: str, task_id: str):
    grants_path = os.getenv("VEFIN_VOICE_LOCAL_TASK_GRANTS_FILE")
    # Operator-managed, private file allows an exact grant after UI Task creation.
    # No endpoint can self-grant ownership; production never uses this resolver.
    grants = json.loads(
        await asyncio.to_thread(Path(grants_path).read_text)
        if grants_path
        else os.getenv("VEFIN_VOICE_LOCAL_TASK_GRANTS", "{}")
    )
    if task_id not in grants.get(user_id, []):
        fail("VOICE_TASK_FORBIDDEN", "当前身份未获该 Task 的授权。", 403)


async def worker_auth(auth: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    expected = os.getenv("VEFIN_VOICE_WORKER_SECRET", "")
    if not (len(expected) >= 32 and auth and hmac.compare_digest(auth.credentials, expected)):
        fail("VOICE_WORKER_UNAUTHORIZED", "Worker 凭证无效。", 401)


def control(request: Request) -> VoiceSessions:
    service = request.app.state.voice_sessions
    if service is None:
        fail("VOICE_MEDIA_UNAVAILABLE", "连续语音控制层尚未启用。", 503)
    return service


@router.post("", response_model=VoiceSessionResponse, status_code=201)
async def create_voice(
    payload: CreateVoiceSession,
    request: Request,
    user: str = Depends(principal),
    key: str = Header(alias="Idempotency-Key"),
):
    availability = voice_provider_availability()
    if payload.interaction_mode == "conversation" and availability.blocked and not local_test_admitted(user, key=key):
        fail("VOICE_PROVIDER_UNAVAILABLE", availability.message, 503, retryable=False)
    return await control(request).create(user, key, payload.interaction_mode, payload.language)


@router.get("/availability", response_model=VoiceProviderAvailability)
async def voice_availability(response: Response, user: str = Depends(principal)):
    response.headers["Cache-Control"] = "no-store"
    return voice_provider_availability()


@router.get("/{session_id}", response_model=VoiceSessionResponse)
async def get_voice(session_id: str, request: Request, user: str = Depends(principal)):
    return await control(request).get(session_id, user)


@router.put("/{session_id}/binding", response_model=VoiceSessionResponse)
async def bind_voice(
    session_id: str, payload: BindVoiceSession, request: Request, user: str = Depends(principal)
):
    return await control(request).bind(session_id, user, payload.task_id, payload.chat_session_id)


@router.post("/{session_id}/credentials", response_model=VoiceCredentials)
async def voice_credentials(
    session_id: str, request: Request, response: Response, user: str = Depends(principal)
):
    response.headers["Cache-Control"] = "no-store"
    session = await control(request).get(session_id, user)
    availability = voice_provider_availability()
    if session.interaction_mode == "conversation" and availability.blocked and not local_test_admitted(user, session_id=session_id):
        fail("VOICE_PROVIDER_UNAVAILABLE", availability.message, 503, retryable=False)
    try:
        return await control(request).credentials(session_id, user)
    except (TimeoutError, ImportError, OSError):
        fail("VOICE_MEDIA_UNAVAILABLE", "媒体服务暂不可用。", 503, retryable=True)


@router.post("/{session_id}/end", response_model=VoiceSessionResponse)
async def end_voice(session_id: str, request: Request, user: str = Depends(principal)):
    return await control(request).end(session_id, user)


@router.get("/{session_id}/events", response_model=VoiceEventsResponse)
async def voice_events(
    session_id: str,
    request: Request,
    user: str = Depends(principal),
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    return await control(request).events(session_id, user, after, limit)


@internal.get("/sessions", dependencies=[Depends(worker_auth)], include_in_schema=False)
async def worker_sessions(request: Request):
    return await control(request).candidates()


@internal.post("/{session_id}/claim", dependencies=[Depends(worker_auth)], include_in_schema=False)
async def worker_claim(session_id: str, payload: WorkerClaim, request: Request):
    return await control(request).claim(session_id)


@internal.post("/{session_id}/poll", dependencies=[Depends(worker_auth)], include_in_schema=False)
async def worker_poll(session_id: str, payload: WorkerPoll, request: Request):
    return await control(request).poll(session_id, payload.lease_id)


@internal.post(
    "/{session_id}/release", dependencies=[Depends(worker_auth)], include_in_schema=False
)
async def worker_release(session_id: str, payload: WorkerPoll, request: Request):
    return await control(request).release(session_id, payload.lease_id)


@internal.post(
    "/{session_id}/consume",
    dependencies=[Depends(worker_auth)],
    include_in_schema=False,
)
async def worker_consume(session_id: str, payload: WorkerConsume, request: Request):
    # Refresh the authoritative state immediately before scheduling any announcement.
    await control(request).poll(session_id, payload.lease_id)
    return await control(request).consume(session_id, payload.lease_id, payload.event_id)


@internal.post(
    "/{session_id}/receipt",
    dependencies=[Depends(worker_auth)],
    include_in_schema=False,
)
async def worker_receipt(session_id: str, payload: WorkerReceipt, request: Request):
    return await control(request).receipt(session_id, payload)


@internal.post("/livekit-webhook", include_in_schema=False)
async def livekit_webhook(request: Request):
    service = control(request)
    if not service.media.configured:
        fail("VOICE_MEDIA_UNAVAILABLE", "媒体服务未配置。", 503)
    from livekit import api

    receiver = api.WebhookReceiver(api.TokenVerifier(service.media.key, service.media.secret))
    body = await request.body()
    if len(body) > 65536:
        fail("REQUEST_VALIDATION_ERROR", "Webhook 内容超限。", 413)
    try:
        event = receiver.receive(body.decode(), request.headers.get("Authorization", ""))
    except Exception:
        fail("VOICE_WEBHOOK_UNAUTHORIZED", "Webhook 签名无效。", 401)
    room_name = event.room.name
    if event.event not in {"room_started", "participant_joined"} or not room_name.startswith(
        "vefin-",
    ):
        return {"accepted": True}
    async with service.sessions() as db:
        row = await db.scalar(select(VoiceSessionRow).where(VoiceSessionRow.room == room_name))
        rejected = row is None or row.status == "ended"
        if row:
            rejected = rejected or service.view(row).remaining_seconds == 0
            if event.event == "participant_joined":
                rejected = rejected or event.participant.identity not in {
                    f"user:{row.id}",
                    f"agent:{row.lease_id}",
                }
    if rejected:
        await service.media.delete_room(room_name)
    return {"accepted": True}


def install_voice(app):
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application):
            media = LiveKitMedia()
            enabled = (
                media.configured
                or bool(os.getenv("VEFIN_VOICE_WORKER_SECRET"))
                or os.getenv("VEFIN_VOICE_AUTH_MODE", "disabled") in {"local", "production"}
            )
            application.state.voice_sessions = None
            if not enabled:
                # Opt-in voice must not add a DB dependency to an existing memory-only API.
                yield
                return
            service = VoiceSessions(
                application,
                os.getenv(
                    "VEFIN_VOICE_DATABASE_URL",
                    get_settings().database_url,
                ),
                media,
            )
            application.state.voice_sessions = service
            if os.getenv("VEFIN_VOICE_AUTH_MODE") == "local":

                async def authorized_local_task(user_id, task_id):
                    coordinator = getattr(application.state, "research_asset_production", None)
                    store = coordinator._durable_store if coordinator else None
                    row = (
                        await asyncio.to_thread(store.get, "research_task_ownership", task_id)
                        if store
                        else None
                    )
                    if row and row["user_id"] == user_id:
                        return
                    await local_task_authorizer(user_id, task_id)

                application.state.voice_task_authorizer = authorized_local_task
            await service.start()
            from src.application.voice_dialogue import VoiceDialogue
            from src.adapters.voice_dialogue_model import DeepSeekVoiceDialogueModel
            import httpx

            voice_settings = get_settings().voice_llm
            voice_client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=3, read=5, write=3, pool=2),
                limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
                http2=False, trust_env=True, follow_redirects=False,
            )
            try:
                voice_model = (
                    DeepSeekVoiceDialogueModel(voice_settings, voice_client)
                    if voice_settings.enabled else None
                )
                service.dialogue = VoiceDialogue(
                    service, voice_model,
                    structured_constraints=__import__("os").getenv("VEFIN_VOICE_STRUCTURED_CONSTRAINTS") == "1",
                )
                yield
            finally:
                await voice_client.aclose()
                await service.close()

    app.router.lifespan_context = lifespan
    app.include_router(router)
    app.include_router(internal)

    # Opt-in local integration: product and lab share one browser permission origin.
    # This serves public build assets only; credentials are still entered in memory.
    local_web = os.getenv("VEFIN_VOICE_LOCAL_WEB_DIR")
    if local_web and os.getenv("VEFIN_VOICE_AUTH_MODE") == "local":
        web_root = Path(local_web).resolve()
        app.mount("/assets", StaticFiles(directory=web_root / "assets"), name="voice-local-assets")

        @app.get("/", include_in_schema=False)
        @app.get("/research/{page:path}", include_in_schema=False)
        @app.get("/workspace/{page:path}", include_in_schema=False)
        async def local_product(page: str = ""):
            return FileResponse(web_root / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/voice-lab", include_in_schema=False)
    async def voice_lab():
        if os.getenv("VEFIN_VOICE_AUTH_MODE") != "local":
            fail("VOICE_SESSION_NOT_FOUND", "页面不存在。", 404)
        return FileResponse(LAB_PATH)

    @app.get("/health/voice", tags=["system"])
    async def voice_health(request: Request):
        if request.app.state.voice_sessions is None:
            return {
                "control": "disabled",
                "media": "unavailable",
                "cleanup": "inactive",
                "auth_mode": "disabled",
                "production_auth": "blocked",
            }
        service = control(request)
        try:
            ready = await service.media.healthy()
        except Exception:
            ready = False
        return {
            "control": "ok",
            "media": "ok" if ready else "unavailable",
            "cleanup": "retrying" if service.cleanup_error else "ok",
            "auth_mode": os.getenv("VEFIN_VOICE_AUTH_MODE", "disabled"),
            "production_auth": "blocked"
            if not getattr(
                app.state,
                "voice_identity_resolver",
                None,
            )
            else "configured",
        }


@internal.post(
    "/{session_id}/dialogue", dependencies=[Depends(worker_auth)], include_in_schema=False
)
async def worker_dialogue(session_id: str, payload: WorkerDialogue, request: Request):
    from src.adapters.llm.provider import (
        LLMProviderUnavailableError,
        LLMRequestError,
        StructuredOutputError,
    )
    from src.application.voice_dialogue import VoiceDialogue, VoiceGroundingError

    service = control(request)
    if not hasattr(service, "dialogue"):
        service.dialogue = VoiceDialogue(service)
    async def configured_turn():
        dialogue = service.dialogue
        owned_client = None
        # Operator allowlist only: retain the same journal, fencing, locks and
        # HTTP pool; configuration never comes from the browser request body.
        if os.getenv("VEFIN_VOICE_AUTH_MODE") == "local":
            from apps.voice_worker.quality import TestTrace
            trace = TestTrace(session_id)
            profile = trace.node_profile()
            if profile and profile.get("llm_selected"):
                from src.adapters.voice_candidate_profile import candidate_node
                from src.adapters.voice_knowledge import configured_knowledge
                client = getattr(service.dialogue.model, "client", None)
                if client is None:
                    raise LLMRequestError("Voice candidate client is unavailable")
                if profile.get('llm_trust_env') is False:
                    from src.adapters.voice_candidate_http import create_client
                    owned_client = create_client(profile)
                    client = owned_client
                model = candidate_node(profile, "llm", client=client,
                    llm_id=profile["llm_selected"],
                    observer=lambda row: trace.event("candidate_llm", observation=row))
                dialogue = VoiceDialogue(service, model, structured_constraints=True,
                    instruction_revision=profile.get("instruction_revision"),
                    history_seed=trace.restored_context(),
                    application_concepts=profile.get("application_concepts", False),
                    communication_revision=profile.get("communication_revision"),
                    knowledge_port=configured_knowledge(profile),
                    skill_config=profile.get("communication_skill"),
                    raw_observer=lambda row: trace.event("candidate_llm_reply", observation=row))
                dialogue.locks = service.dialogue.locks
        try:
            return await dialogue.turn(session_id, payload)
        finally:
            if owned_client is not None:
                await owned_client.aclose()
    task = asyncio.create_task(configured_turn())
    try:
        while not task.done():
            if await request.is_disconnected():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                fail("VOICE_RESPONSE_CANCELLED", "旧回应已取消，原始对话记录保留。", 409)
            await asyncio.sleep(0.05)
        return await task
    except TimeoutError:
        fail("VOICE_RESPONSE_TIMEOUT", "回答生成超时，原始对话已记录，请稍后继续。", 503)
    except VoiceGroundingError:
        fail("VOICE_GROUNDING_FAILED", "答复依据校验未通过，原始对话已记录，本轮答复未播报。", 502)
    except (LLMProviderUnavailableError, LLMRequestError, StructuredOutputError, ValueError):
        fail(
            "VOICE_RESPONSE_UNAVAILABLE", "回应服务暂不可用，原始对话已记录，未执行研究操作。", 503
        )
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
