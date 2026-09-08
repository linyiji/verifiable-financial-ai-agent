# 受控用户 Alpha 就绪情况 — 2026-09-08

[English](USER_ALPHA_READINESS.md)

## 父任务契约冻结

**CONTROLLED_ALPHA_READY = YES**，仅限 3–5 位受邀设计伙伴，在主持协助的只读会话中使用既有 NVDA 证据。这表示可以开展用户研究，**不证明用户已经理解产品**。本准备任务未开展真人会话。首次真人理解仍未测量；30 秒就绪评估为 PARTIAL。

基线：分支 `phase4`，SHA `85962ecb9148c5a93bfd855ee6bffe554967db9b`，tree `a8f4bf4887104aa7b26c1580f8027eb6e948c71f`，标签 `phase5b-incremental-research-2026-09-08`。Phase 5 保持冻结。配套依据：[会话指南](USER_ALPHA_SESSION_GUIDE.zh-CN.md)、[Evaluation 契约](PHASE6_EVALUATION_DATA_CONTRACT_V1.zh-CN.md)、[R5 验收](PHASE5B_R5_ADAPTIVE_ACCEPTANCE.zh-CN.md)。

## 范围与运行门禁

目标 3–5 场会话，每场 20–30 分钟，邀请分析师 / 研究员、具备财务素养的非专业人士及产品 / 技术评审者。仅记录宽泛类别；不收集账户、持仓或个人财务数据。在现有本地产品上主持屏幕共享 / 运维者导航即可。不意味着提供公开 URL、不受限远程访问、引导注册、计费、租户或 Auth/RBAC 开发。这不是生产 SaaS 或企业安全就绪、完整出处覆盖或投资适当性认可。

每场会话前，主持人必须确认预期发布 / 记忆身份、调度器禁用、无活动研究及阻断写入的访问。使用既有受控验收环境，绝不能使用会恢复工作的普通生产启动器。此前 R5 保护仅允许已物化精确 R5 的幂等记忆重放；它**不是通用只读后端**。本只读旅程停留 Object/history/Results 界面，不进入已发布 Run 生命周期页面（会自动请求记忆物化）。不要允许自由点击 `新建研究`、`创建研究对象`、`开始新研究`、prepare、confirm、authorize 或 re-execute。这是真实写工作流，不是假演示按钮；执行需要另行授权任务。若无法提供受控环境 / 监督，会话被阻塞。

无需擦除或隐藏工程历史。直接从 `OBJ-NVDA` 开始，解释 R1–R5 是选定研究血缘，不是整个数据库。Object 有 40 个历史 Run；其他已发布 / 未物化及旧记录仍可见。另行标记的 QA Object 不是真实研究。

## 精确参考血缘

| 别名 | ID | 角色 / 状态 |
| --- | --- | --- |
| R1 | `RUN-57aed683-75d6-4b47-acc6-a73053ea492e` | RELEASED；保留知识基线 v1 |
| R2 | `RUN-e1b27d55-a58f-428d-b98b-0dc519577bc0` | FAILED；历史 Agent 身份缺陷 |
| R3 | `RUN-bd02e630-69e9-468c-a3c8-6819e8facd30` | FAILED；供应商传输 / 可用性 |
| R4 | `RUN-2bf2ef98-dc79-4b5f-aeb7-fb0ea151948a` | FAILED；Fundamental 传输 / 可用性 |
| R5 | `RUN-ab806291-8cbf-4c9b-8852-b6a54f10768d` | RELEASED；当前研究 v2 |

Object `OBJ-NVDA`；相同已确认意图 `SCHEME-b7a81dfc-7863-59e2-afd2-0371e796a1b6`。R5 的 `base_run_id` 是 R1；`reexecution_of_run_id` 是 R4。绝不能互换知识和执行血缘。基线视图 `RVV-05bec42f-ab9b-55c5-b502-c439b8abe948`；当前视图 `RVV-0f7f4dfc-3dfa-538c-b59f-a8e22607007b`，对象版本 `ROV-13d9d21a-661e-5df6-92cd-779ad1f944b0`。最新已发布指针为 R5。

## 严重程度与开放门禁

