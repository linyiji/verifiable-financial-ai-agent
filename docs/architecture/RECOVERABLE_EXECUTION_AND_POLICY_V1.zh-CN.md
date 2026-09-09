# 统一恢复与决策治理 V1 — 冻结接口

这是 PARTIAL 离线实施合同，不是生产认证。本轮仅离线；历史 Run 和旧中断重入保护不变。
完整接口和状态机见[英文合同](RECOVERABLE_EXECUTION_AND_POLICY_V1.md)，两者同版本。

## 开关与边界

新执行必须显式注入 V1 仓储/执行器，提供 `recoverable-execution/v1`、
有限 Intent 总预算、绝对截止时间和完整操作快照。缺失字段标记
LEGACY_NOT_RESUMABLE，不补造预算、授权、价格、epoch。生产仍使用原组合，
仅完成真实组合离线验收后才可开放入口。模型提案默认关闭，普通任务授权不等于
DECIDER 授权。保留当前 Profile 默认预算、4/3/300 例外、生成外层180秒、
候选和动态替换授权的区别。

支持同 Run 崩溃重新投递、新 Task Attempt、已验证输出复用、单次授权业务失败
恢复、授权缺失 Memory 收尾。不支持任意分支重做、暂停、Context 重写、自动补证据、
再认证和新研究。现有 Required/Review/Proof/Release 门不降低。

## 统一身份与事务

共同模型为 ExecutionContract / ExecutionBudget / LeaseToken / CallPurpose。
Intent 可以先于 Run 存在，准入只关联 Run，不重置规划预算。每个 Operation 冻结
Intent/Run/Task、Scheme/Object/as-of、Graph、Required/依赖、输入和 Evidence/
Calculation/父输出摘要、schema/公式/代码/策略/source、候选/替换授权、预算/截止时间。
V1 freeze 原语原子保存完整合同，同一操作身份的新摘要被拒绝，不读取最新配置替代批准。

SQLExecutionLedger 使用独立增量表，每个 Intent 行锁串行化全部操作的预算预留；
同 Task 多 Operation 共享 Task 用量。全部权威写入在同一事务校验 owner、租约和 epoch，
覆盖输出、aggregate、event、checkpoint、Report/Release/Memory 引用。产物按 Attempt
隔离且发布前验证 hash。具体方法签名以英文冻结合同为准；时间是 UTC epoch 秒。

物理调用包括内部 HTTP retry：RESERVED → DISPATCHED → RESULT_SAVED → SETTLED。
仅未派发 RESERVED 可撤销退款；接管时 DISPATCHED 转 RESULT_UNKNOWN，不自动重发，
不当作成功、未调用或零费用。未提供供应商幂等能力时不宣称外部 exactly-once。
检查独立于正式 execution 槽，但消耗总物理额度、时间和已知成本；数字成本硬上限
没有可靠估价时拒绝。精确检查结果复用只消费一份已保存结果，绝不重复调用。
Intent/Task/Operation 和单次 timeout 共同约束；重启不能延长 deadline。

## 投递、检查点与收尾

持久化操作本身是 PENDING/CLAIMED/COMPLETE/FAILED 投递记录，claim 不删除 ACK。
租约到期可发现并接管；业务 FAILED 必须一次性合同绑定授权，保留原失败和 Attempt。
未知结果阻止普通续接。Checkpoint v2 保存合同、owner、输出验证、账本、已检查候选、
绝对截止时间、兼容条件；先对账已保存输出，不能因 checkpoint 落后重发请求。

发布阶段为 PREPARED → RELEASED → MEMORY_MATERIALIZED → COMPLETED，不增加 Run enum。
Memory 需要精确 Object/Run/发布结果身份和授权；缺授权保留已发布待物化，禁止回滚。
同身份重复阶段幂等，换身份拒绝。输入/期间/公式/schema/关键策略/Graph 变化使旧输出
及下游 Review/Proof 失效；不开放随意复算和历史原位替换。

回退关闭 V1 新准入、动作与接管，保留新表供兼容读取、按版本对账在途预留；
不降级数据库、不删除记录。API/UI 仅在真实组合离线验收后开放，恢复不是新建研究。

## 已实现的组合与尚未接入的边界

RecoverableDependencyRunner 使用现有 DependencyScheduler，结合持久化合同、父子
epoch fencing、输出对账、Attempt 产物和 checkpoint v2。假供应商测试覆盖同 Run
中断续接及 API 单次授权恢复。memory_recovery_v1 调用真实 ResearchMemoryRepository，
fencing 与 Memory 物化在同一 PostgreSQL 事务内，覆盖回滚、并发和旧 owner 拒绝。
仅更新发布阶段账本不等于证明真实 ReleasedResult 已经持久化。

LedgerHTTPTransport 已通过实际 FMP / TeamoRouter Adapter 的 mock HTTP 组合测试，
覆盖内部重试与实际 fallback model 计数。原始 HTTP 收据不是已验证的 Task 输出。
PlanningContract 支持 Run 之前的 Scheme / Graph 身份，不虚构 Run、不改变确认意图。

API router 与 UI component 均为 opt-in，**未挂载到默认产品**。模型提案默认 OFF，
DECIDER 独立授权，退路有限。以下生产组合仍未完成：

- 旧准入路径尚未为所有 Intent/Run 冻结 V1 合同。
- 原动态批准事务尚未接入新 freeze 原语。
- 生产规划、数据和模型全部传输尚未统一挂接物理账本。
- V1 event/aggregate 引用尚未完整桥接原产品投影表。
- 执行器支持持久化投递接管，但未启用生产启动扫描器。

所以原语和组合测试通过不等于生产端到端恢复已完成，不能据此开放动作或执行 Live。
详见[离线验收](../validation/RECOVERABLE_EXECUTION_AND_POLICY_V1_ACCEPTANCE.zh-CN.md)。
C03 保留语义字段/记录及祖先路径，无关文案继续原裁剪，每个受保护字段/记录上限32 KiB。
P01 安装前校验构建输入内容；清单不是签名，也不代表新发布镜像已实测。
Windows 原生执行仍为 NOT_OBSERVED。历史审计未观察项不自动升级为 PASS。
