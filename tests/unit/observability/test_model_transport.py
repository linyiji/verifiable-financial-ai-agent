import asyncio
import json
from types import SimpleNamespace

import httpcore
import httpx
import pytest
from pydantic import BaseModel

from src.adapters.llm import LLMMessage, LLMProviderUnavailableError, TeamoRouterClient
from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.mimo import MimoClient
from src.infrastructure.config.settings import LLMSettings
from src.observability.model_transport import TransportObservation
from src.observability.performance import Recorder, configure, span


class Answer(BaseModel):
    value: str


@pytest.fixture
def recorder(monkeypatch):
    # Never inherit workstation egress. Every actual socket test is loopback.
    monkeypatch.setattr(httpx._client, "get_environment_proxies", lambda: {})
    value = Recorder(forbidden_values=["SECRET-CANARY", "PROMPT-CANARY", "BODY-CANARY"])
    configure(value)
    yield value
    configure(None)


def provider(kind, url, client=None):
    model = "mimo-v2.5" if kind == "mimo" else "gpt-5.6-sol"
    p = (MimoClient if kind == "mimo" else TeamoRouterClient)(
        LLMSettings(
            provider=kind,
            api_key="SECRET-CANARY",
            base_url=url,
            primary_model=model,
            fallback_model=model,
        ),
        client=client,
        execution_policy=ProviderExecutionPolicyV1(
            read_timeout_seconds=0.08,
            per_attempt_deadline_seconds=2,
            overall_workload_deadline_seconds=2,
            max_attempts=1,
            bounded_backoff_seconds=(),
        ),
    )
    p.route_ids = {model: "mimo-direct" if kind == "mimo" else "teamorouter-sol"}
    p.task_profile = "peer_analysis"
    return p


async def invoke(p):
    return await p.complete_structured(
        messages=[LLMMessage(role="user", content="PROMPT-CANARY")],
        response_model=Answer,
        schema_name="test",
        workload_type="RESEARCH_AGENT_EXECUTION",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["mimo", "teamorouter"])
@pytest.mark.parametrize(
    "scenario", ["success", "body_timeout", "header_timeout", "disconnect", "incomplete"]
)
async def test_real_loopback_stages_and_owned_client(recorder, kind, scenario):
    handlers = set()

    async def handle(reader, writer):
        task = asyncio.current_task()
        handlers.add(task)
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            length = next(
                int(line.split(b":", 1)[1])
                for line in headers.split(b"\r\n")
                if line.lower().startswith(b"content-length:")
            )
            await reader.readexactly(length)
            if scenario in {"body_timeout", "incomplete"}:
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n{")
                await writer.drain()
            elif scenario == "success":
                body = json.dumps(
                    {
                        "model": "mimo-v2.5" if kind == "mimo" else "gpt-5.6-sol",
                        "choices": [{"message": {"content": '{"value":"BODY-CANARY"}'}}],
                    }
                ).encode()
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Length: "
                    + str(len(body)).encode()
                    + b"\r\n\r\n"
                    + body
                )
                await writer.drain()
            if scenario.endswith("timeout"):
                await reader.read()  # released when timed-out client closes
        finally:
            writer.close()
            await writer.wait_closed()
            handlers.discard(task)

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        p = provider(kind, f"http://127.0.0.1:{port}/v1")
        if scenario == "success":
            assert (await invoke(p)).output.value == "BODY-CANARY"
        else:
            with pytest.raises(LLMProviderUnavailableError):
                await invoke(p)
    finally:
        server.close()
        await server.wait_closed()
        if handlers:
            await asyncio.gather(*list(handlers))
    record = next(r for r in recorder.records if r["operation"] == "model.http")
    assert record["effective_proxy_route"] == "DIRECT"
    assert record["connection_established"] == "YES" and record["request_sent"] == "YES"
    assert record["client_closed"] is True
    assert record["client_ownership"] == "ATTEMPT"
    assert record["logical_call_id"] and record["attempt_id"]
    assert record["client_created_at"] != "UNKNOWN"
    assert record["attempt_completed_at"] and record["duration_ms"] >= 0
    assert record["provider"] == kind and record["httpx_version"] == httpx.__version__
    assert record["task_profile"] == "peer_analysis"
    if scenario in {"body_timeout", "incomplete", "success"}:
        assert record["response_headers_received"] == "YES" and record["http_status"] == 200
        assert record["http_version"] == "HTTP/1.1"
        assert record["response_body_reading"] == "YES"
    else:
        assert record["response_headers_received"] == "UNKNOWN" and "http_status" not in record
    if scenario == "success":
        assert record["response_complete"] == "YES"
    else:
        assert record["response_complete"] == "UNKNOWN"
        expected = "ReadTimeout" if scenario.endswith("timeout") else "RemoteProtocolError"
        assert record["transport_exception_class"] == "httpx." + expected
        assert "httpcore." + expected in record["transport_exception_chain"]
    serialized = json.dumps(recorder.snapshot())
    assert not any(
        s in serialized for s in ["SECRET-CANARY", "PROMPT-CANARY", "BODY-CANARY", "Authorization"]
    )


