# 产品状态

[English](PRODUCT_STATUS.md)

LOCAL DEPLOYABLE = YES

CONTROLLED ALPHA READY = YES

Controlled Alpha 表示已准备好开展有人协助、定向邀请的评估。此前的就绪范围是面向 3–5 位设计合作伙伴的只读体验；不声称已完成真人理解度研究或实现广泛用户采用。

当前对投资者和测试员的建议：使用直接调用 API 的 BYOK 方式，在本地配置自己的凭据，或由 Owner 单独私下提供的测试凭据。内置 API 调用能力不等于内置测试 Key。Owner 网关处于 NOT_DEPLOYED；其一键安装器是仅面向网关的基础版，不是当前可用的一键 BYOK 工作流。请参阅[高级安装](../deployment/ADVANCED_INSTALLATION.zh-CN.md)。完整发布的研究结果仍需要相应的数据／模型访问权限、证明工具链及发布检查。

| 能力 | 状态／边界 |
| --- | --- |
| Object、Goal、已确认的 AI Scheme、Lead／专业 Agent | 已实现 |
| 动态路径、纠错、研究重新规划 | 在现有权限下已实现 |
| 自适应供应商／模型恢复 | 已实现同一 Run 内的有界基础能力 |
| 确定性财务计算／Review | 针对受支持契约已实现 |
| 必需证明 | 仅覆盖有界计算；需要真实证明工具链 |
| Report ↔ Execution | 已有精确映射可用；整体来源／贡献覆盖为 PARTIAL |
| 完整 Claim Trace 抽屉／延期 PDF 功能 | 不可用 |
| Memory v2、增量研究、Base vs Current | 已实现；不是未来路线图 |
| PostgreSQL + React 产品 | 已实现的本地产品 |
| 评估者凭据网关 | 代码基础已实现；Owner HTTPS 网关为 NOT_DEPLOYED。网关模式需要私下签发的凭据包；当前建议投资者／测试员使用直接 API 的 BYOK。 |
| 完整 Evaluation / POT / 证据驱动路由优化 | 未来工作；契约准备不等于已执行 |
| 通用上下文优化／Phase 7 能力认证 | 下一层能力；不声称已实现学习型路由或全局生产认证 |
| ZK Agent Execution Conformance Proof | 计划中的动作／状态转换证明；当前证明仅覆盖有界计算 |
| 公开 SaaS、企业 Auth/RBAC/SSO、计费 | 未作此声明／未在此实现 |
| 投资建议适用性／生产企业级就绪 | 未作此声明 |

下一开发方向：Evaluation → POT → 证据驱动的 Provider / Model Selection。现有记忆复用不依赖这个未来平台的完成。

公开只读 GET 投影目前会重建权威事实而不写入缓存。浏览历史不会自动物化 Memory。只读验收在服务端阻止变更操作。

[验证](../validation/PRODUCT_ACCEPTANCE.zh-CN.md) · [许可证状态](../LEGAL_AND_LICENSE_STATUS.zh-CN.md)。

## 独立金融分支与默认对象

独立金融分析并行执行；单项数据不足进入限制记录，不阻断无依赖结论。当前金融扩展采用最多三个并发分支；这不表示所有 Agent Task 都完全并行。每个已校验计算独立持久化。缺少输入的指标记录 INSUFFICIENT_DATA，不产生数值或依赖结论；真正的执行错误仍然失败。Task 可以带结构化限制完成。

默认一般研究的技术分支为 SUPPORTING；Scheme.calculation_requirements 中显式指定的规范能力 ID 为 REQUIRED。既有完整公式集合的 Financial Review / Proof / Release 规则保持不变：任务继续不等于可以发布，缺项仍可能阻止最终 Release。任务详情展示分支状态与可用/所需输入数。当前改动尚未获得新版本实机发布验收，不应宣称 Alpha 2 已发布。

PostgreSQL 迁移后，产品 API 启动会幂等创建空的 NVIDIA / NVDA Research Object，现有同 ticker 对象保持不变。不会初始化任何 Run、Scheme、证据、报告或 Research Memory，也不调用 provider。BYOK / Owner gateway 的凭证和部署边界没有改变。
