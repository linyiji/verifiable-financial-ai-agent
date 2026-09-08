# FinRobot 图表 — 受控移植归因

[English](FINROBOT_CHARTS_ATTRIBUTION.md)

`src/adapters/finrobot/charts.py` 中的确定性 SVG 渲染器是本项目维护的受控移植，
参考了 FinRobot 的图表呈现理念：

- 项目：FinRobot
- 版权：© 2024–2026 AI4Finance Foundation
- 许可证：Apache License 2.0
- 仓库：`https://github.com/AI4Finance-Foundation/FinRobot`
- 已审计提交：`d221910096de87579b02f8f0674652bf1a175f51`
- 上游源码：`finrobot_equity/core/src/modules/chart_generator.py`
- 相关上游符号：`generate_revenue_ebitda_chart`、
  `generate_ev_ebitda_peer_chart`、`generate_technical_indicators_chart`

许可证全文：<https://www.apache.org/licenses/LICENSE-2.0>

FinRobot 和 AI4Finance 是 AI4Finance Foundation 的商标。本项目不被表述为
官方 FinRobot 发行版或获得其背书的衍生产品。

## 受控移植差异

不导入、修改或执行上游源文件。本移植使用 Python 标准库实现，输出确定性 SVG，
而非调用 pandas、numpy 或 matplotlib。它只接受经现有精确固定版本的
`PinnedFinRobotAdapter` 传入的序列化 `CanonicalReportDTO` 数据；
不依赖供应商、FMP、网络、LLM、配置、凭据或数据库。

SVG 嵌入渲染器版本、精确上游固定版本／源码、规范／已发布记录 ID、
语义哈希和许可证标记。返回的 `ReportArtifactRecord` 记录内容哈希、语义哈希、
渲染器版本、受控产物引用，以及规范／已发布谱系。
