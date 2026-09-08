# WS-E — 保障与可观测性

[English](WS_E_ASSURANCE_OBSERVABILITY.md)

负责范围：

- `src/assurance/**`
- `src/observability/**`
- `src/adapters/risc0/**`
- 保障测试

实现：

- 确定性复核
- 语义复核接口
- ReviewRecord
- ProofPolicy
- ProofAdapter 接口
- ReleaseGate
- NoopTraceAdapter
- 可选的 LangfuseTraceAdapter

Phase 1 必须将真实 ZK 标为 NOT_IMPLEMENTED，除非存在真实证明。

Langfuse 失败不得中断运行。

编写 `WORKSTREAM_REPORT_ASSURANCE.md`。
