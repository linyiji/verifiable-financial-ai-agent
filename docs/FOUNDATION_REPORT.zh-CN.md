# 基础门报告

[English](FOUNDATION_REPORT.md)

## 范围

基础门冻结仓库骨架、Python/Node 基线、领域与传输契约、运行时事件与状态、
能力／追踪／证明接口、数据库基类、仓储协议，以及测试 fixture 基线。
业务实现仍由并行工作线负责。

前端实现仍为 `DEFERRED_PENDING_FINAL_UX_BASELINE`。保留的 HTML 原型是草稿／参考资源，
不是最终或规范前端基线。

## 运行时基线

- Python：`>=3.11,<3.12`
- Node.js：`>=24,<25`
- 修正依据：`ARCHITECTURE_BASELINE_CORRECTION_001`

## 现有逻辑复用矩阵

| 现有模块 | 决策 | 复用方式 | 兼容性 | 操作 |
| --- | --- | --- | --- | --- |
| 设计文档和冻结 ADR | DIRECT_REUSE | 直接复用 | 与运行时无关 PASS | 保留为事实源 |
| `frontend_reference/financial_agent_workspace_v3.html` | ADAPTER_REUSE | 保留原型结构／样式／交互供后续 Web 工作使用 | Node 24 审查延后；保留静态资源 | 封装进未来 Web 应用，不在基础阶段重写 |
| `diagrams/金融研究agent平台全流程图.png` | DIRECT_REUSE | 直接作为文档资源使用 | 与运行时无关 PASS | 保留 |
| 财务计算实现 | PORT_REQUIRED | 当时不存在实现；集成前必须在 FinRobot 中审计复用候选 | 本地不存在 | 仅实现最小原生纵向切片；单独审计 FinRobot |
| FMP 处理实现 | PORT_REQUIRED | 供应商适配器边界 | 本地不存在 | 先添加 fixture 供应商，后接真实供应商 |
| Agent／Skill 实现 | PORT_REQUIRED | 冻结契约及适配器／注册表边界 | 本地不存在 | 实现有界工作线；不重写框架 |
| 报告实现 | PORT_REQUIRED | 输出适配器／构建器边界 | 本地不存在 | 仅实现最小 JSON 输出 |
| `third_party/FinRobot` | PORT_REQUIRED | 计划中的 FinRobot 适配器 | 未检出；Python 3.11 范围与上游元数据一致 | 不阻断基础门；可用时审计精确模块 |

基础工作开始时，在项目根目录未发现已有后端、财务、Agent、工具、包或框架源码。
可用的类似实现资源是保留的 HTML 原型；后端 Phase 1 期间不修改它。

## 契约职责

- 协调者：`pyproject.toml`、`package.json`、`contracts/**`、`src/domain/**`、
  `apps/api/main.py`、数据库基类、全局设置。
- 工作线使用这些契约，并提交 `CONTRACT_CHANGE_REQUEST`，而非直接编辑。

## 基础验证

- Python：`3.11.16`
- Node.js：`v24.18.0`
- npm：`11.6.2`
- pytest：`6 passed, 0 failed, 0 skipped`
- Ruff：`All checks passed`
- FastAPI 导入／应用标题：PASS
- 数据库模式：默认异步 SQLite；通过 SQLAlchemy 配置支持兼容 PostgreSQL 的 URL
