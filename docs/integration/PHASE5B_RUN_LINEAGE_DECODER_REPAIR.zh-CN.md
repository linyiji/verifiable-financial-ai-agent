# Phase 5B Run 血缘解码器修复

[English](PHASE5B_RUN_LINEAGE_DECODER_REPAIR.md)

起始：`phase4`、`a0ae8aadf6da1881fc27a90f7a4c7cf94dc549d9`，tree `e2376d9dc79e9d0cfb43a6731ec324a3f2fb8874`；编辑前干净。

## 契约审计

根因：`RUN_PROJECTION_FRONTEND_STRICT_DECODER_DRIFT`；首个被拒字段 `$.run.base_run_id`。精确接受的后端增量为 `base_run_id`、`base_research_view_version`、`reexecution_of_run_id`。`project_run_detail` 输出这些可选字段；原子投影嵌入该详情。集合 / 历史项有独立显式结构，不继承这些字段。Results 使用原子 Run 结构。未改变后端生产语义或迁移。

共享详情和嵌入式解码器现在均显式接纳这些字段，保留缺失 / null 及既有不透明 ID 验证。知识基线身份必须成对；拒绝自引用血缘及与知识基线相同的前驱。未知字段仍安全拒绝。既有重执行组件使用共享解码器，显示 Scheme、基线、视图及独立执行前驱，不修改其两阶段授权 / 准入工作流。

## 验收

- 前端：17 项血缘测试、6 项既有重执行交互测试、119 项 M3/M4/M5/M6 回归检查：**142 passed**。
- 后端：reexecution、reexecution API、graph/runtime bindings、single-call graph、memory API 和 provider foundation 套件：**61 passed**。
- 专项检查总计：**203 passed**。类型检查和生产构建通过。
- 首次后端测试启动缺少 `TEST_POSTGRESQL_URL`；用已配置连接及一次性隔离 schema 重跑后通过。未向公共生产表写入测试夹具。
- 真实 Chrome 验收使用产品前端及临时生产数据库支持的只读 GET API，不含调度器或供应商。初始临时服务器配置缺少持久化应用仓库；修正测试框架后可读取历史 Memory 结果。
- 精确失败 R2 详情和原子投影解码通过；状态 FAILED，Scheme `SCHEME-b7a81dfc-7863-59e2-afd2-0371e796a1b6`，基线 `RUN-57aed683-75d6-4b47-acc6-a73053ea492e`，视图 `RVV-05bec42f-ab9b-55c5-b502-c439b8abe948`，前驱缺失。
- 已检查截图：失败历史、精确血缘及已启用的“重新执行”可见。未点击授权或准入操作。
- 旧 R1 详情 / 投影在无血缘字段时解码通过。后端 RELEASED 对应既有前端规范状态 COMPLETED。Memory 确认 R1 RELEASED、当前 View v1 和最新版本 1。
- 未来重执行仅通过本地夹具测试。
- 浏览器记录零个写请求。迁移仍为已应用的 20260907_0011；授权仍为 0；Run 仍为 37。全部 22 张历史表指纹、失败 R2、已消耗 Draft、Scheme 和 R1/v1 不变。Memory v2 缺失。供应商 / 模型调用及新生产 Run：0。

本地忽略证据：`artifacts/phase5b_lineage_decoder/browser.json`、`failed-r2.png`、只读 GET 测试框架及浏览器脚本；前后快照在 `artifacts/phase5b_reexecution_authorization/`。

下一步：`PHASE_5B_FAILED_R2_REEXECUTION_AUTHORIZATION_RESUME`。本修复不授权或执行该下一任务。
