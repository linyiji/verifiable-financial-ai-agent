# Phase 3 感知工作负载的供应商可靠性修复

[English](PHASE3_PROVIDER_RELIABILITY_REMEDIATION.md)

## 保留证据

- 候选 `66edc5110b6ab7d81578cef80190497a2f11e5b2`／树
  `5cc1fd63d97fcb07c233b1dba73bd4d1cd16b77f` 保留为
  `PRE_AUTHORITATIVE_PROVIDER_STABILITY_FAILED`。
- `RUN-3bf17fec-efae-4945-8084-432e69a45bc5` 保持为
  `NON_AUTHORITATIVE_PROVIDER_INTERRUPTED_ATTEMPT`。绝不恢复它，也不复用其部分证据。

## 根因

MiMo Generated Capability 资格请求遇到的并非常规读取超时。HTTPX 读取超时是空闲超时。
上游响应持续传来字节，每个字节都会重置空闲窗口，因此响应体读取持续超过 960 秒。
响应体读取与供应商重试路径外部缺少独立墙钟截止时间。最终，资格检查 watchdog
终止了该探测。

本项目客户端直接使用 HTTPX，在该配置中 HTTPX 不会自动重试。
因此，无界耗时不是 SDK 重试泄漏，而是持续活跃读取外部缺少墙钟约束。

## 本项目执行预算

`ProviderExecutionPolicyV1` 现在使用显式连接、读取、写入和连接池限制，以及最大尝试次数、
有界退避、单次尝试墙钟截止时间和整体墙钟截止时间，控制每次真实结构化供应商调用。
外层截止时间包裹完整的尝试／退避链。取消会传播至活跃的 HTTPX 请求，
并在取消期间关闭本项目客户端上下文。不创建脱离管理的后台任务。

默认生产值为：

- 连接：10 秒
- 读取空闲：现有验收客户端请求 60 秒时，为 60 秒
- 写入：30 秒
- 连接池：10 秒
- 尝试：最多 2 次受控模型路由尝试
- 退避：最多 1 秒
- 单次尝试：90 秒
- 整体供应商调用：180 秒

Generated Capability 应用层重试共享同一绝对 180 秒生成截止时间。
到期会取消活跃 builder 调用，并阻止再次发出 builder 请求。

## 感知工作负载的绑定

策略 `MIMO_PRIMARY_TEAMOROUTER_SECONDARY_V2` 通过各工作负载在本项目中的生产接口，
独立评估以下工作负载：

- `SCHEME_PLANNER`
- `LEAD_PLANNER`
- `GENERATED_CAPABILITY`

每种工作负载首先探测 MiMo。只有 MiMo 失败后，才为该工作负载探测 TeamoRouter。
必须连续获得两个有效响应。`RunProviderBindingV1` 为每种工作负载精确保存一个
供应商／模型绑定，在创建 Research Run 前完成定稿，并且不可变。
每个绑定供应商拒绝被用于其他工作负载。

Run 中途自动故障切换仍禁用。绑定供应商失败会使 Run 失败。
内部 `ControlledProviderFailoverRecordV1` 仅为未来显式尝试边界策略预留安全来源字段；
它不激活故障切换，也不新增公开 RuntimeEvent。

## 安全故障与遥测边界

本项目定义的故障规范化包括：认证、配额／限流、可重试 HTTP、供应商不可用、连接超时、
读取超时、整体截止时间、远端协议、无效响应，以及语义／schema 故障。
安全元数据仅限供应商、模型、工作负载、尝试、耗时、可重试性、选择来源、构建身份和结果状态。
不包含凭据、认证请求头、提示词、响应体、生成源码、生成测试和隐藏推理。

此修复不改变任何 Phase 4 公开 API、前端 R2 契约、RuntimeEvent 枚举、财务投影／审查语义、
追踪契约、产物契约或数据库迁移。
