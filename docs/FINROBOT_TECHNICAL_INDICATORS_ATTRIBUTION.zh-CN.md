# FinRobot 技术指标 — 归因与来源

[English](FINROBOT_TECHNICAL_INDICATORS_ATTRIBUTION.md)

`src/adapters/finrobot/technical.py` 中由本项目维护的技术指标移植，
参考了以下源码中的公式选择和输出名称：

- 项目：FinRobot
- 版权：© 2024–2026 AI4Finance Foundation
- 许可证：Apache License 2.0
- 仓库：`https://github.com/AI4Finance-Foundation/FinRobot`
- 已审计提交：`d221910096de87579b02f8f0674652bf1a175f51`
- 源码：`finrobot_equity/core/src/modules/market_data_api.py`
- 符号：`get_technical_indicators`

许可证全文：<https://www.apache.org/licenses/LICENSE-2.0>

FinRobot 和 AI4Finance 是 AI4Finance Foundation 的商标。本项目不被表述为
官方 FinRobot 发行版或获得其背书的衍生产品。

## 移植边界

本项目运行时不导入或修改上游模块。实现仅保留可独立测试的确定性公式行为，
并用本项目的 Python `Decimal` 代码替换 pandas/numpy 操作。它排除了全部上游
FMP/YFinance 调用、API Key／配置处理、日志、宽泛吞异常、图表／报告集成，
以及组合启发式信号。

上游数据和图表模块对 pandas EMA 调整的隐式选择不一致。
因此，本移植明确冻结并版本化以下选择：

- SMA 50/200：最近收盘价窗口的算术平均值。
- RSI 14：最近 14 次价格变化的涨／跌幅简单平均值；需要 15 个收盘价；
  全涨 = 100，全跌 = 0，完全不变 = 50。
- MACD 12/26/9：等价于 pandas `adjust=False` 的递归 EMA，以首次观测收盘价为种子。
  每次快速 EMA、慢速 EMA、差值线、信号 EMA 和柱状值运算均使用
  `macd-decimal-context-v1`，精度为 `28`，舍入方式为 `ROUND_HALF_EVEN`；
  实现不继承进程全局 `Decimal` 上下文。
- Volume Ratio 20：最新成交量除以最近 20 个成交量的平均值，包含最新观测。

生成的每个 `CalculationRecord.source_ref` 均包含上游仓库、精确提交、符号和
`Apache-2.0` 标记；`implementation_hash` 是本项目已检入源码的哈希。

## Phase 3 财务审计修复增量

现有技术语义判定依据（`FS-010`）在不增加验收门的前提下得到强化：现在要求计算快照
和已发布方法说明绑定策略 ID、精度、舍入、EMA 调整／种子、12/26/9 跨度、观测数量、
预热状态和技术价格基础。独立审查者导入同一版本化策略定义进行自身重算，
而不是另行维护一份精度常量。
