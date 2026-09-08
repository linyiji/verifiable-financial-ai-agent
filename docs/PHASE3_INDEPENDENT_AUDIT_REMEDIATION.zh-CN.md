# Phase 3 独立审计修复

[English](PHASE3_INDEPENDENT_AUDIT_REMEDIATION.md)

此变更集在一个新的 Phase 3 候选中，精确关闭四项独立审计发现。
它不改变或替换被拒候选、其权威 Run 或审计证据，也不授权 Phase 4。

## 规范问题项

- `PH3-REM-F1` — `GENERATED_CAPABILITY_PREIMAGE_RETENTION`（P1）：保留已接受生成能力
  构建所使用的精确 UTF-8 源码与测试原文，将其哈希和大小绑定到构建记录，
  并独立重建沙箱输入。强化现有 `P3-CAP-003`、`P3-CAP-004`、
  `P3-CAP-008` 和 `P3-CAP-011` 门，不创建新的门命名空间。
- `PH3-REM-F2` — `REVENUE_GROWTH_FORMULA_SEMANTICS`（P2）：使用
  `(current_revenue - prior_revenue) / prior_revenue`，要求
  `prior_revenue > 0`，否则以稳定原因失败关闭，并将新的可复现 RISC Zero 镜像和
  正式 receipt 绑定到这些语义。通过现有 Phase 3 财务语义、审查和证明门关闭。
- `PH3-REM-F3` — `MACD_DECIMAL_CONTEXT_DETERMINISM`（P2）：用
  `macd-decimal-context-v1`、精度 28 和 `ROUND_HALF_EVEN` 约束完整 MACD 计算；
  持久化策略元数据，证明环境 Decimal 精度为 10、28、50 时结果相同。
  强化 `FS-010` 以及现有报告／发布门。
- `PH3-REM-F4` — `LANGFUSE_PUBLIC_KEY_REDACTION`（P2）：在最终 OTLP 导出边界移除
  已配置凭据，同时在内部保留 Langfuse public key 供认证使用。真实 trace 回读仅记录
  凭据字段名和出现次数，并要求精确的已导出观测集合。强化 `P3-INT-005`。

## 持久化与历史证据

迁移 `20260904_0006` 接续 `20260904_0005`，仅向前推进。它添加 F1 所需的
不可变、内容寻址的生成源码／测试产物存储和构建绑定。F4 不增加数据库迁移。

被拒候选 `e02314c552d88fb736473bc587c650539615224a`、树
`af74ec7e6bcf40d281c0a1ea5463c794d795718f`、Run
`RUN-a5e58911-9b0f-4848-90fe-a65f436fa9c2` 和 Langfuse trace
`3ea5df8d0354816dbb9f35c56820353d` 保持为不可变的审计失败证据。
历史 public-key 出现情况不被描述为干净，也不会仅因暴露值是 Langfuse public key
就轮换凭据。若在已导出遥测中发现真实秘密，即构成停止条件与安全事件。

修复候选必须通过未改变的正式 Phase 3 52 门矩阵，以及内部财务语义和真实集成闭环。
随后，还需针对同一候选与权威 Run 获得新的 Backend Independent Final Audit 和
Financial Semantics Independent Final Audit 结果，才能成为 Approved Phase 3 Backend Parent。
