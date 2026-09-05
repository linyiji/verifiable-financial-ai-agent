from __future__ import annotations

import time
from collections import Counter
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from enum import StrEnum
from importlib import import_module
from typing import Any, Protocol

from src.domain.base import JsonObject
from src.infrastructure.config.settings import LangfuseSettings
from src.observability.noop import FailOpenTraceAdapter, NoopTraceAdapter
from src.observability.safety import sanitize_trace_attributes, sanitize_trace_value

LANGFUSE_OTLP_REDACTION_POLICY = "langfuse-otel-export-redaction-v1"
LANGFUSE_EXPORT_MAX_ATTEMPTS = 3
LANGFUSE_EXPORT_RETRY_DELAY_SECONDS = 0.1
LANGFUSE_FORCE_FLUSH_TIMEOUT_MILLIS = 30_000
LANGFUSE_READBACK_MAX_ATTEMPTS = 10
LANGFUSE_READBACK_MAX_RETRY_DELAY_SECONDS = 2.0


class LangfuseClientBoundary(Protocol):
    def start_span(self, *, name: str, attributes: JsonObject) -> Any: ...

    def create_event(self, *, name: str, attributes: JsonObject) -> Any: ...

    def start_generation(
        self,
        *,
        name: str,
        model: str | None,
        attributes: JsonObject,
        usage_details: JsonObject | None,
        cost_details: JsonObject | None,
    ) -> Any: ...

    def update_generation(
        self,
        generation: Any,
        *,
        model: str | None,
        attributes: JsonObject,
        usage_details: JsonObject | None,
        cost_details: JsonObject | None,
    ) -> None: ...

    def flush(self) -> None: ...


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

    async def event(self, name: str, *, attributes: JsonObject | None = None) -> Any:
        return self._client.create_event(
            name=name,
            attributes=sanitize_trace_attributes(attributes),
        )

    @asynccontextmanager
    async def generation(
        self,
        name: str,
        *,
        model: str | None = None,
        attributes: JsonObject | None = None,
        usage_details: JsonObject | None = None,
        cost_details: JsonObject | None = None,
    ) -> AsyncIterator[Any]:
        generation = self._client.start_generation(
            name=name,
            model=model,
            attributes=sanitize_trace_attributes(attributes),
            usage_details=usage_details,
            cost_details=cost_details,
        )
        try:
            yield generation
        finally:
            end = getattr(generation, "end", None)
            if callable(end):
                end()

    async def complete_generation(
        self,
        generation: Any,
        *,
        model: str | None = None,
        attributes: JsonObject | None = None,
        usage_details: JsonObject | None = None,
        cost_details: JsonObject | None = None,
    ) -> None:
        self._client.update_generation(
            generation,
            model=model,
            attributes=sanitize_trace_attributes(attributes),
            usage_details=usage_details,
            cost_details=cost_details,
        )

    async def flush(self) -> None:
        self._client.flush()


