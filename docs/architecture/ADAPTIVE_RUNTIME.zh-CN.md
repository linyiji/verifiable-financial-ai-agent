# 自适应运行时

[English](ADAPTIVE_RUNTIME.md)

供应商／模型故障 → 系统定义的错误分类 → Lead 恢复提案 → 独立策略门 → 同一 Run 内的有界调用 → 常规结构化输出校验。

恢复过程保留 Object、Run、Scheme、Task、actor/profile，以及精确的输入和输出契约哈希。它不会改变财务证据、重新生成 Scheme、重新规划图，也不会准入另一个 Run。

已注册候选为 teamorouter-sol、teamorouter-luna 和 mimo-direct。健康状态与能力不同：供应商可连接，并不代表它已针对特定 profile/model/schema 完成验证。已有的已验证输出可以提供限定范围的能力证据；否则，只有经单独许可的能力检查才能建立这种证据。新数据库不得导入伪造的认证。

默认上限：任务总调用最多三次，每条路由一次调用，一次模型回退，一次供应商切换，一次能力检查，五次决策，零次运行时重新规划，总时限 300 秒（包括初始调用）。配置后，同一路由的调用上限可以达到两次，但仍受总计三次的限制。恢复用的单路由客户端禁用隐藏重试／回退。

系统定义的超时、可用性、协议和限流故障可以纳入恢复判断。身份认证、身份标识、不安全输出、输出契约和未知故障均按失败关闭原则处理。候选选择由确定性的受控策略决定，而不是由模型判断自己的重试是否安全。

已验收的历史 Peer 示例展示了同一 Run 内的 MiMo 超时 → ALLOW → Sol 成功。这是一次成功的有界恢复证据，不代表供应商具有普遍可靠性。

[领域模型](../../src/domain/recovery.py) · [运行时](../../src/agentic/recovery.py) · [组装](../../src/agentic/recovery_composition.py) · [验收](../validation/ADAPTIVE_RECOVERY_ACCEPTANCE.zh-CN.md)。
