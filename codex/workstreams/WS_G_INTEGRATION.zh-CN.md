# WS-G — 集成

[English](WS_G_INTEGRATION.md)

负责范围：

- `src/application/**`
- API 编排
- 集成测试
- 验收测试

前置条件：

A–F 所有工作流均已合并，并通过模块门禁。

集成：

```text
POST object
→ prepare run
→ scheme generation
→ confirm
→ planner
→ runtime
→ parallel tasks
→ evidence
→ deterministic calculations
→ self-correction
→ replan child task
→ review
→ canonical record
→ released result
→ SSE complete
```

不得通过在 API 路由内重复逻辑来绕过模块。

运行完整的集成与验收测试套件。

编写 `WORKSTREAM_REPORT_INTEGRATION.md`。
