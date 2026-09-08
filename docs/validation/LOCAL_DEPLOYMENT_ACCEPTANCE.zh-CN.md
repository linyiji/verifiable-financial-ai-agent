# 本地部署验收边界

[English](LOCAL_DEPLOYMENT_ACCEPTANCE.md)

LOCAL DEPLOYABLE ALPHA = 已验收的现有本地 PostgreSQL + 真实 API + React 产品。CONTROLLED ALPHA READY = 有人协助的评估就绪，而非生产 SaaS。

本次仓库准备工作的范围：

- 对照源码检查了安装要求、迁移入口、API／前端命令、健康检查路由与 CORS 来源。
- 离线测试了评估者 MiMo Settings 与显式私有文件权限；不需要开发者私有默认文件。
- 在本地执行聚焦的后端测试、前端检查、类型检查及构建，没有供应商／数据调用。
- 当前准备结果：98 项后端用例通过，8 项只读 Memory 检查和 24 项 Object V2 检查通过；Node 24.20.0 类型检查／构建通过。同样的 98 项后端用例也在工作流的内存 SQLite 环境中通过。已有警告：两项库弃用警告和前端包大小提示。
- 本任务**未执行**新数据库迁移、全新机器证明工具安装，以及端到端付费评估者 Run。快速开始指南经过源码核对，不代表在每个操作系统上重新获得认证。

全新克隆既不包含历史生产数据，也不包含对应的完整产物存储；截图是证据，不是用来冒充实时输出的 fixture。完整发布新的 Run 可能需要 Docker、真实证明 host，以及付费供应商／数据权限。

[快速开始](../deployment/EVALUATOR_QUICKSTART.zh-CN.md) · [部署详情](../deployment/LOCAL_DEPLOYMENT.zh-CN.md)。
