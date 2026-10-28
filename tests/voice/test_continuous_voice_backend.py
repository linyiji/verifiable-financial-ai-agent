"""Control-plane tests only. These doubles are never claimed as real audio PASS."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from contracts.api.voice_session import WorkerReceipt
from src.application.errors import ApplicationError
from src.application.service import ResearchApplicationService
from src.application.voice_authority import AuthorityReceipt, read_receipt
from src.application.voice_sessions import VoiceSessions


class MediaDouble:
    configured = True
    public_url = "ws://test-only"

    def __init__(self):
        self.closed = []
        self.present = set()
        self.retired = []

    async def delete_room(self, room):
        self.closed.append(room)
        self.present.discard(room)

    async def room_names(self):
        return set(self.present)

    async def retire_previous_agents(self, room, current_identity):
        self.retired.append((room, current_identity))

    async def healthy(self):
        return True

    def token(self, room, identity, expiry):
        self.present.add(room)
        return "UNIT_TEST_ONLY"


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setenv("VEFIN_VOICE_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/voice.db")
    monkeypatch.setenv("VEFIN_WEB_GOLDEN_FLOW_SOURCE_MATRIX", str(tmp_path / "absent"))
    monkeypatch.setenv("VEFIN_VOICE_AUTH_MODE", "local")
    monkeypatch.setenv("VEFIN_VOICE_LOCAL_TOKENS", json.dumps({"alice": "a" * 32, "bob": "b" * 32}))
    monkeypatch.setenv("VEFIN_VOICE_LOCAL_TASK_GRANTS", "{}")
    monkeypatch.setenv("VEFIN_VOICE_WORKER_SECRET", "w" * 32)
    application = ResearchApplicationService()
    app = create_app(service=application)
    with TestClient(app) as client:
        app.state.voice_sessions.media = MediaDouble()
        yield client, app, application


A = {"Authorization": "Bearer " + "a" * 32}
B = {"Authorization": "Bearer " + "b" * 32}


def create(client, key="voice", user=A):
    result = client.post("/api/voice-sessions", headers={**user, "Idempotency-Key": key}, json={})
    assert result.status_code == 201, result.text
    return result.json()


def test_provider_observation_blocks_conversation_before_session_creation(api, monkeypatch, tmp_path):
    client, _, _ = api
    status = tmp_path / "provider-status.json"
    status.write_text(json.dumps({"provider": "quickrouter", "state": "unavailable",
        "reason": "UPSTREAM_CONNECT_TIMEOUT", "checked_at": "2026-10-24T00:00:00Z",
        "private_field": "DO_NOT_EXPOSE"}))
    monkeypatch.setenv("VEFIN_VOICE_PROVIDER_STATUS_FILE", str(status))
    assert client.get("/api/voice-sessions/availability").status_code == 401
    response = client.get("/api/voice-sessions/availability", headers=A)
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    assert response.json()["provider"] == "quickrouter" and response.json()["blocked"]
    assert "DO_NOT_EXPOSE" not in response.text
    blocked = client.post("/api/voice-sessions", headers={**A, "Idempotency-Key": "blocked"},
        json={"interaction_mode": "conversation", "language": "yue-HK"})
    assert blocked.status_code == 503 and blocked.json()["error"]["code"] == "VOICE_PROVIDER_UNAVAILABLE"
    assert client.get("/internal/voice/sessions", headers={"Authorization": "Bearer " + "w" * 32}).json() == []
    # Upload/preview does not depend on conversational TTS availability.
    assert create(client, key="preview")["interaction_mode"] == "preview"


def test_provider_unavailable_blocks_restored_conversation_credentials(api, monkeypatch, tmp_path):
    client, _, _ = api
    response = client.post("/api/voice-sessions", headers={**A, "Idempotency-Key": "existing"},
        json={"interaction_mode": "conversation"})
    assert response.status_code == 201
    sid = response.json()["id"]
    monkeypatch.setenv("VEFIN_VOICE_PROVIDER_STATUS_FILE", str(tmp_path / "missing-status.json"))
    response = client.post(f"/api/voice-sessions/{sid}/credentials", headers=A)
    assert response.status_code == 503 and response.json()["error"]["code"] == "VOICE_PROVIDER_UNAVAILABLE"
    # Ownership remains checked before revealing supplier status on this endpoint.
    assert client.post(f"/api/voice-sessions/{sid}/credentials", headers=B).status_code == 404
    assert client.post(f"/api/voice-sessions/{sid}/end", headers=A).status_code == 200


def task_and_chat(client, key):
    client.post("/api/objects", json={
        "symbol": "NVDA", "company_name": "NVIDIA Corporation", "exchange": "NASDAQ",
    })
    task = client.post("/api/research-tasks", headers={"Idempotency-Key": key}, json={
        "object_id": "OBJ-NVDA", "user_input": "分析 NVIDIA",
    }).json()
    chat = client.post("/api/research-chat/sessions", json={"research_task_id": task["id"]}).json()
    return task, chat


def test_entry_idempotency_and_no_research_side_effect(api):
    client, app, application = api
    first = create(client)
    again = create(client)
    assert first == again
    assert first["task_id"] is None and first["chat_session_id"] is None
    assert first["status"] == "connecting" and first["remaining_seconds"] == 900
    assert (datetime.fromisoformat(first["warning_at"]) -
            datetime.fromisoformat(first["started_at"])) == timedelta(minutes=13)
    assert client.post("/api/voice-sessions", headers={**A, "Idempotency-Key": "duration-override"},
                       json={"duration_seconds": 3600}).status_code == 422
    assert client.post(f"/api/voice-sessions/{first['id']}/extend", headers=A).status_code == 404
    assert create(client, user=B)["id"] != first["id"]
    assert client.get(f"/api/voice-sessions/{first['id']}", headers=B).status_code == 404
    assert client.post(
        f"/api/voice-sessions/{first['id']}/credentials", headers=B,
    ).status_code == 404
    assert client.post(f"/api/voice-sessions/{first['id']}/end", headers=B).status_code == 404
    assert client.get(f"/api/voice-sessions/{first['id']}/events", headers=B).status_code == 404
    assert client.get(f"/api/voice-sessions/{first['id']}").status_code == 401
    assert client.get("/internal/voice/sessions").status_code == 401
    assert not (awaitable := application.repository._runs)
    assert awaitable == {}
    assert getattr(app.state, "research_task_service", None) is None


def test_default_and_production_auth_fail_closed(api, monkeypatch):
    client, _, _ = api
    monkeypatch.delenv("VEFIN_VOICE_AUTH_MODE")
    assert client.post("/api/voice-sessions", json={}, headers={
        **A, "Idempotency-Key": "closed",
    }).json()["error"]["code"] == "VOICE_AUTH_PRODUCTION_BLOCKED"
    monkeypatch.setenv("VEFIN_VOICE_AUTH_MODE", "production")
    assert client.post("/api/voice-sessions", json={}, headers={
        **A, "Idempotency-Key": "closed",
    }).status_code == 503


def test_local_qa_cookie_voice_entry_preserves_401_and_owner_boundary(api, monkeypatch):
    client, _, _ = api
    origin = "http://127.0.0.1:15364"
    monkeypatch.setenv("VEFIN_LOCAL_QA_SESSION_ENABLED", "1")
    monkeypatch.setenv("VEFIN_RESEARCH_AUTH_MODE", "local")
    monkeypatch.setenv("VEFIN_LOCAL_QA_ORIGIN", origin)
    path = "/api/voice-sessions"
    assert client.post(path, headers={"Idempotency-Key": "anonymous"}, json={}).status_code == 401
    assert client.post("/api/local-qa/session", headers={"Origin": origin},
                       json={"user": "alice"}).status_code == 200
    created = client.post(path, headers={"Idempotency-Key": "cookie"}, json={})
    assert created.status_code == 201
    voice_id = created.json()["id"]
    assert client.get(f"{path}/{voice_id}").status_code == 200
    assert client.get(f"{path}/{voice_id}", headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.post("/api/local-qa/session", headers={"Origin": origin},
                       json={"user": "bob"}).status_code == 200
    assert client.get(f"{path}/{voice_id}").status_code == 404
    assert client.post("/api/local-qa/session", json={"user": "alice"}).status_code == 403


def test_disabled_voice_does_not_require_a_separate_database(monkeypatch):
    for name in ["VEFIN_VOICE_AUTH_MODE", "VEFIN_VOICE_WORKER_SECRET",
                 "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VEFIN_VOICE_DATABASE_URL", "postgresql+asyncpg://unreachable/voice")
    with TestClient(create_app(service=ResearchApplicationService())) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health/voice").json()["control"] == "disabled"
        assert client.post("/api/voice-sessions", json={}, headers={
            "Idempotency-Key": "disabled",
        }).status_code == 503


@pytest.mark.skip(reason="Legacy research task/chat product bridge is not synchronized in the voice publication")
def test_binding_authorization_mismatch_retries_and_end_independence(api, monkeypatch):
    client, _, application = api
    voice = create(client)
    path = f"/api/voice-sessions/{voice['id']}"
    task, chat = task_and_chat(client, "task-1")
    other, other_chat = task_and_chat(client, "task-2")
    binding = {"task_id": task["id"], "chat_session_id": chat["id"]}
    assert client.put(path + "/binding", headers=A, json=binding).status_code == 403
    monkeypatch.setenv("VEFIN_VOICE_LOCAL_TASK_GRANTS", json.dumps({
        "alice": [task["id"], other["id"]],
    }))
    assert client.put(path + "/binding", headers=B, json=binding).status_code == 403
    mismatch = {**binding, "chat_session_id": other_chat["id"]}
    assert client.put(path + "/binding", headers=A, json=mismatch).status_code == 409
    first = client.put(path + "/binding", headers=A, json=binding).json()
    assert client.put(path + "/binding", headers=A, json=binding).json() == first
    assert client.put(path + "/binding", headers=A, json={
        "task_id": other["id"],
    }).status_code == 409
    creds = client.post(path + "/credentials", headers=A).json()
    repeated = client.post(path + "/credentials", headers=A).json()
    assert creds["session"]["id"] == repeated["session"]["id"] == voice["id"]
    assert (creds["session"]["expires_at"] == repeated["session"]["expires_at"]
            == voice["expires_at"])
    assert (creds["session"]["warning_at"] == repeated["session"]["warning_at"]
            == voice["warning_at"])
    # Hanging up never calls runtime cancellation and doesn't append the original question.
    client.post(path + "/end", headers=A)
    assert client.post(path + "/end", headers=A).status_code == 200
    assert client.post(path + "/credentials", headers=A).status_code == 410
    assert client.get(f"/api/research-tasks/{task['id']}", headers=A).json() == task
    assert client.get(f"/api/research-chat/{chat['id']}", headers=A).json()["messages"] == []
    assert application.repository._runs == {}


async def allowed(user, task):
    return None


@pytest.fixture
async def control(tmp_path):
    now = [datetime(2026, 9, 26, 0, 0, tzinfo=UTC)]
    app = SimpleNamespace(state=SimpleNamespace(voice_task_authorizer=allowed))
    media = MediaDouble()
    service = VoiceSessions(app, f"sqlite+aiosqlite:///{tmp_path}/control.db", media,
                            clock=lambda: now[0])
    await service.start(background=False)
    yield service, now, media, app
    await service.close()


async def test_13_15_fixed_deadline_and_restart_cleanup(control):
    service, now, media, _ = control
    session = await service.create("alice", "deadline")
    media.present.add(session.room)
    now[0] += timedelta(minutes=12, seconds=59)
    await service.sweep()
    assert not (await service.events(session.id, "alice", 0, 100))["events"][-1].reason
    now[0] += timedelta(seconds=1)
    await service.sweep()
    await service.sweep()
    events = (await service.events(session.id, "alice", 0, 100))["events"]
    assert sum(e.kind == "duration_warning" for e in events) == 1
    assert events[-1].text == "本次语音通话还剩约2分钟，研究任务不会因挂断而停止。"
    now[0] += timedelta(minutes=2)
    await service.sweep()
    assert (await service.get(session.id, "alice")).status == "ended"
    assert media.closed == [session.room]
    with pytest.raises(ApplicationError, match="通话已到"):
        await service.claim(session.id)
    with pytest.raises(ApplicationError):
        await service.credentials(session.id, "alice")
    # Startup catches a terminal room resurrected by a server-refreshed RTC token.
    media.present.add(session.room)
    await service.close()
    recovered = VoiceSessions(service.app, str(service.engine.url), media, clock=lambda: now[0])
    await recovered.start(background=False)
    assert (await recovered.get(session.id, "alice")).expires_at == session.expires_at
    assert media.closed == [session.room, session.room]
    await recovered.close()


async def test_existing_long_session_keeps_persisted_deadline_and_legacy_warning(control):
    service, now, media, _ = control
    session = await service.create("alice", "existing-before-policy-change")
    async with service.transaction() as db:
        row = await service.row(db, session.id)
        row.expires_at = row.started_at + timedelta(minutes=60)
    original = await service.get(session.id, "alice")
    assert original.expires_at == session.started_at + timedelta(minutes=60)
    assert original.warning_at == session.started_at + timedelta(minutes=55)
    now[0] += timedelta(minutes=13)
    await service.sweep()
    assert not any(e.kind == "duration_warning" for e in
                   (await service.events(session.id, "alice", 0, 100))["events"])
    now[0] += timedelta(minutes=42)
    await service.sweep()
    assert sum(e.kind == "duration_warning" for e in
               (await service.events(session.id, "alice", 0, 100))["events"]) == 1
    assert (await service.credentials(session.id, "alice"))["session"].expires_at == original.expires_at
    new = await service.create("alice", "created-after-policy-change")
    assert new.expires_at == now[0] + timedelta(minutes=15)
    now[0] += timedelta(minutes=5)
    await service.sweep()
    assert (await service.get(session.id, "alice")).ended_reason == "expired"
    assert (await service.get(new.id, "alice")).status != "ended"


async def test_single_scheduler_restart_fencing_and_event_recovery(control):
    service, now, _, _ = control
    session = await service.create("alice", "lease")
    first = await service.claim(session.id)
    with pytest.raises(ApplicationError) as error:
        await service.claim(session.id)
    assert error.value.code == "VOICE_WORKER_BUSY"
    now[0] += timedelta(seconds=16)
    replacement = await service.claim(session.id)
    assert replacement["lease_id"] != first["lease_id"]
    assert (await service.get(session.id, "alice")).expires_at == session.expires_at
    assert (await service.get(session.id, "alice")).warning_at == session.warning_at
    with pytest.raises(ApplicationError) as error:
        await service.receipt(session.id, WorkerReceipt(
            lease_id=first["lease_id"], kind="transcript", text="stale", receipt_id="stale",
        ))
    assert error.value.code == "VOICE_LEASE_LOST"
    payload = WorkerReceipt(lease_id=replacement["lease_id"], kind="transcript",
                            text="real-ASR-is-not-tested-here", receipt_id="repeat")
    await service.receipt(session.id, payload)
    await service.receipt(session.id, payload)
    events = await service.events(session.id, "alice", 0, 2)
    assert events["has_more"] and events["next_cursor"] == 2
    tail = await service.events(session.id, "alice", 2, 100)
    assert sum(e.kind == "transcript" for e in tail["events"]) == 1
    assert tail["next_cursor"] == tail["session"].event_cursor


async def test_duplicate_out_of_order_superseded_and_expired_events(control):
    service, now, _, _ = control
    session = await service.create("alice", "events")
    claim = await service.claim(session.id)
    lease = claim["lease_id"]
    async with service.transaction() as db:
        row = await service.row(db, session.id)
        row.task_id = "RT-1"
    old = AuthorityReceipt("RT-1", "RUN-1", "v1", now[0], "progress", "in progress", "e1")
    await service.accept_source(session.id, lease, old)
    await service.accept_source(session.id, lease, old)
    now[0] += timedelta(seconds=1)
    blocked = AuthorityReceipt("RT-1", "RUN-1", "v2", now[0], "blocked", "blocked", "e2")
    await service.accept_source(session.id, lease, blocked)
    await service.accept_source(session.id, lease, old)
    wrong = AuthorityReceipt("other-task", None, "v3", now[0], "progress", "wrong", "e3")
    await service.accept_source(session.id, lease, wrong)
    events = (await service.events(session.id, "alice", 0, 100))["events"]
    announcements = [e for e in events if e.kind == "announcement"]
    assert len(announcements) == 2
    assert not (await service.consume(session.id, lease, "authority:v1"))["speak"]
    assert (await service.consume(session.id, lease, "authority:v2"))["speak"]
    assert not (await service.consume(session.id, lease, "authority:v2"))["speak"]
    now[0] += timedelta(seconds=121)
    lease = (await service.claim(session.id))["lease_id"]
    await service.accept_source(session.id, lease, AuthorityReceipt(
        "RT-1", None, "v4", now[0], "progress", "new", "e4",
    ))
    now[0] += timedelta(seconds=121)
    lease = (await service.claim(session.id))["lease_id"]
    assert not (await service.consume(session.id, lease, "authority:v4"))["speak"]


async def test_concurrent_creation_is_idempotent(control):
    service, _, _, _ = control
    created = await asyncio.gather(*(service.create("alice", "same") for _ in range(8)))
    assert len({item.id for item in created}) == 1


async def test_equal_timestamp_order(control):
    service, now, _, _ = control
    session = await service.create("alice", "equal-timestamps")
    lease = (await service.claim(session.id))["lease_id"]
    async with service.transaction() as db:
        row = await service.row(db, session.id)
        row.task_id = "RT-1"
    current = AuthorityReceipt("RT-1", "RUN-1", "latest", now[0], "blocked", "blocked", "z2")
    late = AuthorityReceipt("RT-1", "RUN-1", "old", now[0], "progress", "old", "z1")
    await service.accept_source(session.id, lease, current)
    await service.accept_source(session.id, lease, late)
    assert (await service.consume(session.id, lease, "authority:latest"))["speak"]
    assert not (await service.consume(session.id, lease, "authority:old"))["speak"]


async def test_unknown_and_blocked_run_cannot_announce_completion():
    async def task(_):
        return SimpleNamespace(id="RT", created_at=datetime.now(UTC), status="Running")

    async def run(_):
        return SimpleNamespace(run=SimpleNamespace(id="RUN"))

    async def status(_):
        return SimpleNamespace(execution_status=SimpleNamespace(value="Completed"), updated_at=None)

    async def timeline(_):
        return SimpleNamespace(events=[SimpleNamespace(
            id="blocked", created_at=datetime.now(UTC),
            event_type=SimpleNamespace(value="blocked"), message="Execution mapping unavailable",
        )])

    app = SimpleNamespace(state=SimpleNamespace(
        research_task_service=SimpleNamespace(get_research_task=task),
        research_start_service=SimpleNamespace(get_active_run=run),
        run_lifecycle_projection=SimpleNamespace(get_status=status),
        research_execution_observability=SimpleNamespace(timeline=timeline),
    ))
    with pytest.raises(ApplicationError) as caught:
        await read_receipt(app, "RT")
    assert caught.value.code == "VOICE_BUSINESS_PORT_UNAVAILABLE"


@pytest.mark.skip(reason="Legacy research task/chat product bridge is not synchronized in the voice publication")
def test_local_exact_grants_file_reload_and_revocation(api, monkeypatch, tmp_path):
    client, _, _ = api
    task, chat = task_and_chat(client, "file-grant")
    voice = create(client, "file-grant-voice")
    route = f"/api/voice-sessions/{voice['id']}"
    grants = tmp_path / "grants.json"
    grants.write_text('{}')
    monkeypatch.setenv("VEFIN_VOICE_LOCAL_TASK_GRANTS_FILE", str(grants))
    binding = {"task_id": task['id'], "chat_session_id": chat['id']}
    assert client.put(route + '/binding', headers=A, json=binding).status_code == 403
    grants.write_text(json.dumps({'alice': [task['id']]}))
    assert client.put(route + '/binding', headers=A, json=binding).status_code == 200
    assert client.post(route + '/credentials', headers=A).status_code == 200
    grants.write_text('{}')
    assert client.post(route + '/credentials', headers=A).status_code == 403
    assert client.post(route + '/end', headers=A).status_code == 200
