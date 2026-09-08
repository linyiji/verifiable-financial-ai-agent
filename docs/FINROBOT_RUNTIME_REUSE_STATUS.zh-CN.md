# FinRobot 运行时复用状态 — WS-T0

[English](FINROBOT_RUNTIME_REUSE_STATUS.md)

状态：**COMPLETE — ACTIVATION AUDIT**<br>
审计日期：2026-09-04<br>
固定上游提交：`d221910096de87579b02f8f0674652bf1a175f51`

## 范围与决策规则

这是针对当前主项目的定向激活审计，不是重复完整上游审计。下列上游路径均在固定提交上检查。
未修改或纳入任何上游文件。

`ACTIVE_REUSE` 要求具体的上游实现、本项目维护的适配器、已注册能力或渲染器、集成测试，
以及可达的生产调用路径。仅有审计条目、白名单条目、协议或上游源码，不符合要求。

## 运行时激活矩阵

| 模块 | 上游源码 | 分类 | 适配器 | 运行时活跃 | 已测试情况 | 下一操作 |
|---|---|---|---|---:|---|---|
| 财务数据处理器 | `finrobot_equity/core/src/modules/financial_data_processor.py`（`clean_financial_number`、提取器、`calculate_growth_and_forecasts`） | `PORT_PENDING` | 无；仅审计元数据 | 否 | Python 3.11 隔离导入／冒烟记录于 `FINROBOT_EXACT_AUDIT.md`；无项目运行时测试 | 仅在 Evidence 接受后移植不重叠的转换。预测必须使用显式假设并输出 CalculationRecord。原生营收增长率和 EBITDA 利润率保持权威。 |
| 同行聚合 | `finrobot_equity/core/src/modules/market_data_api.py`（`combine_peer_financial_data`、`project_ebitda_for_peers`） | `PORT_PENDING` | 无 | 否 | 仅有上游隔离同行预测冒烟 | 分离供应商获取与纯聚合。使用规范同行 Evidence；任何预测均必须保留 `FORECAST` 分类、假设、版本和 CalculationRecord 谱系。 |
| 技术指标 | `finrobot_equity/core/src/modules/market_data_api.py`（`get_technical_indicators`） | `PORT_PENDING` | 无 | 否 | Python 3.11 隔离导入；无本项目能力测试 | 从函数中提取确定性 SMA/RSI/MACD 公式。输入必须是有序已接受价格 Evidence，输出为数值 CalculationRecord；启发式标签成为 Judgment。不调用上游 FMP 获取代码。 |
| 图表生成器 | `finrobot_equity/core/src/modules/chart_generator.py`（已审查图表函数）；增强模块仍在白名单外 | `ADAPTER_READY_NOT_ACTIVE` | `src/adapters/finrobot/pinned.py`，操作 `charts.render` | 否 | `tests/unit/adapters/test_finrobot_audit.py` 使用 stub 后端通过；上游隔离图表冒烟通过 | 实现固定版本、无网络后端，以及读取规范报告数据、使用受控产物目录的发布后图表服务。激活前增加真实渲染器／集成测试。 |
| 专业 HTML 渲染器 | `finrobot_equity/core/src/modules/html_renderer.py`（`render_html_report`、`render_combined_html_report`） | `PORT_PENDING` | 无可执行适配器操作 | 否 | 仅上游隔离导入 | 添加本项目维护的 `ReleasedResearchResult`／规范报告映射器、转义和净化。渲染器只接收数据，绝不获取数据。 |
| 专业 PDF 渲染器 | `finrobot_equity/core/src/modules/professional_pdf_report.py`（`ProfessionalEquityReport`、`generate_professional_report`） | `PORT_PENDING` | 无可执行适配器操作。现有 `report.render_pdf` 白名单覆盖较旧的 `pdf_generator.py`，而非此专业渲染器。 | 否 | 旧 PDF 边界有 stub 适配器测试；专业渲染器无项目集成测试 | 审计并将精确专业符号加入白名单，映射规范报告数据，限制输出路径，执行真实 PDF 渲染验证。渲染期间不得访问供应商。 |
| 新闻／催化剂分析器 | `finrobot_equity/core/src/modules/news_integrator.py`；`finrobot_equity/core/src/modules/catalyst_analyzer.py` | `REFERENCE_ONLY` | 无 | 否 | 仅定向源码识别；无本项目适配器／运行时测试 | 只有现有真实 FMP Evidence 层提供已接受 News Evidence 后，才复用分类／提示词理念。不复用连接器／密钥处理，权限阻断时不生成催化剂。 |
| 敏感性分析器 | `finrobot_equity/core/src/modules/sensitivity_analyzer.py`（`SensitivityAnalyzer`） | `REJECTED` | 明确不在白名单；`PinnedFinRobotAdapter.calculate` 拒绝计算 | 否 | 隔离导入通过；财务语义已由先前审计拒绝 | 不按原样激活。未来本项目的确定性实现必须使用显式场景假设、Evidence 和 CalculationRecord 谱系，不得将固定波动率区间标为统计保障。 |
| 估值引擎 | `finrobot_equity/core/src/modules/valuation_engine.py`（`ValuationEngine`） | `REJECTED` | 明确不在白名单；计算路径拒绝它 | 否 | 隔离导入通过；隐式默认值已由先前审计拒绝 | 不按原样激活。任何未来估值能力都必须版本化重大假设，并经过 Financial Code、Evidence、CalculationRecord 和 Review。 |
| LLM 章节生成器 | `finrobot_equity/core/src/modules/text_generator_agents.py`（`generate_text_section`）与 `modules/equity_agents/*` | `REJECTED` | 无 | 否 | 无项目运行时测试 | 不得绕过 TeamoRouter、结构化输出校验、Langfuse、Agent/Skill 边界或 Review。可人工参考提示词／角色措辞，但直接客户端／回退生成器不是运行时组件。 |
| Agent 定义 | `finrobot/agents/agent_library.py`；`finrobot_equity/core/src/modules/equity_agents/*.py` | `REFERENCE_ONLY` | 无 | 否 | 无运行时导入或集成测试 | 仅通过本项目 Agent/Skill 契约复用角色分工和提示词理念。不要将上游 Agent 导入调度器。 |
| 旧版 AutoGen | `finrobot/agents/workflow.py`（`FinRobot`、`SingleAssistant*`、`MultiAssistant*`）以及旧演示／实验 | `REJECTED` | 无 | 否 | 无项目运行时测试 | 保持在运行时之外。它会重复本项目的规划器、依赖调度器、检查点、RuntimeEvent、重新规划和审查语义。 |
| FinRobot Web 编排器 | `finrobot_equity/web_app/main.py`（`execute_analysis_pipeline`、FastAPI 路由）和 `run_web_app.py` | `REJECTED` | 无 | 否 | 无项目运行时测试 | 不激活。前端已延后；其子进程／文件日志流水线重复本项目 API／运行时，执行供应商／报告编排，不符合当前契约。 |

