# Phase 5B R5 自适应执行验收 — 2026-09-08

[English](PHASE5B_R5_ADAPTIVE_ACCEPTANCE.md)

Phase 5 完成门禁：**PASS**。一次授权和一个新生产 Run；没有 R6、prepare、新 Draft 或 Scheme 重新生成。不推送。未实现 Phase 6 评估、POT、排名或学习式路由。

## 授权与精确血缘

从干净 `phase4` 的 `ec60923809dd37874d623c1e71822bc96c3ab426`、tree `825ec0daa37bff6a9c4eca69df4a08db0f2cf216` 开始；写入前验证生产迁移 `20260908_0012`。保留已接受 R4 启动器的 MiMo 增量图规划器覆盖；Specialist 初始路由策略不变。

| 身份 | 值 |
| --- | --- |
| Object | `OBJ-NVDA` |
| 授权 | `REAUTH-9e26582f-0671-40a1-a1cd-d5c43e56f2f0` |
| R5 | `RUN-ab806291-8cbf-4c9b-8852-b6a54f10768d` |
| 重执行前驱 R4 | `RUN-2bf2ef98-dc79-4b5f-aeb7-fb0ea151948a` |
| 知识基线 R1 | `RUN-57aed683-75d6-4b47-acc6-a73053ea492e` |
| 基线视图 v1 | `RVV-05bec42f-ab9b-55c5-b502-c439b8abe948` |
| 相同已确认 Scheme | `SCHEME-b7a81dfc-7863-59e2-afd2-0371e796a1b6` |
| 已发布结果 / 报告 | `RESULT-RUN-ab806291-8cbf-4c9b-8852-b6a54f10768d` |
| 规范执行记录 | `CER-RUN-ab806291-8cbf-4c9b-8852-b6a54f10768d` |
| 对象版本 v2 | `ROV-13d9d21a-661e-5df6-92cd-779ad1f944b0` |
| 研究视图 v2 | `RVV-0f7f4dfc-3dfa-538c-b59f-a8e22607007b` |

一次逻辑图规划器调用。schema、规范 Agent ID、任务配置兼容性、精确 Scheme 绑定、决策及基线血缘门禁在原子准入前通过。初始图有 9 个任务。既有研究语义重规划随后新增 risk-follow-up（10 个任务）；这不是恢复图调用或 Scheme 重新生成。既有纠正路径解决 PERIOD_MISMATCH。

## 观测到的真实恢复，不是人为演示

| 任务 | 初始尝试 | 受治理恢复 | 最终尝试 |
| --- | --- | --- | --- |
| Peer | MiMo: READ_TIMEOUT, 60.21s | SWITCH_PROVIDER 到已验证 Sol；Gate ALLOW | Sol PASS, 30.93s |
| Fundamental | Sol: READ_TIMEOUT, 60.41s | CAPABILITY_CHECK Luna ALLOW；检查 PASS 13.95s；SWITCH_MODEL Luna ALLOW | Luna PASS, 35.65s |
| Research/News | MiMo PASS, 7.60s | 无 | 原首次尝试 |

两次可恢复失败、三条决策、23 条持久账本记录。七个完成的 Specialist 任务共有九次执行尝试，另有一次独立 Luna 能力检查。七个成功 Agent 输出。保留原 Task 和 Run ID；下游研究、Review、Proof、Report 和 Release 继续。

Fundamental 初始路由为 `teamorouter-sol / gpt-5.6-sol`；最终为 `teamorouter-luna / gpt-5.6-luna`。这是模型切换，**不是**供应商切换。Fundamental × MiMo 保持 UNKNOWN；MiMo 能力检查 = 0。Main Agent 提议操作，确定性 Policy Gate 逐一授权。已接受预算不变，并针对持久化上下文独立复验。

## 发布、记忆、历史与产品