class LangfuseSDKClient:
    """Narrow bridge over the optional OpenTelemetry-based Langfuse SDK."""

    def __init__(self, sdk_client: Any, *, sensitive_values: Sequence[str] = ()):
        self._sdk_client = sdk_client
        self._sensitive_values = tuple(value for value in sensitive_values if value)

    def __repr__(self) -> str:
        return "LangfuseSDKClient(configured=True)"

    def start_span(self, *, name: str, attributes: JsonObject) -> Any:
        name = self._safe_text(name)
        attributes = self._safe_mapping(attributes)
        start_current = getattr(self._sdk_client, "start_as_current_span", None)
        if callable(start_current):
            manager = start_current(name=name, metadata=attributes)
            return _ManagedSDKSpan(manager)
        start_span = getattr(self._sdk_client, "start_span", None)
        if callable(start_span):
            return start_span(name=name, metadata=attributes)
        raise RuntimeError("installed Langfuse SDK has no supported span API")

    def create_event(self, *, name: str, attributes: JsonObject) -> Any:
        name = self._safe_text(name)
        attributes = self._safe_mapping(attributes)
        create_event = getattr(self._sdk_client, "create_event", None)
        if not callable(create_event):
            raise RuntimeError("installed Langfuse SDK has no supported event API")
        return create_event(name=name, metadata=attributes)

    def start_generation(
        self,
        *,
        name: str,
        model: str | None,
        attributes: JsonObject,
        usage_details: JsonObject | None,
        cost_details: JsonObject | None,
    ) -> Any:
        name = self._safe_text(name)
        model = self._safe_optional_text(model)
        attributes = self._safe_mapping(attributes)
        usage_details = self._safe_optional_mapping(usage_details)
        cost_details = self._safe_optional_mapping(cost_details)
        start_current = getattr(self._sdk_client, "start_as_current_generation", None)
        if not callable(start_current):
            raise RuntimeError("installed Langfuse SDK has no supported generation API")
        kwargs: dict[str, Any] = {"name": name, "metadata": attributes}
        if model is not None:
            kwargs["model"] = model
        if usage_details is not None:
            kwargs["usage_details"] = usage_details
        if cost_details is not None:
            kwargs["cost_details"] = cost_details
        return _ManagedSDKSpan(start_current(**kwargs))

    def update_generation(
        self,
        generation: Any,
        *,
        model: str | None,
        attributes: JsonObject,
        usage_details: JsonObject | None,
        cost_details: JsonObject | None,
    ) -> None:
        model = self._safe_optional_text(model)
        attributes = self._safe_mapping(attributes)
        usage_details = self._safe_optional_mapping(usage_details)
        cost_details = self._safe_optional_mapping(cost_details)
        update = getattr(generation, "update", None)
        if not callable(update):
            raise RuntimeError("installed Langfuse SDK generation has no update API")
        kwargs: dict[str, Any] = {"metadata": attributes}
        if model is not None:
            kwargs["model"] = model
        if usage_details is not None:
            kwargs["usage_details"] = usage_details
        if cost_details is not None:
            kwargs["cost_details"] = cost_details
        update(**kwargs)

    def flush(self) -> None:
        resources = getattr(self._sdk_client, "_resources", None)
        provider = getattr(resources, "tracer_provider", None)
        force_flush = getattr(provider, "force_flush", None)
        if callable(force_flush):
            result = force_flush(timeout_millis=LANGFUSE_FORCE_FLUSH_TIMEOUT_MILLIS)
            if result is False:
                raise TimeoutError("Langfuse span force-flush exceeded its bounded timeout")
            return
        flush = getattr(self._sdk_client, "flush", None)
        if not callable(flush):
            raise RuntimeError("installed Langfuse SDK has no supported flush API")
        flush()

    def _safe_mapping(self, value: Mapping[str, Any]) -> JsonObject:
        sanitized = sanitize_trace_value(value, sensitive_values=self._sensitive_values)
        return sanitized if isinstance(sanitized, dict) else {}

    def _safe_optional_mapping(self, value: JsonObject | None) -> JsonObject | None:
        return self._safe_mapping(value) if value is not None else None

    def _safe_text(self, value: str) -> str:
        sanitized = sanitize_trace_value(value, sensitive_values=self._sensitive_values)
        return sanitized if isinstance(sanitized, str) else "[REDACTED]"

    def _safe_optional_text(self, value: str | None) -> str | None:
        return self._safe_text(value) if value is not None else None


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

    def update(self, **kwargs: Any) -> Any:
        update = getattr(self._span, "update", None)
        if not callable(update):
            raise RuntimeError("installed Langfuse SDK observation has no update API")
        return update(**kwargs)


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
    audit_reader: LangfuseTraceAuditReader | None = field(default=None, repr=False, compare=False)
    drain_barrier: LangfuseTelemetryDrainBarrier | None = field(
        default=None,
        repr=False,
        compare=False,
    )

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
    additional_sensitive_values: Mapping[str, str] | None = None,
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
        "timeout": 10,
    }
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    try:
        sdk_client = factory(**kwargs)
        named_sensitive_values = {
            "LANGFUSE_PUBLIC_KEY": settings.public_key.get_secret_value(),
            "LANGFUSE_SECRET_KEY": settings.secret_key.get_secret_value(),
            **(additional_sensitive_values or {}),
        }
        named_sensitive_values = {
            name: value for name, value in named_sensitive_values.items() if value
        }
        sensitive_values = tuple(named_sensitive_values.values())
        if type(sdk_client).__module__.startswith("langfuse."):
            _install_langfuse_otlp_redaction(
                sdk_client,
                public_key=settings.public_key.get_secret_value(),
                sensitive_values=sensitive_values,
            )
    except Exception:
        return TraceAdapterBuild(
            adapter=NoopTraceAdapter(),
            classification=TraceAdapterClassification.INITIALIZATION_FAILED,
        )
    audit_reader = (
        LangfuseTraceAuditReader(
            sdk_client,
            named_sensitive_values=named_sensitive_values,
        )
        if _has_trace_reader(sdk_client)
        else None
    )
    return TraceAdapterBuild(
        adapter=FailOpenTraceAdapter(
            LangfuseTraceAdapter(LangfuseSDKClient(sdk_client, sensitive_values=sensitive_values))
        ),
        classification=TraceAdapterClassification.ENABLED,
        audit_reader=audit_reader,
        drain_barrier=(
            LangfuseTelemetryDrainBarrier(sdk_client, audit_reader=audit_reader)
            if audit_reader is not None
            else None
        ),
    )


