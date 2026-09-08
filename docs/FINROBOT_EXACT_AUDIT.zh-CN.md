# FinRobot 精确审计与复用报告 — WS-H

[English](FINROBOT_EXACT_AUDIT.md)

状态：**COMPLETE — MODULE GATE PASS**

审计日期：2026-09-04

项目基线：Python `>=3.11,<3.12`

基础基线：`0a5838624776e0854a6d42f5b1ef9d8ba159173e`

## 1. 审计身份与固定版本

| 字段 | 已审计值 |
|---|---|
| 上游 | `https://github.com/AI4Finance-Foundation/FinRobot.git` |
| 精确提交 | `d221910096de87579b02f8f0674652bf1a175f51` |
| 提交时间戳 | `2026-08-23T20:06:08+08:00` |
| 提交标题 | `Update README.md` |
| 检出方式 | detached，仓库外临时目录 |
| 提交 vendor 树 | 否 |
| 运行时固定版本 | `src.adapters.finrobot.audit.FINROBOT_PINNED_COMMIT` |

审计使用架构审查已经明确的精确提交。未修改上游树。
未将 FinRobot 源码、生成产物、配置文件或凭据复制进此仓库。

源码完整性证据：

| 上游文件 | 已审计提交中的 SHA-256 |
|---|---|
| `LICENSE` | `bbcb4226500b503737713f0c9a9da17efce56fa6989b9f0538071dcb60826af5` |
| `NOTICE` | `d1da20e9e1e8a0f3189665c4f21cf35f0eba1a8a1432f95a734db0640e289346` |
| `setup.py` | `16c90b1727b04f8326c11c534800fdb9cfb5085b2ac327e1a6aa580f95c347f0` |
| `requirements.txt` | `685ca02bb04d09f4019f582ec28e41143eff055654fd706e751dd7aa59caae02` |

## 2. 兼容性方法与结果

兼容性结论刻意区分 Python 语法、隔离可选依赖导入，以及与主项目已安装基线的兼容性。

1. `setup.py` 声明 Python `>=3.10,<3.12`，因此 Python 3.11 位于上游元数据范围内。
2. Python `3.11.16` 编译了 `finrobot/` 及股票研究 `modules/` 目录下全部 `.py` 文件。
3. 隔离临时 Python 3.11 环境安装了已审计股票研究依赖集合：
   `numpy 1.26.4`、`pandas 2.0.3`、`Requests 2.31.0`、`matplotlib 3.11.1`、
   `reportlab 5.0.1` 和 `yfinance 0.2.66`。
4. 十个已审计股票研究模块在该隔离环境中成功导入：财务处理器、市场 API、估值、
   敏感性、基础／增强图表、基础／专业 HTML，以及基础／专业 PDF。
5. 历史指标提取、同行 EBITDA 预测及技术指标图表生成的离线冒烟检查通过。
6. 主项目虚拟环境**不**包含这些可选库。本工作线没有改变项目依赖。

导入通过不等于架构验收。以下决策还考虑 Evidence Gate、CalculationRecord、
Forecast/Fact 区别、保障职责、秘密处理和现有 Phase-1 实现。

## 3. 现有逻辑复用矩阵

