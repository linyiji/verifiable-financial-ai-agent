# Phase 3 规划器供应商路由修复

[English](PHASE3_PLANNER_PROVIDER_ROUTER_REMEDIATION.md)

## 处置状态

候选 `38f66c603d61097005b3cf961dc93948bfceba83` 和树
`6a520e457dce199454d86ff2968da79cc8f35072` 保持为不可变历史状态，
处置结果为 `PRE_AUTHORITATIVE_BLOCKED_BY_PROVIDER_CAPABILITY`。

此修复创建新候选，因为此前实现如实地只支持 TeamoRouter。它不改变 Phase 3 财务、
审查、证明、DTO 或 RuntimeEvent 契约，也不引入迁移。
预期迁移头仍为 `20260904_0006`。

## 受控供应商策略

内部 `PlannerProviderRouter` 负责供应商偏好策略：

1. `mimo` 是首选供应商。
2. `teamorouter` 是次选供应商。
3. 未知供应商按失败关闭处理。
4. 首个供应商通过本项目定义的规划器预检后，停止探测。
5. 创建 Research Run 前锁定选中的供应商和精确模型。禁用 Run 中途切换。

两个供应商适配器均通过同一本项目维护的结构化输出边界规范化。
供应商特定响应体留在该边界内。安全选择证据仅包含供应商／模型标识、策略、原因、
回退状态、健康检查时间和安全故障分类。

## 运行时配置与秘密处理

MiMo 配置仅通过外部运行时变量提供：`MIMO_API_KEY`、`MIMO_BASE_URL`、
`MIMO_CHAT_MODEL` 和 `MIMO_DATA_MODEL`。仓库不包含任何凭据值。
TeamoRouter 继续使用其现有外部变量配置。

验收运行器将每个已配置供应商凭据同时纳入本地产物哨兵扫描与 Langfuse 递归脱敏审计。
FMP 凭据在验收证据中通过授权别名绑定；其值绝不记录。
供应商／模型选择证据附加到根 trace 和验收摘要。

## 权威资格规则

调用运行器前，必须针对干净的新候选完成外部 FMP 与规划器预检。
运行器会按受控顺序独立重复两次连续的本项目规划器探测，锁定首个健康供应商／模型，
并在 Scheme 生成、Lead 规划和 Generated Capability 构建中使用同一身份。
选择后供应商失效或身份漂移会使 Run 失败；绝不触发静默故障切换。
