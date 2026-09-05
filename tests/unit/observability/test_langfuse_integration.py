from __future__ import annotations

import json
from contextlib import AbstractContextManager
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from src.adapters.llm.provider import LLMMessage, LLMStructuredResponse
from src.infrastructure.config.settings import LangfuseSettings
from src.observability import (
    InMemoryTraceReferenceRepository,
    InstrumentedLLMProvider,
    LangfuseConnectivityClassification,
    NoopTraceAdapter,
    ObservationStage,
    RuntimeInstrumentation,
    TraceAdapterClassification,
    TraceRuntimeStatus,
    create_langfuse_trace_adapter,
    run_langfuse_smoke,
)
from src.observability.langfuse_adapter import (
    LANGFUSE_OTLP_REDACTION_POLICY,
    LangfuseSDKClient,
    LangfuseTelemetryDrainBarrier,
    LangfuseTraceAuditReader,
    _LangfuseOTLPRedactingExporter,
)


class FakeSpan:
    def __init__(self, trace_id: str, span_id: str) -> None:
        self.trace_id = trace_id
        self.span_id = span_id
        self.updates: list[dict] = []

    def update(self, **kwargs: object) -> None:
        self.updates.append(kwargs)


class FakeSpanManager(AbstractContextManager):
    def __init__(self, sdk: FakeLangfuseSDK, span: FakeSpan) -> None:
        self.sdk = sdk
        self.span = span
        self.exited = False

    def __enter__(self) -> FakeSpan:
        self.sdk.trace_stack.append(self.span.trace_id)
        return self.span

    def __exit__(self, *args: object) -> None:
        self.sdk.trace_stack.pop()
        self.exited = True


class FakeLangfuseSDK:
    def __init__(self) -> None:
        self.spans: list[tuple[str, dict, FakeSpanManager]] = []
        self.generations: list[tuple[str, dict, dict, FakeSpanManager]] = []
        self.events: list[tuple[str, dict]] = []
        self.trace_stack: list[str] = []
        self.flush_count = 0

    def auth_check(self) -> bool:
        return True

    def _manager(self) -> FakeSpanManager:
        index = len(self.spans) + len(self.generations) + 1
        trace_id = self.trace_stack[-1] if self.trace_stack else f"trace-{index}"
        return FakeSpanManager(self, FakeSpan(trace_id, f"span-{index}"))

    def start_as_current_span(self, *, name: str, metadata: dict) -> FakeSpanManager:
        manager = self._manager()
        self.spans.append((name, metadata, manager))
        return manager

    def start_as_current_generation(
        self,
        *,
        name: str,
        metadata: dict,
        **kwargs: object,
    ) -> FakeSpanManager:
        manager = self._manager()
        self.generations.append((name, metadata, kwargs, manager))
        return manager

    def create_event(self, *, name: str, metadata: dict) -> FakeSpan:
        index = len(self.spans) + len(self.generations) + len(self.events) + 1
        trace_id = self.trace_stack[-1] if self.trace_stack else f"trace-{index}"
        event = FakeSpan(trace_id, f"span-{index}")
        self.events.append((name, metadata))
        return event

    def flush(self) -> None:
        self.flush_count += 1

    def shutdown(self) -> None:
        pass


def settings(*, public: str | None, secret: str | None) -> LangfuseSettings:
    return LangfuseSettings(
        public_key=public,
        secret_key=secret,
        base_url="https://langfuse.invalid",
    )