## ACTIVE_REUSE 证据

当前主分支上的 FinRobot `ACTIVE_REUSE` 模块数为**零**。

可达的财务运行时为：

```text
Research Task
→ IntegratedTaskExecutor
→ ToolRuntime
→ CapabilityRegistry
→ NativeToolBackend
→ RevenueGrowthCapability / EbitdaMarginCapability
```

注册表仅包含 `revenue_growth` 和 `ebitda_margin`。没有 Skill、Task、Capability、
服务、API 路由或发布渲染器构造 `PinnedFinRobotAdapter`。

当前 FinRobot 边界停留在非活跃协议路径：

```text
prospective caller
→ PinnedFinRobotAdapter.execute(operation)
→ FinRobotBackend.invoke(audited entry, copied inputs)
→ [no concrete backend exists]
```

因此，没有可如实列出的 FinRobot `capability_id` 或真实上游运行时调用路径。
两个白名单操作（`charts.render`、`report.render_pdf`）是安全边界已就绪的适配器契约，
不是活跃复用。

## 建议激活顺序

1. **图表** — 在具体固定版本、无网络后端之后激活已在白名单的基础图表函数。
   只使用经过审查的规范数据。
2. **专业 HTML 渲染器** — 在严格规范报告 DTO 和 HTML 净化边界之后移植；绝不获取数据。
3. **专业 PDF 渲染器** — 单独审计／将专业实现加入白名单，映射同一规范 DTO，
   限制资源路径，并对输出进行视觉验证。
4. **技术指标** — 只将纯公式移植为处理已接受历史价格 Evidence 的确定性财务代码，
   生成 CalculationRecord。
5. **同行聚合辅助函数** — 移植纯透视／聚合代码。同行获取保留在现有真实 FMP Evidence 层，
   预测仍受显式假设约束。

## 保留的护栏

- 不激活 FinRobot FMP 连接器；真实 FMP Evidence 仍是唯一供应商路径。
- 估值和敏感性代码不能绕过 Financial Code、Evidence、CalculationRecord、Review
  或 CanonicalExecutionRecord。
- 渲染器只可使用 `ReleasedResearchResult` 或规范报告数据，不可获取数据。
- 不修改、复制 FinRobot 上游源码到项目中，也不将其置于主导入路径。
- 前端保持延后。

## 验证

- 固定提交常量等于要求的上游提交：PASS。
- 定向上游检出解析为精确提交：PASS。
- `tests/unit/adapters/test_finrobot_audit.py`：9 项通过。
- 在适配器包外搜索 `PinnedFinRobotAdapter`、`charts.render` 和 `report.render_pdf`，
  未发现运行时构造或调用位置：PASS。
- 能力注册表检查仅发现本项目的两项原生财务能力：PASS。
