# 08 — 保障、Langfuse 与 ZK V1

[English](08_ASSURANCE_LANGFUSE_ZK_V1.md)

## 1. 控制平面原则

> Agent 对执行拥有自主权，但对保障机制没有自主裁量权。

## 2. 财务审查

### 确定性检查

- 证据已接受
- 数值一致性
- 计算状态
- 期间一致性
- 实际值／估计值一致性
- 单位／币种
- 必需字段完整性
- 报告数字／计算一致性

### 语义检查

- 主张有证据支持
- 逻辑跳跃
- 证据冲突
- 主张强度
- 限制披露
- 判断与事实混淆

状态：

```text
PASS
REVIEW
BLOCK
```

## 3. 审查修复闭环

```text
Review Finding
→ Correction Request
→ Original Task / Agent
→ Self-Correction
→ Resubmit
→ Review Again
```

若纠错改变范围／依赖 → Replan。

## 4. Langfuse

定位：

> 技术可观测性／追踪证据。

埋点：

- 运行
- 规划
- Agent 生成
- 技能
- 工具
- 财务代码
- 纠错
- 重新规划
- 审查
- 证明适配器
- 报告渲染

Langfuse 不是业务事实源。

Canonical Execution Record 保存追踪引用。

## 5. Langfuse 故障不阻断业务

可观测性故障不得中断研究执行。

实现：

- LangfuseTraceAdapter
- NoopTraceAdapter

无凭据 → Noop。

### Phase 3 修复：出站凭据脱敏

`langfuse-otel-export-redaction-v1` 保留 Langfuse SDK 原始 instrumentation-scope
中的 `public_key`，直到 `LangfuseSpanProcessor` 完成项目路由检查。随后，适配器在
处理器的 OTLP exporter 边界克隆已完成的 span，递归移除凭据形态字段，并从 scope、
resource、span、event、link、status、provider、tool 以及嵌入式 JSON 载荷中
脱敏已配置的凭据值。委托 exporter 及其认证请求头保持不变。

现有 Phase 3 `P3-INT-005` 门在 flush 后通过 Langfuse API 回读。仅用于验收的排空屏障
按 `0/2/5/10/20/40/60` 秒的有界单调时间表轮询精确 trace；若本地与远端观测身份集合
未在 60 秒截止前精确收敛，则失败关闭。同时要求一个根 trace，以及精确的 Run/trace
元数据闭合。每次尝试保留时间戳、耗时、计数和身份差异；最终证据保留完整的规范化
预期／实际观测身份集合。绝不持久化 trace 载荷和已配置凭据值。
`LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`、`FMP_API_KEY` 和
`TEAMOROUTER_API_KEY` 的出现次数必须各为零。缺少回读或回读失败会导致验收门失败，
但不会改变普通业务执行中可观测性故障不阻断业务的行为。

## 6. ZK 证明边界

MVP 建议证明：

```text
Accepted evidence commitment
→ deterministic revenue growth program
→ numeric output commitment
→ receipt
→ verification
```

或最终数值一致性检查。

不要尝试证明完整的 LLM 叙述。

## 7. ZK 语义

可以证明：

- 已知程序已执行
- 使用了已承诺的输入
- 输出／journal 与已验证 receipt 一致

不能证明：

- 供应商数据客观真实
- 投资论点客观正确
- 绝不可能产生幻觉

## 8. Release Gate

```text
Review required statuses satisfied
AND
all MUST_PROVE proofs valid
AND
no hard block
→ RELEASE
```