def test_factory_is_noop_until_both_credentials_are_injected() -> None:
    calls = 0

    def forbidden_factory(**kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError(kwargs)

    for configured in (
        settings(public=None, secret=None),
        settings(public="public-sentinel", secret=None),
        settings(public=None, secret="secret-sentinel"),
    ):
        result = create_langfuse_trace_adapter(configured, sdk_factory=forbidden_factory)
        assert result.classification is TraceAdapterClassification.NOT_CONFIGURED
        assert isinstance(result.adapter, NoopTraceAdapter)
        assert result.enabled is False
    assert calls == 0


def test_factory_enables_fake_sdk_without_exposing_credentials() -> None:
    captured: dict[str, object] = {}
    sdk = FakeLangfuseSDK()

    def factory(**kwargs: object) -> FakeLangfuseSDK:
        captured.update(kwargs)
        return sdk

    result = create_langfuse_trace_adapter(
        settings(public="public-sentinel", secret="secret-sentinel"),
        sdk_factory=factory,
    )

    assert result.classification is TraceAdapterClassification.ENABLED
    assert result.enabled is True
    assert captured == {
        "public_key": "public-sentinel",
        "secret_key": "secret-sentinel",
        "base_url": "https://langfuse.invalid",
        "timeout": 10,
    }
    assert "public-sentinel" not in repr(result)
    assert "secret-sentinel" not in repr(result)


def test_missing_sdk_and_initialization_error_are_classified_fail_open(monkeypatch) -> None:
    monkeypatch.setattr("src.observability.langfuse_adapter._load_sdk_factory", lambda: None)
    missing = create_langfuse_trace_adapter(
        settings(public="public-sentinel", secret="secret-sentinel")
    )
    assert missing.classification is TraceAdapterClassification.SDK_NOT_INSTALLED
    assert isinstance(missing.adapter, NoopTraceAdapter)

    def broken_factory(**kwargs: object) -> object:
        del kwargs
        raise RuntimeError("backend initialization failed")

    broken = create_langfuse_trace_adapter(
        settings(public="public-sentinel", secret="secret-sentinel"),
        sdk_factory=broken_factory,
    )
    assert broken.classification is TraceAdapterClassification.INITIALIZATION_FAILED
    assert isinstance(broken.adapter, NoopTraceAdapter)


@pytest.mark.asyncio
async def test_one_run_root_covers_required_observations_and_persists_only_refs() -> None:
    sdk = FakeLangfuseSDK()
    build = create_langfuse_trace_adapter(
        settings(public="public-sentinel", secret="secret-sentinel"),
        sdk_factory=lambda **kwargs: sdk,
    )
    references = InMemoryTraceReferenceRepository()
    hooks = RuntimeInstrumentation(build.adapter, reference_repository=references)

    async with hooks.research_run(run_id="RUN-1") as run:
        assert run.trace_id == "trace-1"
        assert run.root_observation_id == "span-1"
        async with run.scheme_generation(
            requested_model="requested",
            actual_model="actual",
            provider="provider",
            latency_ms=12.5,
            input_tokens=10,
            output_tokens=4,
            total_tokens=14,
            cost_usd=0.001,
        ):
            pass
        async with run.planner_generation(requested_model="requested"):
            pass
        managers = [
            run.task(task_id="TASK-1"),
            run.evidence_batch(
                task_id="TASK-1",
                evidence_count=2,
                providers=["provider"],
                periods=["FY2025"],
                normalized_fields=["revenue"],
                status_counts={"accepted": 2},
            ),
            run.agent(task_id="TASK-1"),
            run.skill(task_id="TASK-1"),
            run.tool(task_id="TASK-1"),
            run.calculation(task_id="TASK-1"),
            run.correction(task_id="TASK-1"),
            run.replan(task_id="TASK-1"),
            run.review(),
            run.release(),
        ]
        for manager in managers:
            async with manager as span:
                assert span.trace_id == "trace-1"

    refs = await references.list_by_run("RUN-1")
    expected_stages = {
        ObservationStage.RUN,
        ObservationStage.SCHEME_GENERATION,
        ObservationStage.PLANNER_GENERATION,
        ObservationStage.TASK,
        ObservationStage.EVIDENCE,
        ObservationStage.AGENT,
        ObservationStage.SKILL,
        ObservationStage.TOOL,
        ObservationStage.CALCULATION,
        ObservationStage.CORRECTION,
        ObservationStage.REPLAN,
        ObservationStage.REVIEW,
        ObservationStage.RELEASE,
    }
    assert {reference.stage for reference in refs} == {stage.value for stage in expected_stages}
    assert all(reference.trace_id == "trace-1" for reference in refs)
    assert all(not hasattr(reference, "metadata") for reference in refs)
    assert all(manager.exited for _, _, manager in sdk.spans)
    assert all(manager.exited for _, _, _, manager in sdk.generations)

    scheme = sdk.generations[0]
    assert scheme[0] == "vfas.scheme_generation"
    assert scheme[1]["requested_model"] == "requested"
    assert scheme[1]["actual_model"] == "actual"
    assert scheme[1]["provider"] == "provider"
    assert scheme[1]["latency_ms"] == 12.5
    assert scheme[2] == {
        "model": "actual",
        "usage_details": {"input": 10, "output": 4, "total": 14},
        "cost_details": {"total": 0.001},
    }
    evidence_metadata = next(metadata for name, metadata, _ in sdk.spans if name == "vfas.evidence")
    assert evidence_metadata["evidence_count"] == 2
    assert "evidence_id" not in evidence_metadata
    assert "value" not in evidence_metadata


class StructuredAnswer(BaseModel):
    answer: str


class FakeLLMProvider:
    provider_name = "provider"

    async def complete_structured(self, **kwargs: object) -> LLMStructuredResponse:
        del kwargs
        return LLMStructuredResponse(
            output=StructuredAnswer(answer="sensitive-output"),
            provider="provider",
            requested_model="requested-model",
            actual_model="actual-model",
            attempted_models=("requested-model", "actual-model"),
            input_tokens=11,
            output_tokens=7,
        )


@pytest.mark.asyncio
async def test_provider_wrapper_records_real_response_usage_without_content() -> None:
    sdk = FakeLangfuseSDK()
    build = create_langfuse_trace_adapter(
        settings(public="public-sentinel", secret="secret-sentinel"),
        sdk_factory=lambda **kwargs: sdk,
    )
    hooks = RuntimeInstrumentation(build.adapter)
    async with hooks.research_run(run_id="RUN-1") as run:
        provider = InstrumentedLLMProvider(
            FakeLLMProvider(),
            trace=run,
            stage=ObservationStage.SCHEME_GENERATION,
        )
        response = await provider.complete_structured(
            messages=[LLMMessage(role="user", content="sensitive-prompt")],
            response_model=StructuredAnswer,
            schema_name="answer_v1",
        )

    assert response.actual_model == "actual-model"
    generation_span = sdk.generations[0][3].span
    update = generation_span.updates[0]
    assert update["model"] == "actual-model"
    assert update["usage_details"] == {"input": 11, "output": 7, "total": 18}
    metadata = update["metadata"]
    assert metadata["requested_model"] == "requested-model"
    assert metadata["actual_model"] == "actual-model"
    assert metadata["provider"] == "provider"
    assert metadata["latency_ms"] >= 0
    assert "sensitive-prompt" not in str(sdk.generations)
    assert "sensitive-output" not in str(sdk.generations)


@pytest.mark.asyncio
async def test_metadata_is_sanitized_for_spans_and_events() -> None:
    sdk = FakeLangfuseSDK()
    build = create_langfuse_trace_adapter(
        settings(public="public-sentinel", secret="secret-sentinel"),
        sdk_factory=lambda **kwargs: sdk,
    )
    hooks = RuntimeInstrumentation(build.adapter)

    unsafe = {
        "api_key": "credential-value",
        "nested": {"authorization": "credential-value", "safe": "kept"},
        "object_id": "OBJ-1",
        "request_body": {"secret": "credential-value"},
        "messages": ["credential-value"],
        "normalized_value": 42,
        "output": "credential-value",
    }
    async with hooks.run(run_id="RUN-1", attributes=unsafe):
        pass
    event = await build.adapter.event(
        "vfas.task.started",
        attributes={"run_id": "RUN-1", "task_id": "TASK-1", **unsafe},
    )

    span_metadata = sdk.spans[0][1]
    event_metadata = sdk.events[0][1]
    assert event.span_id == "span-2"
    for metadata in (span_metadata, event_metadata):
        assert metadata["api_key"] == "[REDACTED]"
        assert metadata["nested"]["authorization"] == "[REDACTED]"
        assert metadata["nested"]["safe"] == "kept"
        assert metadata["request_body"] == "[REDACTED]"
        assert metadata["messages"] == "[REDACTED]"
        assert metadata["normalized_value"] == "[REDACTED]"
        assert metadata["output"] == "[REDACTED]"
        assert "credential-value" not in str(metadata)


@pytest.mark.asyncio
async def test_sdk_bridge_redacts_all_configured_credentials_across_keys_and_values() -> None:
    sdk = FakeLangfuseSDK()
    configured_values = {
        "FMP_API_KEY": "fmp-sensitive-sentinel",
        "TEAMOROUTER_API_KEY": "router-sensitive-sentinel",
        "MIMO_API_KEY": "mimo-sensitive-sentinel",
    }
    build = create_langfuse_trace_adapter(
        settings(public="public-sensitive-sentinel", secret="secret-sensitive-sentinel"),
        sdk_factory=lambda **kwargs: sdk,
        additional_sensitive_values=configured_values,
    )
    hooks = RuntimeInstrumentation(build.adapter)
    unsafe = {
        "provider": "fmp-sensitive-sentinel",
        "nested": {
            "safe_label": "router-sensitive-sentinel",
            "selected_model": "mimo-sensitive-sentinel",
            "chain_of_thought": "hidden-reasoning-sentinel",
            "publicKey": "unknown-public-value",
            "client-password": "unknown-password-value",
            "sessionTokenField": "unknown-token-value",
            "api-key": "unknown-api-key-value",
        },
    }

    async with hooks.run(run_id="RUN-REDACTION", attributes=unsafe):
        pass
    await hooks.emit(
        ObservationStage.TOOL,
        "failed",
        run_id="RUN-REDACTION",
        attributes={"error": unsafe, "secret": "secret-sensitive-sentinel"},
    )

    serialized = json.dumps(
        {"spans": sdk.spans, "events": sdk.events},
        default=str,
        sort_keys=True,
    )
    for sentinel in (
        "public-sensitive-sentinel",
        "secret-sensitive-sentinel",
        "fmp-sensitive-sentinel",
        "router-sensitive-sentinel",
        "mimo-sensitive-sentinel",
        "hidden-reasoning-sentinel",
        "unknown-public-value",
        "unknown-password-value",
        "unknown-token-value",
        "unknown-api-key-value",
    ):
        assert sentinel not in serialized


class _CapturingSpanExporter:
    def __init__(self) -> None:
        self.spans: tuple[object, ...] = ()
        self.authorization = "public-sensitive-sentinel:secret-sensitive-sentinel"

    def export(self, spans: tuple[object, ...]) -> object:
        from opentelemetry.sdk.trace.export import SpanExportResult

        self.spans = spans
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


def test_otlp_export_boundary_removes_credentials_from_fully_serialized_spans() -> None:
    from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import Event, ReadableSpan
    from opentelemetry.sdk.util.instrumentation import InstrumentationScope
    from opentelemetry.trace import (
        Link,
        SpanContext,
        SpanKind,
        Status,
        StatusCode,
        TraceFlags,
        TraceState,
    )

    configured = (
        "public-sensitive-sentinel",
        "secret-sensitive-sentinel",
        "fmp-sensitive-sentinel",
        "router-sensitive-sentinel",
    )
    payloads = {
        "root": {"public-key": "generic-root-sentinel"},
        "observation": {"secret": "generic-observation-sentinel"},
        "error": {"password": "generic-error-sentinel"},
        "provider": {"apiKey": "generic-provider-sentinel"},
        "tool": {"bearerTokenValue": "generic-tool-sentinel"},
    }
    context = SpanContext(
        trace_id=1,
        span_id=2,
        is_remote=False,
        trace_flags=TraceFlags(1),
        trace_state=TraceState(),
    )
    scope = InstrumentationScope(
        "langfuse-sdk",
        attributes={"public_key": configured[0]},
    )
    spans = tuple(
        ReadableSpan(
            name=f"vfas.{surface}",
            context=context,
            resource=Resource(
                {
                    "service.name": "vfas",
                    "FMP_API_KEY": configured[2],
                }
            ),
            attributes={
                "payload": json.dumps(payload),
                "provider_reference": configured[3],
            },
            events=(
                Event(
                    "exception",
                    attributes={"exception.message": configured[1]},
                ),
            ),
            links=(Link(context, attributes={"accessToken": "generic-link-sentinel"}),),
            kind=SpanKind.INTERNAL,
            instrumentation_scope=scope,
            status=Status(StatusCode.ERROR, description=configured[1]),
            start_time=1,
            end_time=2,
        )
        for surface, payload in payloads.items()
    )
    delegate = _CapturingSpanExporter()
    exporter = _LangfuseOTLPRedactingExporter(
        delegate,
        sensitive_values=configured,
    )

    exporter.export(spans)

    assert spans[0].instrumentation_scope.attributes["public_key"] == configured[0]
    assert delegate.authorization == f"{configured[0]}:{configured[1]}"
    assert len(delegate.spans) == len(payloads)
    assert all(span.instrumentation_scope.attributes == {} for span in delegate.spans)
    outbound = encode_spans(delegate.spans).SerializeToString()
    for sentinel in (
        *configured,
        "generic-root-sentinel",
        "generic-observation-sentinel",
        "generic-error-sentinel",
        "generic-provider-sentinel",
        "generic-tool-sentinel",
        "generic-link-sentinel",
    ):
        assert sentinel.encode() not in outbound
    for sensitive_field in (
        b"public_key",
        b"FMP_API_KEY",
        b"public-key",
        b"secret",
        b"password",
        b"apiKey",
        b"bearerTokenValue",
        b"accessToken",
    ):
        assert sensitive_field not in outbound


def test_factory_wraps_only_matching_langfuse_exporter_after_project_routing() -> None:
    public = "public-sensitive-sentinel"
    delegate = _CapturingSpanExporter()
    processor_type = type("LangfuseSpanProcessor", (), {})
    processor_type.__module__ = "langfuse._client.span_processor"
    processor = processor_type()
    processor.public_key = public
    processor._batch_processor = SimpleNamespace(_exporter=delegate)
    sdk_type = type("Langfuse", (), {})
    sdk_type.__module__ = "langfuse.fake"
    sdk = sdk_type()
    sdk._resources = SimpleNamespace(
        tracer_provider=SimpleNamespace(
            _active_span_processor=SimpleNamespace(_span_processors=(processor,))
        )
    )
    sdk.start_as_current_span = lambda **kwargs: None
    sdk.create_event = lambda **kwargs: None
    sdk.flush = lambda: None

    build = create_langfuse_trace_adapter(
        settings(public=public, secret="secret-sensitive-sentinel"),
        sdk_factory=lambda **kwargs: sdk,
        additional_sensitive_values={"FMP_API_KEY": "fmp-sensitive-sentinel"},
    )

    assert build.enabled is True
    assert isinstance(processor._batch_processor._exporter, _LangfuseOTLPRedactingExporter)
    assert processor.public_key == public
    assert processor._batch_processor._exporter._delegate is delegate


def test_trace_readback_audit_reports_only_named_counts() -> None:
    values = {
        "LANGFUSE_PUBLIC_KEY": "public-sensitive-sentinel",
        "LANGFUSE_SECRET_KEY": "secret-sensitive-sentinel",
        "FMP_API_KEY": "fmp-sensitive-sentinel",
        "TEAMOROUTER_API_KEY": "router-sensitive-sentinel",
    }
    response = {
        "metadata": {"scope": {"attributes": {"public_key": values["LANGFUSE_PUBLIC_KEY"]}}},
        "observations": [
            {
                "metadata": {
                    "scope": {"attributes": {"public_key": values["LANGFUSE_PUBLIC_KEY"]}}
                },
                "provider": values["TEAMOROUTER_API_KEY"],
                "tool": values["FMP_API_KEY"],
                "error": values["LANGFUSE_SECRET_KEY"],
            }
        ],
    }
    sdk = SimpleNamespace(api=SimpleNamespace(trace=SimpleNamespace(get=lambda trace_id: response)))

    audit = LangfuseTraceAuditReader(
        sdk,
        named_sensitive_values=values,
    ).audit("trace-id", attempts=1)

    assert audit.policy_id == LANGFUSE_OTLP_REDACTION_POLICY
    assert audit.passed is False
    assert audit.occurrence_count == 5
    assert audit.expected_observation_count is None
    assert dict(audit.named_occurrence_counts) == {
        "FMP_API_KEY": 1,
        "LANGFUSE_PUBLIC_KEY": 2,
        "LANGFUSE_SECRET_KEY": 1,
        "TEAMOROUTER_API_KEY": 1,
    }
    serialized_audit = repr(audit)
    assert all(value not in serialized_audit for value in values.values())


def test_trace_audit_waits_for_the_exact_exported_observation_set() -> None:
    payloads = iter(
        (
            {"observations": [{"name": "root"}]},
            {"observations": [{"name": "root"}, {"name": "tool"}]},
        )
    )
    sdk = SimpleNamespace(
        api=SimpleNamespace(trace=SimpleNamespace(get=lambda trace_id: next(payloads)))
    )

    audit = LangfuseTraceAuditReader(
        sdk,
        named_sensitive_values={"LANGFUSE_PUBLIC_KEY": "public-sentinel"},
    ).audit(
        "trace-id",
        attempts=2,
        retry_delay_seconds=0,
        expected_observation_count=2,
    )

    assert audit.passed is True
    assert audit.read_succeeded is True
    assert audit.observation_count == 2
    assert audit.expected_observation_count == 2
    assert audit.attempts == 2


def test_trace_audit_fails_closed_for_an_incomplete_remote_observation_set() -> None:
    sdk = SimpleNamespace(
        api=SimpleNamespace(
            trace=SimpleNamespace(get=lambda trace_id: {"observations": [{"name": "root"}]})
        )
    )

    audit = LangfuseTraceAuditReader(
        sdk,
        named_sensitive_values={"LANGFUSE_PUBLIC_KEY": "public-sentinel"},
    ).audit(
        "trace-id",
        attempts=1,
        expected_observation_count=2,
    )

    assert audit.passed is False
    assert audit.read_succeeded is True
    assert audit.occurrence_count == 0
    assert audit.observation_count == 1
    assert audit.expected_observation_count == 2


def _trace_payload(*identities: str, trace_id: str = "trace-id") -> dict:
    return {
        "id": trace_id,
        "observations": [
            {"id": identity, "traceId": trace_id, "name": f"vfas.{identity}"}
            for identity in identities
        ],
    }


def test_trace_audit_eventually_reaches_the_exact_expected_identity_set() -> None:
    payloads = iter((_trace_payload("root"), _trace_payload("root", "tool")))
    sdk = SimpleNamespace(
        api=SimpleNamespace(trace=SimpleNamespace(get=lambda trace_id: next(payloads)))
    )

    audit = LangfuseTraceAuditReader(sdk, named_sensitive_values={}).audit(
        "trace-id",
        attempts=2,
        retry_delay_seconds=0,
        expected_observation_identities=("root", "tool"),
    )

    assert audit.passed is True
    assert audit.expected_observation_count == 2
    assert audit.observed_observation_identities == ("root", "tool")
    assert audit.missing_observation_identities == ()
    assert audit.unexpected_duplicate_identities == ()
    assert audit.one_root_trace is True


def test_trace_audit_reports_the_exact_missing_identity() -> None:
    sdk = SimpleNamespace(
        api=SimpleNamespace(
            trace=SimpleNamespace(get=lambda trace_id: _trace_payload("root"))
        )
    )

    audit = LangfuseTraceAuditReader(sdk, named_sensitive_values={}).audit(
        "trace-id",
        attempts=1,
        expected_observation_identities=("root", "tool"),
    )

    assert audit.passed is False
    assert audit.missing_observation_identities == ("tool",)
    assert audit.observed_observation_identities == ("root",)


def test_duplicate_identity_cannot_satisfy_a_missing_identity() -> None:
    sdk = SimpleNamespace(
        api=SimpleNamespace(
            trace=SimpleNamespace(get=lambda trace_id: _trace_payload("root", "root"))
        )
    )

    audit = LangfuseTraceAuditReader(sdk, named_sensitive_values={}).audit(
        "trace-id",
        attempts=1,
        expected_observation_identities=("root", "tool"),
    )

    assert audit.observation_count == 2
    assert audit.passed is False
    assert audit.missing_observation_identities == ("tool",)
    assert audit.unexpected_duplicate_identities == ("root",)


def test_exact_identity_audit_rejects_observations_from_another_root_trace() -> None:
    payload = _trace_payload("root", "tool")
    payload["observations"][1]["traceId"] = "another-trace"
    sdk = SimpleNamespace(
        api=SimpleNamespace(trace=SimpleNamespace(get=lambda trace_id: payload))
    )

    audit = LangfuseTraceAuditReader(sdk, named_sensitive_values={}).audit(
        "trace-id",
        attempts=1,
        expected_observation_identities=("root", "tool"),
    )

    assert audit.passed is False
    assert audit.one_root_trace is False


class _FakeTraceProvider:
    def __init__(self, result: bool) -> None:
        self.result = result
        self.timeouts: list[int] = []

    def force_flush(self, *, timeout_millis: int) -> bool:
        self.timeouts.append(timeout_millis)
        return self.result


def _drain_sdk(provider: _FakeTraceProvider, payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        _resources=SimpleNamespace(tracer_provider=provider),
        api=SimpleNamespace(trace=SimpleNamespace(get=lambda trace_id: payload)),
    )


def test_drain_barrier_force_flushes_then_closes_the_exact_set() -> None:
    provider = _FakeTraceProvider(True)
    sdk = _drain_sdk(provider, _trace_payload("root", "tool"))
    reader = LangfuseTraceAuditReader(
        sdk,
        named_sensitive_values={"LANGFUSE_PUBLIC_KEY": "credential-sentinel"},
    )

    audit = LangfuseTelemetryDrainBarrier(sdk, audit_reader=reader).audit(
        "trace-id",
        expected_observation_identities=("root", "tool"),
        flush_timeout_millis=25,
        readback_attempts=1,
    )

    assert audit.passed is True
    assert audit.force_flush_succeeded is True
    assert audit.occurrence_count == 0
    assert provider.timeouts == [25]


def test_drain_barrier_fails_closed_when_force_flush_times_out() -> None:
    provider = _FakeTraceProvider(False)
    sdk = _drain_sdk(provider, _trace_payload("root", "tool"))
    reader = LangfuseTraceAuditReader(sdk, named_sensitive_values={})

    audit = LangfuseTelemetryDrainBarrier(sdk, audit_reader=reader).audit(
        "trace-id",
        expected_observation_identities=("root", "tool"),
        flush_timeout_millis=25,
        readback_attempts=1,
    )

    assert audit.passed is False
    assert audit.force_flush_succeeded is False
    assert provider.timeouts == [25]


def test_readback_polling_has_a_hard_attempt_bound() -> None:
    calls = 0

    def read(trace_id: str) -> dict:
        nonlocal calls
        calls += 1
        return _trace_payload("root")

    sdk = SimpleNamespace(api=SimpleNamespace(trace=SimpleNamespace(get=read)))

    audit = LangfuseTraceAuditReader(sdk, named_sensitive_values={}).audit(
        "trace-id",
        attempts=999,
        retry_delay_seconds=0,
        expected_observation_identities=("root", "tool"),
    )

    assert audit.passed is False
    assert audit.attempts == 10
    assert calls == 10
    assert audit.elapsed_seconds < 1


def test_exporter_retries_the_same_redacted_batch_after_bounded_failure(monkeypatch) -> None:
    failure = SimpleNamespace(name="FAILURE", value=1)
    success = SimpleNamespace(name="SUCCESS", value=0)

    class Delegate:
        def __init__(self) -> None:
            self.calls: list[tuple[object, ...]] = []

        def export(self, spans: tuple[object, ...]) -> object:
            self.calls.append(spans)
            return (failure, success)[len(self.calls) - 1]

    monkeypatch.setattr(
        "src.observability.langfuse_adapter._redacted_readable_span",
        lambda span, sensitive_values: span,
    )
    delegate = Delegate()
    exporter = _LangfuseOTLPRedactingExporter(
        delegate,
        sensitive_values=(),
        retry_delay_seconds=0,
    )

    result = exporter.export((object(), object()))

    assert result is success
    assert len(delegate.calls) == 2
    assert delegate.calls[0] is delegate.calls[1]


def test_exporter_retries_a_transport_timeout_with_a_hard_attempt_bound(monkeypatch) -> None:
    success = SimpleNamespace(name="SUCCESS", value=0)

    class Delegate:
        def __init__(self) -> None:
            self.calls = 0

        def export(self, spans: tuple[object, ...]) -> object:
            del spans
            self.calls += 1
            if self.calls < 3:
                raise TimeoutError("bounded test timeout")
            return success

    monkeypatch.setattr(
        "src.observability.langfuse_adapter._redacted_readable_span",
        lambda span, sensitive_values: span,
    )
    delegate = Delegate()
    exporter = _LangfuseOTLPRedactingExporter(
        delegate,
        sensitive_values=(),
        max_attempts=99,
        retry_delay_seconds=0,
    )

    assert exporter.export((object(),)) is success
    assert delegate.calls == 3


class BrokenSDK:
    def start_as_current_span(self, **kwargs: object) -> object:
        raise RuntimeError("trace unavailable")

    def create_event(self, **kwargs: object) -> None:
        raise RuntimeError("trace unavailable")


class BrokenReferenceRepository:
    async def add(self, reference: object) -> None:
        del reference
        raise RuntimeError("business trace-ref persistence unavailable")


@pytest.mark.asyncio
async def test_sdk_and_reference_failures_never_break_business_execution() -> None:
    build = create_langfuse_trace_adapter(
        settings(public="public-sentinel", secret="secret-sentinel"),
        sdk_factory=lambda **kwargs: BrokenSDK(),
    )
    hooks = RuntimeInstrumentation(
        build.adapter,
        reference_repository=BrokenReferenceRepository(),
    )
    async with hooks.run(run_id="RUN-1"):
        marker = "business continued"
    await hooks.emit(ObservationStage.REVIEW, "completed", run_id="RUN-1")
    assert marker == "business continued"
    assert hooks.status is TraceRuntimeStatus.TRACE_DEGRADED

    healthy_sdk = FakeLangfuseSDK()
    healthy = create_langfuse_trace_adapter(
        settings(public="public-sentinel", secret="secret-sentinel"),
        sdk_factory=lambda **kwargs: healthy_sdk,
    )
    hooks = RuntimeInstrumentation(
        healthy.adapter,
        reference_repository=BrokenReferenceRepository(),
    )
    async with hooks.review(run_id="RUN-1"):
        marker = "business still continued"
    assert marker == "business still continued"
    assert hooks.status is TraceRuntimeStatus.TRACE_DEGRADED


def test_sdk_bridge_repr_and_event_mapping_are_secret_free() -> None:
    sdk = FakeLangfuseSDK()
    bridge = LangfuseSDKClient(sdk)
    span = bridge.start_span(name="vfas.run", attributes={"run_id": "RUN-1"})
    bridge.create_event(name="vfas.run.started", attributes={"run_id": "RUN-1"})
    generation = bridge.start_generation(
        name="vfas.scheme_generation",
        model="model",
        attributes={"run_id": "RUN-1"},
        usage_details={"total": 1},
        cost_details=None,
    )
    generation.end()
    bridge.flush()
    span.end()

    assert repr(bridge) == "LangfuseSDKClient(configured=True)"
    assert sdk.spans[0][0] == "vfas.run"
    assert sdk.events[0][0] == "vfas.run.started"
    assert sdk.generations[0][0] == "vfas.scheme_generation"
    assert sdk.flush_count == 1


def test_smoke_uses_fixed_names_and_returns_only_ids_and_status() -> None:
    sdk = FakeLangfuseSDK()
    smoke_settings = LangfuseSettings(
        public_key="public-sentinel",
        secret_key="secret-sentinel",
        base_url="https://jp.cloud.langfuse.com",
    )
    result = run_langfuse_smoke(smoke_settings, sdk_factory=lambda **kwargs: sdk)

    assert result.classification is LangfuseConnectivityClassification.CONNECTED
    assert result.trace_id == "trace-1"
    assert result.root_observation_id == "span-1"
    assert result.span_observation_id == "span-2"
    assert result.flushed is True
    assert sdk.spans[0][0] == "verifiable-financial-agent-smoke-test"
    assert sdk.spans[1][0] == "backend-connectivity"
    assert "sentinel" not in repr(result)


def test_smoke_classifies_auth_failure_without_creating_trace() -> None:
    sdk = FakeLangfuseSDK()
    sdk.auth_check = lambda: False  # type: ignore[method-assign]
    smoke_settings = LangfuseSettings(
        public_key="public-sentinel",
        secret_key="secret-sentinel",
        base_url="https://jp.cloud.langfuse.com",
    )
    result = run_langfuse_smoke(smoke_settings, sdk_factory=lambda **kwargs: sdk)

    assert result.classification is (
        LangfuseConnectivityClassification.CONFIGURED_BUT_CONNECTIVITY_FAILED
    )
    assert result.failure_type == "auth_check_failed"
    assert result.trace_id is None
    assert sdk.spans == []
