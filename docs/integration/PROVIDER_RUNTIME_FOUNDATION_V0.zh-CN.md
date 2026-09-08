# Provider Runtime Foundation v0 — MiMo 能力 PASS

[English](PROVIDER_RUNTIME_FOUNDATION_V0.md)

起始 HEAD：3fc3324c66ca995823f5020b9829d6f5ee9e27a8。本检查点增加显式可用性路由，不是 Phase 6 模型选择。不增加自动供应商故障切换、排名、质量路由、超时或 R2。

## 契约与组装

复用 LLMProvider.complete_structured、LLMMessage、LLMStructuredResponse、ProviderExecutionPolicyV1 及既有逻辑 / 尝试遥测。ProviderRoute 是冻结、不含秘密的描述：route/provider/model、端点授权引用、结构化输出模式及超时 / 韧性策略。不引入重复请求 / 结果框架。

路由：teamorouter-sol、teamorouter-luna、mimo-direct。显式选择项为 INCREMENTAL_PROVIDER_ROUTE；默认仍为 teamorouter-sol。应用组装调用 configured_incremental_provider；研究逻辑绝不依据适配器类分支。MiMo 选择仅影响增量 Scheme / 图规划。既有运行时专家和 TeamoRouter 的 60s 读取、90s 单次、180s 总计、双模型路由及一秒退避不变。不进行全局自动供应商切换。

每次逻辑调用 / 尝试经既有允许列表内部记录器记录 task_profile、route、provider、请求 / 尝试模型、ID、开始 / 结束、时长、失败及已观测用量。尝试次数和回退可从尝试记录导出；不编造失败调用 token 或费用。不新增 Evaluation 表。

## 本地授权与协议

原位读取外部 AtlasAnalyse production-runtime-v1 MiMo 授权。MIMO_API_KEY 和 MIMO_BASE_URL 非空；精确 MIMO_CHAT_MODEL 为 mimo-v2.5。未将文件复制到仓库。加载器只接受获批 HTTPS api.xiaomimimo.com/v1 授权，禁止 URL 凭据 / 查询 / 片段，对缺失授权或未建立模型能力安全拒绝。SecretStr 持有凭据；路由描述及遥测不含凭据值。生产记录器禁止值列表包含所选路由密钥。

此前 AtlasAnalyse 适配器源码（保留的 9 月 4 日构建）使用 OpenAI 兼容 chat completions、Bearer 认证、非流式 JSON 模式及本地输出验证。仅复用这些协议概念和授权，不复用其应用运行时。

MiMo 官方结构化输出指南为 mimo-v2.5 记录 json_object，而非原生 JSON-schema 强制验证。分类：JSON_MODE_WITH_STRICT_LOCAL_VALIDATION。适配器在 system 输入提供完整既有 schema，要求仅 JSON、禁用 thinking、完成 token 上限 8192，并用 json.loads 及未变 Pydantic 验证器解析完整 content。不剥离 Markdown、不提取片段、不丢字段、不虚构来源、不接受自由文本输出。解析后执行精确增量策略及来源验证。不宣称原生 schema 强制验证。

文档：https://mimo.mi.com/docs/en-US/quick-start/usage-guide/text-generation/structured-output

MiMo Direct 与 TeamoRouter 的区别在网关 / 基础 URL 及凭据授权。整体失败域独立性为 PARTIAL：避开已观测网关和凭据路由，但共享用户机器和网络出口。未审计配置授权之外的独立上游归属 / 账户内部情况。

## 一次实时能力操作

2026-09-07 09:21:42.199–09:22:11.483 UTC。一次逻辑调用、一次 HTTP 尝试、HTTP200。报告模型 mimo-v2.5；逻辑延迟 29.284s。观测用量：2783 输入 token、710 输出 token。无回退。诊断证据未持久化提示词、原始供应商响应或推理内容。

真实精确基线：OBJ-NVDA / RUN-57aed683-75d6-4b47-acc6-a73053ea492e / RVV-05bec42f-ab9b-55c5-b502-c439b8abe948。返回 Scheme 通过全部类型、策略、精确来源、公开投影及不可变草案哈希检查。实际决策：REUSE0、REFRESH1、REVALIDATE1、PREVENT1、UNKNOWN0。当前工作范围覆盖当前财务证据、增长 / 盈利能力、估值 / 风险和近期披露，并区分已验证 / 未验证。

能力运行器调用生产 backend.prepare_run，不启动应用 / 调度器，不调用 confirm。持久化真实草案事务。同一 prepare 键重放返回完全相同存储草案，不再调用模型。

## 精确下一任务交接

Draft：DRAFT-036cd4bd-fb8b-4c05-a9ba-25c654588342，version1。Scheme：SCHEME-b7a81dfc-7863-59e2-afd2-0371e796a1b6。Draft 哈希：sha256:543ea7eda59287104b3cb1c2c1ca2f19da256aaa60359a3b6fa39876ab7ebf21。Prepare 重放键：mimo-capability-exact-nvda-v1-20260907。既有冻结 30 分钟租约于 2026-09-07 09:51:42.157929 UTC 到期。

下一任务必须加载 / 审阅并确认这份持久化草案，不生成新 Scheme。confirm_run 从经哈希检查的存储快照重建 Scheme；调用图规划器，而非 Scheme 生成器。真实隔离 PostgreSQL 测试证明 prepare 重放和确认复用。图规划是下一 R2 任务中的独立新工作，不是重复 Scheme 调用。

若租约过期，在准入前停止：不绕过到期，不进行付费 prepare。已验证 Scheme 保留供显式本地草案续期 / 审阅步骤使用，Scheme 内容不变。未静默延长租约，不得确认过期草案。R2 许可仍受既有确认 / 到期门禁和下一任务授权约束。

下一生产进程须显式选择 INCREMENTAL_PROVIDER_ROUTE=mimo-direct。不要重跑两份已消耗验证脚本；两者有排他尝试标记。不要误跑旧浏览器 --start 流程，它会 prepare 新 Scheme；下一流程必须从保留草案开始。

## 验证与检查点

269 项专项 Python 测试通过，包括真实隔离 PostgreSQL prepare/confirm 重放、MiMo JSON 解析 / 失败 / 脱敏、精确基线、等价性、记忆和结果。187 项前端回归检查通过。类型检查 / 构建及针对性 lint 通过。全部 36 个真实 Run ID 和 R1/v1 指纹未变。没有 R2、任务、专家输出、review/proof/report/released result、Memory v2 或指针推进。

保留的先前脏诊断标注、等价性测试、受保护验证支持及历史阻塞回执有持久出处价值，一并连贯纳入。无无关改动。一个基础检查点，无 Phase5B 标签、不推送。证据：artifacts/mimo_provider_capability/{result,attempts,history-guard,validated-persisted-draft}.json。精确验证的公开草案也持久保存于 PostgreSQL，并非仅文件产物。

NEXT_EXACT_ACTION = PHASE_5B_EXECUTE_SINGLE_LIVE_R2_FINAL。在确认前 STOP。
