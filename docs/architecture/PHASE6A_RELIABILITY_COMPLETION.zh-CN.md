# Phase 6A 可靠性与完成性

[English](PHASE6A_RELIABILITY_COMPLETION.md)

## Live 后续：Proof 执行归属重复

后续唯一一次 live 验收在真实 VERIFIED Proof 和 PASS Review 之后失败。
`execute_run` 先为部分研究执行证明，随后 `_assure_and_release` 再次执行同一证明。
第二次正确拒绝已存在的输入路径，但返回的空结果覆盖了聚合里的第一次成功证明，
导致释放阻塞，公开投影也隐藏了仍然持久化存在的 Proof。之前离线故障重放直接进入
`_assure_and_release`，遗漏了这一完整组合路径。

单独获得修复授权后，闭环改为接收调用方已产生的精确 Proof 结果，仍执行原有策略与
血缘校验。完整 `execute_run` 回归断言证明工作流仅调用一次。只读投影同时读取精确
持久化 Proof，不更新历史；跨 Run 或相互冲突的记录仍被拒绝。未释放 Run 的完整
Review 页面独立读取已保留 Review，不再依赖已释放的 Results Workspace。

原始失败仍是历史事实。单独获得 Owner 明确授权后，`recover_closure` 增加一次
仅闭环恢复：不可变失败快照与事件摘要 → 已保留 Review/VERIFIED Proof 门禁
→ Release/Report → Memory。迁移 `20260909_0015` 让审计记录仅可追加，每个 Run
只允许一条 STARTED 记录；已消耗或中断的恢复尝试均不自动重试。
不调用调度器、模型、计算或证明生成。原事件不变，`closure.recovery_started`
绑定原失败终态事件，开启唯一恢复段；普通终态后的事件写入仍被禁止。
释放结果与新的聚合/事件水位原子提交；Memory 完成单独记录，不能隐藏写回失败。

恢复后通过不代表原冻结版本通过了 live 门禁，也不意味着 GitHub 发布或 Phase 6B
获得授权。

## 历史基础修复的门禁与范围（live 后续之前）

Completion → Trust → Performance。本次是经过离线测试的 Phase 6A 基础修复，
不是 Phase 6B 实现，也不代表新一轮 live 验收通过。本轮没有付费 Provider 调用、
生产 Run、历史重试、发布或历史数据库迁移。进入 Phase 6B 前仍需明确授权一次
全新的独立 NVDA Run；之前的一次授权已经消耗。

起点为 `phase4` 分支的 `e5fed7dd3cc5512d4b5aa78827149116ac04b57b`。
历史 FAILED Run 仍然 FAILED。下述重放产生的释放状态仅存在于隔离测试 schema，
测试后这些 schema 已移除。

## 已证实根因及修复契约

最新故障已完成 PASS Review 和 VERIFIED Proof，随后
`ResearchApplicationService._assure_and_release` 对所有非空 `partial_research`
抛出 `INCOMPLETE_RESEARCH_NOT_RELEASED`。外层将其统一报告为
`POST_SCHEDULER_FAILED`，隐藏了这个策略门禁。执行没有到达报告和写回阶段，
不能据此判断证明失败或 Run 没有启动。

现在闭环依据精确输出依赖与必需计算判定。只有已知定性任务的叙述输出被明确冻结为
supporting 时，其失败才允许继续；未知任务、必需输出缺失、完整性错误及正确性失败
仍阻止释放。可选缺失不会被包装为 Agent 成功或虚构数值。
策略阻塞保留类型化原因诊断，未知闭环异常仍然致命。

仅成功输出进入规范贡献集合，完整执行历史则保留 FAILED 输出及唯一对应的真实
TASK_FAILED 事件。原生 Revenue Growth 通过精确 Calculation、Evidence、
calculation.completed 事件、Review 和 Proof 贡献报告，不伪造模型、token 或
AgentOutput。报告与 Research Memory 同样保留这一语义区分。

## 候选资格

模型注册、配置、授权、能力证据和有界恢复仍是不同概念。候选集合在执行前冻结，
Provider 响应不能授予自己权限。Fundamental、Valuation、Risk 可使用已配置的
Sol、Luna、Terra、MiMo 路由，但仍需通过现有资格检查。Risk 现纳入授权的
Luna → Terra 替换。Peer/News 候选为 MiMo、Sol、Luna；Synthesis 为
Sol、Luna、MiMo。生成式 FCF 仍仅允许 Sol/Luna/Terra。
MiMo 使用独立授权和 `mimo-v2.5`，不是 TeamoRouter 的别名。
延迟和 token 数量不授予资格，也不能覆盖正确性要求。

## 数据能力策略

| 能力 | 注册候选 | 当前执行范围 |
| --- | --- | --- |
| 财务报表 / 行情历史 | FMP | SELECT_ONE，结构化输入 |
| 公司新闻 | FMP、Bocha | FALLBACK；采集器可显式启用 FUSE |
| 财报电话会文字稿 | FMP、Bocha | FMP 文字稿；Bocha 仅发现原文 |
| 官方文档搜索 / 网络研究 | Bocha | 已注册；尚非独立默认任务 |
| 管理层指引 / 公司事件 | FMP、Bocha | 已注册；不宣称专门提取或已认证指引 |