@dataclass(frozen=True, slots=True)
class LangfuseTraceRedactionAudit:
    policy_id: str
    passed: bool
    read_succeeded: bool
    occurrence_count: int
    named_occurrence_counts: tuple[tuple[str, int], ...]
    field_count: int
    observation_count: int
    expected_observation_count: int | None
    attempts: int
    inspected_surfaces: tuple[str, ...] = ("trace", "observations")
    expected_observation_identities: tuple[str, ...] | None = None
    observed_observation_identities: tuple[str, ...] = ()
    missing_observation_identities: tuple[str, ...] = ()
    unexpected_observation_identities: tuple[str, ...] = ()
    unexpected_duplicate_identities: tuple[str, ...] = ()
    one_root_trace: bool | None = None
    force_flush_succeeded: bool | None = None
    elapsed_seconds: float = 0.0


class LangfuseTraceAuditReader:
    """Read back a trace and return counts only; never expose remote trace content."""

    def __init__(
        self,
        sdk_client: Any,
        *,
        named_sensitive_values: Mapping[str, str],
    ) -> None:
        self._sdk_client = sdk_client
        self._named_sensitive_values = tuple(
            sorted((name, value) for name, value in named_sensitive_values.items() if value)
        )

    def __repr__(self) -> str:
        return "LangfuseTraceAuditReader(configured=True)"

    def audit(
        self,
        trace_id: str,
        *,
        attempts: int = 6,
        retry_delay_seconds: float = 1.0,
        expected_observation_count: int | None = None,
        expected_observation_identities: Sequence[str] | None = None,
        force_flush_succeeded: bool | None = None,
    ) -> LangfuseTraceRedactionAudit:
        started = time.monotonic()
        bounded_attempts = min(max(int(attempts), 1), LANGFUSE_READBACK_MAX_ATTEMPTS)
        bounded_delay = min(
            max(float(retry_delay_seconds), 0.0),
            LANGFUSE_READBACK_MAX_RETRY_DELAY_SECONDS,
        )
        expected_identities = (
            tuple(sorted({str(item) for item in expected_observation_identities if str(item)}))
            if expected_observation_identities is not None
            else None
        )
        expected_identity_duplicates = (
            _duplicate_identities(tuple(str(item) for item in expected_observation_identities))
            if expected_observation_identities is not None
            else ()
        )
        if expected_identities is not None:
            if expected_observation_count is None:
                expected_observation_count = len(expected_identities)
            elif expected_observation_count != len(expected_identities):
                raise ValueError(
                    "expected observation count must equal the exact identity set size"
                )
        used_attempts = 0
        last_read: LangfuseTraceRedactionAudit | None = None
        for attempt in range(1, bounded_attempts + 1):
            used_attempts = attempt
            try:
                payload = _model_payload(self._sdk_client.api.trace.get(trace_id))
            except Exception:
                if attempt < bounded_attempts:
                    time.sleep(bounded_delay)
                continue
            named_counts = tuple(
                (name, _sensitive_occurrence_count(payload, (value,)))
                for name, value in self._named_sensitive_values
            )
            occurrence_count = sum(count for _, count in named_counts)
            observation_count = _observation_count(payload)
            observed_sequence = _observation_identities(payload)
            observed_identities = tuple(sorted(set(observed_sequence)))
            duplicate_identities = tuple(
                sorted({*expected_identity_duplicates, *_duplicate_identities(observed_sequence)})
            )
            missing_identities = (
                tuple(sorted(set(expected_identities) - set(observed_identities)))
                if expected_identities is not None
                else ()
            )
            unexpected_identities = (
                tuple(sorted(set(observed_identities) - set(expected_identities)))
                if expected_identities is not None
                else ()
            )
            one_root_trace = (
                _one_exact_root_trace(payload, trace_id)
                if expected_identities is not None
                else None
            )
            if expected_identities is not None:
                observation_set_complete = (
                    not missing_identities
                    and not unexpected_identities
                    and not duplicate_identities
                    and observation_count == expected_observation_count
                    and one_root_trace is True
                )
            else:
                observation_set_complete = (
                    expected_observation_count is None
                    or observation_count == expected_observation_count
                )
            last_read = LangfuseTraceRedactionAudit(
                policy_id=LANGFUSE_OTLP_REDACTION_POLICY,
                passed=(
                    occurrence_count == 0
                    and observation_set_complete
                    and force_flush_succeeded is not False
                ),
                read_succeeded=True,
                occurrence_count=occurrence_count,
                named_occurrence_counts=named_counts,
                field_count=_mapping_field_count(payload),
                observation_count=observation_count,
                expected_observation_count=expected_observation_count,
                attempts=used_attempts,
                expected_observation_identities=expected_identities,
                observed_observation_identities=observed_identities,
                missing_observation_identities=missing_identities,
                unexpected_observation_identities=unexpected_identities,
                unexpected_duplicate_identities=duplicate_identities,
                one_root_trace=one_root_trace,
                force_flush_succeeded=force_flush_succeeded,
                elapsed_seconds=time.monotonic() - started,
            )
            if observation_set_complete:
                return last_read
            if attempt < bounded_attempts:
                time.sleep(bounded_delay)
        if last_read is not None:
            return last_read
        return LangfuseTraceRedactionAudit(
            policy_id=LANGFUSE_OTLP_REDACTION_POLICY,
            passed=False,
            read_succeeded=False,
            occurrence_count=0,
            named_occurrence_counts=tuple((name, 0) for name, _ in self._named_sensitive_values),
            field_count=0,
            observation_count=0,
            expected_observation_count=expected_observation_count,
            attempts=used_attempts,
            expected_observation_identities=expected_identities,
            missing_observation_identities=expected_identities or (),
            unexpected_duplicate_identities=expected_identity_duplicates,
            one_root_trace=False if expected_identities is not None else None,
            force_flush_succeeded=force_flush_succeeded,
            elapsed_seconds=time.monotonic() - started,
        )


