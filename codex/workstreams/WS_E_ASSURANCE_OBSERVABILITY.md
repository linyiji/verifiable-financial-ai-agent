# WS-E — Assurance & Observability

[简体中文](WS_E_ASSURANCE_OBSERVABILITY.zh-CN.md)

Ownership:
- `src/assurance/**`
- `src/observability/**`
- `src/adapters/risc0/**`
- assurance tests

Implement:
- deterministic review
- semantic review interface
- ReviewRecord
- ProofPolicy
- ProofAdapter interface
- ReleaseGate
- NoopTraceAdapter
- optional LangfuseTraceAdapter

Phase 1 must mark real ZK as NOT_IMPLEMENTED unless a real proof exists.

Langfuse failure must not break run.

Write `WORKSTREAM_REPORT_ASSURANCE.md`.
