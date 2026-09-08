# Phase 2.1 语义契约门

[English](PHASE2_1_CONTRACT_GATE.md)

基线：`947496f482751493b97223d03ce2f85d2e6ddbfe`

状态：PASS

此门仅新增向后兼容的语义字段：

- Run 全局的 Evidence 所有权元数据与任务本地证据引用。
- 显式证据获取结果，不改变调度器终态语义。
- 可审计的图边事件类型。
- 计算实现／运行时，以及 Review/Canonical 谱系字段。
- 分离的 PeerCandidate 与 PeerSelectionDecision 契约。

冻结规则保持不变：只有已接受 Evidence 进入财务代码；确定性财务数字由代码产生；
Agent 不得绕过保障机制；RISC Zero 仍为 `NOT_IMPLEMENTED`；
前端仍为 `DEFERRED_PENDING_FINAL_UX_BASELINE`。

此门修改的共享文件归协调者负责。工作线必须使用它们，并提交
`CONTRACT_CHANGE_REQUEST`，而非编辑共享契约。
