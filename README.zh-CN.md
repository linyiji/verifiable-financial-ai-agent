# Verifiable Financial AI Agent

**自主研究 · 结果可验证 · 执行可审计**

AIx Origin Summit · 香港会场 — Flux · 流境

**主方向：C · 可验证的 AI 推理审计 / 金融 Agent**

[English](./README.md) | [简体中文](./README.zh-CN.md)

📄 [最终项目报告 — Flux 比赛提交版](./docs/submission/Verifiable_Financial_AI_Agent_Flux_Final_Report.pdf)

Verifiable Financial AI Agent 是一个面向金融研究的多 Agent 系统：它能够自主规划并完成金融研究、生成真实研究报告，并让报告中的结论反向追踪到产生该结论的真实 AI 执行记录。

## 项目概览

产品将研究对象与研究目标转化为经确认的研究方案、已执行的多 Agent 任务图、持久化的专家输出、Research Lead 综合结论以及内容寻址的 HTML 报告。报告结论始终关联到准确的 Run、Task、Agent 输出、执行事件和报告贡献。

## Flux 方向契合

本项目属于 **Flux · 流境，主方向 C**：可验证的 AI 推理审计 / 金融 Agent，是一个 AI × Fintech 产品。

- 解决真实金融研究任务，AI 是不可替代的执行组件
- 专家 Agent 与 Research Lead 自主执行
- Agent 输出结构化、持久化且可审计
- 使用真实金融数据和确定性金融计算
- Report ↔ Execution 双向追踪
- 面向验证、可在本地复现的比赛路径

当前并非每个研究步骤都需要区块链。系统准确组合 AI 执行、证据、确定性计算、审计记录，以及适用场景下的有限范围证明策略。

## 为什么重要

普通 AI 金融研究通常止步于生成文本。金融工作还需要审阅者知道：哪个 Agent 完成了任务、使用了哪些安全输入和可观察动作、持久化了什么结构化输出，以及该输出如何进入报告。本项目把这条执行谱系直接做成产品能力。

## 产品价值

| 层级 | 状态 | 产品路径 |
| --- | --- | --- |
| **能用 · 自主研究** | 已实现 | Research Object → Goal → AI Research Scheme → Confirm → Auto-start → Research Lead → Specialist Agents → Dynamic Research Path → Synthesis → Report |
| **敢用 · 可验证、可审计** | 比赛最小闭环已实现 | Report ↔ Agent Output ↔ Execution Record |
| **越用越好 · 证据驱动优化** | **路线图 / 下一阶段** | Historical Runs → Evaluation → POT → Model Selection Candidate |

更广义的保障设计是 `Claim → Evidence → Calculation → Review → Proof`。它与已验收的最小 Demo 边界不同，只在当前能力与证明策略支持的范围内使用。

## 当前可用能力

- 创建 Research Object 和 Goal，生成 AI 研究方案，经用户确认后自动启动 Run。
- 采集并标准化真实 FMP 金融证据。
- 通过依赖感知 Runtime 执行模型提供方支持的专家 Agent 与 Research Lead。
- 按准确 Run 和 Task 谱系持久化结构化 Agent 输出。
- 必要时先进行 Task 内 Self-Correction，再由 Research Lead 受控 Replan。
- 将研究综合为真实、内容寻址的 HTML 报告。
- 从报告贡献打开真实执行详情，并返回报告中的准确锚点。
- 通过 SSE 向 React/TypeScript 前端持续推送 Run 进度。

## 已验收比赛 Demo

| 验收项 | 结果 |
| --- | --- |
| REAL AI RESEARCH | PASS |
| REAL SPECIALIST OUTPUTS | PASS |
| RESEARCH SYNTHESIS | PASS |
| REPORT GENERATION | PASS |
| HTML ARTIFACT | PASS |
| OPEN REPORT | PASS |
| REPORT SOURCE MAP | PASS |
| REPORT → EXECUTION | PASS |
| EXECUTION → REPORT | PASS |
| SAME RUN IDENTITY | PASS |
| CROSS RUN FALLBACK | 0 |
| FIXTURE FALLBACK | 0 |

