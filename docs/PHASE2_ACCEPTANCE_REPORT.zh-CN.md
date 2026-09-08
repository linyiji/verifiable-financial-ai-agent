# Phase 2 后端验收报告

[English](PHASE2_ACCEPTANCE_REPORT.md)

日期：2026-09-04

基线：Python `>=3.11,<3.12`；Node.js `>=24,<25`

前端：`DEFERRED_PENDING_FINAL_UX_BASELINE`

## A. 环境

- Python：`3.11.16`
- Node.js：`v24.18.0`
- npm：`11.6.2`
- 后端：继续推进
- 前端：延后；未将任何框架或原型提升为最终／规范基线

## B. 秘密与配置安全

| 检查 | 结果 |
|---|---|
| `.env.local` 被忽略 | PASS |
| `.env.local` 受跟踪 | NO |
| `FMP_API_KEY` | SET |
| `TEAMOROUTER_API_KEY` | SET |
| Langfuse 凭据 | NOT SET |
| Git diff 中包含已配置秘密字节 | NO |
| Unified Settings 优先级（先 `.env`，后 `.env.local`） | PASS |
| Settings 表示形式不泄露秘密 | PASS |

密钥、预览、哈希、请求认证头和原始秘密值均不包含在源码、测试、日志、RuntimeEvent、
产物、本报告或 Git 中。

## C. 工作线结果

| WS | 结果 | 提交 | 模块门 |
|---|---|---|---|
| H FinRobot 精确审计 | PASS / MERGED | `44c8f18` | 9 项聚焦；分支完整 86 项 |
| I 真实 FMP | PASS / MERGED | `deb654f` | 16 项聚焦；分支完整 92 项 |
| J PostgreSQL | PASS / MERGED | `759ee30` | 4 项通过；1 项预期环境跳过 |
| K TeamoRouter | PASS / MERGED | `275220c` | 10 项聚焦；分支完整 87 项 |
| L Langfuse | PASS / MERGED | `73121fa` | 9 项聚焦；分支完整 84 项 |

每个模块均通过 Ruff、契约／职责检查、秘密扫描及其工作线报告门。

## D. 已测试的真实 FMP 端点

最终集成的 NVDA Run 对每个端点发出一次有界请求。

| 端点 | HTTP | 结果 | 已接受数量 |
|---|---:|---|---:|
| 公司概况 | 200 | PASS | 12 |
| 利润表 | 200 | PASS | 4 |
| 资产负债表 | 200 | PASS | 3 |
| 现金流量表 | 200 | PASS | 3 |
| 股票同行 | 200 | PASS | 9 |
| 报价 | 200 | PASS | 3 |
| 历史收盘价 | 200 | PASS | 10 |
| 分析师共识 | 200 | PASS | 5 |
| 股票新闻 | 402 | ENTITLEMENT_BLOCKED | 0 |
| 财报电话会记录 | 402 | ENTITLEMENT_BLOCKED | 0 |

供应商连接、套餐权限和代码状态分别报告。两次 402 响应不是代码故障，
也没有伪造替代数据。

## E. 真实 LLM 集成

- 供应商：`teamorouter`
- 请求的主模型：`gpt-5.6-sol`
- 配置的回退模型：`gpt-5.6-luna`
- Research Lead Planner 实际模型：`gpt-5.6-sol`
- Planner 结构化校验：PASS
- Planner 图：10 个计划任务，schema／依赖／无环／Skill／领域检查 PASS
- Scheme 请求模型：`gpt-5.6-sol`
- Scheme 结果：出现 `LLMProviderUnavailableError` 后采用确定性回退
- Scheme schema／领域校验：回退快照 PASS

Scheme 供应商结果刻意不表述为真实模型成功。
财务数字仍位于 Scheme 和 Planner schema 之外。

## F. 真实财务纵向切片

最终 Run：`RUN-5a4066f7-daaa-479f-8c5c-ff9720dba1f6`（`RELEASED`）

```text
Live FMP responses
  -> RawDataEnvelope / raw artifacts
  -> freshness / validation / normalization / conflict resolution
  -> 49 Accepted Evidence records
  -> native financial capabilities
  -> 2 CalculationRecords
  -> independent review PASS
  -> CanonicalExecutionRecord
  -> ReleasedResearchResult
```

| 能力 | 真实 Evidence ID | 计算 ID | 真实结果 |
|---|---|---|---:|
| 营收增长率 | `EVD-5befb05f-941d-591b-9e48-363cb02d20c9`, `EVD-d4635248-dcb8-5e25-8d1a-52bf6270b5f0` | `CALC-RUN-5a4066f7-daaa-479f-8c5c-ff9720dba1f6-GROWTH` | `0.6547353579009479145114447075` |
| EBITDA 利润率 | `EVD-2797cdc5-5115-5bb2-8020-651ba55552f5`, `EVD-d4635248-dcb8-5e25-8d1a-52bf6270b5f0` | `CALC-RUN-5a4066f7-daaa-479f-8c5c-ff9720dba1f6-MARGIN` | `0.6694143689392325574933545740` |

Fixture 比较：

