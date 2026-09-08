# Phase 5B — 精确草案租约续期与审阅

[English](PHASE5B_EXACT_DRAFT_RENEWAL_REVIEW.md)

起始：`2da5d15760f3d91e3defd1d281eea5799e2399b0`（phase4，干净）。

## 契约审计与窄范围修复

既有续期能力：NO。`expires_at` 属于不可变公开 Draft 载荷及其规范哈希。此前没有独立草案授权记录。更新 expires_at 会破坏 Owner 要求的哈希。提供的 `sha256:543ea7...` 是完整 Draft 哈希，不是独立 Scheme 专属哈希。

修复新增独立仅追加授权表，不替换 Draft/Scheme。每项授权绑定精确 Draft 哈希、Scheme ID、Base Run、Base View 和前驱到期时间，记录授权时间及有界新到期时间。PostgreSQL 拒绝更新 / 删除审计行。续期锁定与确认共用的 Draft 行，拒绝已消耗、损坏、身份不匹配、错误前驱及尚未到期的租约。相同幂等重放返回同一授权，不延长时间。

不可变 Draft 载荷、原始到期时间、版本、prepare 重放及哈希均不变。确认现在验证从持久存储加载的生效授权到期时间，包括精确绑定检查，同时保留既有哈希 / 版本 / 身份 / 消耗门禁。无续期时，原到期语义不变。30 分钟租约策略不变。

迁移：`20260907_0010`，隔离 PostgreSQL 测试通过后应用。迁移未重写既有行。

## 实际授权

- Draft：`DRAFT-036cd4bd-fb8b-4c05-a9ba-25c654588342`，版本 1
- Scheme：`SCHEME-b7a81dfc-7863-59e2-afd2-0371e796a1b6`
- Draft 哈希：`sha256:543ea7eda59287104b3cb1c2c1ca2f19da256aaa60359a3b6fa39876ab7ebf21`
- 授权：`LEASE-0e2bb5a10755b04f754bb905e1b5a8a004676c6fcbd1735ce1e92492f15a9bcf`
- 原到期时间：`2026-09-07T09:51:42.157929Z`
- 授权时间：`2026-09-07T10:09:17.555353Z`
- 新的生效到期时间：`2026-09-07T10:39:17.555353Z`（上海时间 18:39:17）
- 续期重放键：`owner-exact-draft-lease-renewal-20260907-1`

续期前后，完整数据库 Draft 的规范内容与原始能力产物逐字节相同。决策保持 REUSE0 / REFRESH1 / REVALIDATE1 / PREVENT1 / UNKNOWN0，理由及来源身份不变。基线仍为 OBJ-NVDA / RUN-57aed683-75d6-4b47-acc6-a73053ea492e / RVV-05bec42f-ab9b-55c5-b502-c439b8abe948。未修改 Goal 或 Scheme。

## 真实产品审阅

`/drafts/{exact-draft-id}` 通过 `GET /api/research-drafts/{draft_id}` 读取持久化 Draft 及独立授权。显示精确存储的目标、范围、要求、决策、历史来源和技术身份，并明确说明续期而非重新生成。此只读审阅页不包含确认按钮或模型调用。到期显示使用生效授权，而非不可变历史 `draft.expires_at`。

可见的应用内浏览器及专用 Chrome 审阅了实际 PostgreSQL 响应。刷新及关闭 / 重开保留相同 Draft 内容和生效到期时间。浏览器请求进行零次写入。精确历史 R1/View 及 0/1/1/1/0 计数可见。审阅服务器中间件拒绝所有写入；不含模型适配器，绝不启动运行时 worker。

证据：`artifacts/phase5b_exact_draft_renewal/browser-review.json` 和 `exact-draft-review.png`。租约审计本身是持久 PostgreSQL 证据，而非仅产物文件。此前 MiMo 能力产物经哈希检查未变。全部 36 个 Run ID 和 R1/v1 历史指纹保持不变。

## 验证与下一任务边界

174 项专项 Python 测试和 58 项前端检查通过；类型检查 / 构建及 lint 通过。测试包括真实 PostgreSQL 续期 / 重放 / 审计不可变性、实际确认仓库、原始 / 续期到期拒绝、哈希 / 基线 / 消耗拒绝、产品 API 读取，以及无模型 / 图 / 准入依赖。

MODEL_CALLS = 0；SCHEME_GENERATION_CALLS = 0；GRAPH_PLANNER_CALLS = 0；R2_CREATED = NO。续期未创建任务、执行事件、Agent 输出、Review、Proof、Report、Release 或 Memory v2。最新仍为精确 R1 / View v1。未创建 Phase 5B 标签或推送。

下一步：PHASE_5B_CONFIRM_RENEWED_DRAFT_AND_EXECUTE_R2。通过精确审阅端点或持久 Draft 记录读取生效租约；不要仅依据不可变 Draft 的旧到期时间判断。在图规划前立即复查。过期即停止。不 prepare 或重新生成 Scheme。Owner 最多允许一次图模型调用；下一任务必须落实此预算，并在图失败时安全拒绝（通用规划器的验证重试 / 确定性回退不构成超出 Owner 更窄门禁的授权）。本任务没有图工作。