Review PASS（54 项检查）；强制 Proof VERIFIED；规范执行记录和已发布结果可用；终止 SUCCESS。仅发布后原子记忆回写创建 v2，来源精确为 R5。重复回写、浏览器刷新和重开保留相同 v2 ID。过期写入 / 发布 / 幂等保护通过专项回归。生产总数由 39 变为 40 个 Run，授权由 2 变为 3，无进一步 Run 准入。

真实应用内浏览器验收覆盖 Object 当前 v2、历史、R5 血缘、A/B/C、Base vs Current、两个精确 R1/R5 Results 链接、刷新及标签关闭 / 重开。C 显示实际失败分类、路由 / 模型、尝试、能力检查、决策、Gate 结果、延迟和记录 ID。请求契约修复后，刷新 / 重开没有服务错误。这是真实持久化产品数据。

可用性保持诚实：A 为 `REPORT_SOURCE_MAP_PARTIAL`；C 为 `REPORT_CONTRIBUTIONS_PARTIAL`。HTML、已发布报告及恢复证据可用；缺失来源 / 贡献映射和暂缓的 PDF 不被改标 READY。这些保留的展示限制不代表 Release 门禁失败。财务限制（包括估值输入不足及同业 / 新闻证据不可用）仍可见；未强化财务论断来通过验收。

R1 保持 RELEASED。R2 `RUN-e1b27d55-a58f-428d-b98b-0dc519577bc0`、R3 `RUN-bd02e630-69e9-468c-a3c8-6819e8facd30` 和 R4 保持 FAILED。历史 Run、Task、事件、object/view v1、Draft、Goal 和 Scheme 快照前后指纹匹配。R5 发布后自身未变。已审计公开界面未观测到跨 Run 回退、跨 Object 复用、不安全公开字段、隐藏 CoT 或配置秘密值。

## 产品理解 — PASS

1. **是：**Run 血缘和比较明确保留 R1/v1 作为知识基线。
2. **是：**Object 历史独立显示 R2/R3/R4 FAILED，不覆盖它们。
3. **是：**R5 标识相同已确认 S1，并单独链接前驱 R4。
4. **是：**C 在原始 R5 Task ID 下组织两组恢复序列。
5. **是：**可检查持久化尝试 / 决策 / Gate 结果；预算重放通过。
6. **是：**Main Agent 提议；Policy/Budget 授权，不能被覆盖。
7. **是：**Base vs Current 通过受治理身份打开精确 R1 和 R5 Results。
8. **是：**显式 v1/v2 历史及已发布来源指针累积研究，不把失败尝试提升为知识权威。

## 实时验收发现的窄范围源码修复

- 新增安全、精确 Run 恢复解码和只读 C 时间线；不渲染原始供应商输出 / 私有上下文，不对不可用数据回退。
- 在恢复端点协商既有产品契约头。
- 为既有前端记忆回写提供确定性 Object/source-Run 幂等键。不改变持久化语义或运行时恢复策略。

验收 API 封装禁用调度器启动，除精确已物化 R5 记忆重放外阻止全部写入。未重启历史 Run。

## 按风险比例验证

- 后端：**148 passed**，两个依赖弃用警告。范围：恢复策略 / 运行时、重执行准入、图身份、Specialist 路由、恢复持久化、API 协商、Memory PostgreSQL 和比较。
- 前端：**150 checks passed**：M3/M7-R1 20、M4 27、M5 37、M6 35、恢复投影 / 渲染 24、记忆请求幂等性 7。
- 专项测试 / 检查总数：**298**。TypeScript 类型检查和 Vite 构建 PASS。
- 只读精确 API/DB 验收、历史指纹、未变的已发布 R5 哈希、有界恢复重放和浏览器纵向切片 PASS。

本地证据保留在被忽略的 `artifacts/phase5b_r5_adaptive/`：dispatch、authorization、admission、graph、terminal、memory、performance、recovery、before/after history、acceptance audit 及 final receipt。不要重跑 `execute.py`。

下一精确操作：`USER_ALPHA_AND_PHASE_6_EVALUATION_PREP` — 此处未执行。
