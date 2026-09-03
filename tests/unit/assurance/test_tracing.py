import pytest

from src.observability.langfuse_adapter import build_trace_adapter
from src.observability.noop import NoopTraceAdapter


class BrokenClient:
    def start_span(self, **kwargs: object) -> object:
        raise RuntimeError("trace backend unavailable")

    def create_event(self, **kwargs: object) -> object:
        raise RuntimeError("trace backend unavailable")


@pytest.mark.asyncio
async def test_no_credentials_returns_noop() -> None:
    adapter = build_trace_adapter()
    assert isinstance(adapter, NoopTraceAdapter)
    async with adapter.span("run", attributes={"run_id": "RUN-1"}):
        await adapter.event("task.started")


@pytest.mark.asyncio
async def test_langfuse_failure_is_fail_open() -> None:
    adapter = build_trace_adapter(BrokenClient())
    async with adapter.span("run", attributes={"run_id": "RUN-1"}):
        marker = "business execution continues"
    await adapter.event("task.completed")
    assert marker == "business execution continues"

