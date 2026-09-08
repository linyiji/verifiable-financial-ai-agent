# Codex 主并行执行提示词 V1

[English](CODEX_MASTER_PARALLEL_EXECUTION_PROMPT_V1.md)

你是 Verifiable Financial Agent System 的工程协调者。

首先阅读：

1. `README.md`
2. `docs/00_READ_FIRST.md`
3. `docs/03_ARCHITECTURE_DECISIONS_V1.md`
4. `docs/19_PARALLEL_MODULE_BUILD_AND_INTEGRATION_V1.md`
5. `docs/02_BACKEND_ARCHITECTURE_V1.md`
6. `docs/04_DOMAIN_DATA_MODEL_V1.md`
7. `docs/14_ACCEPTANCE_TEST_PLAN_V1.md`

用户目标路径：

`<repository-root>`

不要假设路径存在，必须确认。

## 目标

按以下顺序执行后端实现：

> 基础门禁 → 并行工作流 → 集成 → 验收

如果具备并行执行/工作树能力，不要在一个上下文中串行实现整个项目。

## 阶段 1 — 基础

仅完成：

- 仓库骨架
- pyproject
- Python 3.11 后端基线与 Node.js 24 Web 基线
- 共享枚举
- 领域契约
- RuntimeEvent
- API 模式
- 数据库基础
- 测试夹具基础
- 能力/追踪/证明接口

运行测试。

提交：

`foundation: freeze v1 contracts`

不要在此构建全部业务逻辑。

## 阶段 2 — 创建并行工作流

为以下工作创建隔离分支/工作树：

- data-evidence
- agentic
- runtime
- financial-capabilities
- assurance
- output

使用以下目录中的提示词：

`codex/workstreams/`

各工作流不得修改职责外文件，除非提交 CONTRACT_CHANGE_REQUEST。

## 阶段 3 — 模块门禁

针对每个分支：

- 运行测试
- 检查差异
- 阅读 WORKSTREAM_REPORT
- 拒绝重复领域定义
- 拒绝跨层捷径
- 拒绝 API 路由业务逻辑
- 拒绝被标为完成的虚假实现

## 阶段 4 — 合并

按并行计划中记录的依赖安全顺序合并。

仅由协调者解决集成问题。

## 阶段 5 — 集成

执行：

`codex/workstreams/WS_G_INTEGRATION.md`

必需真实链路：

```text
Object
→ Goal
→ AI/fallback Scheme
→ Confirm
→ Run
→ Planned Graph
→ parallel Tasks
→ Evidence
→ Financial Code
→ Self-Correction
→ Replan
→ Review
→ Canonical Execution Record
→ Released Result
```

## 阶段 6 — 验收

运行完整离线验收。

不要在第一个非关键失败后停止。

收集全部失败。

输出最终报告：

```text
A Environment
B Workstreams
C Commits
D Merge result
E Test summary
F Acceptance matrix
G Known gaps
H Next task
```

不要自动启动后续阶段。
