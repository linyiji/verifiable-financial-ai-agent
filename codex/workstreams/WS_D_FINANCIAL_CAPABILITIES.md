# WS-D — Financial Capabilities

[简体中文](WS_D_FINANCIAL_CAPABILITIES.zh-CN.md)

Ownership:
- `src/capabilities/**`
- `src/tooling/**`
- `src/adapters/finrobot/**`
- financial tests

Implement:
- CapabilityRegistry
- NativeToolBackend
- MCPToolBackend interface
- GeneratedToolBackend interface
- revenue_growth
- ebitda_margin
- CalculationRecord creation
- deterministic tests
- FinRobot adapter interface

Rules:
- official deterministic numbers only here
- Accepted Evidence required
- do not import FinRobot randomly in Agent code

Write `WORKSTREAM_REPORT_FINANCIAL.md`.
