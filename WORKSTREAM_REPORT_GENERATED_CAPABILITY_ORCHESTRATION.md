# WS-U1 — Generated Capability Orchestration

## Scope

Implemented the governed orchestration and Code Builder boundary only. Static analysis, Docker
sandbox execution, financial validation internals, scoped-registry storage, and PostgreSQL
persistence remain injected ports owned by their respective workstreams.

## Runtime path

```text
Task (RUNNING)
→ assigned Skill capability request
→ scoped/global registry lookup
→ NOT FOUND
→ CapabilityGapRecord + WAITING_FOR_CAPABILITY
→ Research Lead SPEC approval
→ bounded CapabilityBuildRequest
→ TeamoRouterCodeBuilder via owned LLMProvider
→ U2/U3 validation handoff
→ Research Lead ACTIVATION approval
→ TASK_APPROVED scoped registration
→ ACTIVE_FOR_SCOPE lookup
→ same Task READY → RUNNING
```

The build does not create or mutate a Research Task or dependency graph node. Specialist request
schemas contain no approval or registration authority. Generated capabilities can only be
registered for `TASK` or `RUN` scope, never into the global native registry.

## Observability and safety

- Code generation uses the existing `LLMProvider` abstraction and requires provider identity
  `teamorouter`; no direct OpenAI/HTTP client was added.
- Langfuse integration uses the owned `TraceAdapter` boundary and is fail-open.
- Trace and RuntimeEvent payloads contain model/provider/latency/token metadata and SHA-256 only.
- Generated source, tests, prompts, responses, secrets, environment, and chain-of-thought are not
  emitted to observability.
- Generated source is never imported, compiled, executed, or persisted by WS-U1.

## Failure semantics

Generation and validation attempts are bounded (default: 2). Each failed attempt emits
`capability.build_failed`; validation failures additionally emit `capability.test_failed`. Exhaustion
sets the original task to `CAPABILITY_BUILD_FAILED` and raises `CapabilityBuildFailedError` with
safe audit records.

## CONTRACT_CHANGE_REQUEST — WS-U1-001

The shared `src/runtime/lifecycle.py` transition table predates the Phase 3 `TaskStatus` values.
Coordinator should extend it so the generic runtime understands at least:

- `RUNNING → WAITING_FOR_CAPABILITY`
- `WAITING_FOR_CAPABILITY → READY | CAPABILITY_BUILD_FAILED | CANCELLED`
- an explicit policy for recovery/terminal transitions from `CAPABILITY_BUILD_FAILED`

The scheduler should also recognize `CAPABILITY_BUILD_FAILED` when handling terminal failures, so
it does not attempt an invalid legacy `transition_task(..., FAILED)` after U1 raises. WS-U1 did not
modify these shared runtime contracts; its tightly scoped coordinator enforces the temporary
`RUNNING → WAITING_FOR_CAPABILITY → READY → RUNNING` path locally.

## Verification

- Focused generated-capability tests: 9 passed.
- Unit + financial + focused runtime integration regression: 151 passed after this addition.
- Ruff and `git diff --check`: PASS.
