# Verifiable Financial Agent System — Design & Execution Package

> Foundation runtime baseline: backend Python `>=3.11,<3.12`, frontend Node.js `>=24,<25`.

## Current backend status

Phase 1 and the Phase-2 backend integration are implemented. Phase 2 adds unified secret-safe
settings, live FMP evidence collection, TeamoRouter structured Scheme/Planner adapters, a pinned
FinRobot reuse audit, PostgreSQL migrations/durable repository paths, and optional fail-open
Langfuse instrumentation. The controlled Phase-1 fixture remains the default API composition.

Frontend implementation is explicitly `DEFERRED_PENDING_FINAL_UX_BASELINE`. Existing HTML
prototypes remain references only; none is declared final or canonical.

## Quickstart

The current executable scope is an offline, controlled vertical slice. It creates a Research
Object, generates and confirms a deterministic fallback Scheme, runs a dependency graph with real
parallel tasks, validates the bundled NVIDIA fixture, produces Revenue Growth and EBITDA Margin
through registered native capabilities, performs task-local correction and Lead-controlled replan,
then independently reviews and releases one Canonical Execution Record and its A/B/C outputs.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
PYTHONPATH=. pytest -q
PYTHONPATH=. ruff check .
PYTHONPATH=. python scripts/run_acceptance.py
PYTHONPATH=. python scripts/run_phase2_acceptance.py  # requires ignored .env.local credentials
PYTHONPATH=. uvicorn apps.api.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; OpenAPI is at `/docs`. The default composition
uses an in-memory SQLite database and the controlled fixture at
`tests/fixtures/nvda_financials.json`. No live FMP credential is required. The Phase-1 proof adapter
returns `NOT_IMPLEMENTED`; the application never represents that status as a verified proof.

For frontend tooling, use the already-installed Node 24 runtime and run `npm run check:runtime`.
No frontend framework is selected or replaced in this phase; `apps/web/` remains the reserved
integration boundary pending the user's final UX baseline correction.

本目录是当前产品的 **V1 工程设计基线**，用于直接放入：

`/user/mac/Verifiable_Financial_Agent_System`

> 注意：这里使用的是用户指定路径字符串。若本机实际路径是 macOS 常见的 `/Users/mac/...`，请以本机真实目录为准，不要由 Codex 自行猜测或迁移。

## 1. 当前产品一句话

用户选择 / 创建 Research Object，输入 Research Goal；AI 生成本次 Research Scheme 并由用户确认；Research Lead Agent 基于 Object、Goal、Scheme、已有数据和系统能力生成完整 Initial Planned Task Graph；Dynamic Runtime 按依赖并行执行 Specialist Agents / Skills / Capabilities，Task 内优先 Self-Correction，只有必要时才 Controlled Replan；所有正式数据先经过 Evidence Layer，所有确定性金融数字由 Code 产生；最终经过 Financial Review、Proof Policy / ZK、Release Gate，形成 Financial Report 与同一执行事实下的两个复核视角，并将可沉淀结果写回 Research Object。

## 2. 文档权威顺序

如文档之间出现冲突，按以下顺序处理：

1. `docs/03_ARCHITECTURE_DECISIONS_V1.md`
2. `docs/02_BACKEND_ARCHITECTURE_V1.md`
3. `docs/04_DOMAIN_DATA_MODEL_V1.md`
4. `docs/05_AGENT_SKILL_CAPABILITY_RUNTIME_V1.md`
5. `docs/06_DATA_EVIDENCE_FINANCIAL_COMPUTE_V1.md`
6. `docs/07_DYNAMIC_RUNTIME_EVENTS_V1.md`
7. `docs/08_ASSURANCE_LANGFUSE_ZK_V1.md`
8. `docs/09_API_CONTRACT_V1.md`
9. `docs/10_DATABASE_STORAGE_V1.md`
10. 其他专题文档

Codex Phase 1 的执行范围以：

`codex/CODEX_EXECUTION_PROMPT_PHASE_1_V1.md`

为准，但该 Prompt **不能覆盖已冻结 Architecture Decisions**。

## 3. 文件说明

