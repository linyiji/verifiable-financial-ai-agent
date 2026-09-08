# Phase 4 Codex A — 主协调方交接

[English](PHASE4_CODEX_A_PARENT_HANDOFF.md)

状态：`A_WORK_COMPLETE_PARENT_INTEGRATION_REQUIRED`

本交接限于 Owner 授权子分支 `p4-backend-product`，它是请求的 `phase4/backend-product` 分支的扁平名称替代。
本交接不授权合并、迁移或更改 `phase4`/`main`。

## 冻结权威与来源身份

- 来源父提交：`4b6721b6db433aae300f94750e1a405b6b450501`
- 来源树：`35c47508ed65220c26620f5ec4bdd14cb798480d`
- 契约冻结标签：`p4-ig00-contract-freeze`
- 冻结 Phase 4 契约集 SHA-256：
  `0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741`
- Owner 批准的 V17 R2 规范 SHA-256：
  `fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19`
- 访问范围：`LOCAL_SINGLE_USER`

## A 内部职责映射

| 负责人 | 独占新文件 | 范围 |
|---|---|---|
| A 协调者 | `contracts.py`、`errors.py`、`api.py`、包导出及本交接 | 共享传输/错误/HTTP 边界与串行集成 |
| A1 | `hashing.py`、`admission.py` | 规范哈希、Prepare/Confirm、幂等与调度器准入值 |
| A2 | `reconstruction.py`、`durability.py` | 严格聚合重建与 PostgreSQL 事务协议 |
| A3 | `safety.py`、`projections.py`、`artifacts.py` | 安全投影、状态/进度映射、追踪/产物闭合 |
| A4 | `tests/phase4/backend_product/**` | 仅契约及负面验收测试 |

专家和协调者均未修改仅主协调方可写文件。
现有 Phase 3 财务、Generated Capability、Proof/RISC Zero、CER、Review、ReleasedResult、provider-router、Langfuse、事件、检查点、调度器与 SSE 实现保持不变。

## 已交付子任务实现

本分支新增文件：

- `src/phase4_product/`：11 个隔离模块（`__init__`、admission、API、artifacts、contracts、durability protocols、errors、hashing、projections、reconstruction、safety）。
- `tests/phase4/backend_product/`：19 个聚焦契约/负面测试模块。
- `docs/phase4/PHASE4_CODEX_A_PARENT_HANDOFF.md`：本交接及下述 15 项仅主协调方可实施的语义提案。

隔离实现提供：

- 精确 17 条 A 所有产品路由，不注册 C 所有事件路由；
- 严格封闭 DTO、版本/媒体协商、错误信封、ETag 和 Prepare/Confirm 响应语义；
- 不可变草稿、作用域幂等结果、精确重放、全有或全无 Confirm 写入集校验、原始初始事件清单、Run 准入及带栅栏的调度器转换值；
- 确定性、绑定筛选器的不透明 Run 集合游标，含精确排序与生命周期/事件一致性检查；
- 精确无回退快照重建与类型化不可用状态；
- 安全 Run、Task Graph、Released Result、Financial Review、Canonical Execution、TraceBundle、已发布对象及报告产物投影构建器；
- 产物身份/Run/发布/字节大小/媒体/哈希验证，失败时返回零受保护字节；
- 在公开投影/错误边界递归拒绝秘密、bearer、本地路径、提供方载荷及隐藏推理。

Financial Review 投影现要求保留完整 E/K/M/C/J 加 ProofPolicyDecision 输入集，从这些记录派生主体权威，并使用既有 Phase 3 算法重新计算 `input_snapshot_hash`。
不把该历史哈希重新定义为 RFC 8785 Phase 4 哈希。

## 已执行验证

- 恢复/最终化聚焦 A 所有套件：`368 passed`、`0 failed`。
- 全仓库回归：`833 passed`、`11 skipped`、`0 failed`。
- 完整回归是中断前最后确认的结果；恢复时未冗余重跑，因为恢复后的聚焦范围和全部静态门禁仍通过且未改变。
- 11 项跳过属于环境限制：三项要求配置真实 PostgreSQL URL 和 `asyncpg`；八项要求预构建 RISC Zero proof host。
- Ruff：全部 `src/phase4_product` 和 `tests/phase4/backend_product` 文件通过。
- Ruff 格式检查：相同文件通过。
- 编译检查：相同文件通过。
- 变更范围凭据扫描：未发现凭据材料。匹配项仅为安全过滤器与明确负面测试假值。
- 未启动任何权威 Phase 3 Research Run。