@pytest.mark.asyncio
async def test_system_proxy_selection_without_network(recorder, monkeypatch):
    import httpx._utils

    monkeypatch.setattr(
        httpx._utils, "getproxies", lambda: {"https": "http://user:SECRET-CANARY@127.0.0.1:7890"}
    )
    monkeypatch.setattr(
        httpx._client, "get_environment_proxies", httpx._utils.get_environment_proxies
    )
    for host in ["api.teamorouter.com", "api.xiaomimimo.com"]:
        with span("model.http") as timing:
            o = TransportObservation(
                timing, owned=True, provider="mimo", model="mimo-v2.5", route="mimo-direct"
            )
            async with httpx.AsyncClient() as client:
                o.bind(client, "https://" + host)
            o.finish(None)
    assert all(
        r["effective_proxy_route"] == "PROXY"
        and r["proxy_host"] == "127.0.0.1"
        and r["proxy_port"] == 7890
        and r["trust_env"]
        for r in recorder.records
    )
    assert "SECRET-CANARY" not in json.dumps(recorder.snapshot())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [httpx.ReadError, httpx.ConnectError, httpx.WriteTimeout, httpx.PoolTimeout]
)
async def test_generic_failure_class_caller_ownership_and_redaction(recorder, error):
    async def handler(request):
        raise error("SECRET-CANARY " + str(request.url)) from httpcore.ReadError("PROMPT-CANARY")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        p = provider("mimo", "https://no-network.invalid/v1", client)
        for _ in range(2):
            with pytest.raises(LLMProviderUnavailableError):
                await invoke(p)
        records = [r for r in recorder.records if r["operation"] == "model.http"]
        assert records[0]["transport_client_id"] == records[1]["transport_client_id"]
        assert all(
            r["client_closed"] is False and r["client_created_at"] == "UNKNOWN" for r in records
        )
        assert all(r["transport_exception_class"] == "httpx." + error.__name__ for r in records)
        assert all(r["effective_proxy_route"] == "UNKNOWN" for r in records)
    assert not any(
        s in json.dumps(recorder.snapshot())
        for s in ["SECRET-CANARY", "PROMPT-CANARY", "no-network.invalid"]
    )


@pytest.mark.asyncio
async def test_connect_response_not_confused_with_provider_headers(recorder):
    with span("model.http") as timing:
        o = TransportObservation(
            timing, owned=False, provider="mimo", model="mimo-v2.5", route=None
        )
        await o.trace(
            "http11.send_request_headers.started", {"request": SimpleNamespace(method=b"CONNECT")}
        )
        await o.trace(
            "http11.receive_response_headers.complete",
            {"return_value": (b"HTTP/1.1", 200, b"OK", [(b"Authorization", b"SECRET-CANARY")])},
        )
        await o.trace("malformed.SECRET-CANARY", {"exception": ValueError("SECRET-CANARY")})
        o.finish(None)
    assert recorder.records[0]["response_headers_received"] == "UNKNOWN"
    assert "http_status" not in recorder.records[0]


@pytest.mark.asyncio
async def test_concurrent_attempt_count_and_context_reset(recorder):
    entered = 0
    ready = asyncio.Event()

    async def handler(request):
        nonlocal entered
        entered += 1
        if entered == 2:
            ready.set()
        await ready.wait()
        raise httpx.ReadError("SECRET-CANARY")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await asyncio.gather(
            invoke(provider("mimo", "https://offline.invalid", client)),
            invoke(provider("teamorouter", "https://offline.invalid", client)),
            return_exceptions=True,
        )
    assert all(isinstance(exc, LLMProviderUnavailableError) for exc in result)
    records = [r for r in recorder.records if r["operation"] == "model.http"]
    assert sorted(r["concurrent_http_attempts"] for r in records) == [1, 2]
    assert len({r["logical_call_id"] for r in records}) == 2
    from src.observability.model_transport import _ACTIVE

    assert _ACTIVE == 0


@pytest.mark.asyncio
async def test_disabled_instrumentation_preserves_wire_and_result(recorder):
    payloads = []
    traces = []

    async def handler(request):
        payloads.append(request.content)
        traces.append("trace" in request.extensions)
        return httpx.Response(
            200,
            json={"model": "mimo-v2.5", "choices": [{"message": {"content": '{"value":"ok"}'}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        p = provider("mimo", "https://offline.invalid", client)
        before = await invoke(p)
        configure(None)
        after = await invoke(p)
    assert before.output == after.output
    assert payloads[0] == payloads[1]
    assert traces == [True, False]


def test_untrusted_exception_subclass_name_not_retained(recorder):
    exception = type("SECRET-CANARY", (httpx.ReadError,), {})
    with span("model.http") as timing:
        o = TransportObservation(
            timing, owned=False, provider="mimo", model="mimo-v2.5", route=None
        )
        o.finish(exception("PROMPT-CANARY"))
    assert recorder.records[0]["transport_exception_class"] == "UNKNOWN"
    assert "SECRET-CANARY" not in json.dumps(recorder.snapshot())
