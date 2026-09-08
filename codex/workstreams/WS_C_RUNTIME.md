# WS-C — Dynamic Runtime

[简体中文](WS_C_RUNTIME.zh-CN.md)

Ownership:
- `src/runtime/**`
- runtime/event integration tests
- SSE route only if foundation assigns it

Implement:
- RuntimeState
- Planned/Actual graph
- dependency scheduler
- asyncio parallel execution
- Task lifecycle
- retry
- graph mutation API
- checkpoint interface
- RuntimeEvent persistence
- monotonic event sequence
- SSE replay / heartbeat

Do not:
- decide financial formulas
- perform semantic analysis
- let Specialist mutate graph directly

Write `WORKSTREAM_REPORT_RUNTIME.md`.