聚焦测试模块：

1. `test_admission.py`
2. `test_api_contract.py`
3. `test_api_negotiation_audit.py`
4. `test_artifact_integrity_audit.py`
5. `test_artifacts.py`
6. `test_confirm_commit_integrity.py`
7. `test_contract_strictness_audit.py`
8. `test_contracts_and_errors.py`
9. `test_financial_projection_builders.py`
10. `test_hashing.py`
11. `test_identity_contracts.py`
12. `test_projection_safety.py`
13. `test_projection_status.py`
14. `test_reconstruction.py`
15. `test_release_validation.py`
16. `test_run_collection.py`
17. `test_scheduler_durability.py`
18. `test_top_level_projection_builders.py`
19. `test_trace_builder.py`

## 持久性边界与已知阻塞

本分支包含仅 PostgreSQL 的仓储/工作单元协议、精确 MVCC 快照重建、原子写入集验证器与确定性栅栏转换。
有意不包含具体 PostgreSQL 适配器、模式迁移或生产应用组合。
因此不宣称重启持久性、精确一次持久化 Confirm/Run 准入，或生产产物恢复。

当前 Phase 3 快照在重启后也无法重建 AVAILABLE Review，因为缺少完整不可变 E/K/M/C/J 输入原像和类型化 Check 主体/纠正权威。
同样无法重新计算四个持久化 ReleaseValidation 哈希，因为未保留其不可变发布时证明、实质输出、产物与闭合原像。
对于 RELEASED Run，重建现以 `REVIEW_INPUT_PREIMAGE_NOT_PERSISTED` 或 `RELEASE_VALIDATION_PREIMAGE_NOT_PERSISTED` 失败关闭；
混合 BLOCKED/ALLOWED 历史也被拒绝，直至持久化能区分决定的历史原像。
摘要语法本身绝不视为发布权威。
提供全部显式输入时，隔离发布门确实会重算其版本化哈希；其 Canonical Execution 原像有意排除事件分页与游标传输状态。

因此 A2、真实重启/故障验收、应用级 A1 准入与整体 Codex A 验收仍被主协调方批准迁移及主协调方专有组合提案阻塞。
纯/隔离 A3 投影范围及聚焦负面测试通过。
不存在冻结契约冲突；唯一身份偏差是上述明确授权的扁平子分支恢复。

## 迁移审查门禁

`MIGRATION_REQUIRED = YES`

### 原因

迁移头 `20260904_0006` 持久化 Phase 3 聚合及支持记录，但对冻结契约明确分类为 `BACKEND_FIELD_REQUIRED` 的若干事实，没有规范化持久权威。
JSON 载荷、进程缓存、约定或仓储扫描无法跨 API/worker 重启强制所需唯一性、栅栏、基数、仅追加历史或原子投影发布。

### 必需模式差异

主协调方必须在 `20260904_0006` 后分配仅向前修订，至少审查以下规范化约束：

1. 草稿生命周期：版本、不可变请求/草稿哈希、过期，以及全有或全无的消费时间/准入/Run 身份。
2. 持久幂等结果：有效作用域、方法、规范化路由、键摘要与请求哈希；一个不可变响应/准入结果和唯一作用域键。
3. 调度器准入：每 Run 和幂等结果一行，冻结 `PENDING -> LEASED -> ACKNOWLEDGED|FAILED` 状态、尝试计数、租约代次/过期、唯一起始事件身份和不可变开始提交。
4. Run 投影发布：每 Run 的 `projection_revision` 和原子事件水位，每个影响投影的事务递增一次。
5. 终态效果/最终化器：重复交付和重启下，每 Run 一个持久终态结果及终态事件。
6. 复核决定：稳定 Check ID、类型化主体、精确 Check-to-Correction 关系、异常状态、Check 级解决时间和不可变有序 E/K/M/C/J 哈希原像。
7. Claim 锚点：不可变哈希绑定清单行、固定 HTML/PDF 表示锚点及显式 Claim-to-safe-RuntimeEvent 链接。
8. 产物生成：独立表示槽位、仅追加尝试行、持久安全失败原因、验证成功字节元数据及保留/撤销状态。
9. 发布验证：对符合条件发布恰好一次成功验证，绑定 O/R/Review/X/L、每个策略 ID/哈希及实质输出/产物闭合，包含足以重启重算的不可变版本化哈希原像。

### 契约要求

