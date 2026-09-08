# Phase 2.1 + 基础设施真实集成验收报告

[English](PHASE2_1_INFRASTRUCTURE_ACCEPTANCE_REPORT.md)

日期：2026-09-04（Asia/Shanghai）<br>
决策：**PASS**<br>
前端 / Generated Capability / RISC Zero / POT / Comparison：**DEFERRED / OUT OF SCOPE**

## A. 基线 HEAD

- WS-R/WS-S 集成前的执行基线：`aa003c9`
- 本报告前的集成代码和状态基线：`d6b06a6`
- 运行时基线：项目 `.venv` Python `3.11.16`；Node.js `24.18.0`；npm `11.6.2`
- `pyproject.toml` 保持 Python `>=3.11,<3.12`。

## B. PostgreSQL

- 现有容器：`verifiable-financial-postgres`；运行中；未执行 `docker run`、删除卷、
  删除 schema 或降级。
- 服务器：PostgreSQL `16.15`；数据库 `verifiable_financial_agent`；应用用户 `vfa`。
- Unified Settings 从被忽略的 `.env.local` 加载 `DATABASE_URL`；文件权限 `0600`；
  `.env.example` 保留空白 `DATABASE_URL=` 模板。
- Alembic 将现有数据库从无修订依次迁移经过 `0001`、`0002` 及只追加的
  `20260904_0003`；最终 schema 包含 18 张表。
- 迁移 `0003` 添加持久化的计划／实际 `TaskDependency` 行，不重写此前修订。
- 真实 PostgreSQL 套件：9 项通过。
- 五十个并发事件写者产生连续、唯一的 Run 内序列，无缺口或重复；
  一次显式跳号被拒绝。
- 权威 NVDA Run 持久化了 120 个 RuntimeEvent，序号 `1..120`，图版本 2，
  15 条计划和 16 条实际依赖行，以及检查点、Evidence/Calculation 谱系、纠错、
  重新规划、审查、规范记录和已发布结果。
- 新的 engine/session 组装恢复了聚合、检查点、事件回放、规范记录和已发布结果，
  完整模型相等。SSE 回放从序号 1 恢复。
- P2-019 和 INFRA-001..007：PASS。

## C. Langfuse

- 区域：`https://jp.cloud.langfuse.com`。
- 凭据通过 Unified Settings 加载，从不打印、提交或写入产物。
- 官方 Python SDK：3.15.0，可选运行时依赖已安装于项目环境。
- 连接冒烟测试：CONNECTED；认证与 flush 通过。冒烟 trace：
  `b2f5e49bfbd4831c2c9d428fd00bbd08`。
- 权威 Research Run trace：`b335fc3bd1765aa5dcf9e6da50dd73ed`。
- 一个根 trace 包含 57 个标识引用，覆盖 Scheme／Planner 生成、规划、Run、Task、
  Agent、Skill、Tool、Evidence 批次、计算、自纠、重新规划、审查和发布。
- LLM 生成使用 SDK 原生 generation observation。映射请求／实际模型、供应商、
  测得延迟及供应商返回的 Token 数；缺少成本时省略，而非捏造。
- 排除提示词、模型输出、原始 FMP JSON、规范化值、环境变量和秘密。
  Evidence 观测仅包含元数据摘要。
- CanonicalExecutionRecord 仅保存本项目定义的追踪引用 ID。
- 此前一个非权威 Run 遇到日本区 exporter 读取超时但继续发布，
  证明故障不阻断业务行为。权威 Run 完成并 flush，未发生 exporter 错误。
- TRACE-001..012：PASS。

## D. Phase 2.1 工作线