来源结果使用 AVAILABLE、PARTIAL、UNAVAILABLE_ENTITLEMENT、
UNAVAILABLE_PROVIDER、INSUFFICIENT_DATA、FAILED。FMP 新闻/文字稿 402
不会禁用成功的结构化财务来源。首选/实际 Provider、来源状态和回退原因落在所属
Task，能够经过持久化与公开解码。

Bocha 是可选 BYOK 配置 `BOCHA_API_KEY`，凭证不内置、不进入公开 DTO。
Evaluator Gateway 尚未增加 Bocha 代理。缺少密钥表示来源不可用，不代表研究全局失败。
仅明确配置的官方发布者具备资格，本阶段已配置 NVDA。每次最多一次搜索和五次
有界原文读取，不自动重试、不跟随重定向、不向原文站点转发搜索凭证。

搜索摘要和 AI 答案不是 Evidence。接纳原文保留发布者、URL、日期、内容摘要值及
HTML，提取文本排除脚本和样式。未知发布日期、过期/未来内容和不可信主机被拒绝。
Evidence 身份绑定原始快照和精确 Run。文字稿发现为 PARTIAL，明确未验证财务期间，
也不代表完整文字稿；不得将其替代结构化金融计算输入。

FUSE 显式启用：发现结果按原文 URL 去重，进行权威性和新鲜度过滤，再按权威性、
时间降序排列；FMP 标准化新闻保持独立归属。不宣称跨 Provider 文章语义去重，
离线契约验证的是 Evidence 身份不重复。未加入学习排序、Provider 基准测试或
性能驱动的路由选择。

适配器依据 [Bocha 官方接入示例](https://github.com/bocha-ai/dsh-web-search-bocha/blob/main/README.md)。

## 正确性、充分性与 Review

沿用 `OutputRequirements`/`evidence_sufficiency` 的 HARD_REQUIRED、ANY_OF、
SUPPORTING、ENRICHMENT 语义。财务期间错误必须修正，不能归为数据不足。
程序搜索所有已接纳且期间对齐的候选；没有合法替代时保留失败/待修正状态。
只有修正计算成功后才记录 RESOLVED。技术指标历史不足不产生数值、Claim 或假修正，
也不阻止独立分支。Scheme 明确要求的能力缺失仍然阻止释放。

Review 与 Release 独立绑定 `financial-requirements/v1` 中的精确 Scheme 指纹
和分支结果。公式集合、数量检查按必需项及明确记载的 supporting 缺失判定。
Judgment 要求随有效公式产生：有效 RSI Judgment 不应仅因 MACD 不可用而失败。
每个实际 Judgment 仍必须关联同一 Run 的精确 Calculation/Evidence。
历史 Review 哈希保持不变，旧 Evidence 序列化时不新增空的 document authority 字段。
只读 GET 不重跑 Review、不改写历史。

Review/Proof 的存在独立于释放可用性。失败 Run 可以显示真实保留的 PASS/BLOCK
Review 与 VERIFIED Proof，但不会因此获得报告或 released result。
公开身份检查仍然遇到不一致即拒绝。

## 离线验收与剩余 live 门禁

最终回归 **1310 passed**，无 deselection；前端 **119/119**。
类型检查与 Web 构建通过，现有大包体积警告不等于释放失败。
Installer Docker 镜像已构建，双语和凭证扫描随本地冻结回执交付。
Mock 成功不代表 Provider 健康或 live 调用已成功。

| 必需场景 | 验证依据 |
| --- | --- |
| 1 FMP 混合状态；2 Bocha 回退；3 FUSE | `test_phase6a_data_completion.py`：真实采集器、HTTP 替身、PostgreSQL、Task DTO |
| 4 期间错误；5 历史不足 | `test_phase6a_review_completion.py`：真实金融分支执行 |
| 6 叙述候选耗尽 | `test_output_dependencies.py` 及精确历史状态重放 |
| 7 Risk 授权替换；8 未授权实际模型 | `test_dynamic_model_routing.py` 及模型策略回归 |
| 9 可选公式缺失；10 必需公式缺失 | `test_phase6a_review_completion.py`：PASS 与 BLOCK 对照 |
| 11 保留证明/复核；12 调度后闭环 | 两份不可变故障快照、真实保留 Proof、隔离持久化重放 |

两份重放覆盖真实保留的 Proof/Commitment/Verification、闭环前事件、独立 Review、
原生报告贡献、释放、SQLAlchemy 持久化、六个生产 GET 面和每 Run 六个真实
TypeScript 解码器、HTML、materialize_memory、Object detail 与 Memory GET。
失败 Agent 记录仍为 FAILED，新 RVV 仅存在于一次性测试 schema。

迁移 `20260908_0014` 为 Evidence 增加可空 document authority；新获授权的
运行环境应先迁移再启动此版本。现有历史 API 进程没有重启，因此本次源码冻结
不表示当前浏览器已经由修复版后端提供服务。

**READY_FOR_PHASE6B = NO。** 下一步是离线通过后，明确授权一次全新的独立 NVDA
live 复验。不重试历史 Run，不静默复用已消耗授权。性能/POT 工作继续受门禁限制。
