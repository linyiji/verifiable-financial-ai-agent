# WS-W4 — FinRobot 同行辅助模块受控移植

[English](WS_W4_FINROBOT_PEER_HELPERS_REPORT.md)

## 结果

PASS。本项目维护的同行辅助移植仅包含确定性期间对齐、透视转换、指标矩阵构建和算术聚合。
它不获取数据、发现候选、选择可比对象、填补缺失值或预测未来期间。

## 固定源码与归因

- 上游：AI4Finance Foundation / FinRobot
- 许可证：Apache-2.0
- 精确提交：`d221910096de87579b02f8f0674652bf1a175f51`
- 已审查符号：
  `finrobot_equity/core/src/modules/market_data_api.py:combine_peer_financial_data`
- 本项目移植：`src/adapters/finrobot/peer_port.py`
- 能力：`finrobot_peer_metric_aggregation@1.0.0`

上游函数将 FMP 调用与 pandas 记录构建、透视转换混合在一起。
WS-W4 只移植从纯记录到矩阵的理念。供应商获取仍在现有 FMP Evidence Layer 中。
不移植 `project_ebitda_for_peers`，因为它内嵌预测假设，需要显式预测契约。

## 决策矩阵

| 关注点 | 上游行为 | WS-W4 决策 | 运行时状态 |
| --- | --- | --- | --- |
| 供应商获取 | 同行合并函数内部调用 FMP | REJECTED；使用现有 Evidence Layer | 不存在 |
| 候选发现 | 向获取循环提供股票代码列表 | REJECTED；保留现有候选来源 | 不存在 |
| 可比对象选择 | 隐含为调用者职责 | 保留 `PeerSelectionPolicy` 作为唯一选择器 | 现有边界 |
| 期间对齐 | 稀疏 pandas 透视表 | PORTED；仅保留完整历史期间 | 活跃 |
| 透视／指标矩阵 | pandas pivot | PORTED 为确定性 DTO，无 pandas 依赖 | 活跃 |
| 聚合 | 未分离 | ADAPTED 为显式均值／中位数／最小值／最大值公式 | 活跃 |
| 缺失值 | 可能出现稀疏单元格／NaN | 失败关闭或报告排除的期间；绝不填补 | 活跃 |
| 预测 | 平均增长预测辅助函数 | 本工作线 REJECTED | 不存在 |

## 输入与选择边界

移植仅接受 `SelectedComparableMetric` 值。只有带字面量 `selected=true` 保护条件时，
才能直接创建规范指标，表示可比对象已经被选中。Evidence 构造器还要求：

1. `EvidenceStatus.ACCEPTED`；
2. `EvidenceCategory.PEER`；
3. 已存在对应同一股票代码的 `PeerSelectionDecision`；
4. `PeerSelectionDecision.selected == true`。

被拒决策会抛出 `PeerMetricInputError`。辅助模块绝不编辑或替换决策。
在现有候选 → 选择策略 → 已选可比对象架构下，缺少补充信息仍导致拒绝。

## 实际运行时调用路径

```text
FMP peer candidate Evidence
  → StockPeersCandidateSource
  → PeerSelectionPolicy
  → selected PeerSelectionDecision
  → SelectedComparableMetric.from_accepted_evidence
  → align_peer_periods
  → pivot_peer_metrics / PeerMetricMatrixDTO
  → CapabilityRegistry
  → ToolRuntime
  → NativeToolBackend
  → PeerMetricAggregationCapability
  → CalculationRecord[]
```

每个数值聚合都是一个 `CalculationRecord`，包含能力和公式版本、精确输入 Evidence ID
和值、输出单位、实现哈希、Python 运行时、上游提交 URL 及 Apache-2.0 归因。
计算参数显式记录 `projection_policy=PROHIBITED` 和
`missing_value_policy=EXCLUDE_INCOMPLETE_PERIOD_NO_FILL`。

## 安全检查

- 本项目移植不导入 `requests`、`httpx`、`aiohttp` 或 `urllib`。
- 不存在供应商／配置／密钥输入。
- 移植中不存在候选来源或选择策略实现。
- 不重复实现 FMP 连接器。
- 无隐式预测、插值或前值延续。
- 跨单位／跨币种聚合按失败关闭处理。
- `CapabilityContext.accepted_evidence_ids` 之外的 Evidence 按失败关闭处理。
- 上游检出目录保持只读且未修改。

## 验证

聚焦测试命令：

```text
PYTHONPATH=$PWD .venv/bin/pytest -q \
  tests/financial/test_finrobot_peer_port.py \
  tests/integration/test_finrobot_peer_runtime.py
```

结果：`10 passed`。

全仓库回归：`230 passed, 3 skipped`（三个跳过项是现有选择性启用的真实 PostgreSQL 检查，
需要配置 PostgreSQL URL 和 `asyncpg`）。

集成测试执行真实的候选 → 策略 → 已选指标 → 矩阵 → 注册表 → 运行时 → 原生能力路径。
它证明缺少补充信息的同行仍为 `selected=false`，不能进入矩阵，也不会在聚合时被修改。
AST 级依赖断言验证了移植没有 HTTP 客户端导入。

## 契约变更请求

无。WS-W4 不改变任何共享领域契约、枚举、设置、依赖、数据库契约、API 核心或前端文件。