| 已验收证据 | 标识符 |
| --- | --- |
| Branch | `phase4` |
| Commit | `bc636762f0a89ba2313ab1f9e09df8b0db9f2f6b` |
| Tag | `flux-minimum-demo-2026-09-06` |
| Demo Run | `RUN-57aed683-75d6-4b47-acc6-a73053ea492e` |
| Report | `RESULT-RUN-57aed683-75d6-4b47-acc6-a73053ea492e` |
| Hero anchor | `metric-revenue-growth` |
| Hero actor | `fundamental_analyst` |
| Agent output | `AGOUT-9ab72a67-87e1-523a-a88f-1c4246a26330` |
| Execution event | `EVT-9dc4ef04-5617-4652-9510-61b9905274a0` |

这些标识符是不可变的验收证据，不是生产环境中的硬编码查询条件。产品会解析当前正在查看的 Run 的真实标识。

## 端到端产品流程

```text
Research Object → Goal → AI Research Scheme → User Confirm → Auto-start
→ Initial Task Graph → Specialist Agents → Dynamic Execution
→ Research Lead Synthesis → HTML Financial Report
↔ Exact Observable Execution Record
```

## 多 Agent 研究

| 角色 | 职责 |
| --- | --- |
| Research Lead | 规划研究并对权威综合结论负责 |
| Fundamental Analyst | 分析财务报表和经营表现 |
| Peer Analyst | 建立并解释可比公司语境 |
| Research & News Analyst | 收集相关公司与市场信息 |
| Valuation Analyst | 在可用证据边界内完成估值分析 |
| Risk Analyst | 识别风险、局限与后续研究需求 |

专家输出按准确 Run/Task 谱系持久化，并由 Research Synthesis 消费。辅助执行服务和确定性能力不会被描述为 Agent。

## 动态研究路径

```text
Initial Graph → Execution → Evidence or correction issue
→ Self-Correction first → Lead-controlled Replan where needed → Actual Graph
```

Runtime 遵循 **Initial Plan First**、Task 内 **Self-Correction first** 和 **Lead-controlled Replan**。Graph v1 记录初始方案；当某次 Run 确有必要时，Graph v2 记录经批准的变化路径。并非每次 Run 都会 Replan。

## Report ↔ Execution 追踪

普通 AI 生成一份报告。

Verifiable Financial AI Agent 让报告中的结论能够回到产生它的真实 AI 执行记录。

```text
Financial Report
    ↓
Revenue Growth
    ↓
查看研究来源
    ↓
Fundamental Analyst
    ↓
Exact Task
    ↓
Input → Observable Process → Structured Output
    ↓
Report Contribution
    ↓
返回报告
```

**只展示 Observable Process。** 执行详情展示安全输入、可观察动作、结构化输出、标识符和报告贡献；不会展示隐藏 Chain-of-Thought、原始 Prompt、模型提供方原始 Payload 或密钥。

## 技术架构

```text
React + TypeScript UI
        │ REST + SSE
        ▼
FastAPI product API
        │
PostgreSQL-backed runtime worker and dependency scheduler
        ├── Research Lead + Specialist Agents ── configured model provider
        ├── Evidence collection ──────────────── FMP
        ├── Deterministic financial capabilities
        ├── Review / proof policy ────────────── RISC Zero where bounded
        └── Content-addressed Agent and report artifacts
```

API 应用生命周期会自动启动 PostgreSQL-backed runtime worker；比赛组合不需要单独启动 Scheduler 进程。

## 可验证性设计

已验收最小闭环在同一个准确 Run 上完成 `Report ↔ Agent Output ↔ Execution Record`。每个报告贡献都能解析其 `run_id`、`task_id`、actor、`agent_output_id`、执行 event/action、结构化输出和报告锚点。

仓库的更广义设计还包括 Evidence gating、确定性计算、Review、Release 和 Proof Policy。RISC Zero 支持证明有限范围的确定性计算，例如受支持的 Revenue Growth 工作流；它不证明外部数据的客观真实性，也不证明所有 AI 结论。

## 技术栈

