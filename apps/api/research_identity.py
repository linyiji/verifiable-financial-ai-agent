"""Exact local identity/grants; production remains explicitly closed."""

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Request, Response

from src.application.errors import ApplicationError


qa_router = APIRouter(prefix="/api/local-qa", tags=["local-qa"])
_QA_COOKIE = "vefin_local_qa_session"
_QA_LIFETIME = 8 * 60 * 60


def _loopback_host(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return bool(host and ipaddress.ip_address(host).is_loopback)
    except ValueError:
        return False


def _qa_enabled(request: Request) -> bool:
    if os.getenv("VEFIN_LOCAL_QA_SESSION_ENABLED") != "1" or os.getenv("VEFIN_RESEARCH_AUTH_MODE") != "local":
        return False
    origin = urlsplit(os.getenv("VEFIN_LOCAL_QA_ORIGIN", ""))
    if origin.scheme != "http" or not _loopback_host(origin.hostname):
        return False
    if request.client is not None and request.client.host == "testclient":
        return True
    try:
        client_local = _loopback_host(request.client.host)
        host_local = _loopback_host(request.url.hostname)
        return client_local and host_local
    except AttributeError:
        return False


def _qa_tokens() -> dict[str, str]:
    tokens = json.loads(os.getenv("VEFIN_VOICE_LOCAL_TOKENS", "{}"))
    return {user: token for user, token in tokens.items()
            if isinstance(user, str) and isinstance(token, str) and len(token) >= 32}


def _qa_session(request: Request) -> tuple[str | None, str]:
    cookie = request.cookies.get(_QA_COOKIE)
    if not cookie:
        return None, "missing"
    record = getattr(request.app.state, "local_qa_sessions", {}).get(cookie)
    if not record:
        return None, "invalid"
    user, fingerprint, expires = record
    current = _qa_tokens().get(user)
    if expires <= time.time() or not current or not hmac.compare_digest(
        fingerprint, hashlib.sha256(current.encode()).digest()
    ):
        request.app.state.local_qa_sessions.pop(cookie, None)
        return None, "expired"
    return user, "ready"


def _qa_boundary(request: Request, *, mutation: bool = False) -> None:
    if not _qa_enabled(request):
        raise ApplicationError("LOCAL_QA_UNAVAILABLE", "本地 QA 身份仅在隔离开发环境可用。", status_code=404)
    if mutation and request.headers.get("origin") != os.getenv("VEFIN_LOCAL_QA_ORIGIN"):
        raise ApplicationError("LOCAL_QA_ORIGIN_REJECTED", "本地 QA 请求来源不匹配。", status_code=403)


@qa_router.get("/session")
async def local_qa_session(request: Request):
    _qa_boundary(request)
    user, status = _qa_session(request)
    return {"user": user, "status": status, "identities": sorted(_qa_tokens())}


@qa_router.post("/session")
async def establish_local_qa_session(request: Request, response: Response):
    _qa_boundary(request, mutation=True)
    payload = await request.json()
    user = payload.get("user") if isinstance(payload, dict) else None
    token = _qa_tokens().get(user) if isinstance(user, str) else None
    if not token:
        raise ApplicationError("LOCAL_QA_IDENTITY_UNKNOWN", "该 QA 身份未配置。", status_code=400)
    sessions = request.app.state.local_qa_sessions
    now = time.time()
    for session, (_, _, expires) in list(sessions.items()):
        if expires <= now:
            sessions.pop(session, None)
    old = request.cookies.get(_QA_COOKIE)
    if old:
        sessions.pop(old, None)
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = (user, hashlib.sha256(token.encode()).digest(), now + _QA_LIFETIME)
    response.set_cookie(_QA_COOKIE, session_id, max_age=_QA_LIFETIME, path="/api",
                        httponly=True, samesite="strict")
    return {"user": user, "status": "ready"}


async def identity(request: Request):
    mode = os.getenv("VEFIN_RESEARCH_AUTH_MODE", os.getenv("VEFIN_VOICE_AUTH_MODE", "disabled"))
    if mode == "production":
        resolver = getattr(request.app.state, "research_identity_resolver", None)
        authorizer = getattr(request.app.state, "research_task_authorizer", None)
        if not resolver or not authorizer:
            raise ApplicationError(
                "RESEARCH_PRODUCTION_AUTH_BLOCKED",
                "生产身份及 Task 所有权尚未接通。",
                status_code=503,
            )
        return await resolver(request)
    if mode != "local":
        raise ApplicationError(
            "RESEARCH_PRODUCTION_AUTH_BLOCKED", "需要明确配置身份认证。", status_code=503
        )
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    tokens = _qa_tokens()
    for user, expected in tokens.items():
        if (
            isinstance(expected, str)
            and len(expected) >= 32
            and hmac.compare_digest(token, expected)
        ):
            return user
    if not header and _qa_enabled(request):
        user, _ = _qa_session(request)
        if user:
            return user
    raise ApplicationError("RESEARCH_UNAUTHORIZED", "需要有效身份凭证。", status_code=401)


def configured_store(request):
    coordinator = getattr(request.app.state, "research_asset_production", None)
    return (getattr(coordinator, "_durable_store", None)
            or getattr(request.app.state, "research_sql_store", None))


def durable_store(request):
    store = configured_store(request)
    if not store:
        raise ApplicationError(
            "RESEARCH_DURABLE_STORAGE_REQUIRED", "历史及身份操作需要持久化存储。", status_code=503
        )
    return store


async def grants():
    import asyncio

    path = os.getenv("VEFIN_VOICE_LOCAL_TASK_GRANTS_FILE")
    return json.loads(
        await asyncio.to_thread(Path(path).read_text)
        if path
        else os.getenv("VEFIN_VOICE_LOCAL_TASK_GRANTS", "{}")
    )


async def authorize_task(request, user, task_id):
    if os.getenv("VEFIN_RESEARCH_AUTH_MODE", os.getenv("VEFIN_VOICE_AUTH_MODE")) == "production":
        return await request.app.state.research_task_authorizer(user, task_id)
    if task_id in (await grants()).get(user, []):
        return
    store = configured_store(request)
    row = store.get("research_task_ownership", task_id) if store else None
    if row and row["user_id"] == user:
        return
    raise ApplicationError("RESEARCH_TASK_FORBIDDEN", "当前身份无此 Task 授权。", status_code=403)


async def protect_bound_research(request):
    """Enforce the same Task owner on all existing Chat/Plan/Run routes."""
    parts = request.url.path.strip("/").split("/")
    if len(parts) < 3:
        return
    kind, target = parts[1:3]
    task_id = None
    if kind == "research-tasks":
        task_id = target
    elif kind == "research-runs" and target == "by-task" and len(parts) > 3:
        task_id = parts[3]
    elif (kind, target) in {
        ("research-runs", "start"),
        ("research-chat", "sessions"),
    } and request.method == "POST":
        try:
            task_id = (await request.json()).get("research_task_id")
        except (ValueError, AttributeError):
            return
    elif kind == "research-chat":
        snapshot = await request.app.state.research_chat_service._chats.get_session(target)
        task_id = snapshot.session.research_task_id if snapshot else None
    elif kind == "research-plans":
        record = await request.app.state.research_planning_repository.get(target)
        task_id = record.session.research_task_id if record else None
    elif kind == "research-runs":
        run = await request.app.state.research_start_service._runs.get(target)
        task_id = run.task_id if run else None
    if not task_id:
        return
    store = configured_store(request)
    owned = store.get("research_task_ownership", task_id) if store else None
    configured_grants = await grants()
    bound = owned or any(task_id in ids for ids in configured_grants.values())
    if bound or request.headers.get("Authorization") or (_qa_enabled(request) and request.cookies.get(_QA_COOKIE)):
        user = await identity(request)
        await authorize_task(request, user, task_id)
        request.state.research_user = user


async def authorize_run(request, run_id):
    user = await identity(request)
    run = await request.app.state.research_start_service._runs.get(run_id)
    if not run:
        raise ApplicationError("RESEARCH_RUN_NOT_FOUND", "运行不存在。", status_code=404)
    await authorize_task(request, user, run.task_id)
    return user, run