冻结 UAC-005、UAC-007、UAC-009、UAC-011、UAC-013、UAC-014、UAC-016、UAC-017 要求这些变更。
它们是诚实重启持久性、精确一次逻辑 Run 准入/开始、原子投影 ETag、追踪锚点、产物状态及已发布对象选择的前置条件。

### 考虑过的替代方案

- 复用当前 JSON 聚合：拒绝，因为无法强制关系唯一性、栅栏/基数及仅追加历史。
- 进程全局或继承的内存映射：拒绝，因为状态与幂等性重启后丢失，并在多个 worker 间分歧。
- 扫描既有行并选择 `first`/`latest`：精确身份与无回退规则拒绝。
- 仅 PostgreSQL advisory lock 而无持久行：拒绝，因为无法保留冻结结果、租约/栅栏或重启证据。
- 把新事实编码到无关载荷字段：拒绝，属于隐藏模式变更，且数据库权威不足。

本分支未创建或应用迁移。按要求继续了非迁移的传输、准入、重建、安全和测试工作。

## 主协调方语义补丁提案

### P4A-PROP-001

- 目标文件：`apps/api/main.py`
- 原因：根应用组合仅主协调方可写。
- 必需语义变更：构建生产 PostgreSQL Phase 4 后端，安装冻结产品错误处理器，通过 `app.state.phase4_product_backend` 提供；向 `request.state.request_id` 签发不透明服务端请求 ID；绝不使用 SQLite/内存产品事实。
- 必需导入/类型：`Phase4ProductBackend`、`install_phase4_error_handlers`、主协调方批准的 PostgreSQL 适配器。
- 预期行为：lifespan 初始化/关闭一个生产组合；全部产品响应使用冻结错误/版本边界，包括路由层 404/405 失败，且不改变无关 Phase 3 路由。
- 必需测试：启动/关闭、仅 PostgreSQL 预检、缺少后端 503 信封、通用异常 500 信封、带明确 UTF-8 JSON 媒体类型的产品路由 404/405 `phase4-error/v1` 信封、重启重建。
- 对 A 实现的依赖：`src.phase4_product.api` 与 A2 持久协议；被获批迁移阻塞。

### P4A-PROP-002

- 目标文件：`apps/api/routes.py`
- 原因：A 产品路由和 C SSE 在此主协调方专有注册表汇合。
- 必需语义变更：从 `create_phase4_product_router` 注册 17 条 A 所有路由；替换重叠旧处理器，而非暴露两个实现；保留精确事件路由的 C 职责。
- 必需导入/类型：`create_phase4_product_router`；C 的冻结 SSE 路由/处理器。
- 预期行为：冻结 18 路由清单唯一，不存在执行点击、`BackgroundTasks`、旧结果/复核/执行体或路由顺序遮蔽；
  未匹配或方法无效的产品请求进入主协调方作用域错误边界，而非 Starlette 默认响应体。
- 必需测试：精确方法/路径清单、无重复路由、201/200 Confirm 重放、A/C 版本头一致。
- 对 A 实现的依赖：`src.phase4_product.api`；`/events` 依赖 C。

### P4A-PROP-003

- 目标文件：`contracts/api/models.py`
- 原因：中央 DTO 注册表仅主协调方可写，当前 Confirm/请求模式与冻结冲突。
- 必需语义变更：重新导出或委派到封闭 Phase 4 DTO；从产品路由移除旧宽松响应权威。
- 必需导入/类型：`src.phase4_product.contracts` 中的请求、准入、投影、追踪、产物和错误 DTO。
- 预期行为：额外字段失败；Confirm 要求版本/哈希/Object 身份及 `confirm_scheme=true`；公开模型不暴露原始运行时字典。
- 必需测试：OpenAPI/JSON-schema 一致及额外字段拒绝。
- 对 A 实现的依赖：`src.phase4_product.contracts`。

### P4A-PROP-004

- 目标文件：`contracts/api/__init__.py`
- 原因：共享契约导出仅主协调方可写。
- 必需语义变更：仅暴露主协调方批准、A/B/C 集成所需的 Phase 4 DTO 导入范围。
- 必需导入/类型：从 `src.phase4_product.contracts` 批准的精确导出。
- 预期行为：每个公开契约只有一个规范 DTO 类。
- 必需测试：导入冒烟及重复类身份检查。
- 对 A 实现的依赖：P4A-PROP-003。

### P4A-PROP-005

