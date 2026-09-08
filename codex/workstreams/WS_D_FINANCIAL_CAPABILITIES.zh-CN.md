# WS-D — 财务能力

[English](WS_D_FINANCIAL_CAPABILITIES.md)

负责范围：

- `src/capabilities/**`
- `src/tooling/**`
- `src/adapters/finrobot/**`
- 财务测试

实现：

- CapabilityRegistry
- NativeToolBackend
- MCPToolBackend 接口
- GeneratedToolBackend 接口
- revenue_growth
- ebitda_margin
- 创建 CalculationRecord
- 确定性测试
- FinRobot 适配器接口

规则：

- 正式确定性数字只能在此生成
- 必须使用已接受证据
- 不得在 Agent 代码中随意导入 FinRobot

编写 `WORKSTREAM_REPORT_FINANCIAL.md`。