| 工作线 | 结果 | 集成证据 |
|---|---|---|
| WS-M Evidence 所有权／事件 | PASS | 限定范围的生产者所有权；已接受 Evidence 事件精确一次 |
| WS-N Replan 依赖完整性 | PASS | 原子重连 Risk → Follow-up → Synthesis；图 v2 |
| WS-O Calculation 来源 | PASS | 可复现源码哈希；Evidence/Review/Canonical 谱系 |
| WS-P TeamoRouter Scheme 路由 | PASS | 真实结构化 Scheme 与 Planner 来源；无确定性回退 |
| WS-Q 同行／规范化 | PASS | 9 个候选和 9 项明确决策；员工单位 `COUNT` |
| WS-R PostgreSQL | PASS / MERGED | 真实 PostgreSQL 16 迁移、并发、恢复、SSE |
| WS-S Langfuse | PASS / MERGED | 日本区连接、原生 generation、故障不阻断业务、追踪引用 |
| WS-T0 FinRobot 激活 | PASS | 13 模块运行时激活矩阵；零项虚假 `ACTIVE_REUSE` 声明 |

## E. Evidence 所有权修复

公司、同行和研究新闻获取具有独立范围。Task 输出仅包含该 Task 产生的 Evidence，
消费者保留引用，每个已接受 Evidence 身份产生一个事件。权威 Run 包含 40 条公司
Evidence 和 9 条同行 Evidence。新闻及电话会记录返回 HTTP 402，未产生 Evidence。

下游研究新闻 Task 现在报告 `entitlement_blocked` 并附明确限制；
不能冒充已完成分析，也不能引用无关公司 Evidence。

## F. Replan 图修复

实际图将 Risk 到 Synthesis 的直接边替换为 Risk 到 Follow-up 和 Follow-up 到 Synthesis。
边增删事件以及版本从 1 到 2 的转换均持久化且可回放。
Synthesis 仅在运行时新增的必需跟进 Task 完成后才启动。

## G. Calculation 来源

营收增长率与 EBITDA 利润率记录均携带可复现 SHA-256 源码哈希、Python 运行时／源码引用、
已接受 Evidence 输入，以及 Review/Canonical ID。计算值仍是确定性财务代码输出；
没有 LLM 或 FinRobot 估值结果绕过 CalculationRecord 边界。

## H. Scheme 路由

- Scheme：TeamoRouter，请求 `gpt-5.6-sol`，实际 `gpt-5.6-luna`，结构化输出已验证，
  无确定性回退。
- Planner：TeamoRouter，请求／实际均为 `gpt-5.6-sol`，第二次语义校验尝试通过，
  无确定性回退。
- attempted-model 来源记录实际路由和重试尝试。

## I. 同行选择

FMP 返回九个同行候选。确定性策略创建九项对应选择决策，但选中数量为零，
因为缺少分类、业务相关性、市值比率、数据可用性和指标可比性所需的补充信息。
候选发现不会被报告为已选可比对象。

## J. 真实 NVDA PostgreSQL + Langfuse Run

| 记录 | 标识／结果 |
|---|---|
| Research Run | `RUN-452a94c8-e4a4-4445-816e-668ead86c8dd` — RELEASED |
| Langfuse Trace | `b335fc3bd1765aa5dcf9e6da50dd73ed` |
| Runtime Events | 120；序号连续且唯一 |
| 已接受 Evidence | 49 |
| 计划／实际 Task | 9 / 10；并行峰值 3 |
| 计算 1 | `CALC-RUN-452a94c8-e4a4-4445-816e-668ead86c8dd-GROWTH` |
| 计算 2 | `CALC-RUN-452a94c8-e4a4-4445-816e-668ead86c8dd-MARGIN` |
| 规范记录 | `CER-RUN-452a94c8-e4a4-4445-816e-668ead86c8dd` |
| 已发布结果 | `RESULT-RUN-452a94c8-e4a4-4445-816e-668ead86c8dd` |
| PostgreSQL 重启 | 完整聚合／规范／已发布／检查点／事件相等性 PASS |
| SSE 回放 | 首个已持久化事件从序号 1 回放 |