| 能力 | Phase-1 fixture | Phase-2 真实值 | 差值（百分点） |
|---|---:|---:|---:|
| 营收增长率 | `0.6544061302681992337164750958` | `0.6547353579009479145114447075` | `+0.0329227633` |
| EBITDA 利润率 | `0.6600277906438165817508105604` | `0.6694143689392325574933545740` | `+0.9386578295` |

供应商派生比率和指标仍为 `provider_reference_*`；上述两项真实计算
均未使用 FMP 计算的比率作为权威结果。

## G. 测试

最终集成门：

- pytest：123 passed, 0 failed, 1 skipped
- 跳过项：真实 PostgreSQL 测试，缺少环境前置条件
- Ruff：PASS
- compileall：PASS
- 警告：FastAPI/Starlette TestClient 的 2 项依赖弃用警告

变更路径格式验证和最终秘密扫描也通过。未机械重写全仓库格式，
因为较早验收文件早于当前格式化器输出。

## H. Phase 1 回归

PASS。fixture 供应商仍是默认组装，完整 Phase-1 验收链仍能发布规范结果。
Phase-1 产物单独保留于 `artifacts/acceptance/latest`；
Phase-2 产物使用 `artifacts/phase2/acceptance/latest`。

## I. Phase 2 验收矩阵

| ID | 结果 | 证据 |
|---|---|---|
| P2-001 | PASS | `.env.local` 被忽略 |
| P2-002 | PASS | Unified Settings 报告 FMP 凭据 SET |
| P2-003 | PASS | Unified Settings 报告 TeamoRouter 凭据 SET |
| P2-004 | PASS | Git diff 中不存在已配置秘密字节 |
| P2-005 | PASS | 真实 FMP 连接 |
| P2-006 | PASS | NVDA Profile HTTP 200 |
| P2-007 | PASS | NVDA 利润表／资产负债表／现金流量表 HTTP 200 |
| P2-008 | PASS | 原始 FMP 响应经过 Evidence Pipeline |
| P2-009 | PASS | 49 条已接受 Evidence 记录 |
| P2-010 | PASS | 营收增长率由原生能力产生 |
| P2-011 | PASS | EBITDA 利润率由原生能力产生 |
| P2-012 | PASS | 供应商计算指标仍仅供参考 |
| P2-013 | PASS | 真实 Planner 响应证明 TeamoRouter 可连接 |
| P2-014 | DEFERRED_PROVIDER_UNAVAILABLE | 真实 Scheme 调用耗尽有界供应商路由；采用回退 |
| P2-015 | PASS | 生成的 Scheme 通过冻结 Pydantic／领域 schema 校验 |
| P2-016 | PASS | Research Lead Planner 使用真实 `gpt-5.6-sol` |
| P2-017 | PASS | 10 任务 Planned Graph 校验通过 |
| P2-018 | PASS | CalculationRecord 仅包含基于 Evidence ID 的原生能力输出 |
| P2-019 | DEFERRED_ENVIRONMENT_ABSENT | 本地 PostgreSQL 和 asyncpg 不可用；代码／离线迁移门 PASS |
| P2-020 | PASS | 完整 Phase-1 回归套件仍全部通过 |

没有将必需验收项虚报为 PASS。P2-014 和 P2-019 保留明确的外部环境分类。

## J. 已知缺口

- 有界供应商路由上的真实 Scheme 生成仍不可用；确定性回退正常，
  真实 Planner 响应证明 TeamoRouter 可连接。
- 新闻和电话会记录受已配置 FMP 套餐权限阻断。
- 真实 PostgreSQL 并发／SSE 验证需要一次性 PostgreSQL 服务，
  以及已经声明的 `postgres` 可选依赖。
- Langfuse 为 `NOT_CONFIGURED`；Noop／故障不阻断业务行为已启用且经过测试。
- FinRobot 渲染器复用已固定／审计，但其隔离的可选依赖后端尚未激活。
- 前端、Generated Capability Sandbox、完整 MCP 后端、RISC Zero、POT／评估
  和比较仍不在本阶段范围内。

## K. Git 提交与合并

- 配置／秘密安全门：`0a58386`
- WS-H 提交 `44c8f18`；合并 `15d1437`
- WS-K 提交 `275220c`；合并 `76254aa`
- WS-I 提交 `deb654f`；合并 `dfc3254`
- WS-L 提交 `73121fa`；合并 `f748669`
- WS-J 提交 `759ee30`；合并 `67bcd05`
- 集成／验收实现：`113a0a5`

## L. 建议下一步

不要开始前端。先在 TeamoRouter 可用时重跑真实 Scheme 调用，
并针对一次性服务运行条件式 PostgreSQL 套件。两项工作都可以在不改变冻结契约的情况下，
关闭两条延后验收项。

## 已保存验收证据

使用以下命令重新生成：

```text
PYTHONPATH=. .venv/bin/python scripts/run_phase2_acceptance.py
```

已忽略、仅保存在本地的产物：

- `artifacts/phase2/acceptance/latest/acceptance_summary.json`
- `artifacts/phase2/acceptance/latest/accepted_evidence.json`
- `artifacts/phase2/acceptance/latest/calculation_records.json`
- `artifacts/phase2/acceptance/latest/runtime_events.json`
- `artifacts/phase2/acceptance/latest/canonical_execution_record.json`
- `artifacts/phase2/acceptance/latest/released_research_result.json`