| 领域 | 当前实现 |
| --- | --- |
| 后端 | Python `>=3.11,<3.12`、FastAPI、Pydantic、SQLAlchemy、Alembic |
| 前端 | Node.js `>=24,<25`、React、TypeScript、Vite |
| 持久化 | PostgreSQL；内容寻址的本地 Artifact |
| 金融数据 | Financial Modeling Prep（FMP） |
| 模型路径 | TeamoRouter / 已配置模型提供方；配置支持 Mimo Planner 路由 |
| Runtime | 依赖调度器、事件驱动执行、Checkpoint、SSE |
| 金融计算 | 确定性 Python Capability Runtime |
| 验证 | Review/Release Policy 和有限范围的 RISC Zero Proof Workflow |
| 可观察性 | 可选 Langfuse 集成，包含脱敏控制 |

## 快速开始

前置要求：Python 3.11、Node.js 24、PostgreSQL；Generated Capability 验证需要 Docker；有限范围证明工作流需要 RISC Zero 工具链。

1. 安装后端和前端依赖。

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   python -m pip install -e '.[dev,postgres]'
   cd apps/web
   npm ci
   cd ../..
   ```

2. 创建本地配置，并填入自己的 PostgreSQL、FMP 和模型提供方凭证。

   ```bash
   cp .env.example .env.local
   ```

3. 根据 `DATABASE_URL` 创建 PostgreSQL 数据库，执行迁移并构建 Proof Host。

   ```bash
   PYTHONPATH=. python scripts/postgresql_migrate.py
   ./zk/revenue_growth/build-host.sh
   ```

4. 启动后端。Runtime worker 会随应用自动启动。

   ```bash
   PYTHONPATH=. uvicorn apps.api.main:app --host 127.0.0.1 --port 8010
   ```

5. 在另一个终端启动前端。

   ```bash
   cd apps/web
   npm exec vite -- --host 127.0.0.1 --port 4173
   ```

6. 打开 `http://127.0.0.1:4173`，创建 Research Run，生成并确认研究方案，等待 Run 到达 `RELEASED`。
7. 打开研究结果，点击 **Revenue Growth → 查看研究来源**，检查准确执行详情，再点击 **返回报告** 回到相同 Revenue Growth 锚点。

端口 4173 默认连接本地 8010 API，也可通过 `VITE_API_BASE_URL` 指定其他 API Origin。

## 配置

将 [`.env.example`](./.env.example) 复制为已被 Git 忽略的 `.env.local`。只在文档中展示变量名，绝不提交真实值。

| 用途 | 环境变量名 |
| --- | --- |
| 数据库与存储 | `DATABASE_URL`、`ARTIFACT_ROOT`、`WORKSPACE_ROOT` |
| 前端 API | `VITE_API_BASE_URL` |
| FMP | `FMP_API_KEY` 或连续的 `FMP_API_KEY_1`…`FMP_API_KEY_N`、`FMP_BASE_URL` |
| TeamoRouter | `TEAMOROUTER_API_KEY`、`TEAMOROUTER_BASE_URL`、`TEAMOROUTER_MODEL`、`TEAMOROUTER_FALLBACK_MODEL` |
| Mimo Planner 路由 | `MIMO_API_KEY`、`MIMO_BASE_URL`、`MIMO_DATA_MODEL`、`MIMO_CHAT_MODEL` |
| Provider Policy | `PLANNER_PREFERRED_PROVIDER`、`PLANNER_FALLBACK_PROVIDERS`、`LLM_PROVIDER` |
| 可选可观察性 | `LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`、`LANGFUSE_BASE_URL` |

## API / FMP 集成

FastAPI 产品接口用于创建和确认 Run、读取当前 Run 状态与 Artifact，并通过 SSE 推送执行事件。FMP Adapter 包含凭证选择、Provider Mapping、财务报表采集、标准化、Evidence Handling、Focused Tests、Controlled Fixtures 和只读的 NVDA Live Smoke 路径。大多数测试是确定性的，不需要真实 FMP 访问。

## 测试与验收

GitHub 更新验收门均已通过：