| 现有模块／符号 | 类别 | 决策 | Python 3.11 | 输入 | 输出 | 依赖 | 操作 |
|---|---|---|---|---|---|---|---|
| `financial_data_processor.py`：`clean_financial_number`、API/PDF 提取器 | 财务数据处理器 | `PORT_REQUIRED` | 隔离导入通过 | 标量或供应商原始／PDF DataFrame | float/NaN 或混合 DataFrame | numpy, pandas | 只在 Evidence 接受后移植有用且不重叠的规范化。 |
| `financial_data_processor.py`：`calculate_growth_and_forecasts` | 财务计算 | `PORT_REQUIRED` | 隔离导入通过 | 历史 DataFrame、未版本化预测配置 | 混合实际值／预测值 DataFrame | numpy, pandas | 保留 Phase-1 原生增长率／利润率；未来移植必须输出 CalculationRecord 并关联 AssumptionSet。 |
| `finrobot/data_source/fmp_utils.py`：`FMPUtils` | FMP 连接器 | `REJECT_FOR_MVP` | 语法通过；未安装完整包栈 | 股票代码／日期／年份及全局环境密钥 | 字符串、dict、DataFrame | numpy, pandas, requests 及包导入 | 保留 Phase-1 异步 `FMPProvider`。 |
| `market_data_api.py`：FMP 报表／比率获取函数 | FMP 连接器 | `REJECT_FOR_MVP` | 隔离导入通过 | 股票代码、明文密钥、期间、上限 | 原始 DataFrame | pandas, requests, yfinance | 不得绕过 RawProviderSnapshot 与 Evidence 摄取。 |
| `market_data_api.py`：`combine_peer_financial_data` | 同行逻辑 | `PORT_REQUIRED` | 隔离导入通过 | 股票代码列表、密钥、年份 | EBITDA 和 EV/EBITDA 透视表 | pandas, requests | 分离获取与纯聚合；使用规范同行值。 |
| `market_data_api.py`：`project_ebitda_for_peers` | 同行逻辑 | `PORT_REQUIRED` | 隔离导入／冒烟通过 | 历史同行 EBITDA、预测跨度 | 历史 + 预测 DataFrame | pandas | 要求假设／版本／Run 谱系并保留 `FORECAST`。 |
| `valuation_engine.py`：`ValuationEngine` | 计算 | `REJECT_FOR_MVP` | 隔离导入通过 | 松散财务／同行 dict | 目标价对象及综合 dict | numpy, pandas | 无显式模型契约时，默认值不能获得财务认证。 |
| `sensitivity_analyzer.py`：`SensitivityAnalyzer` | 计算 | `REJECT_FOR_MVP` | 隔离导入通过 | 混合预测 DataFrame、场景范围 | 表、区间、叙述 | numpy, pandas | 固定波动率“置信区间”不得作为统计保障发布。 |
| `market_data_api.py`：`get_technical_indicators` | 技术指标 | `PORT_REQUIRED` | 隔离导入通过 | 股票代码 + 密钥；内部获取价格序列 | SMA/RSI/MACD 和启发式标签 | numpy, pandas, requests | 分离获取与纯公式；输入已接受 Evidence，输出 CalculationRecord。 |
| `chart_generator.py`：已审查图表函数 | 图表 | `ADAPTER_REUSE` | 隔离导入／冒烟通过 | 已审查 DataFrame/dict、股票代码、受控路径 | base64 PNG + 文件 | matplotlib, numpy, pandas | 经固定版本、无网络渲染器操作 `charts.render` 复用。 |
| `html_renderer.py`：HTML 报告函数 | 报告渲染器 | `PORT_REQUIRED` | 隔离导入通过 | 固定 schema dict + 模板 | HTML 字符串 | pandas | 添加转义／净化及规范 FinancialReport 映射。 |
| `pdf_generator.py`：`EquityReportPDF`、`generate_equity_report_pdf` | 报告渲染器 | `ADAPTER_REUSE` | 隔离导入通过 | 已审查报告 dict、受控路径 | PDF 资源 | pandas, reportlab | 经 `report.render_pdf` 提供可选发布后渲染器；不替换报告 JSON。 |
| `finrobot/functional/reportlab.py`：`build_annual_report` | 报告渲染器 | `REJECT_FOR_MVP` | 语法通过；未安装完整包栈 | 叙述、股票代码、图表路径 | PDF 路径／错误文本 | reportlab, FMPUtils, YFinanceUtils | 拒绝报告生成时重新获取数据及混合供应商／渲染职责。 |

矩阵汇总：

- `DIRECT_REUSE`：0
- `ADAPTER_REUSE`：2
- `PORT_REQUIRED`：6
- `REJECT_FOR_MVP`：5

零项 `DIRECT_REUSE` 是刻意决策：即使看似纯净的渲染函数也会执行文件 I/O，
并要求受控输出路径，因此适配器边界仍是必需的。

## 4. 分类发现

### 4.1 财务数据处理器

存在有用源码逻辑，但在本系统中不能向它传入原始 FMP DataFrame。API 提取器混合规范化
和计算，并将比率输出为百分比字符串。它的真值判断会丢弃有效零值。
预测函数混合实际与预测列，包含隐式 EPS 增长和 P/E 压缩假设，却没有 AssumptionSet
或计算谱系。

决策：仅移植选定且不重叠的转换。已接受的原生营收增长率和 EBITDA 利润率能力保持权威。

### 4.2 FMP 连接器

两个上游连接器变体均与项目边界冲突：

- 在计算／报告流程中执行同步网络请求；
- 将供应商原始 DataFrame 直接返回给下游代码；
- 将凭据放入 URL 查询字符串；
- 许多请求没有显式超时；
- 宽泛异常处理将故障转换为 `None`／文本；
- 股票研究示例打印密钥前缀，`common_utils.py` 打印加载的密钥值；
- 旧类依赖进程全局环境值；
- 重复端点调用，以及报告生成期间访问供应商。

决策：MVP 拒绝两个上游 FMP 连接器。保留 Phase-1 `HttpxFMPTransport`、`FMPProvider`
和 `EvidenceIngestionService`。上游端点覆盖只可作为参考。

### 4.3 同行逻辑

透视构建理念可复用，但与供应商调用耦合。EBITDA 预测使用历史同比增长均值，
这是预测假设而非事实。

决策：后续分两个边界移植：先是规范同行聚合，再是具有假设、Run、版本和输出类型谱系的
显式预测能力。

### 4.4 计算与估值