P0 = 数据 / 安全 / 跨身份或灾难性真实性失败。P1 = 范围内主要工作流不可用或误导。P2 = 明显摩擦；P3 = 文案 / 润色 / 低影响问题。开放要求 P0=0 和 P1=0；不追求 P2/P3 清零。新增 P0/P1 时暂停会话及受控 Alpha，等待分类 / 修复 / 重验。

运维者 / 源码 / 浏览器审计：在此窄范围内 **P0=0, P1=0, P2=5, P3=2**。这是七项去重就绪发现，不是参与者报告的缺陷。

| ID | 严重程度 | 观测摩擦 / 保留限制 | 处理 |
| --- | --- | --- | --- |
| A-01 | P2 | 首屏密集，Object/Run/Memory/View 英文术语互相干扰 | 先无帮助观察；回答后才提供术语解释 |
| A-02 | P2 | `上次研究` 容易被理解成最近失败尝试，而非已发布基线 R1 | 必要时才澄清；验证复述理解 |
| A-03 | P2 | 恢复时间线含 UUID、代码及独立开始 / 完成行 | 请其讲述自然语言故事，不考 ID 记忆 |
| A-04 | P2 | 40 个 Run 的历史、旧禁用项及其他非记忆发布遮蔽选定血缘 | 从当前 v2 开始；使用精确比较链接；不隐藏历史 |
| A-05 | P2 | A `REPORT_SOURCE_MAP_PARTIAL`、C `REPORT_CONTRIBUTIONS_PARTIAL` 限制可追溯性 | 保持 PARTIAL 可见；询问缺失映射是否降低信任 |
| A-06 | P3 | PDF 暂缓；当前练习依赖 HTML | 不承诺导出；不在会话范围 |
| A-07 | P3 | 缺失行业元数据及已标记测试 Object 增加视觉噪声 | 从 NVDA 开始；不编造元数据 |

这些发现不足以要求修复产品源码。主要读取动作到达精确目标；不可用旧动作已禁用，不是假可用链接。此处不执行或重新认证新 Run 操作实现。

## 产品问题与证据级别

冻结问题 A1–A8 及观察量表位于会话指南。以下运维者就绪判断不替代实际用户回答。

| 门禁 | 就绪情况 | 依据 |
| --- | --- | --- |
| 30_SECOND_PRODUCT_COMPREHENSION | PARTIAL | 混合术语密集；尚无参与者计时测试 |
| RESEARCH_OBJECT_COMPREHENSION | PASS | 公司身份和持久当前视图入口存在 |
| RESEARCH_MEMORY_COMPREHENSION | PASS | 已验证材料、精确出处和缺失类别可见 |
| INCREMENTAL_RESEARCH_COMPREHENSION | PASS | 解释 refresh/revalidate/prevent 及独立当前证据 |
| FAILED_EXECUTION_HISTORY_COMPREHENSION | PASS | R2/R3/R4 明确失败，与已发布 R1/v1 分开 |
| RECOVERY_COMPREHENSION | PARTIAL | 同 Run 时间线正确，但展示偏工程化 |
| A_B_C_COMPREHENSION | PASS | 报告 / 复核 / 执行角色独立，可用性诚实 |
| BASE_VS_CURRENT_COMPREHENSION | PASS | v1/v2 比较解释不变值仍独立验证 |
| PRIMARY_ACTION_INTEGRITY | PASS | 范围内 Object/history/精确 Results 导航有效 |

真实浏览器就绪 = PASS，仅适用于引导只读旅程，并保留上述理解限制。会话开展前，**每项**门禁的实际真人理解均为 NOT_OBSERVED；不要把运维者 PASS 转换成用户成功率。

## 审计与下一步

准备采用并行只读诊断、父任务负责的文档冻结，然后独立验证证据 / 术语并进行真实浏览器导航。无需功能开发或新提取器。既有精确 Run API、类型化恢复账本和安全保留遥测覆盖 Evaluation 准备。生产快照使用只读 repeatable-read SQL、行数和哈希，不导出原始载荷。前后身份 / 记忆 / 历史检查保留在本地准备回执中。不授权供应商 / 模型调用或新 Run。

下一精确操作：`CONTROLLED_USER_ALPHA`。Owner 可另行并行选择 `PHASE_6A_EVALUATION_PLANE`；两者均不在本任务启动。
