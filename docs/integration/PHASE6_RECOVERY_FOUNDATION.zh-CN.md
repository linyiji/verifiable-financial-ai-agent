# Phase 6 自适应运行时恢复基础

[English](PHASE6_RECOVERY_FOUNDATION.md)

设计依据：`<local-design-directory>/PHASE6_ADAPTIVE_EXECUTION_RECOVERY_DESIGN.md`（Owner 提供的设计文档，不是仓库文件）。
起始检查点：`e6d690364c4abd3e53113ad9f52205d50d8d8e40`（`phase4`）。

## 冻结范围

运行时恢复意味着**相同已确认工作，不同的有界调用尝试**。研究纠正 / 重规划意味着改变工作，仍由既有 Dynamic Research Path 授权。本任务不扩展调度器重试、不准入新 Run、不生成 Scheme/Graph、不发布或发布记忆。

此前，`LLMResearchAgent.execute` 将供应商失败转换为不可重试调用错误；调度器使 Task 失败、阻止依赖任务并使 Run 失败。恢复现在仅在构建精确上下文之后包裹 Specialist 的 `complete_structured` 调用。不重放 Calculation、证据采集、Review 或 Proof。已配置初始路由保留已接受调用授权；替代路由需要匹配的能力证据或另行门禁的能力检查。

任务身份不同于尝试身份。只要独立策略允许另一次调用，恢复就使 Task 保持 RUNNING。成功输出经未改变的 Specialist 产物 / 输出验证和普通调度器完成路径返回。不重定义调度器 `attempt_count`：新证据描述该次调度执行内部的调用尝试。

## 领域与授权

- 确定性分类器使用系统定义的适配器代码，绝不猜测异常字符串。超时、路由不可用、协议错误及有界可重试 HTTP / 速率失败可恢复。适配器合并的 408/5xx 诚实分类为 PROVIDER_UNAVAILABLE。输出契约、认证、身份、不安全输出和未知错误安全拒绝。
- ProviderDetector 遵循 Tool 注册表有限解析 / 可用性理念，不重载 ToolRegistry 或构建通用能力平台。
- 仅存在 `teamorouter-sol`、`teamorouter-luna` 和 `mimo-direct`。规范供应商 / 模型对及既有凭据授权独立验证。
- 健康与 profile/model/schema 特定能力分离。健康不等于 VERIFIED。近期传输证据影响健康，不影响财务真实性。
- RecoveryContext 最多包含三个候选、三条执行路由和十二个证据引用，以及精确 Run/Task/Object/Scheme/actor/profile 身份、输入及输出契约哈希和剩余限制。不含提示词、输出正文或原始日志。依赖 / 下游字段描述当前调度器接口，不是新 Graph。
- ResearchLeadRecoverySupervisor 是确定性 Lead 策略，遵循既有 replan-decider 模式。按固定注册顺序，先提议已知能力路由，再检查 UNKNOWN。不调用 LLM 识别传输失败。
- 独立策略检查身份、引用、已注册授权、健康、能力、耗尽、操作类型及预算。Supervisor 错误是安全终止拒绝。
- 封闭操作包括重试、模型 / 供应商切换、能力检查、Task/Run 失败、等待及语义纠正 / 重规划。此基础仅执行有界调用操作和失败。等待和语义操作在此被拒绝，不会静默执行。

## 硬预算

默认：Task 总计三次调用、每路由一次调用、一次模型回退、一次供应商切换、一次能力检查、五条决策、零次运行时重规划、包含初始调用在内 300 秒。配置值不能超出这些上限；唯一例外是同路由次数可显式升至二次，但仍在总计三次内。单路由客户端禁用隐藏重试 / 回退：一次 HTTP 尝试、读取超时 60 秒、路由截止时间 90 秒，同时受剩余恢复时间限制。

能力检查单独标记和计数，不隐藏成成功 Task 执行：检查 PASS 后，实际调用前仍需新决策。因此每 Task 最多四次供应商调用（三次执行加一次检查）。检查失败隔离 profile/route/model/schema，不能强行执行。预算绝不授权第四次执行或第二次检查。

实际费用不可观测。`max_total_recovery_cost=None` 明确表示无费用权威；配置数值限制时拒绝调用，而非编造费用。终止耗尽持久化为 `RECOVERY_BUDGET_EXHAUSTED`。

## 持久证据与被动认证