估值引擎硬编码重大默认值，包括 10% 净债务、60% EBITDA 到 FCF 转换率、默认估值倍数、
增长／WACC 值以及置信权重。DCF 敏感性范围改变折现，却未一致地重算终值。
敏感性分析器的置信区间假设固定 15% 标准差，并非经验置信区间。

决策：MVP 拒绝这些估值／敏感性计算。它们可以为未来契约设计提供参考，
但不能按原样成为已认证财务能力。

### 4.5 技术指标

SMA、RSI 和 MACD 公式可识别，且在 Python 3.11 下运行，但该函数自行获取 FMP 数据、
捕获全部异常、返回部分 `None` 值，并将数值结果与非确定性启发式标签混合。

决策：必须移植。未来移植应接受有序的已接受价格／成交量快照，版本化公式选择
（包括 EMA 调整），输出数值 CalculationRecord，并在适当时将标签分类为 Judgment。

### 4.6 图表与报告渲染器

图表和基础 PDF 模块是最佳复用候选，因为可以处理传入的已审查数据。
仅批准经受控适配器使用：无网络、固定已审计修订、受控输出目录、无凭据，以及发布后数据。

HTML 尚未批准，因为报告值流入大型模板时缺少显式净化契约。
旧 ReportLab 工具被拒绝，因为它在渲染时重新获取 FMP/YFinance 数据。

## 5. 已实现适配器边界

新增本项目维护代码：

- `src/adapters/finrobot/audit.py`
  - 精确上游仓库与提交固定；
  - 机器可读的六类审计矩阵；
  - 仅允许 `DIRECT_REUSE`／`ADAPTER_REUSE` 行的操作查找。
- `src/adapters/finrobot/pinned.py`
  - 依赖注入后端；导入主应用不会导入 FinRobot；
  - 强制精确修订；
  - 操作白名单（`charts.render`、`report.render_pdf`）；
  - 深复制输入；
  - 递归拒绝含凭据的输入键；
  - 强制报告资源路径的结果类型。

此边界不声称已安装 FinRobot，也不会自行执行上游函数。后续可选后端只有在依赖、许可证、
沙箱和资源路径门均通过后，才能绑定获准模块符号。

## 6. 安全与秘密审查

- 未进行真实供应商调用。
- 未读取、打印、持久化或提交凭据或本地环境值。
- 适配器在调用后端前，拒绝包含凭据的报告／图表输入。
- 错误消息不包含输入值。
- 上游克隆始终位于仓库之外。
- 明确不复用会记录密钥材料的上游示例。

## 7. 许可证与归因

在已审计提交中：

- 根 `LICENSE` 是 Apache License 2.0；
- `NOTICE` 要求保留，并包含商标／免责声明；
- `TRADEMARK_POLICY.md` 限制产品名／logo 用法；
- `setup.py` 仍声明 MIT 元数据／分类器。

根 LICENSE/NOTICE 视为权威，元数据冲突仍是发布审查项。
未来分发适配后的上游源码／资源时，必须保留 Apache-2.0 声明，记录精确提交，
避免产品品牌混淆，并单独验证 FMP API 商业／展示权利。

## 8. 契约与依赖请求

### CONTRACT_CHANGE_REQUEST-FR-001 — 可选渲染器依赖

状态：**DEFERRED / NOT APPLIED**

若集成负责人激活 `charts.render` 或 `report.render_pdf`，
应添加隔离可选依赖组，而非主运行时依赖：

```text
numpy>=1.24,<2
pandas>=2,<3
matplotlib>=3.6,<4       # charts only
reportlab>=3.6           # PDF only
```

必须锁定版本并在 Python 3.11 上重新测试。本工作线未编辑 `pyproject.toml`。

未请求领域、枚举、API、Settings 或应用契约变更。

## 9. 模块门证据

```text
Python 3.11 upstream compileall: PASS
Isolated equity module imports: 10/10 PASS
Offline upstream smoke checks: PASS
WS-H adapter tests: 9 PASS
Full project tests: 86 PASS (2 dependency deprecation warnings)
Ruff lint: PASS
Owned Python format check: PASS (5 files)
Contract boundary diff: PASS; frozen files unchanged
Secret scan: PASS; no credential-shaped values in changed files
FinRobot import boundary: PASS; no FinRobot import outside adapter package
```

## 10. 已知缺口

- 未添加 FinRobot vendor／子模块；部署尚不能激活该后端。
- 获准渲染器操作仍需要沙箱化后端和受控产物路径。
- HTML 净化尚未实现。
- FMP 端点扩展属于现有 FMP/Evidence 工作线，而非此适配器。
- 同行、预测、技术指标和估值契约移植仍是未来工作。
- 上游依赖文件未完全锁定；精确生产依赖解析需要锁文件。

## 11. 契约偏差

**NONE.** FinRobot 仍是第三方能力来源，不会成为主运行时、供应商边界、编排器、
计算权威或报告事实源。
