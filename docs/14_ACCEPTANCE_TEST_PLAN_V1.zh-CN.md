# 14 — 验收与测试计划 V1

[English](14_ACCEPTANCE_TEST_PLAN_V1.md)

## 1. 测试理念

不要在遇到首个非关键故障时停止全部验收。

尽可能完成独立检查，汇总缺陷，再修复并重跑。

## 2. 必需测试层

### 单元测试

- 领域模型
- 枚举
- 图依赖
- 能力注册表
- 证据校验
- 财务公式
- 审查规则
- 自纠
- 重新规划决策
- 事件序列化

### 集成测试

- API + DB
- 准备 Scheme
- 确认 Run
- 运行时调度
- SSE
- 规范记录
- 已发布结果

### 财务测试

- 已知输入 → 已知结果
- 期间对齐
- 实际值／预测值
- 缺失数据
- 零分母
- 单位／币种

### 验收

端到端离线受控流程。

## 3. 验收用例

| ID | 目标 |
|---|---|
| AC-001 | 创建 Research Object |
| AC-002 | Object + Goal → AI／回退 Scheme |
| AC-003 | 用户确认 Scheme Snapshot |
| AC-004 | 创建 Research Run |
| AC-005 | Lead Planner 生成初始计划图 |
| AC-006 | 独立任务并行执行 |
| AC-007 | Evidence 门阻止未接受数据 |
| AC-008 | 营收增长率由确定性代码产生 |
| AC-009 | CalculationRecord 关联 Evidence |
| AC-010 | Task 执行自纠而不新增顶层 Task |
| AC-011 | 专业 Agent 提交 Replan Request |
| AC-012 | Lead 批准后通过图变更新增子 Task |
| AC-013 | 出现能力缺口 |
| AC-014 | 生成能力通过测试／任务批准 |
| AC-015 | 独立 Review 的 PASS／REVIEW／BLOCK 有效 |
| AC-016 | 证明策略返回正确要求 |
| AC-017 | 后续阶段的真实 ZK 证明通过验证 |
| AC-018 | Release Gate 阻止保障无效的结果 |
| AC-019 | 生成 Canonical Execution Record |
| AC-020 | B/C 投影共享同一记录 ID |
| AC-021 | 从已发布结果生成 Financial Report |
| AC-022 | 对象回写遵循 Fact/Calc/Forecast/Judgment 类型 |
| AC-023 | SSE 可以恢复／回放有序事件 |
| AC-024 | Langfuse 故障不中断 Run |
| AC-025 | Run 检查点可以恢复 |
| AC-026 | 比较门拒绝不兼容的期间／定义 |

Phase 3 修复强化了现有 `P3-INT-005` 中 Langfuse 验收判定依据，并未新增验收门。
flush 后，按仅用于验收的 `0/2/5/10/20/40/60` 秒有界核对时间表回读权威 trace 及全部观测。
PASS 要求观测身份精确相等，没有缺失、意外或重复身份，仅有一个根 trace，Run/trace
元数据精确闭合，已配置凭据出现次数为零。保留的机器证据包含每次回读尝试与完整的
最终规范化身份集合；绝不包含已配置凭据值或原始 trace 载荷。

## 4. Phase 1 最小验收

进入 Phase 2 前必须通过：

```text
Object
→ Goal
→ Scheme
→ Confirm
→ Run
→ Planned Graph
→ Parallel runtime
→ Evidence
→ Revenue Growth / Margin Code
→ Self-Correction
→ Replan
→ Review
→ Canonical Record
→ Released Result
```

真实 ZK 在 Phase 1 可以保持 `NOT_IMPLEMENTED`，但绝不能伪造。

## 5. 验收证据

保存：

- pytest 输出
- API 测试结果
- Run 事件日志
- fixture 哈希
- 计算输出
- 规范记录 JSON
- 最终验收报告
