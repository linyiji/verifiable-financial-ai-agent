from __future__ import annotations

from contextlib import AbstractContextManager

import pytest

from src.infrastructure.config.settings import LangfuseSettings
from src.observability import (
    InMemoryTraceReferenceRepository,
    NoopTraceAdapter,
    ObservationStage,
    RuntimeInstrumentation,
    TraceAdapterClassification,
    create_langfuse_trace_adapter,
)
from src.observability.langfuse_adapter import LangfuseSDKClient


class FakeSpan:
    def __init__(self, trace_id: str, span_id: str) -> None:
        self.trace_id = trace_id
        self.span_id = span_id


class FakeSpanManager(AbstractContextManager):
    def __init__(self, span: FakeSpan) -> None:
        self.span = span
        self.exited = False

    def __enter__(self) -> FakeSpan:
        return self.span

    def __exit__(self, *args: object) -> None:
        self.exited = True


class FakeLangfuseSDK:
    def __init__(self) -> None:
        self.spans: list[tuple[str, dict, FakeSpanManager]] = []
        self.events: list[tuple[str, dict]] = []

    def start_as_current_span(self, *, name: str, metadata: dict) -> FakeSpanManager:
        index = len(self.spans) + 1
        manager = FakeSpanManager(FakeSpan(f"trace-{index}", f"span-{index}"))
        self.spans.append((name, metadata, manager))
        return manager

    def create_event(self, *, name: str, metadata: dict) -> None:
        self.events.append((name, metadata))


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
        "host": "https://langfuse.invalid",
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
async def test_all_required_stages_are_instrumented_and_persist_only_trace_refs() -> None:
    sdk = FakeLangfuseSDK()
    build = create_langfuse_trace_adapter(
        settings(public="public-sentinel", secret="secret-sentinel"),
        sdk_factory=lambda **kwargs: sdk,
    )
    references = InMemoryTraceReferenceRepository()
    hooks = RuntimeInstrumentation(build.adapter, reference_repository=references)

    root_stages = {
        ObservationStage.RUN: hooks.run(run_id="RUN-1"),
        ObservationStage.PLANNING: hooks.planning(run_id="RUN-1"),
        ObservationStage.SCHEME: hooks.scheme(run_id="RUN-1"),
        ObservationStage.REVIEW: hooks.review(run_id="RUN-1"),
    }
    task_stages = {
        ObservationStage.TASK: hooks.task(run_id="RUN-1", task_id="TASK-1"),
        ObservationStage.AGENT: hooks.agent(run_id="RUN-1", task_id="TASK-1"),
        ObservationStage.SKILL: hooks.skill(run_id="RUN-1", task_id="TASK-1"),
        ObservationStage.TOOL: hooks.tool(run_id="RUN-1", task_id="TASK-1"),
        ObservationStage.CALCULATION: hooks.calculation(run_id="RUN-1", task_id="TASK-1"),
        ObservationStage.SELF_CORRECTION: hooks.self_correction(run_id="RUN-1", task_id="TASK-1"),
        ObservationStage.REPLAN: hooks.replan(run_id="RUN-1", task_id="TASK-1"),
    }
    for stage, manager in {**root_stages, **task_stages}.items():
        async with manager as span:
            assert span.trace_id.startswith("trace-")
        assert sdk.spans[-1][0] == f"vfas.{stage.value}"

    refs = await references.list_by_run("RUN-1")
    assert {reference.stage for reference in refs} == {stage.value for stage in ObservationStage}
    assert all(reference.trace_id.startswith("trace-") for reference in refs)
    assert all(not hasattr(reference, "metadata") for reference in refs)
    assert all(manager.exited for _, _, manager in sdk.spans)


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


def test_sdk_bridge_repr_and_event_mapping_are_secret_free() -> None:
    sdk = FakeLangfuseSDK()
    bridge = LangfuseSDKClient(sdk)
    span = bridge.start_span(name="vfas.run", attributes={"run_id": "RUN-1"})
    bridge.create_event(name="vfas.run.started", attributes={"run_id": "RUN-1"})
    span.end()

    assert repr(bridge) == "LangfuseSDKClient(configured=True)"
    assert sdk.spans[0][0] == "vfas.run"
    assert sdk.events[0][0] == "vfas.run.started"