| 验收门 | 命令 | 结果 |
| --- | --- | --- |
| FMP focused | `.venv/bin/python -m pytest -q -p no:cacheprovider tests/unit/data/test_fmp_adapter.py tests/unit/data/test_live_fmp_integration.py tests/integration/live_fmp/test_nvda_evidence_calculation_flow.py tests/unit/data/test_peer_data_semantics.py tests/unit/application/test_evidence_semantics.py tests/integration/test_peer_selection_pipeline.py` | PASS |
| Agent focused | `.venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_research_agent_runtime.py tests/unit/agentic/test_research_agent_outputs.py` | PASS |
| Report trace | `.venv/bin/python -m pytest -q -p no:cacheprovider tests/unit/adapters/test_finrobot_professional_reporting.py tests/phase4/backend_product/test_artifacts.py tests/phase4/backend_product/test_api_contract.py` | PASS |
| Typecheck | `cd apps/web && node_modules/.bin/tsc --noEmit -p tsconfig.json` | PASS |
| Production build | `cd apps/web && npm run build` | PASS |
| FMP live smoke | `.venv/bin/python tests/integration/live_fmp/run_nvda_vertical_slice.py` | PASS |

Live Smoke 需要已配置 FMP 凭证；确定性 Focused Tests 不需要。

## 安全 / 合规

- 不需要真实客户资金，也不需要未脱敏的个人金融数据。
- 外部金融数据和模型提供方仍然是运行依赖。
- 本项目是研究支持软件，不是持牌证券服务或投资保证。
- AI 输出可能包含错误和不确定性；可追踪不代表结论得到保证。
- 报告执行详情排除密钥、原始 Provider Payload、Prompt 和隐藏 Chain-of-Thought。
- 密码学证明只证明有限范围计算，不证明外部金融数据的客观真实性。

## 可复现性

检出已验收 Tag，可复现比赛代码基线：

```bash
git checkout flux-minimum-demo-2026-09-06
```

使用自己的 PostgreSQL、FMP 和模型提供方配置，然后按照“快速开始”执行。以上已验收标识符记录了一次真实 Demo 执行；新的 Run 会产生新的身份，不依赖 Cross-Run 或 Fixture Fallback 完成比赛路径。

## 最终项目报告

完整比赛叙事、架构、验收证据和产品定位请阅读 [Flux 比赛最终项目报告](./docs/submission/Verifiable_Financial_AI_Agent_Flux_Final_Report.pdf)。不可变提交坐标见简短的 [Submission Manifest](./docs/submission/README.md)。

## 原创性 / 开源复用

系统使用开源及第三方基础设施，同时清晰区分比赛产品工作和集成边界。权威披露见 [原创性与复用说明](./docs/18_ORIGINALITY_AND_REUSE.md)；历史 Attribution 文档保持不变。

## 当前局限

- FMP 数据覆盖范围与 Endpoint Entitlement 取决于所配置账户。
- 模型提供方可用性和输出质量仍属于外部依赖。
- 并非每次 Run 都需要或执行 Replan。
- 已验收最小闭环证明报告到执行的谱系；更广义的 Review 和 Proof 能力取决于具体 Capability 与 Policy。
- 系统支持金融研究与审计，不执行自主托管、交易，也不保证投资决策。
- Historical Run Evaluation、POT 和自动模型选择尚不是当前生产自动进化能力。

## 路线图

| 阶段 | 范围 |
| --- | --- |
| **当前** | Verifiable Autonomous Research |
| **下一步** | Research Object Memory |
| **随后** | POT / Evaluation / Model Selection |
| **未来** | Capability Certification / Global Reuse |

只有“当前”阶段被描述为已经实现的比赛功能。

## 文档

README 是当前产品入口。现有 [`docs/`](./docs/) 文档包用于保留架构 / 设计历史和冻结决策记录，不再代表当前 Landing Page 状态。

- [阅读入口](./docs/00_READ_FIRST.md)
- [架构决策](./docs/03_ARCHITECTURE_DECISIONS_V1.md)
- [后端架构](./docs/02_BACKEND_ARCHITECTURE_V1.md)
- [原创性与复用](./docs/18_ORIGINALITY_AND_REUSE.md)
- [Phase 4 文档](./docs/phase4/)
- [最终报告提交清单](./docs/submission/README.md)
