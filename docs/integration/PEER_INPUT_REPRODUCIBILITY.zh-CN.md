# Peer 模型输入可复现性

[English](PEER_INPUT_REPRODUCIBILITY.md)

重复组装相同的持久化 Peer 授权数据曾产生不同模型输入，因为新构建的 PeerCandidate/PeerSelectionDecision 对象携带基于时钟的 created_at 元数据。模型支持投影现在仅从 candidates、selection_decisions 和 selected_comparables 中省略这些组装时间戳。领域对象和持久化任务产物仍保留时间戳。证据观测日期及所有业务字段保留。

专项验证：29 项测试通过，包含新增的时钟独立性和字段保留测试。从不可变历史 R3 重复构建，在修复后也得到相同上下文。Ruff 和差异检查通过。

Owner 授权的前瞻性传输探测：一次 MiMo Peer 请求，冻结为 14,462 字节，SHA-256 c15d911c9a8b0fbbf51ce1e32d700fce2738d4a81ea06661188d971a64596d3b。当前系统代理路径在 14.872s 内返回 HTTP/1.1 200 和完整正文。类型验证通过；保守的仅探测语义门禁失败。该门禁是启发式规则，可能拒绝有效的数字重排或计数；其本身不足以证明生产输出契约存在缺陷。不执行 Stage B 或重试。代理因果关系仍未证实。

未更改供应商传输策略，未创建生产 Run、AgentOutput 或写入 Memory。未保留历史请求原像：此实验不宣称精确重放历史请求。安全元数据位于 artifacts/model_transport_discriminating_probe；原始提示词 / 响应不在其中。