脱敏后的本地验收产物位于 `artifacts/infrastructure/acceptance/latest/`，
并刻意由 Git 忽略。

## K. 测试

- 全仓库：159 项通过；一项 Starlette/AnyIO 依赖弃用警告。
- Phase 1 + Phase 2 回归选择：35 项通过。
- PostgreSQL + Langfuse + 运行时可观测性 + FinRobot 选择：29 项通过。
- 真实 PostgreSQL 套件：9 项通过。
- FinRobot 适配器审计：9 项通过。
- Phase 2.1 真实语义评估器：P2.1-001..013 全部通过。
- Ruff lint：PASS。
- 自基础设施基线以来变更的全部 26 个 Python 文件均通过 `ruff format --check`。
- compileall：PASS。
- Git diff 空白检查：PASS。
- 已配置秘密精确值及凭据模式扫描：274 个跟踪／验收文件，零泄漏。

## L. 验收矩阵

| 门组 | 结果 |
|---|---|
| INFRA-001..007 | PASS |
| TRACE-001..012 | PASS |
| P2.1-001..013 | PASS |
| P2.1-014 Phase 1 回归 | PASS |
| P2.1-015 Phase 2 回归 | PASS |
| P2-019 真实 PostgreSQL | PASS；此前延后项已关闭 |
| 秘密／配置安全 | PASS |

## M. 回归

Foundation、Phase 1、Phase 2、Phase 2.1、数据库、可观测性和适配器套件一同通过。
项目级 Ruff lint 门干净。全仓库格式检查仍识别出本次差异之外的 40 个旧文件；
因其属于无关用户／项目历史，未机械重写。本次执行修改的每个 Python 文件均通过格式门。

## N. Git 提交

- `b82f017` — WS-S 真实 Langfuse 追踪。
- `b4775c3` — 合并 WS-S。
- `a0e0ac1` — WS-R 真实 PostgreSQL 持久化。
- `794885f` — 合并 WS-R。
- `221bedb`、`c0a6227`、`384d358` — 新闻语义修复和评估器强化。
- `9a37e99`、`1236408` — 追踪引用及运行时观测组装。
- `cb9121f`、`a9b1e9e` — 统一真实运行器，以及组合证据／超时修复。
- `d6b06a6` — FinRobot 激活矩阵及最终并行状态。

## O. 最终 HEAD

精确的最终仓库 HEAD 是添加本报告并关闭验收状态的提交；
它与 `git status` 干净状态一起记录在交接回复中。

## P. 剩余缺口

1. FMP News 和 Transcript 受权限阻断（HTTP 402）。运行时现将其保留为限制，不伪造内容。
2. 同行候选缺少补充信息，因此没有可比对象被选中。这是保守的 PASS，不是同行估值结果。
3. 跨适配器数据库写入在共享 engine 上使用独立事务；事务性 outbox／unit-of-work
   仍是后续韧性强化项。
4. TeamoRouter 响应未提供金额成本，因此省略 Langfuse 成本。
   返回／测得 Token 与延迟时，保留其来源。
5. FinRobot 的活跃运行时模块数为零。图表适配器已准备但缺少具体固定版本后端；
   技术指标、专业 HTML/PDF 和同行辅助模块需要完成
   `FINROBOT_RUNTIME_REUSE_STATUS.md` 中的移植。
6. 系统 Python 命令当前解析为 Python 3.14.3，而项目按要求运行在已验证的
   `.venv` Python 3.11.16 中。未采用 Python 3.14 项目基线。
7. 首次统一尝试（`RUN-4d342dc0-12cb-4d5d-aa43-c8fa0d83075d`）作为非权威审计样本保留：
   业务发布／故障不阻断业务成功，但强化语义验收拒绝了 Planner 回退及当时尚未修复的
   组合任务语义。

未开始前端、Generated Capability、RISC Zero 实现、POT 或比较工作。
