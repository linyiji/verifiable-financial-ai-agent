"""Installed HTTPX/httpcore framing over synthetic in-memory network streams."""

import json
from unittest.mock import patch

from src.agentic.recovery import RecoveryStopped
from src.application import execution_profiles as profiles
from src.application.repository import initialize_binding
from tests.execution_profiles.fallback_fixture import configured_family
from tests.execution_profiles.test_bounded_terra_fallback import bound, request_scope
from tests.unit.observability.test_safe_transport_evidence import (
    Backend,
    Stream,
    adapter,
    local_client,
)


class ResearchStream(Stream):
    async def write(self, buffer, timeout=None):  # noqa: ASYNC109
        await super().write(buffer, timeout)
        if self.method == b"POST" and self.response:
            status = 400 if self.backend.failure == "400" else 200
            output = dict(
                summary="Synthetic result",
                key_findings=["Synthetic finding"],
                risks=[],
                limitations=[],
                requires_follow_up=False,
            )
            payload = (
                {"error": {"code": 400, "message": "SENTINEL_SECRET"}}
                if status == 400
                else {
                    "model": self.backend.wire[-1]["model"],
                    "choices": [{"message": {"content": json.dumps(output)}}],
                }
            )
            body = json.dumps(payload).encode()
            self.response = (
                f"HTTP/1.1 {status} OK\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body
            )


class ResearchBackend(Backend):
    async def connect_tcp(self, host, port, **kwargs):
        stream = ResearchStream(self)
        self.streams.append(stream)
        return stream


async def physical_fixture(tmp_path, kind, *, terra_failure=None, store=None):
    service, value, _, _ = await configured_family(tmp_path, kind, persist=False, store=store)
    task, _ = bound(value)
    agent = profiles.configured_agent(service, task, None)
    recovery = profiles.recovery_for(agent)
    for route, model in (
        ("teamorouter-sol", "gpt-5.6-sol"),
        ("teamorouter-luna", "gpt-5.6-luna"),
        ("teamorouter-terra", "gpt-5.6-terra"),
    ):
        recovery.clients[route] = adapter(model)
    agent._provider = recovery.clients["teamorouter-sol"]
    value.node_binding = None
    initialize_binding(value, service=service)
    task, profile = bound(value)
    ctx, _, request = request_scope(task)
    failures = iter(("read_timeout", terra_failure))
    clients, backends = [], []

    def factory(**kwargs):
        backend = ResearchBackend(next(failures))
        client = local_client("proxy", backend, **kwargs)
        clients.append(client)
        backends.append(backend)
        return client

    token = profiles.execution_profile_context.set((task.run_id, task.task_id, profile, {}))
    try:
        with patch("src.adapters.llm.teamorouter.httpx.AsyncClient", factory):
            try:
                response = await recovery.execute(ctx, agent._provider, **request)
                assert response.actual_model == "gpt-5.6-terra"
                assert terra_failure is None
            except RecoveryStopped:
                assert terra_failure == "400"
    finally:
        profiles.execution_profile_context.reset(token)
    assert all(c.is_closed for c in clients)
    assert [b.wire[0]["model"] for b in backends] == ["gpt-5.6-sol", "gpt-5.6-terra"]
    assert sum(b.posts for b in backends) == 2 and sum(b.connects for b in backends) == 2
    return await recovery.store.records()
