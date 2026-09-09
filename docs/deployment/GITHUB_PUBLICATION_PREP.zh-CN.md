# GitHub 发布准备 — 不更改远端

[English](GITHUB_PUBLICATION_PREP.md)

建议描述：可本地部署的自适应财务研究智能体，具备可验证执行、财务复核、研究记忆及有界运行时恢复能力。

建议主题：financial-research、multi-agent、ai-agents、research-memory、adaptive-runtime、fastapi、react、postgresql、verifiable-computation。

建议发布标题：Verifiable Financial Agent — Local Deployable Alpha。

默认分支建议：审慎审查并同步后，通过 Owner 批准的 main 集成或明确的默认分支决策，将已接受的产品分支设为公开入口。不要假设当前默认分支包含已接受的产品。

分支清理：在另行授权的发布任务中盘点并比较远端分支的可达关系。保留验收标签及未合并工作；不要仅凭名称删除。

发布前：审查脱敏的密钥审计及许可证决策。获奖信息现已由 Owner 确认：AIx Origin Summit Hong Kong · Flux Track · Bronze Award；不应再描述为尚未确认。不要发布私有数据库 / 产物、运行时授权文件、密钥或参与者原始数据。供应商基础 URL / 模型 ID 是配置，不是凭据。

投资者 / 测试员可使用 Docker 引导安装器及 Owner 私下提供的加密 `.vfacred` 包，或使用[原生 BYOK](LOCAL_DEPLOYMENT.zh-CN.md)。产品内置 API 集成，而不是 API 密钥。可选网关仍为 NOT_DEPLOYED；加密直连凭据不依赖它。Release 镜像打包锁定的 RISC Zero 3.0.6 Proof 与受治理 Sandbox Broker。

本发布准备任务未执行推送、Release 发布、远端标签创建、元数据修改、默认分支变更或远端分支删除。