- `docs/00_READ_FIRST.md`：Codex / 开发者阅读顺序与边界
- `docs/01_PRODUCT_AND_WORKFLOW_V1.md`：产品、页面、完整业务流程图
- `docs/02_BACKEND_ARCHITECTURE_V1.md`：后端总体架构基线
- `docs/03_ARCHITECTURE_DECISIONS_V1.md`：冻结决策 / 项目“宪法”
- `docs/04_DOMAIN_DATA_MODEL_V1.md`：核心对象、关系、Canonical Record
- `docs/05_AGENT_SKILL_CAPABILITY_RUNTIME_V1.md`：Agent / Skill / Tool / Capability / MCP / Code Builder
- `docs/06_DATA_EVIDENCE_FINANCIAL_COMPUTE_V1.md`：数据、Evidence、财务计算链
- `docs/07_DYNAMIC_RUNTIME_EVENTS_V1.md`：Planned / Actual Graph、状态机、SSE
- `docs/08_ASSURANCE_LANGFUSE_ZK_V1.md`：Review / Langfuse / ZK / Release
- `docs/09_API_CONTRACT_V1.md`：REST / SSE 契约
- `docs/10_DATABASE_STORAGE_V1.md`：PostgreSQL、Artifact、Trace、Workspace 存储
- `docs/11_FRONTEND_BACKEND_MAPPING_V1.md`：稳定页面与后端对象映射
- `docs/12_OPEN_SOURCE_INTEGRATION_REUSE_V1.md`：FinRobot / Langfuse / RD-Agent / RISC Zero / MCP
- `docs/13_SECURITY_SANDBOX_LOCAL_RUNTIME_V1.md`：Server Sandbox 与未来 Local Runtime
- `docs/14_ACCEPTANCE_TEST_PLAN_V1.md`：测试路径 / Acceptance
- `docs/15_MVP_ROADMAP_V1.md`：实施阶段与优先级
- `docs/16_GLOSSARY_V1.md`：术语
- `docs/17_RISKS_OPEN_QUESTIONS_V1.md`：当前仍未冻结事项
- `docs/18_ORIGINALITY_AND_REUSE.md`：比赛原创与开源复用边界
- `codex/CODEX_EXECUTION_PROMPT_PHASE_1_V1.md`：第一阶段工程执行指令
- `frontend_reference/`：当前 UI 原型，仅供契约和 UX 参考
- `diagrams/`：当前流程图
- `references/`：用户原始流程资料

## 4. 当前一级前端入口

MVP 只强调：

1. 新建任务
2. 任务列表
3. 研究对象

Research Scheme **仍然存在**，但不是独立配置中心。新建任务时：

`Object + Goal → AI Generate Scheme → User Confirm → Create Run`

## 5. 当前工程原则

- Task 是 Agent 拆出来的，不是用户手工创建的内部执行单元。
- Research Run 是用户发起的一次完整研究。
- Scheme 先生成、确认，再规划 Task。
- Initial Plan First，运行中仅受控 Replan。
- Self-Correction 优先在 Task 内完成。
- 未验证数据不得进入正式金融推理。
- 确定性金融数字必须走 Code。
- Agent 对 execution 有自主权，对 assurance 没有绕过权。
- Langfuse 是横切 observability。
- ZK 只证明指定确定性执行，不证明金融事实本身“绝对正确”。
- Financial Report 是业务主输出。
- Financial Review / Execution Details 来自同一 Canonical Execution Record。
- Object 是长期资产，Run 是一次研究执行。

## 6. 建议 Codex 阅读顺序

```text
README.md
↓
docs/00_READ_FIRST.md
↓
docs/03_ARCHITECTURE_DECISIONS_V1.md
↓
docs/02_BACKEND_ARCHITECTURE_V1.md
↓
docs/04_DOMAIN_DATA_MODEL_V1.md
↓
docs/05_AGENT_SKILL_CAPABILITY_RUNTIME_V1.md
↓
docs/06_DATA_EVIDENCE_FINANCIAL_COMPUTE_V1.md
↓
docs/07_DYNAMIC_RUNTIME_EVENTS_V1.md
↓
docs/08_ASSURANCE_LANGFUSE_ZK_V1.md
↓
docs/14_ACCEPTANCE_TEST_PLAN_V1.md
↓
codex/CODEX_EXECUTION_PROMPT_PHASE_1_V1.md
```

## 7. Parallel engineering execution

Backend implementation should follow `docs/19_PARALLEL_MODULE_BUILD_AND_INTEGRATION_V1.md` and `codex/CODEX_MASTER_PARALLEL_EXECUTION_PROMPT_V1.md`.
