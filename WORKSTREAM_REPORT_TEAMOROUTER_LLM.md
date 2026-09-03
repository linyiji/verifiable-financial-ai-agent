# WS-K — TeamoRouter LLM Integration Report

## Outcome

**PASS** for the Phase-2 WS-K module gate.

The implementation adds an injected, OpenAI-compatible TeamoRouter boundary and integrates it only
with Research Scheme generation and Research Lead initial planning. Existing deterministic
generators remain the terminal safety fallback. No financial capability, CalculationRecord,
runtime, assurance, API route, domain contract, settings definition, or package baseline was
modified.

## Runtime and route

| Field | Result |
|---|---|
| Python | `3.11.16` |
| Provider | `teamorouter` |
| Requested primary model | `gpt-5.6-sol` |
| Configured fallback model | `gpt-5.6-luna` |
| API style | OpenAI-compatible `/chat/completions` |
| Structured output | Pydantic-generated JSON Schema with strict response format |
| Credentials | injected `SecretStr`; never returned, logged, persisted, or committed |

The client records provider, requested model, actual response model, attempted model names,
request ID, and token counts when returned. Public representations contain only non-secret routing
metadata.

## Delivered files

| Path | Responsibility |
|---|---|
| `src/adapters/llm/provider.py` | provider protocol, safe structured result, classified errors |
| `src/adapters/llm/teamorouter.py` | OpenAI-compatible TeamoRouter client and model routing |
| `src/adapters/llm/__init__.py` | public adapter exports |
| `src/agentic/llm_integration.py` | SchemeGenerator and Research Lead Planner structured adapters |
| `tests/unit/llm/test_teamorouter.py` | provider routing/error/secret-safety tests |
| `tests/unit/llm/test_agentic_llm_integration.py` | Scheme/Planner validation/retry/fallback tests |

## Model fallback policy

The primary route always requests `gpt-5.6-sol`. `gpt-5.6-luna` is used only when:

- the provider times out;
- a network/provider availability error occurs;
- HTTP `408`, `429`, or `5xx` is returned; or
- the caller explicitly sets the fallback policy flag.

HTTP request/auth errors and malformed structured content do **not** switch models. Structured or
semantic validation failure retries the same configured route, up to the bounded validation count,
before selecting the existing deterministic Scheme/Planner implementation.

## Agentic structured boundaries

### SchemeGenerator

`TeamoRouterSchemeGenerator.generate` satisfies the existing async SchemeGenerator shape. Its
schema permits research scope, data/agent/skill/calculation requirements, boolean assurance rules,
report requirements, and limitations. It rejects numeric values and requires:

- accepted evidence only;
- deterministic financial values; and
- CalculationRecords for reported calculable values.

It cannot author a financial number or CalculationRecord.

### ResearchLeadPlanner

`TeamoRouterResearchLeadPlanner.plan` produces task proposals with symbolic keys. Integration maps
those keys to run-scoped task IDs, validates unique keys, known dependencies, acyclicity, complete
confirmed-Scheme skill coverage, and finally constructs the frozen `PlannedTaskGraph`, invoking its
domain validation.

Both adapters return `StructuredAgentDecision` audit records through `*_with_decision`, retain them
in their decision audit list, and expose safe `LLMExecutionAudit` routing metadata. Decision
summaries state the validation outcome and model route only; prompts do not request and records do
not store hidden chain-of-thought.

## Deterministic fallback evidence

Tests cover:

- semantic Scheme validation failure followed by a same-route structured retry;
- provider exhaustion followed by deterministic Scheme generation;
- cyclic graph rejection and bounded retries followed by deterministic Lead planning; and
- preservation of the confirmed-Scheme and initial-graph domain guards.

## Sanitized real acceptance

Credentials were available through the ignored local settings file. Live calls were executed
without printing or saving any credential material. Sanitized evidence is stored only in ignored
`artifacts/phase2/teamorouter/live_acceptance.json`.

| Call | Provider | Requested model | Actual model | Structured validation | Result |
|---|---|---|---|---|---|
| Scheme | teamorouter | gpt-5.6-sol | none | deterministic fallback | PASS_WITH_DETERMINISTIC_FALLBACK after bounded provider unavailability |
| Planner | teamorouter | gpt-5.6-sol | gpt-5.6-sol | PASS | 10-task graph passed schema, dependency, acyclic, skill-coverage, and domain validation |

An additional independent Scheme retry was bounded and cancelled after approximately 60 seconds
without a response so the module gate would not wait indefinitely. It produced no committed or
user-visible provider content.

## Test and gate results

```text
$ PYTHONPATH=. python -m pytest -q tests/unit/llm
10 passed

$ PYTHONPATH=. python -m pytest -q
87 passed, 2 dependency deprecation warnings

$ PYTHONPATH=. python -m ruff check .
All checks passed!

$ PYTHONPATH=. python -m compileall -q src/adapters/llm src/agentic/llm_integration.py
PASS

$ git diff --check
PASS
```

The warnings originate from the installed FastAPI/Starlette TestClient dependency surface, not
WS-K.

## Secret and ownership gate

- `.env.local` remains ignored and unmodified.
- No credential value, prefix, hash, preview, request authorization header, or raw provider payload
  is in tracked artifacts or the report.
- Secret scan of WS-K production/report paths: PASS.
- Owned implementation paths only: PASS.
- Frozen Settings, `pyproject.toml`, domain contracts/enums, `apps/api/main.py`, and
  `PARALLEL_EXECUTION_STATUS.md`: unchanged.

## Existing logic reuse

| Existing module | Decision | Method | Action |
|---|---|---|---|
| `DeterministicSchemeGenerator` | DIRECT_REUSE | terminal fallback | preserve |
| `ResearchLeadPlanner` | DIRECT_REUSE | terminal fallback | preserve |
| `ResearchSchemeSnapshot` | DIRECT_REUSE | validated output contract | keep frozen |
| `PlannedTaskGraph` / `Task` | DIRECT_REUSE | validated output contract | keep frozen |
| `StructuredAgentDecision` | DIRECT_REUSE | safe audit decision | keep frozen |
| `LLMSettings` | DIRECT_REUSE | constructor injection | keep frozen |

## Contract changes and deviations

**NONE.** No shared contract change is required for WS-K.

## Deferred

- Application composition may choose these adapters in a later integration workstream.
- Specialist agents, financial capabilities, report prose, semantic review, and other LLM routes
  remain outside WS-K.
- Provider request persistence is limited to sanitized audit metadata; raw prompts/responses are not
  persisted by this workstream.