class LangfuseTelemetryDrainBarrier:
    """Bounded force-flush plus exact-identity ingestion/read-back closure."""

    def __init__(self, sdk_client: Any, *, audit_reader: LangfuseTraceAuditReader) -> None:
        self._sdk_client = sdk_client
        self._audit_reader = audit_reader

    def __repr__(self) -> str:
        return "LangfuseTelemetryDrainBarrier(configured=True)"

    def audit(
        self,
        trace_id: str,
        *,
        expected_observation_identities: Sequence[str],
        flush_timeout_millis: int = LANGFUSE_FORCE_FLUSH_TIMEOUT_MILLIS,
        readback_attempts: int = 6,
        retry_delay_seconds: float = 1.0,
    ) -> LangfuseTraceRedactionAudit:
        started = time.monotonic()
        flush_succeeded = _force_flush_trace_provider(
            self._sdk_client,
            timeout_millis=min(max(int(flush_timeout_millis), 1), 60_000),
        )
        audit = self._audit_reader.audit(
            trace_id,
            attempts=readback_attempts,
            retry_delay_seconds=retry_delay_seconds,
            expected_observation_identities=expected_observation_identities,
            force_flush_succeeded=flush_succeeded,
        )
        return replace(
            audit,
            passed=audit.passed and flush_succeeded,
            force_flush_succeeded=flush_succeeded,
            elapsed_seconds=time.monotonic() - started,
        )


class _LangfuseOTLPRedactingExporter:
    """Strip credentials from completed spans at the final OTLP export boundary."""

    def __init__(
        self,
        delegate: Any,
        *,
        sensitive_values: Sequence[str],
        max_attempts: int = LANGFUSE_EXPORT_MAX_ATTEMPTS,
        retry_delay_seconds: float = LANGFUSE_EXPORT_RETRY_DELAY_SECONDS,
    ) -> None:
        self._delegate = delegate
        self._sensitive_values = tuple(value for value in sensitive_values if value)
        self._max_attempts = min(max(int(max_attempts), 1), LANGFUSE_EXPORT_MAX_ATTEMPTS)
        self._retry_delay_seconds = min(max(float(retry_delay_seconds), 0.0), 1.0)

    def __repr__(self) -> str:
        return f"_LangfuseOTLPRedactingExporter(policy={LANGFUSE_OTLP_REDACTION_POLICY!r})"

    def add_sensitive_values(self, values: Sequence[str]) -> None:
        self._sensitive_values = tuple(
            sorted({*self._sensitive_values, *(value for value in values if value)})
        )

    def export(self, spans: Sequence[Any]) -> Any:
        redacted = tuple(
            _redacted_readable_span(span, sensitive_values=self._sensitive_values) for span in spans
        )
        last_result: Any = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                last_result = self._delegate.export(redacted)
            except Exception:
                if attempt == self._max_attempts:
                    raise
            else:
                if _export_succeeded(last_result):
                    return last_result
            if attempt < self._max_attempts:
                time.sleep(self._retry_delay_seconds)
        return last_result

    def shutdown(self) -> Any:
        return self._delegate.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> Any:
        force_flush = getattr(self._delegate, "force_flush", None)
        return force_flush(timeout_millis) if callable(force_flush) else True


