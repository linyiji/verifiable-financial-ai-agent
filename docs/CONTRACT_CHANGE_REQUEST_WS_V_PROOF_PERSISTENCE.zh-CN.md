# CONTRACT_CHANGE_REQUEST — WS-V 证明持久化

[English](CONTRACT_CHANGE_REQUEST_WS_V_PROOF_PERSISTENCE.md)

状态：`REQUESTED`

请求负责方：协调者／PostgreSQL 单写者

请求方：WS-V RISC Zero Proof

## 原因

WS-V 刻意不修改已冻结的共享契约、全局数据库配置或 Alembic schema。
Phase 3 集成需要持久化证明谱系，而非将适配器返回的 receipt 路径视为权威记录。

## 请求的持久记录

在不改变含义的前提下，持久化已冻结的领域字段：

- `ProofInputCommitment`：承诺 id、run id、计算 id、公式 id、能力 id、
  实现哈希、有序证据引用、规范输入、输入承诺、预期输出承诺、时间戳。
- `ProofRecord`：证明 id、run id、计算 id、后端、程序 id、镜像 id、实现哈希、
  输入承诺、receipt 产物引用／哈希、journal 哈希、状态、证明耗时、时间戳。
- `ProofVerificationRecord`：验证 id、证明 id、验证器、镜像 id、receipt 哈希、
  journal 哈希、状态、verified、详情、时间戳。
- `ProofArtifactReference`：产物 id、证明 id、产物类型／引用、内容哈希、字节大小、
  时间戳。

## 完整性要求

- 外键必须将证明记录关联到其 Run 和计算，将验证／产物行关联到其证明。
- `proof_id`、`commitment_id`、`verification_id` 和 `artifact_id` 是唯一／幂等键。
- receipt 存放在关系型 JSON 之外；只持久化其受控产物引用、SHA-256 哈希和大小。
- 无损持久化有序证据引用和规范输入。
- 转换为 `VERIFIED` 时，必须要求程序镜像 id、输入承诺、receipt 哈希和 journal 哈希匹配。
  失败绝不能覆盖此前不可变的验证记录。

## 集成说明

适配器当前在 `ProofResult.verifier_result` 中返回全部必需值，在
`ProofResult.receipt_ref` 中返回 receipt 产物路径。协调者应在合并 WS-V 后，将这些值映射
到冻结的领域模型和迁移。WS-V 分支不包含任何持久化迁移。
