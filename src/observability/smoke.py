from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.infrastructure.config.settings import LangfuseSettings
from src.observability.langfuse_adapter import _load_sdk_factory, _span_identifier

JAPAN_LANGFUSE_BASE_URL = "https://jp.cloud.langfuse.com"
SMOKE_TRACE_NAME = "verifiable-financial-agent-smoke-test"
SMOKE_SPAN_NAME = "backend-connectivity"


class LangfuseConnectivityClassification(StrEnum):
    CONNECTED = "CONNECTED"
    CONFIGURED_BUT_CONNECTIVITY_FAILED = "CONFIGURED_BUT_CONNECTIVITY_FAILED"


@dataclass(frozen=True, slots=True)
class LangfuseSmokeResult:
    classification: LangfuseConnectivityClassification
    trace_id: str | None = None
    root_observation_id: str | None = None
    span_observation_id: str | None = None
    flushed: bool = False
    failure_type: str | None = None


def run_langfuse_smoke(
    settings: LangfuseSettings,
    *,
    sdk_factory: Callable[..., Any] | None = None,
) -> LangfuseSmokeResult:
    """Create and flush the fixed smoke trace without retaining secret or body data."""

    if not settings.enabled:
        return _failed("credentials_not_configured")
    if settings.base_url != JAPAN_LANGFUSE_BASE_URL:
        return _failed("japan_endpoint_preflight_failed")
    factory = sdk_factory or _load_sdk_factory()
    if factory is None:
        return _failed("sdk_not_installed")

    client = None
    try:
        client = factory(
            public_key=settings.public_key.get_secret_value(),
            secret_key=settings.secret_key.get_secret_value(),
            base_url=settings.base_url,
            timeout=10,
            debug=False,
            flush_at=1,
        )
        auth_check = getattr(client, "auth_check", None)
        if not callable(auth_check) or auth_check() is not True:
            return _failed("auth_check_failed")
        with client.start_as_current_span(
            name=SMOKE_TRACE_NAME,
            metadata={"component": "backend", "purpose": "connectivity"},
        ) as root:
            update_trace = getattr(root, "update_trace", None)
            if callable(update_trace):
                update_trace(name=SMOKE_TRACE_NAME)
            trace_id = _span_identifier(root, "trace")
            root_observation_id = _span_identifier(root, "span")
            with client.start_as_current_span(
                name=SMOKE_SPAN_NAME,
                metadata={"component": "backend", "status": "smoke"},
            ) as child:
                span_observation_id = _span_identifier(child, "span")
        client.flush()
        return LangfuseSmokeResult(
            classification=LangfuseConnectivityClassification.CONNECTED,
            trace_id=trace_id,
            root_observation_id=root_observation_id,
            span_observation_id=span_observation_id,
            flushed=True,
        )
    except Exception as exc:
        return _failed(type(exc).__name__)
    finally:
        shutdown = getattr(client, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception:
                pass


def _failed(failure_type: str) -> LangfuseSmokeResult:
    return LangfuseSmokeResult(
        classification=LangfuseConnectivityClassification.CONFIGURED_BUT_CONNECTIVITY_FAILED,
        failure_type=failure_type,
    )