- 目标文件：`src/application/errors.py`
- 原因：旧应用错误当前使用不同词汇和信封。
- 必需语义变更：在产品适配器映射 `RESOURCE_NOT_FOUND -> NOT_FOUND` 与 `RESULT_NOT_RELEASED -> NOT_RELEASED`；全部其他公开失败走精确策略和安全允许列表。
- 必需导入/类型：`ProductError`、`ErrorEnvelopeV1`、`ErrorCodeV1`。
- 预期行为：任意 500、堆栈/SQL/路径/提供方响应体或旧错误名称不得越过产品边界。
- 必需测试：全部 17 个代码/状态/重试/恢复元组及泄漏负面测试。
- 对 A 实现的依赖：`src.phase4_product.errors`。

### P4A-PROP-006

- 目标文件：`src/application/repository.py`
- 原因：共享仓储接口仅主协调方可写，当前生产行为继承进程本地身份映射。
- 必需语义变更：添加精确 ID、Run/Object 作用域仓储操作，以及持久幂等/草稿/准入/发布验证/锚点访问；禁止 latest/first/text 回退。
- 必需导入/类型：A2 快照与工作单元协议及冻结领域记录类型。
- 预期行为：每个嵌套读取闭合到一个 O/R 身份，分别报告缺失、外来和损坏事实。
- 必需测试：跨 Run/Object/Claim/产物负面测试及重启读取。
- 对 A 实现的依赖：A2 `reconstruction.py`/`durability.py` 与获批迁移。

### P4A-PROP-007

- 目标文件：`src/application/persistence.py`
- 原因：共享持久化仅主协调方可写，当前在独立事务中提交聚合、子项和事件。
- 必需语义变更：为 Confirm、投影可见变更、终态最终化和精确 MVCC 读取实现 A2 原子 PostgreSQL 工作单元；移除进程缓存的产品权威地位。
- 必需导入/类型：A1 准入记录、A2 事务协议、C 事件/检查点持久化。
- 预期行为：一个 Confirm 事务全有或全无发布；一个业务事务连同其事件水位仅推进一次修订。
- 必需测试：回滚/故障切点、重复交付、并发读者、API/worker 重启。
- 对 A 实现的依赖：A1/A2 和 C；被迁移批准阻塞。

### P4A-PROP-008

- 目标文件：`src/application/service.py`
- 原因：中央组合仅主协调方可写，当前 Confirm 通过进程本地路径启动工作。
- 必需语义变更：将冻结产品服务适配到精确仓储/构建器，Confirm 时提交一次持久调度器准入，移除产品对 `BackgroundTasks` 的使用。
- 必需导入/类型：A1 准入函数、A2 工作单元与重建、A3 投影/产物构建器。
- 预期行为：精确重放返回一个不可变准入；新键消费已消费草稿发生冲突；运行时仅从持久交付启动。
- 必需测试：Prepare/Confirm 矩阵、响应丢失后重试、重启，以及一次逻辑 Run/开始效果。
- 对 A 实现的依赖：所有 A 专家和主协调方批准的数据库实现。

### P4A-PROP-009

- 目标文件：`src/application/execution.py`
- 原因：A/C 编排边界仅主协调方可写。
- 必需语义变更：worker 启动/对账消费持久带栅栏调度器准入，并通过共享工作单元提交不可变 `started_at` 与一个 `run.started` 事件。
- 必需导入/类型：A1 `RunSchedulerAdmissionV1`、A2 栅栏辅助函数、C 运行时调度器/事件类型。
- 预期行为：租约过期重新交付相同 Run；旧栅栏不写入任何内容；已确认重新交付不再发出开始事件。
- 必需测试：租约过期、过期 worker、开始提交与确认前后崩溃。
- 对 A 实现的依赖：A1/A2、C 及迁移批准。

### P4A-PROP-010

- 目标文件：`src/infrastructure/database/models.py`
- 原因：规范化 SQLAlchemy 元数据仅主协调方可写。
- 必需语义变更：以外键、唯一/检查约束及不可变/仅追加关系建模已审查模式差异，而非无治理 JSON 载荷。
- 必需导入/类型：主协调方分配、匹配 A1/A2 记录契约的 Phase 4 行模型。
- 预期行为：PostgreSQL 拒绝重复 Run 效果、部分消费、无效租约、重复发布验证和锚点/尝试基数违规。
- 必需测试：元数据/模式约束检查及事务级负面插入。
- 对 A 实现的依赖：迁移提案 P4A-PROP-015。

### P4A-PROP-011

