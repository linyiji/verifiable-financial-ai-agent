# WS-F — 规范记录与输出

[English](WS_F_OUTPUT_CANONICAL.md)

负责范围：

- `src/output/**`
- 仅在基础工作委派时负责规范执行领域模型
- 输出测试

实现：

- CanonicalExecutionRecord 构建器
- ReleasedResearchResult
- FinancialReviewView 投影
- ExecutionDetails 投影
- FinancialReport 数据模型
- ObjectWritebackProposal

测试：

- B/C 使用相同的规范记录 ID
- 不从独立来源重复计算
- 保留判断与事实的区别

编写 `WORKSTREAM_REPORT_OUTPUT.md`。
