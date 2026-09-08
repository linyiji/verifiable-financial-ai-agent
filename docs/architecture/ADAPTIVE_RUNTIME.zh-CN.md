# 自适应运行时

[English](ADAPTIVE_RUNTIME.md)

生成能力构建与 Specialist 共用注册表、单路由客户端、RecoveryBudget、Lead 决策、模型执行策略和追加式证据存储。生成操作绑定真实 Task 和能力需求，防止重复进入或外层构建重置预算，同时允许同一 Task 随后执行 Specialist。迁移 0013 仅修改去重索引；旧记录默认属于 Specialist 操作，内容保持不可变。

规格能力证据必须在匹配原始需求的确定性编译通过后才能记录 PASS，并持久化请求／实际模型和候选哈希。UNKNOWN 不代表已有验证。Docker 验证和注册批准仍是独立必需门槛。明确的生成或财务验证拒绝仅影响对应输出，保留构建 ID 和阶段；认证、授权、哈希／安全／运行环境完整性以及未知契约错误仍然致命。生成操作保持原有 180 秒整体构建上限。

来源／依赖事件使用冻结的进度格式和真实记录的任务进度。受限的公开 `message_code` 格式为 `SOURCE_OUTCOME:<endpoint>:<status>:<accepted_count>`、`FINANCIAL_BRANCH:<calculation_type>:<status>:<available>/<required>:<reason>` 或 `BLOCKED_BY_DEPENDENCY:<required_output_ids>`。它们只是展示快照，不是成功或计算依据。来源覆盖只公开十个已定义端点及明确的状态／计数字段；未知字段仍被拒绝。历史畸形事件不重写，也不通过放宽校验接受。

供应商／模型故障 → 系统定义的错误分类 → Lead 恢复提案 → 独立策略门 → 同一 Run 内的有界调用 → 常规结构化输出校验。

恢复过程保留 Object、Run、Scheme、Task、actor/profile，以及精确的输入和输出契约哈希。它不会改变财务证据、重新生成 Scheme、重新规划图，也不会准入另一个 Run。

已注册候选为 teamorouter-sol、teamorouter-luna、teamorouter-terra（gpt-5.6-terra）和 mimo-direct。Terra 在没有精确任务／profile／schema 证据时为 UNKNOWN，不代表已验证能力。健康状态与能力不同：供应商可连接，并不代表它已针对特定 profile/model/schema 完成验证。已有的已验证输出可以提供限定范围的能力证据；否则，只有经单独许可的能力检查才能建立这种证据。新数据库不得导入伪造的认证。

受控动态模型路由：系统可以允许 Provider 在一次执行预先授权的模型集合内进行动态模型替换。Preferred Model 表示优先请求模型，Actual Model 表示真实执行模型。真实执行模型必须属于该次调用在执行前已批准的 Authorized Model Set，并完整进入执行记录；Provider 返回值不能自行扩展授权范围。模型可以变化，模型变化的授权规则不能被绕过。新策略 `bounded-model-execution/v1` 在 HTTP 前解析并随每次尝试持久化。Luna→Terra 的明确授权仅覆盖基本面、估值和生成式自由现金流率；UNKNOWN Terra 需要预算内能力检查，否则需要已有精确范围的能力证据。其他 profile 保持精确路由。MiMo Provider / `mimo-v2.5` 通过 `mimo-direct` 获得授权，不属于 TeamoRouter 的替换集合；跨 Provider 必须独立批准。未知身份、缺失身份及关闭替换时仍拒绝，不重新解释历史失败。

成功的替换能力检查可以直接提供已验证的精确 Task 输出，无需再请求一次；这只是成功观察，不认证 Luna 或 Terra。恢复切换与 Provider 替换分别记录。策略快照保留本次首选／wire 模型；Specialist 旧字段 `requested_model` 保持首次请求语义，`actual_model` 标明真实执行。[共享策略](../../src/domain/model_execution.py) 用于 Specialist、生成器和能力检查。图规划与 evaluator 网关维持独立精确路由契约，本次不宣称这两条路径支持动态替换。发布、复核、证明和来源可用性规则不变。

默认上限：任务总调用最多三次，每条路由一次调用，一次模型回退，一次供应商切换，一次能力检查，五次决策，零次运行时重新规划，总时限 300 秒（包括初始调用）。配置后，同一路由的调用上限可以达到两次，但仍受总计三次的限制。恢复用的单路由客户端禁用隐藏重试／回退。

系统定义的超时、可用性、协议和限流故障可以纳入恢复判断。身份认证、身份标识、不安全输出、输出契约和未知故障均按失败关闭原则处理。候选选择由确定性的受控策略决定，而不是由模型判断自己的重试是否安全。

已验收的历史 Peer 示例展示了同一 Run 内的 MiMo 超时 → ALLOW → Sol 成功。这是一次成功的有界恢复证据，不代表供应商具有普遍可靠性。

[领域模型](../../src/domain/recovery.py) · [运行时](../../src/agentic/recovery.py) · [组装](../../src/agentic/recovery_composition.py) · [验收](../validation/ADAPTIVE_RECOVERY_ACCEPTANCE.zh-CN.md)。
