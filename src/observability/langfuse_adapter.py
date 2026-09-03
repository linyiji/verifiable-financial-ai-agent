from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from importlib import import_module
from typing import Any, Protocol

from src.domain.base import JsonObject
from src.infrastructure.config.settings import LangfuseSettings
from src.observability.noop import FailOpenTraceAdapter, NoopTraceAdapter
from src.observability.safety import sanitize_trace_attributes


class LangfuseClientBoundary(Protocol):
    def start_span(self, *, name: str, attributes: JsonObject) -> Any: ...

    def create_event(self, *, name: str, attributes: JsonObject) -> Any: ...


class LangfuseTraceAdapter:
    """Small SDK boundary; wrapped fail-open by `build_trace_adapter`."""

    def __init__(self, client: LangfuseClientBoundary):
        self._client = client

    @asynccontextmanager
    async def span(self, name: str, *, attributes: JsonObject | None = None) -> AsyncIterator[Any]:
        span = self._client.start_span(
            name=name,
            attributes=sanitize_trace_attributes(attributes),
        )
        try:
            yield span
        finally:
            end = getattr(span, "end", None)
            if callable(end):
                end()

    async def event(self, name: str, *, attributes: JsonObject | None = None) -> None:
        self._client.create_event(
            name=name,
            attributes=sanitize_trace_attributes(attributes),
        )


class LangfuseSDKClient:
    """Narrow bridge over the optional OpenTelemetry-based Langfuse SDK."""

    def __init__(self, sdk_client: Any):
        self._sdk_client = sdk_client

    def __repr__(self) -> str:
        return "LangfuseSDKClient(configured=True)"

    def start_span(self, *, name: str, attributes: JsonObject) -> Any:
        start_current = getattr(self._sdk_client, "start_as_current_span", None)
        if callable(start_current):
            manager = start_current(name=name, metadata=attributes)
            return _ManagedSDKSpan(manager)
        start_span = getattr(self._sdk_client, "start_span", None)
        if callable(start_span):
            return start_span(name=name, metadata=attributes)
        raise RuntimeError("installed Langfuse SDK has no supported span API")

    def create_event(self, *, name: str, attributes: JsonObject) -> Any:
        create_event = getattr(self._sdk_client, "create_event", None)
        if not callable(create_event):
            raise RuntimeError("installed Langfuse SDK has no supported event API")
        return create_event(name=name, metadata=attributes)


class _ManagedSDKSpan:
    def __init__(self, manager: Any) -> None:
        self._manager = manager
        self._span = manager.__enter__()
        self.trace_id = _span_identifier(self._span, "trace")
        self.span_id = _span_identifier(self._span, "span")
        self._ended = False

    def end(self) -> None:
        if not self._ended:
            self._manager.__exit__(None, None, None)
            self._ended = True


class TraceAdapterClassification(StrEnum):
    ENABLED = "ENABLED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    SDK_NOT_INSTALLED = "SDK_NOT_INSTALLED"
    INITIALIZATION_FAILED = "INITIALIZATION_FAILED"


@dataclass(frozen=True, slots=True)
class TraceAdapterBuild:
    adapter: Any
    classification: TraceAdapterClassification
    provider: str = "langfuse"

    @property
    def enabled(self) -> bool:
        return self.classification is TraceAdapterClassification.ENABLED


def build_trace_adapter(client: LangfuseClientBoundary | None = None) -> Any:
    if client is None:
        return NoopTraceAdapter()
    return FailOpenTraceAdapter(LangfuseTraceAdapter(client))


def create_langfuse_trace_adapter(
    settings: LangfuseSettings,
    *,
    sdk_factory: Callable[..., Any] | None = None,
) -> TraceAdapterBuild:
    """Build an enabled adapter only when both injected credentials exist."""

    if not settings.enabled:
        return TraceAdapterBuild(
            adapter=NoopTraceAdapter(),
            classification=TraceAdapterClassification.NOT_CONFIGURED,
        )
    factory = sdk_factory or _load_sdk_factory()
    if factory is None:
        return TraceAdapterBuild(
            adapter=NoopTraceAdapter(),
            classification=TraceAdapterClassification.SDK_NOT_INSTALLED,
        )
    kwargs: dict[str, Any] = {
        "public_key": settings.public_key.get_secret_value(),
        "secret_key": settings.secret_key.get_secret_value(),
    }
    if settings.base_url:
        kwargs["host"] = settings.base_url
    try:
        sdk_client = factory(**kwargs)
    except Exception:
        return TraceAdapterBuild(
            adapter=NoopTraceAdapter(),
            classification=TraceAdapterClassification.INITIALIZATION_FAILED,
        )
    return TraceAdapterBuild(
        adapter=FailOpenTraceAdapter(LangfuseTraceAdapter(LangfuseSDKClient(sdk_client))),
        classification=TraceAdapterClassification.ENABLED,
    )


def _load_sdk_factory() -> Callable[..., Any] | None:
    try:
        module = import_module("langfuse")
    except ImportError:
        return None
    factory = getattr(module, "Langfuse", None)
    return factory if callable(factory) else None


def _span_identifier(span: Any, kind: str) -> str | None:
    direct = getattr(span, f"{kind}_id", None)
    if isinstance(direct, (str, int)):
        return _format_identifier(direct)
    getter = getattr(span, f"get_{kind}_id", None)
    if callable(getter):
        value = getter()
        if isinstance(value, (str, int)):
            return _format_identifier(value)
    context_getter = getattr(span, "get_span_context", None)
    if callable(context_getter):
        context = context_getter()
        value = getattr(context, f"{kind}_id", None)
        if isinstance(value, (str, int)):
            return _format_identifier(value)
    return None


def _format_identifier(value: str | int) -> str:
    return f"{value:032x}" if isinstance(value, int) else value
