# WS-C — 动态运行时

[English](WS_C_RUNTIME.md)

负责范围：

- `src/runtime/**`
- 运行时/事件集成测试
- 仅在基础工作明确分配时负责 SSE 路由

实现：

- RuntimeState
- 计划图/实际图
- 依赖调度器
- asyncio 并行执行
- Task 生命周期
- 重试
- 图变更 API
- 检查点接口
- RuntimeEvent 持久化
- 单调事件序列
- SSE 重放/心跳

禁止：

- 决定财务公式
- 执行语义分析
- 让专家直接修改图

编写 `WORKSTREAM_REPORT_RUNTIME.md`。
