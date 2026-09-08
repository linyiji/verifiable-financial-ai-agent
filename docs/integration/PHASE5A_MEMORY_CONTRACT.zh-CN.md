# Phase 5A 记忆契约（v1）

[English](PHASE5A_MEMORY_CONTRACT.md)

在只读持久化、血缘和 V17 审计后，由父任务冻结。

精确接受来源为 RUN-57aed683-75d6-4b47-acc6-a73053ea492e，权威归属 OBJ-NVDA。复用已运行的 Phase 4 released-result 和 A/B/C 验证器，不使用未启用的 release-validation-row 要求。绝不重写历史聚合、报告、输出或证明记录。

新增不可变 ResearchObjectVersion 和 ResearchViewVersion 记录，以及每个 Object 一条显式指针行。正整数版本标识仅追加资产；稳定版本 ID 从精确 Object/Run 身份导出。保留源 Run/result/report/canonical 身份。一个视图引用一个精确对象版本。紧凑记忆项引用权威 metric/claim 或已解决纠正，不复制完整聚合或私有执行载荷。

仅独立 VERIFIED 指标及其精确支持的论断进入已验证类别。已发布但未经证明验证，不等于 VERIFIED。缺失的 peer/path/reusable 类别为 NOT_OBSERVED，不为填充内容而生成。

物化采用显式 POST /api/objects/{object_id}/memory/materialize，封闭正文为 {source_run_id}；GET /api/objects/{object_id}/memory 读取持久指针。这扩展了既有 Object API 族。同一 Object/Run 在持久层唯一，并返回原始版本。首个精确来源绑定指针。已绑定时不同来源返回 CONFLICT，不进行写入。不存在跨 Run 排序授权：未来显式推进暂缓实现，不从日期、字符串、ticker 或数组推断。不执行新研究。

锁定精确 Object；验证来源；在一个事务中创建 ObjectVersion + ViewVersion + 指针。在 PostgreSQL 中强制版本仅追加；任何部分写入均回滚。使用数据库读取，而非应用对象 / Run 身份缓存。真实 Object API 读取中，新记忆指针取代按时间戳推导的最新摘要。纯冻结 Phase 4 摘要辅助函数不变。

保留 V17 Object 头部、概览 / 历史标签及 Start New Research。在概览下新增 Current Research View 和 Research Memory；来源链接指向精确 Results / 权威报告锚点。既有不兼容历史行仍可见。不增加增量 / 复用执行、比较、从记忆规划或原型事实。来源元数据及可用性须始终显式。

串行门禁：模型 / 测试 → 迁移 / 仓库 / 测试 → 来源服务 / 测试 → API / 测试 → 前端 / 构建 → 真实浏览器 / 重开 / 幂等性 → 回归 / 冻结。

## 已接受实现与操作

迁移：`20260907_0009`，位于 `20260905_0008` 之后，通过仓库 PostgreSQL 迁移辅助程序应用。迁移或 GET 不回填。显式 POST 精确来源选择；已绑定的不同来源返回安全 CONFLICT。同源重试返回原持久资产，包括 created_at 和 ID。不涉及供应商 / 模型调用。

Object memory GET 包含紧凑的 Released 历史引用。不兼容历史仍可见，但结果身份不可用。既有 Object 历史列表继续显示失败 / 取消及不兼容行。不依据该列表显示顺序作选择。

已接受切片保留一个经过证明验证的营收指标、其匹配论断及一个已解决的 period-mismatch 问题。v1 明确不保留 peer/path/reusable 上下文。来源仍可通过原始精确 Results 访问。

维护的专项测试：`test_memory_contracts.py`、`test_memory_source.py`、`test_memory_api.py`、`test_memory_postgresql.py`（TEST_POSTGRESQL_URL，隔离临时 schema），以及 `apps/web/scripts/research-memory.test.mjs`。真实留存验收：`node scripts/accept_research_memory.mjs`，使用 API 8010、web 4173 和独立 Chrome 调试 9227。须先显式物化已接受的 Run。此脚本重试物化，但绝不启动研究或创建供应商 Run。