迁移 `20260908_0012` 仅新增 `phase6_recovery_evidence`、索引及不可变 UPDATE/DELETE 触发器。不回填。尝试开始在调用前提交，完成在调用后提交；决策保留有界上下文及 ALLOW/DENY 结果。证据包含系统定义失败代码、路由 / 模型、延迟、供应商提供时的用量及输出哈希。补充既有传输遥测，不复制原始 HTTP 载荷。

首个调用 Run/Task 上的部分唯一性防止并发重复执行。已有证据时重启 / 重新投递拒绝重置预算。进程中断可能留下 STARTED 而无 COMPLETED；这是诚实的未完成证据，不是伪造成功。自动崩溃恢复不在此基础范围内。

历史认证只读进行：精确 Task/actor/Run 绑定、实际路由 / 模型、SHA 校验原产物、保留结构化输出等价性、当前 profile schema 验证和秘密检查。持久化的新 PASS 仅在其匹配 STARTED 证据的 attempt、scope、route/model 及 check 标记均一致时认证能力。普通传输失败不替换之前成功的能力引用。缺失或无法验证的证据保持 UNKNOWN。没有已知实际模型的历史失败不编造模型特定健康事实。

只读生产审计发现 Peer 和 Research/News MiMo VERIFIED，Fundamental MiMo UNKNOWN。Fundamental Luna 同样没有导入的成功 profile 认证；不能凭配置的回退名称授予认证。固定顺序 UNKNOWN 探测可能在 MiMo 前把唯一检查用在 Luna；此基础承诺有界受治理恢复，不保证所有实时可用性模式都能恢复。未执行实时探测，不宣称未来 R5 成功。

权威增量后端投影：`GET /research-runs/{run_id}/recovery`。检查精确 Run 存在并返回类型化系统记录。历史 Run 返回空列表，不重建尝试。不新增前端恢复时间线。既有 A/B/C 投影契约完整保留。

## 产品理解

1. 存在允许路由时，可恢复超时不会立即使 Task/Run 失败。
2. Lead 策略在有限限制内决定再次受治理尝试是否值得。
3. 不能编造供应商：身份封闭，注册表独立门禁。
4. 不能超预算：每项操作都受门禁约束，客户端没有隐藏重试循环。
5. 健康供应商的任务能力仍可能为 UNKNOWN、UNSUPPORTED 或 QUARANTINED。
6. UNKNOWN 只允许有界检查；检查成功仍需新决策。
7. 尝试与决策是仅追加、精确身份、公开安全的证据。
8. 语义失败不属于基础设施切换；Review/Proof 不变。

## 验证与运行边界

Mock 供应商测试覆盖 Sol 失败 → 已验证 Luna 失败 → UNKNOWN MiMo 检查 PASS → MiMo 执行 PASS。真实 DependencyScheduler 测试随后在同一 Graph 完成下游工作并进入 REVIEW。这是本地确定性证据，不是生产完成声明。PostgreSQL 测试使用隔离临时 schema，涵盖不可变证据、并发入口、重启预算保护和精确 Run API 视图。

广泛回归发现两个既有 currency 夹具失败，已在干净起始提交复现。仅将计算夹具从通用 CURRENCY 修正为 USD，以匹配既有发布契约；未更改生产投影代码。还要求前端类型检查 / 构建及 M3–M6 交互检查。

本任务不包含真实模型 / 供应商调用、重执行授权、R5、Memory v2、学习式排名、POT、标签或推送。哈希审计覆盖全部历史 Run、Draft、Scheme、Goal、Task、事件、计算、Review/Release 记录和 Memory 表。基础接受后停止。下一任务：`PHASE_5B_EXECUTE_R5_WITH_ADAPTIVE_RUNTIME`。

最终验证：724 项 Python 测试通过（后端产品、Agentic、Peer 输入、TeamoRouter 执行策略和传输可观测性）；119 项前端 M3–M6 检查通过；TypeScript 类型检查、Vite 构建、变更文件 Ruff 和 Python 编译通过。两个既有 Starlette/httpx 弃用警告不阻塞。增量生产迁移已应用，证据行数为零，无回填。本地审计产物为 `artifacts/phase6_recovery/before.json` 和 `after.json`，仅含哈希及公开标识；全部 16 张历史审计表计数和哈希相同：39 个 Run、两项重执行授权、一个 Research View，R1/v1 记忆指针不变。
