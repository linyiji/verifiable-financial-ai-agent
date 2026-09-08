# 自适应运行时

[English](ADAPTIVE_RUNTIME.md)

生成能力构建与 Specialist 共用注册表、单路由客户端、RecoveryBudget、Lead 决策、独立策略门和追加式证据存储。初始使用受治理的 Sol 路由；Terra 是显式候选，绝不接受 Luna 别名。模型不符的响应被拒绝并隔离对应路由；另一条独立批准的决策可以在原有预算内选择其他路由。生成操作绑定真实 Task 和能力需求，防止重复进入或外层构建重置预算，同时允许同一 Task 随后执行 Specialist。迁移 0013 仅修改去重索引；旧记录默认属于 Specialist 操作，内容保持不可变。

规格能力证据必须在匹配原始需求的确定性编译通过后才能记录 PASS，并持久化请求／实际模型和候选哈希。UNKNOWN 不代表已有验证。Docker 验证和注册批准仍是独立必需门槛。明确的生成或财务验证拒绝仅影响对应输出，保留构建 ID 和阶段；认证、授权、哈希／安全／运行环境完整性以及未知契约错误仍然致命。生成操作保持原有 180 秒整体构建上限。

来源／依赖事件使用冻结的进度格式和真实记录的任务进度。受限的公开 `message_code` 格式为 `SOURCE_OUTCOME:<endpoint>:<status>:<accepted_count>`、`FINANCIAL_BRANCH:<calculation_type>:<status>:<available>/<required>:<reason>` 或 `BLOCKED_BY_DEPENDENCY:<required_output_ids>`。它们只是展示快照，不是成功或计算依据。来源覆盖只公开十个已定义端点及明确的状态／计数字段；未知字段仍被拒绝。历史畸形事件不重写，也不通过放宽校验接受。

供应商／模型故障 → 系统定义的错误分类 → Lead 恢复提案 → 独立策略门 → 同一 Run 内的有界调用 → 常规结构化输出校验。

恢复过程保留 Object、Run、Scheme、Task、actor/profile，以及精确的输入和输出契约哈希。它不会改变财务证据、重新生成 Scheme、重新规划图，也不会准入另一个 Run。

已注册候选为 teamorouter-sol、teamorouter-luna、teamorouter-terra（gpt-5.6-terra）和 mimo-direct。Terra 在没有精确任务／profile／schema 证据时为 UNKNOWN，不代表已验证能力。健康状态与能力不同：供应商可连接，并不代表它已针对特定 profile/model/schema 完成验证。已有的已验证输出可以提供限定范围的能力证据；否则，只有经单独许可的能力检查才能建立这种证据。新数据库不得导入伪造的认证。

请求 Luna 却返回 Terra 仍记录 MODEL_IDENTITY_MISMATCH 并拒绝。只有明确获准的 Terra 请求和精确 Terra 响应才能通过；缺少实际模型身份也会被拒绝。注册第四条候选不增加任何调用或恢复预算。这是受控维护，不是学习型路由或能力认证。

默认上限：任务总调用最多三次，每条路由一次调用，一次模型回退，一次供应商切换，一次能力检查，五次决策，零次运行时重新规划，总时限 300 秒（包括初始调用）。配置后，同一路由的调用上限可以达到两次，但仍受总计三次的限制。恢复用的单路由客户端禁用隐藏重试／回退。

系统定义的超时、可用性、协议和限流故障可以纳入恢复判断。身份认证、身份标识、不安全输出、输出契约和未知故障均按失败关闭原则处理。候选选择由确定性的受控策略决定，而不是由模型判断自己的重试是否安全。

已验收的历史 Peer 示例展示了同一 Run 内的 MiMo 超时 → ALLOW → Sol 成功。这是一次成功的有界恢复证据，不代表供应商具有普遍可靠性。

[领域模型](../../src/domain/recovery.py) · [运行时](../../src/agentic/recovery.py) · [组装](../../src/agentic/recovery_composition.py) · [验收](../validation/ADAPTIVE_RECOVERY_ACCEPTANCE.zh-CN.md)。
