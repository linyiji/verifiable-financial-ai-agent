"""Opt-in bounded metadata spans. Never part of authoritative product events.

No per-span I/O. A run-end/shutdown flush writes a snapshot off the event loop.
The allowlist deliberately excludes arbitrary attributes, URLs, errors and bodies.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from time import perf_counter_ns
from uuid import uuid4

_context: ContextVar[dict | None] = ContextVar("performance_context", default=None)
_parent: ContextVar[str | None] = ContextVar("performance_parent", default=None)
_logical: ContextVar[str | None] = ContextVar("performance_logical", default=None)
_active: ContextVar[span | None] = ContextVar("performance_active", default=None)
_recorder: Recorder | None = None
_ID = re.compile(r"(?:RUN|EVT)-[A-Za-z0-9-]+(?::[A-Za-z0-9_-]+)?\Z")
_MODEL = re.compile(r"(?:gpt|mimo|claude|gemini|test)[A-Za-z0-9._:/-]{0,90}\Z")
_NUMBERS = {
    "attempt_number",
    "event_sequence",
    "http_status",
    "input_tokens",
    "output_tokens",
    "configured_delay_s",
}
_ACTORS = {
    "fundamental_analyst",
    "peer_analyst",
    "research_news_analyst",
    "valuation_analyst",
    "risk_analyst",
    "research_lead",
    "evidence_pipeline",
    "research_analyst",
}


class Recorder:
    def __init__(self, path: Path | None = None, *, limit: int = 20000, forbidden_values=()):
        self.path = path
        self.limit = limit
        self.forbidden_values = tuple(v for v in forbidden_values if v)
        self.session_id = str(uuid4())
        self.records: list[dict] = []
        self.dropped = 0
        self.flush_failed = False

    def safe(self, key, value):
        if isinstance(value, str) and any(v in value for v in self.forbidden_values):
            return None
        if key in _NUMBERS:
            return value if type(value) in (int, float) and 0 <= value < 10**15 else None
        if key in {"run_id", "task_id", "event_id"}:
            return value if isinstance(value, str) and _ID.fullmatch(value) else None
        if key == "actor":
            return value if isinstance(value, str) and value in _ACTORS else None
        if key == "provider":
            return (
                value
                if isinstance(value, str) and value in {"teamorouter", "mimo", "fmp"}
                else None
            )
        if key in {"requested_model", "attempted_model", "actual_model"}:
            return value if isinstance(value, str) and _MODEL.fullmatch(value) else None
        if key in {"actual_model_reported", "result_present"}:
            return value if type(value) is bool else None
        if key == "run_status":
            return (
                value
                if isinstance(value, str)
                and value in {"CREATED", "RUNNING", "REVIEW", "RELEASED", "FAILED", "CANCELLED"}
                else None
            )
        if key == "transport_outcome":
            return value if value in {"TIMEOUT", "NETWORK_ERROR", "RESPONSE"} else None
        return None

    def append(self, record):
        if len(self.records) < self.limit:
            self.records.append(record)
        else:
            self.dropped += 1

    def snapshot(self):
        return {
            "schema_version": "runtime-performance/v1",
            "session_id": self.session_id,
            "dropped_spans": self.dropped,
            "flush_failed": self.flush_failed,
            "provider_inference_time": "NOT_OBSERVED",
            "provider_queue_time": "NOT_OBSERVED",
            "records": list(self.records),
        }

    async def flush(self):
        if self.path is None:
            return
        snapshot = self.snapshot()

        def write():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(f".{self.session_id}.tmp")
            temporary.write_text(json.dumps(snapshot, separators=(",", ":")) + "\n")
            temporary.replace(self.path)

        try:
            await asyncio.to_thread(write)
        except Exception:
            self.flush_failed = True  # Diagnostic I/O must never break the Run.


def configure(recorder: Recorder | None):
    global _recorder
    _recorder = recorder


def configure_from_environment(*, forbidden_values=()):
    path = os.environ.get("VFA_PERFORMANCE_PATH")
    configure(Recorder(Path(path), forbidden_values=forbidden_values) if path else None)


async def flush():
    if _recorder is not None:
        await _recorder.flush()


def annotate(**attributes):
    current = _active.get()
    if current is not None:
        current.set(**attributes)


def milestone(operation: str):
    with span(operation):
        pass


@asynccontextmanager
async def measured_lock(lock, operation: str):
    with span(operation):
        await lock.acquire()
    try:
        yield
    finally:
        lock.release()


class span:
    def __init__(self, operation: str, **attributes):
        self.recorder = _recorder
        self.operation = operation
        self.attributes = attributes

    def set(self, **attributes):
        if self.recorder is not None:
            for key, value in attributes.items():
                safe = self.recorder.safe(key, value)
                if safe is not None:
                    self.record[key] = safe

    def __enter__(self):
        if self.recorder is None:
            return self
        self.start = perf_counter_ns()
        self.record = {
            "span_id": str(uuid4()),
            "parent_span_id": _parent.get(),
            "logical_call_id": _logical.get(),
            "operation": self.operation,
            "start_utc": datetime.now(UTC).isoformat(),
            "start_monotonic_ns": self.start,
            "classification": "OBSERVED",
        }
        self.set(**(_context.get() or {}))
        self.set(**self.attributes)
        self.parent_token = _parent.set(self.record["span_id"])
        self.active_token = _active.set(self)
        self.logical_token = None
        if self.operation == "model.logical_call":
            self.record["logical_call_id"] = self.record["span_id"]
            self.logical_token = _logical.set(self.record["span_id"])
        if self.operation == "model.attempt":
            self.record["attempt_id"] = self.record["span_id"]
        return self

    def __exit__(self, typ, exc, tb):
        if self.recorder is None:
            return False
        end = perf_counter_ns()
        self.record.update(
            end_utc=datetime.now(UTC).isoformat(),
            end_monotonic_ns=end,
            duration_ms=(end - self.start) / 1e6,
            outcome="SUCCESS"
            if typ is None
            else "CANCELLED"
            if isinstance(exc, asyncio.CancelledError)
            else "FAILURE",
        )
        # Only owned enum values, never exception text/type supplied by a provider.
        from src.adapters.llm.provider import LLMFailureClassification

        failure = getattr(exc, "failure_classification", getattr(exc, "classification", None))
        if isinstance(failure, LLMFailureClassification):
            self.record["failure_code"] = failure.value
        elif isinstance(exc, TimeoutError):
            self.record["failure_code"] = "OWNED_TIMEOUT"
        _parent.reset(self.parent_token)
        _active.reset(self.active_token)
        if self.logical_token is not None:
            _logical.reset(self.logical_token)
        self.recorder.append(self.record)
        return False


def observe(
    operation: str,
    *,
    run: str | None = None,
    task: str | None = None,
    event: str | None = None,
    aggregate: str | None = None,
):
    """Decorate owned boundaries, with explicit identity parameters only."""

    def decorate(function):
        signature = inspect.signature(function)

        def enter(args, kwargs):
            bound = signature.bind(*args, **kwargs).arguments
            context = dict(_context.get() or {})
            if run and run in bound:
                context["run_id"] = bound[run]
            if task and task in bound:
                item = bound[task]
                context.update(run_id=item.run_id, task_id=item.task_id, actor=item.assigned_agent)
            if event and event in bound:
                item = bound[event]
                context.update(
                    run_id=item.run_id,
                    task_id=item.task_id,
                    event_id=item.event_id,
                    event_sequence=item.sequence,
                )
            if aggregate and aggregate in bound:
                context["run_id"] = bound[aggregate].run.run_id
            token = _context.set(context)
            attributes = {
                "attempt_number": bound.get("attempt"),
                "attempted_model": bound.get("model"),
            }
            if aggregate and aggregate in bound:
                value = bound[aggregate]
                attributes.update(
                    run_status=value.run.status.value,
                    result_present=value.artifacts.released_result is not None,
                )
            owner = bound.get("self")
            if operation.startswith("model."):
                attributes.update(
                    provider=getattr(owner, "provider_name", None),
                    requested_model=getattr(owner, "model_name", None),
                )
            return token, span(operation, **attributes)

        @wraps(function)
        async def asynchronous(*args, **kwargs):
            if _recorder is None:
                return await function(*args, **kwargs)
            token, timing = enter(args, kwargs)
            try:
                with timing:
                    result = await function(*args, **kwargs)
                    if operation == "data.http_attempt":
                        code = getattr(result, "error_code", None)
                        timing.set(
                            http_status=getattr(result, "http_status", None),
                            transport_outcome=code
                            if code in {"TIMEOUT", "NETWORK_ERROR"}
                            else "RESPONSE",
                        )
                    return result
            finally:
                _context.reset(token)
                if operation == "run.execution":
                    await flush()

        @wraps(function)
        def synchronous(*args, **kwargs):
            if _recorder is None:
                return function(*args, **kwargs)
            token, timing = enter(args, kwargs)
            try:
                with timing:
                    return function(*args, **kwargs)
            finally:
                _context.reset(token)

        return asynchronous if inspect.iscoroutinefunction(function) else synchronous

    return decorate
