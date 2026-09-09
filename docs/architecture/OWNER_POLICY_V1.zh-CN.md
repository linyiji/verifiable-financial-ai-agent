# Owner 策略 V1

[English](OWNER_POLICY_V1.md)

版本：`recoverable-owner-policy/v1`。唯一描述源：[owner_policy.py](../../src/domain/owner_policy.py)。
本描述统一既有前瞻授权，不新增全局模型权限。运行时候选、动态替换授权、恢复预算与自适应传输默认值来自该源；离线一致性测试把双语矩阵与描述逐字比较。历史策略和审计证据不改写。

<!-- OWNER_POLICY_TABLE_START -->
| TaskProfile | Preferred | Candidates | Dynamic grants | Cross-provider | Execution/check/physical | Check | Outer seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GENERATED_CAPABILITY:gross_margin | teamorouter-sol | teamorouter-sol, teamorouter-luna, teamorouter-terra | NONE | NO | 3/1/4 | SEPARATE_EXECUTION | 180.0 |
| fundamental_analysis | teamorouter-sol | teamorouter-sol, teamorouter-luna, teamorouter-terra, mimo-direct | teamorouter-luna→teamorouter-terra | YES | 3/1/4 | SEPARATE_EXECUTION | N/A |
| valuation_analysis | teamorouter-sol | teamorouter-sol, teamorouter-luna, teamorouter-terra, mimo-direct | teamorouter-luna→teamorouter-terra | YES | 3/1/4 | SEPARATE_EXECUTION | N/A |
| risk_analysis | teamorouter-sol | teamorouter-sol, teamorouter-luna, teamorouter-terra, mimo-direct | teamorouter-luna→teamorouter-terra | YES | 3/1/4 | SEPARATE_EXECUTION | N/A |
| risk_follow_up | teamorouter-sol | teamorouter-sol, teamorouter-luna, teamorouter-terra, mimo-direct | teamorouter-luna→teamorouter-terra | YES | 4/3/4 | CONSUME_ONCE | N/A |
| peer_analysis | mimo-direct | mimo-direct, teamorouter-sol, teamorouter-luna | NONE | YES | 3/1/4 | SEPARATE_EXECUTION | N/A |
| research_news_analysis | mimo-direct | mimo-direct, teamorouter-sol, teamorouter-luna | NONE | YES | 3/1/4 | SEPARATE_EXECUTION | N/A |
| report_synthesis | teamorouter-sol | teamorouter-sol, teamorouter-luna, teamorouter-terra, mimo-direct | NONE | YES | 4/3/4 | CONSUME_ONCE | N/A |
| GENERATED_CAPABILITY:free_cash_flow_margin | teamorouter-sol | teamorouter-sol, teamorouter-luna, teamorouter-terra | teamorouter-luna→teamorouter-terra | NO | 3/1/4 | SEPARATE_EXECUTION | 180.0 |
| evidence_collection | NATIVE_DATA | NONE | NONE | NO | N/A | NOT_APPLICABLE | N/A |
<!-- OWNER_POLICY_TABLE_END -->

Execution/check/physical 是不同上限：失败检查消耗物理调用预算，但不必占正式执行槽。risk_follow_up/report_synthesis 保留四次物理调用、三次检查、300 秒的显式有序恢复例外。普通 Profile 保留三次执行加一次检查。检查不是免费调用。未知费用为 null，不是零；数字成本硬上限没有可靠计量时拒绝调用。

模型任务默认保留每路由一次、具有独立授权候选时最多一次跨 Provider、五次决策、零次 Replan、300 秒任务上限。普通 Profile 一次模型切换，有序例外两次。显式 RecoveryBudget 构造参数保留原覆盖优先级，V1 必须同时冻结覆盖来源。首选路由来自 Settings.specialist_provider_routes 或 GovernedCodeBuilder.initial_route，仍需通过候选门。生成操作额外受既有 180 秒外层上限约束。V1 重启不能获得新的截止时间。

直接允许 Terra 不等于允许 Luna 返回 Terra。五项明确替换授权是基本面、估值、风险、风险 follow-up 和生成式自由现金流率。Synthesis 和生成式毛利率虽然可直接选择 Terra，仍无 Luna→Terra 替换权限。MiMo 是独立跨 Provider 候选，不是 TeamoRouter 的替换模型。

有序 Profile 的验证成功 exact check 只消费一次。其他 exact check 仅建立限定能力，之后需另一次经 Gate 的执行。成功的已授权替换检查可一次性提供已验证输出。复用绑定 Task/Operation、输入、schema、实际 Provider/Model 与验证结果；简单探测不能充当研究输出。新冻结 V1 合同保留这些区别。

## 独立入口合同

Scheme、Graph 不借用 Specialist 候选或替换授权。二者使用显式配置的精确路由（配置 Sol 可保留原 Luna fallback）、90 秒单次与 180 秒 workload 策略、零次能力检查。Scheme 保留两次验证；生产 Graph 保留一次验证及 fail-closed，独立构造器覆盖单独冻结。每次内部 HTTP attempt 都计数，而非只数外层方法。INCREMENTAL_RESEARCH_PLANNING 仅是遥测别名，不是第三项模型操作。初始确定性 Scheme/Graph 不伪造模型调用。

原生 Evidence 使用 FMP 结构化金融数据与 Bocha Web 发现，均保留 20 秒 HTTP 默认值；Bocha AI 不在范围内。原生数据不继承模型预算。V1 准入要求显式有限 Intent/Run 总预算，缺失则拒绝而非凭空增加额度。FMP 瞬态重试及受控凭据轮换各自计入物理请求。quality_review 仍仅声明，非可执行 Profile。

自适应单路由传输默认值：连接 10 秒、读取 60 秒、写入 30 秒、连接池 10 秒、一次 attempt、无隐藏 backoff/fallback、90 秒单次墙钟上限。所有外层和绝对 deadline 共同约束执行。

## FMP 健康作用域

端点 402/403 或 payload 权限拒绝保持 ENTITLEMENT_DENIED，不使认证失效、不遍历凭据池；文字稿拒绝不能污染报价或财务报表端点。模糊 403 不升级全局认证失败。401 或明确认证分类使对应凭据跨端点失效。有界槽排除适用于 HTTP429 及已分类的 payload200 限流，耗尽槽不自动重置；结构化证据明确为账号级限制时停止所有槽、不轮换。单端点失败不推断 Provider 整体故障。混合池耗尽保留最后实际分类，不伪造认证失败。本修复不推断任何历史 Run 的因果。
