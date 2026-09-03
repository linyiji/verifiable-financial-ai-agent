from __future__ import annotations

from contextlib import AbstractContextManager

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
from src.observability.langfuse_adapter import LangfuseSDKClient


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

    def create_event(self, *, name: str, metadata: dict) -> None:
        self.events.append((name, metadata))

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
    await hooks.emit(
        ObservationStage.TASK,
        "started",
        run_id="RUN-1",
        task_id="TASK-1",
        attributes=unsafe,
    )

    span_metadata = sdk.spans[0][1]
    event_metadata = sdk.events[0][1]
    for metadata in (span_metadata, event_metadata):
        assert metadata["api_key"] == "[REDACTED]"
        assert metadata["nested"]["authorization"] == "[REDACTED]"
        assert metadata["nested"]["safe"] == "kept"
        assert metadata["request_body"] == "[REDACTED]"
        assert metadata["messages"] == "[REDACTED]"
        assert metadata["normalized_value"] == "[REDACTED]"
        assert metadata["output"] == "[REDACTED]"
        assert "credential-value" not in str(metadata)


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