def _install_langfuse_otlp_redaction(
    sdk_client: Any,
    *,
    public_key: str,
    sensitive_values: Sequence[str],
) -> None:
    resources = getattr(sdk_client, "_resources", None)
    provider = getattr(resources, "tracer_provider", None)
    active = getattr(provider, "_active_span_processor", None)
    processors = tuple(getattr(active, "_span_processors", ()))
    matching = [
        item
        for item in processors
        if type(item).__module__ == "langfuse._client.span_processor"
        and getattr(item, "public_key", None) == public_key
    ]
    if len(matching) != 1:
        raise RuntimeError("Langfuse OTLP redaction could not resolve one project span processor")
    batch = getattr(matching[0], "_batch_processor", None)
    exporter = getattr(batch, "_exporter", None)
    if isinstance(exporter, _LangfuseOTLPRedactingExporter):
        exporter.add_sensitive_values(sensitive_values)
        return
    if exporter is None:
        raise RuntimeError("Langfuse OTLP redaction could not resolve the span exporter")
    batch._exporter = _LangfuseOTLPRedactingExporter(  # noqa: SLF001
        exporter,
        sensitive_values=sensitive_values,
    )


def _redacted_readable_span(span: Any, *, sensitive_values: Sequence[str]) -> Any:
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import Event, ReadableSpan
    from opentelemetry.sdk.util.instrumentation import InstrumentationScope
    from opentelemetry.trace import Link, Status

    scope = span.instrumentation_scope
    safe_scope = None
    if scope is not None:
        safe_scope = InstrumentationScope(
            name=_safe_outbound_text(scope.name, sensitive_values),
            version=_safe_optional_outbound_text(scope.version, sensitive_values),
            schema_url=_safe_optional_outbound_text(scope.schema_url, sensitive_values),
            attributes=_safe_outbound_mapping(scope.attributes, sensitive_values),
        )
    resource = span.resource
    safe_resource = Resource(
        _safe_outbound_mapping(resource.attributes, sensitive_values),
        schema_url=_safe_optional_outbound_text(resource.schema_url, sensitive_values),
    )
    events = tuple(
        Event(
            _safe_outbound_text(event.name, sensitive_values),
            attributes=_safe_outbound_mapping(event.attributes, sensitive_values),
            timestamp=event.timestamp,
        )
        for event in span.events
    )
    links = tuple(
        Link(
            link.context,
            attributes=_safe_outbound_mapping(link.attributes, sensitive_values),
        )
        for link in span.links
    )
    description = _safe_optional_outbound_text(span.status.description, sensitive_values)
    status = Status(span.status.status_code, description=description)
    return ReadableSpan(
        name=_safe_outbound_text(span.name, sensitive_values),
        context=span.context,
        parent=span.parent,
        resource=safe_resource,
        attributes=_safe_outbound_mapping(span.attributes, sensitive_values),
        events=events,
        links=links,
        kind=span.kind,
        instrumentation_info=safe_scope,
        status=status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=safe_scope,
    )


def _safe_outbound_mapping(value: Mapping[str, Any] | None, secrets: Sequence[str]) -> JsonObject:
    sanitized = sanitize_trace_value(
        dict(value or {}),
        sensitive_values=secrets,
        drop_sensitive_fields=True,
        sanitize_json_strings=True,
    )
    return sanitized if isinstance(sanitized, dict) else {}


def _safe_outbound_text(value: str, secrets: Sequence[str]) -> str:
    sanitized = sanitize_trace_value(value, sensitive_values=secrets)
    return sanitized if isinstance(sanitized, str) else "[REDACTED]"


def _safe_optional_outbound_text(value: str | None, secrets: Sequence[str]) -> str | None:
    return _safe_outbound_text(value, secrets) if value is not None else None


