# 06 — 数据、证据与财务计算 V1

[English](06_DATA_EVIDENCE_FINANCIAL_COMPUTE_V1.md)

## 1. 两道财务硬门

> 未经验证的数据不得进入正式财务推理。

> LLM 不得作为任何确定性财务数字的权威生成来源。

## 2. 数据流

```text
Object Existing Data
      ↓ Freshness
Reusable ──────────┐
                   ↓
FMP / Other Source → Raw Snapshot
                   ↓
                Validate
                   ↓
                Normalize
                   ↓
             Conflict Resolve
                   ↓
           Accepted Evidence
              /         \
             ↓           ↓
          Agents     Financial Code
```

## 3. 数据新鲜度

策略示例：

- 公司概况：缓慢变化
- 年度财务：出现新申报／重述时刷新
- 季度财务：出现新申报时刷新
- 市场价格：短 TTL
- 新闻：短 TTL
- 同行估值倍数：短／中 TTL

MVP 可以使用粗粒度 TTL，但 schema 必须允许按数据类型设置策略。

## 4. 冲突处理

不得把来源存在等同于内容真实。

冲突检查：

- 期间不匹配
- TTM 与 FY 差异
- 财务重述
- 币种
- 单位
- 调整后与未调整口径差异
- 来源优先级
- 缺失情况

输出：

```text
ACCEPTED
CONFLICT
REJECTED
PARTIAL
```

## 5. 证据包

原始文件进入 Artifact Store。

数据库保留元数据和引用。

## 6. 财务报表

规范报表模型应支持：

- 利润表
- 资产负债表
- 现金流量表
- 年度／季度
- 实际值／估计值
- 供应商来源
- 重述版本

## 7. 财务计算

正式计算：

```text
Accepted Evidence IDs
→ Calculation Inputs Snapshot
→ Capability Version
→ Deterministic Code
→ Output
→ Calculation Record
```

## 8. MVP 计算

最小实用集合：

- 营收增长率
- CAGR（复合年增长率）
- 毛利率
- EBITDA 利润率
- 数据可用时的贡献毛利率
- ROE（净资产收益率）
- 流动比率
- 债务／权益比率
- 自由现金流
- 自由现金流利润率
- P/E
- EV / EBITDA
- SMA / RSI / MACD

### 8.1 营收增长率 v1 已审查语义

`revenue_growth_v1` 精确等于 `(current_revenue - prior_revenue) / prior_revenue`，
语义前置条件为 `prior_revenue > 0`。前期值为零或负数时，按失败关闭原则返回
`REVENUE_GROWTH_PRIOR_REVENUE_MUST_BE_POSITIVE`；绝不能输出增长百分比。

## 9. 预测

不得混淆预测值与实际值。

每项预测必须关联：

```text
Assumption Set
Forecast Horizon
Run
Calculation / Model Version
```

## 10. AI 判断

LLM 可以输出：

```text
judgment_type
claim
evidence_ids
calculation_ids
confidence
limitations
requires_review
```

判断绝不会被静默转换为事实。