- 目标文件：`src/infrastructure/database/composition.py`
- 原因：根 PostgreSQL 适配器组合仅主协调方可写。
- 必需语义变更：在既有共享 engine/session factory 上组合已审查 Phase 4 仓储/工作单元，提供模式能力缺失即失败关闭的能力预检。
- 必需导入/类型：A2 能力报告/协议及主协调方批准 SQL 适配器。
- 预期行为：生产不能静默回退到 SQLite、内存或部分迁移数据库。
- 必需测试：后端/驱动检查、迁移头/能力预检、共享会话原子性与正常关闭。
- 对 A 实现的依赖：A2 和 P4A-PROP-010/015。

### P4A-PROP-012

- 目标文件：`src/infrastructure/database/artifacts.py`
- 原因：持久产物/Run 记录仓储仅主协调方可写。
- 必需语义变更：加载精确报告表示/尝试、锚点清单与发布验证行；内部定位符只保留在存储适配器；仅在完整 O/R/X/L/产物闭合后返回已验证字节。
- 必需导入/类型：A3 产物快照/验证器类型及已批准行模型。
- 预期行为：HTML/PDF 状态分离；每次失败零受保护字节；DTO/错误/日志/重定向不包含 `artifact_ref`。
- 必需测试：篡改、MIME/大小/哈希、保留/撤销、Range、跨 Run 替换及重启。
- 对 A 实现的依赖：`src.phase4_product.artifacts` 与已批准模式。

### P4A-PROP-013

- 目标文件：`src/output/projections.py`
- 原因：共享投影组合仅主协调方可写。
- 必需语义变更：在 A2 精确快照上，将产品状态/进度、已发布指标、Review、执行、追踪、产物及已发布对象组装委派给 A3 失败关闭构建器。
- 必需导入/类型：`src.phase4_product.projections`、`src.phase4_product.artifacts`、冻结 DTO。
- 预期行为：没有客户端/LLM 财务运算、回退关联、受保护字段，只有一致的修订/水位。
- 必需测试：全部完整映射、身份闭合、无损指标字段、安全投影及不完整快照负面测试。
- 对 A 实现的依赖：A2/A3。

### P4A-PROP-014

- 目标文件：`src/output/__init__.py`
- 原因：输出导出仅主协调方可写。
- 必需语义变更：串行 A/B/C 集成后暴露已审查产品投影适配器。
- 必需导入/类型：仅 P4A-PROP-013 中主协调方批准的导出。
- 预期行为：单一安全公开投影路径；Phase 3 输出语义仍可用且不变。
- 必需测试：导出/导入冒烟与旧版回归套件。
- 对 A 实现的依赖：P4A-PROP-013。

### P4A-PROP-015

- 目标文件：
  `alembic/versions/<PARENT_ALLOCATED>_phase4_product_durability.py`
- 原因：新修订 ID 和迁移链需要主协调方/Owner 明确分配。
- 必需语义变更：基于 `20260904_0006` 实现上述已审查仅向前模式差异，不重写任何此前修订。
- 必需导入/类型：P4A-PROP-010 映射的 SQLAlchemy/PostgreSQL 类型与约束。
- 预期行为：升级原子且可预检；不自动应用；降级遵循项目仅向前策略。
- 必需测试：从 `0006` 干净升级、模式契约、约束负面测试、重启/故障矩阵，以及此前修订字节未改变。
- 对 A 实现的依赖：Owner 批准及主协调方修订 ID 分配。

提案数：`15`。

## 跨子任务集成依赖（并非由 A 修改主协调方专有文件）

- C 必须将其事件计数器、事件追加、检查点、调度器和终态最终化器绑定到主协调方共享 PostgreSQL 工作单元。
- C 负责 `GET /api/research-runs/{run_id}/events`；成功流必须回显两个冻结契约头，游标/重放语义必须使用 A 暴露的相同持久水位。
- B 只能使用冻结产品 DTO；不得通过前端运算、回退身份、推断复核状态或合成追踪锚点弥补后端事实缺失。

## 集成就绪规则

只有在主协调方批准/分配迁移、将这些提案与 C 事件/运行时改动串行应用，并运行真实 PostgreSQL 重启/故障验收后，才能集成本分支。
本子任务不宣称 VS01。

## 恢复/最终化记录

- 在 `p4-backend-product` 原地恢复；未重置、丢弃或重建实现。
- 职责检查：恢复的变更集仅包含上述 31 个 A 所有文件；未修改任何已跟踪或主协调方专有文件。
- 聚焦测试、Ruff lint、Ruff format 和字节码编译在恢复文件系统上全部通过。
- 未写入 `main` 或 `phase4`；仍不宣称 VS01。
