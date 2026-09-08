# Phase 6A Results 语义闭合 — 离线验收

[English](RESULTS_SEMANTIC_CLOSURE_ACCEPTANCE.md) · [契约](../architecture/RESULTS_WORKSPACE_CONTRACT.zh-CN.md)

日期：2026-09-09。W2 PASS；W3 历史只读投影 PASS；离线回归 PASS。
本回执不代表付费 NVDA、投资者发布、全新下载或 Phase 6B 验收完成。

## 实际验收结果

- 历史 Run：`RUN-75daae15-9f35-4233-83ff-6d24f2e151ba`，对象 `OBJ-NVDA`。
- 10 项已复核结论、62 项原始 PASS 检查、八类共 1,229 条精确执行记录。
- 保留原 FAILED 历史及 Owner 授权从 Release 恢复的过程，新增模型、计算和 Proof
  均为 0；最终状态 RELEASED，同时明确研究限制。
- A→B→C 与 C→A 精确引用跳转通过；不存在的引用明确拒绝，不回退到其他记录。
- 8 项纯内存反例均被拒绝：修改结论、重复计算/事件、错误 Task 事件、修改
  Review/Evidence/Scheme，以及非零恢复调用计数。
- PostgreSQL 强制只读，前后聚合、事件、恢复与 Memory 快照哈希一致；保留 Proof
  清单及原 HTML 文件哈希未变。六个历史 GET 投影及原 HTML 下载均返回 200。
- 新 HTML/PDF 渲染使用相同的 10 项类型化结论，不把未经复核的 Agent 叙述作为财务结论。
- 完成并目视检查 10 张真实 1440×900 截图，无内容注入、Provider 调用、新 Run 或历史文件改写。

## 离线回归

后端执行：`TEST_POSTGRESQL_URL=<隔离测试数据库> .venv/bin/pytest tests/unit tests/integration tests/phase4/backend_product tests/installer tests/evaluator tests/test_phase3_acceptance_runner.py -q --disable-warnings`

结果：**1,399 passed**，1 条 warning。前端 M3/M4/M5/M6 共 119 项通过；
新增 `node --experimental-strip-types scripts/results-semantic.test.mjs` 14 项通过。
TypeScript/Vite、Docker 安装器镜像构建、Ruff、`git diff --check` 通过。
新增本回执前，全库 Markdown 本地目标扫描 464 个，失效 0 个；随后另行检查新增回执
及中英文互链。仓库可发布文件和构建后前端的本地真实凭证精确值扫描无泄漏。

## 剩余外部门禁

Web Search = CONFIGURED + LIVE_PROVEN，追加 Web 调用 0。
AI Search = CONFIGURED + LIVE_HEALTH_UNPROVEN/403；原响应正文未保留，根因 NOT_PROVEN。
Owner 外部确认并修正权限、余额、配置后，允许恰好一次 AI-only smoke，目前追加调用 0。
不得无证据归因为无效 Key，也不得宣称 AI Search 健康。

下一精确动作：`BOCHA_AI_ACCESS_FIX`。本轮付费 NVDA Run 为 0。GitHub 发布、加密注册表
交付和全新下载后的实测尚未执行。