def _has_trace_reader(sdk_client: Any) -> bool:
    api = getattr(sdk_client, "api", None)
    trace = getattr(api, "trace", None)
    return callable(getattr(trace, "get", None))


def _model_payload(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json", by_alias=True)
    dictionary = getattr(value, "dict", None)
    if callable(dictionary):
        return dictionary(by_alias=True)
    return value


def _sensitive_occurrence_count(value: Any, secrets: Sequence[str]) -> int:
    if isinstance(value, Mapping):
        return sum(
            _sensitive_occurrence_count(key, secrets) + _sensitive_occurrence_count(item, secrets)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return sum(_sensitive_occurrence_count(item, secrets) for item in value)
    if isinstance(value, str):
        return sum(value.count(secret) for secret in secrets if secret)
    return 0


def _mapping_field_count(value: Any) -> int:
    if isinstance(value, Mapping):
        return len(value) + sum(_mapping_field_count(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return sum(_mapping_field_count(item) for item in value)
    return 0


def _observation_count(value: Any) -> int:
    if not isinstance(value, Mapping):
        return 0
    observations = value.get("observations")
    return len(observations) if isinstance(observations, (list, tuple)) else 0


def _observation_identities(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        return ()
    observations = value.get("observations")
    if not isinstance(observations, (list, tuple)):
        return ()
    identities: list[str] = []
    for observation in observations:
        if isinstance(observation, Mapping):
            identity = observation.get("id") or observation.get("observationId")
        else:
            identity = getattr(observation, "id", None) or getattr(
                observation, "observation_id", None
            )
        if isinstance(identity, (str, int)):
            identities.append(_format_identifier(identity, kind="span"))
    return tuple(identities)


def _duplicate_identities(identities: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(identity for identity, count in Counter(identities).items() if count > 1))


def _one_exact_root_trace(value: Any, expected_trace_id: str) -> bool:
    if not isinstance(value, Mapping):
        return False
    top_level_trace_id = value.get("id") or value.get("traceId") or value.get("trace_id")
    if top_level_trace_id is not None and str(top_level_trace_id) != expected_trace_id:
        return False
    observations = value.get("observations")
    if not isinstance(observations, (list, tuple)) or not observations:
        return False
    trace_ids: set[str] = set()
    for observation in observations:
        if not isinstance(observation, Mapping):
            return False
        trace_id = observation.get("traceId") or observation.get("trace_id")
        if not isinstance(trace_id, (str, int)):
            return False
        trace_ids.add(_format_identifier(trace_id, kind="trace"))
    return trace_ids == {expected_trace_id}


def _force_flush_trace_provider(sdk_client: Any, *, timeout_millis: int) -> bool:
    resources = getattr(sdk_client, "_resources", None)
    provider = getattr(resources, "tracer_provider", None)
    force_flush = getattr(provider, "force_flush", None)
    if not callable(force_flush):
        return False
    try:
        result = force_flush(timeout_millis=timeout_millis)
    except Exception:
        return False
    return result is not False


def _export_succeeded(result: Any) -> bool:
    if result is None:
        return True
    name = getattr(result, "name", None)
    if isinstance(name, str):
        return name.casefold() == "success"
    value = getattr(result, "value", result)
    return value == 0 or value is True


def _load_sdk_factory() -> Callable[..., Any] | None:
    try:
        module = import_module("langfuse")
    except ImportError:
        return None
    factory = getattr(module, "Langfuse", None)
    return factory if callable(factory) else None


def _span_identifier(span: Any, kind: str) -> str | None:
    direct_names = [f"{kind}_id"]
    if kind == "span":
        direct_names.extend(("observation_id", "id"))
    for name in direct_names:
        direct = getattr(span, name, None)
        if isinstance(direct, (str, int)):
            return _format_identifier(direct, kind=kind)
    getter = getattr(span, f"get_{kind}_id", None)
    if callable(getter):
        value = getter()
        if isinstance(value, (str, int)):
            return _format_identifier(value, kind=kind)
    context_getter = getattr(span, "get_span_context", None)
    if callable(context_getter):
        context = context_getter()
        value = getattr(context, f"{kind}_id", None)
        if isinstance(value, (str, int)):
            return _format_identifier(value, kind=kind)
    return None


def _format_identifier(value: str | int, *, kind: str) -> str:
    if not isinstance(value, int):
        return value
    width = 32 if kind == "trace" else 16
    return f"{value:0{width}x}"
