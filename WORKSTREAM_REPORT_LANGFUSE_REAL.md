# WS-S — Langfuse Real Integration Report

## Outcome

**PASS** for the WS-S module gate. The official Langfuse Python SDK connected to the Japan data
region, authenticated, created the required smoke root/span, and flushed successfully. Runtime
tracing remains fail-open and persists identifiers only.

## Runtime and real smoke evidence

| Item | Result |
|---|---|
| Unified Settings credentials | configured (values never read outside adapter construction) |
| Endpoint gate | `https://jp.cloud.langfuse.com` |
| Official SDK | `langfuse==3.15.0` installed into the shared Python 3.11 venv |
| Classification | `CONNECTED` |
| Root name | `verifiable-financial-agent-smoke-test` |
| Child span | `backend-connectivity` |
| Trace ID | `b2f5e49bfbd4831c2c9d428fd00bbd08` |
| Root observation ID | `450d8ab67c7f0c5a` |
| Child observation ID | `a8792635afad0553` |
| Flush | `true` |

The ignored result artifact contains only the same classification, IDs, flush flag, and null
failure type. No key, key preview/hash, Authorization header, prompt, request body, provider body,
or financial value was printed or stored. The SDK install used the dependency already declared by
the `langfuse` optional extra; `pyproject.toml` was not changed.

## TRACE-001 through TRACE-012

| ID | Requirement | Result | Evidence |
|---|---|---|---|
| TRACE-001 | Unified Settings and Japan endpoint | PASS | factory accepts injected `LangfuseSettings`; smoke rejects a non-Japan endpoint before network activity |
| TRACE-002 | Official SDK real connection | PASS | official SDK `auth_check()` returned true against Japan |
| TRACE-003 | Required smoke root/span/flush | PASS | public trace and observation IDs above; flush returned normally |
| TRACE-004 | One Research Run = one root trace | PASS | `research_run()` owns the active root; tests prove all nested observations share its trace ID |
| TRACE-005 | LLM work uses native generation observations | PASS | Scheme and Planner map to SDK v3 `start_as_current_generation`, not ordinary spans |
| TRACE-006 | Real LLM provenance | PASS | requested/actual model, provider, measured latency, response token counts, and optional cost are supported; missing fields are omitted/null, never fabricated |
| TRACE-007 | Task observation | PASS | task-scoped hook and identifier persistence implemented |
| TRACE-008 | Evidence observation volume/content control | PASS | one task/batch summary; only counts/providers/periods/field names/status counts; no raw or normalized values |
| TRACE-009 | Agent/Skill/Tool/Calculation | PASS | nested hooks implemented and tested under the run root |
| TRACE-010 | Correction/Replan | PASS | task-scoped hooks implemented and tested |
| TRACE-011 | Review/Release | PASS | run-scoped hooks implemented and tested |
| TRACE-012 | Fail-open and durable handoff boundary | PASS | runtime exposes `TRACE_DEGRADED`; repository stores/list only trace reference identifiers |

## Observation types

- Langfuse span observations: Run root, Task, Evidence batch, Agent, Skill, Tool, Calculation,
  Correction, Replan, Review, Release.
- Langfuse generation observations: Scheme LLM and Planner LLM.
- Event observations remain available for low-cardinality stage events.

The legacy `PLANNING`, `SCHEME`, and `SELF_CORRECTION` hooks remain for compatibility, but the new
Coordinator-facing run handle uses the explicit generation/correction stages above.

## LLM provider wrapper and provenance semantics

`InstrumentedLLMProvider(delegate, trace=run_trace, stage=...)` is a structural `LLMProvider`
wrapper. It does not inspect or upload messages or structured output. It measures elapsed latency
around the real delegated request, then reads these fields from the actual
`LLMStructuredResponse`: `requested_model`, `actual_model`, `provider`, `input_tokens`, and
`output_tokens`. `total_tokens` is computed only when both response counts exist. Cost is omitted
because the current provider response has no cost field.

The generation API also supports explicit completion when a different provider wrapper is used:

```python
async with run.scheme_generation(attributes={"schema_name": schema_name}) as generation:
    response = await provider.complete_structured(...)
    await run.complete_generation(
        generation,
        requested_model=response.requested_model,
        actual_model=response.actual_model,
        provider=response.provider,
        latency_ms=measured_latency_ms,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        total_tokens=total_tokens_or_none,
    )
```

Null token/cost data is not forwarded as SDK `usage_details`/`cost_details`. Prompt, messages,
request/response bodies, and output values are rejected by the sanitization boundary.

## Coordinator API

```python
build = create_langfuse_trace_adapter(settings.langfuse)
instrumentation = RuntimeInstrumentation(
    build.adapter,
    reference_repository=trace_reference_repository,
)

async with instrumentation.research_run(run_id=run_id, attributes=safe_run_metadata) as trace:
    scheme_provider = InstrumentedLLMProvider(
        provider,
        trace=trace,
        stage=ObservationStage.SCHEME_GENERATION,
    )
    planner_provider = InstrumentedLLMProvider(
        provider,
        trace=trace,
        stage=ObservationStage.PLANNER_GENERATION,
    )
    # Execute Scheme, Planner, Task/Evidence batch, Agent/Skill/Tool/Calculation,
    # Correction/Replan, Review and Release while this context remains active.

await instrumentation.flush()
trace_status = instrumentation.status
trace_refs = await trace_reference_repository.list_by_run(run_id)
```

`ResearchRunTrace.trace_id` and `root_observation_id` are available during the run. The
Coordinator/Canonical builder should store only `TraceReference.reference_id` values returned by
`list_by_run(run_id)`.

## Fail-open behavior

Span start/end, generation start/update/end, event, flush, and trace-reference repository failures
are contained. Business exceptions still propagate unchanged. Observability errors append only an
operation and exception type to the in-process degradation list; they never include provider error
text or payload. `RuntimeInstrumentation.status` changes to `TRACE_DEGRADED` without failing the
Research Run.

## Verification

```text
Focused tests: 10 passed
Full suite: 152 passed, 1 skipped (PostgreSQL service unavailable), 1 dependency warning
Ruff check: PASS
Ruff format check: PASS
compileall: PASS
git diff --check: PASS
Secret/artifact boundary scan: PASS
```

## Ownership and boundary review

- Changes are limited to `src/observability/**`, the WS-S test, smoke script, and this report.
- Settings schema, `pyproject.toml`, domain/contracts/enums, application service/execution,
  `apps/api/main.py`, and `PARALLEL_EXECUTION_STATUS.md` are unchanged.
- `.env.local` and the smoke artifact remain ignored and untracked.
- No shared contract or dependency change is required.

## Known integration gap

The existing application service opens Scheme/Planner work outside its current run span. WS-S was
explicitly forbidden from editing that service. Coordinator integration must adopt the
`research_run()` lifetime and wrap both real LLM providers as shown above. Until that merge-time
wiring is made, the new API is tested and real connectivity is proven, but the existing service
path does not yet emit the complete single-root production Research Run.
