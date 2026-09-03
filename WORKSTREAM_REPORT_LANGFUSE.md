# WS-L — Langfuse Integration Report

## Outcome

**PASS** for the Phase-2 WS-L module gate.

Langfuse is implemented as optional, fail-open technical observability. It does not become a Task,
Agent Tool, business repository, assurance authority, or Canonical Execution Record. Coordinator
can compose the reusable hooks without moving business logic into the observability layer.

## Current environment classification

| Field | Result |
|---|---|
| Langfuse credentials | `NOT_CONFIGURED` |
| Optional SDK in current shared virtualenv | not installed |
| Factory classification | `NOT_CONFIGURED` |
| Active adapter | `NoopTraceAdapter` |
| Real connectivity | `DEFERRED / NOT_CONFIGURED` |

This is the expected non-failure state. The factory does not import or initialize the SDK unless
both injected credentials are present.

## Delivered implementation

| File | Responsibility |
|---|---|
| `src/observability/langfuse_adapter.py` | real optional SDK bridge, settings-driven factory, safe classifications |
| `src/observability/instrumentation.py` | reusable Run-to-Review instrumentation hooks |
| `src/observability/references.py` | identifier-only trace-reference persistence bridge |
| `src/observability/safety.py` | recursive metadata sanitization |
| `src/observability/noop.py` | existing fail-open and Noop behavior, reused unchanged |
| `src/observability/tracing.py` | existing TraceAdapter protocol, reused unchanged |
| `tests/unit/observability/test_langfuse_integration.py` | factory, stages, safety, SDK mapping, fail-open, reference tests |

## Factory behavior

`create_langfuse_trace_adapter` receives `LangfuseSettings`; it never reads environment files.

| Condition | Classification | Adapter |
|---|---|---|
| one or both credentials absent | `NOT_CONFIGURED` | Noop |
| both credentials present, SDK unavailable | `SDK_NOT_INSTALLED` | Noop |
| SDK construction fails | `INITIALIZATION_FAILED` | Noop |
| credentials and SDK available | `ENABLED` | `FailOpenTraceAdapter(LangfuseTraceAdapter(...))` |

The existing `build_trace_adapter(client)` API remains backward compatible for Foundation callers
and tests.

## Real SDK boundary

`LangfuseSDKClient` wraps the optional OpenTelemetry-based SDK without importing it at module load.
It maps:

- `start_as_current_span(name=..., metadata=...)` to the project `span` context;
- `create_event(name=..., metadata=...)` to project events; and
- SDK trace/span identifiers to safe handles for reference persistence.

The bridge has a secret-free representation. Initialization and runtime failures are contained by
the factory and `FailOpenTraceAdapter`.

## Instrumented stages

`RuntimeInstrumentation` provides reusable context hooks for every required stage:

1. Run
2. Planning
3. Scheme
4. Task
5. Agent
6. Skill
7. Tool
8. Calculation
9. Self-Correction
10. Replan
11. Review

It also exposes stage-scoped events. Coordinator owns where hooks are wired; WS-L does not edit the
application or API composition root.

## Metadata and secret safety

Sanitization occurs at both the high-level hook and Langfuse adapter boundary. Credential-shaped
keys—including API keys, authorization, passwords, public/private keys, access/refresh tokens, and
secrets—are replaced with `[REDACTED]`. `SecretStr` values are always redacted. Unsupported Python
objects become type placeholders rather than potentially unsafe string representations.

No prompt, provider response, credential, environment preview, or raw business artifact is stored
by this implementation.

## Trace-reference persistence bridge

`TraceReferenceRepository` stores only:

- project reference ID;
- run ID;
- instrumentation stage;
- Langfuse trace ID;
- optional span ID;
- optional task ID; and
- safe tags.

The included in-memory repository demonstrates the contract. Repository failures are fail-open.
Canonical output can consume these reference IDs later without using Langfuse as the business
source of truth.

## Verification

```text
$ PYTHONPATH=. python -m pytest -q tests/unit/assurance/test_tracing.py tests/unit/observability
9 passed

$ PYTHONPATH=. python -m pytest -q
84 passed, 2 dependency deprecation warnings in 0.73s

$ PYTHONPATH=. python -m ruff check .
All checks passed!

$ PYTHONPATH=. python -m ruff format --check src/observability/__init__.py \
  src/observability/langfuse_adapter.py src/observability/instrumentation.py \
  src/observability/references.py src/observability/safety.py tests/unit/observability
PASS

$ PYTHONPATH=. python -m compileall -q src/observability
PASS

$ git diff --check
PASS
```

The two warnings originate in the installed FastAPI/Starlette TestClient dependency surface.

## Module gate coverage

| Gate | Result |
|---|---|
| both credentials required before SDK construction | PASS |
| no credentials selects Noop | PASS |
| optional SDK missing classification | PASS |
| SDK initialization failure classification | PASS |
| all 11 required stages observed | PASS |
| events mapped to SDK | PASS |
| metadata secrets redacted | PASS |
| SDK runtime failure does not break business work | PASS |
| trace-reference persistence failure does not break business work | PASS |
| only trace/span references cross into repository bridge | PASS |
| legacy Foundation trace tests remain green | PASS |
| real connectivity | DEFERRED / NOT_CONFIGURED |

## Ownership and contract gate

- Modified implementation only under `src/observability/**`.
- Added WS-L tests only under `tests/unit/observability/**`.
- Added this required workstream report.
- Settings, `pyproject.toml`, domain contracts/enums, `apps/api/main.py`, and
  `PARALLEL_EXECUTION_STATUS.md` are unchanged.
- Secret scan of changed implementation/tests/report: PASS.

## Existing logic reuse

| Existing module | Decision | Method | Action |
|---|---|---|---|
| `TraceAdapter` | DIRECT_REUSE | instrumentation dependency | keep frozen |
| `NoopTraceAdapter` | DIRECT_REUSE | unconfigured behavior | preserve |
| `FailOpenTraceAdapter` | DIRECT_REUSE | runtime failure containment | preserve |
| `LangfuseTraceAdapter` | ADAPTER_REUSE | extend metadata safety and SDK bridge | adapt |
| `LangfuseSettings` | DIRECT_REUSE | constructor injection | keep frozen |
| Canonical `trace_refs` | ADAPTER_REUSE | identifier-only bridge | Coordinator wires later |

## Contract changes and deviations

**NONE.** No shared contract change is required.

## Deferred

- Real Langfuse connectivity, because credentials are not configured.
- Installing the optional SDK in the current shared environment; the existing `langfuse` optional
  dependency remains unchanged.
- Coordinator composition into application runtime and persistence implementation for the
  `TraceReferenceRepository` protocol.
