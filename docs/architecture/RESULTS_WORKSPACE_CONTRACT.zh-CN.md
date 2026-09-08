# Results Workspace 语义契约 — W1

[English](RESULTS_WORKSPACE_CONTRACT.md)

## 冻结与门禁

当前 Owner 校准覆盖下述历史门禁：仅保留 Bocha Web Search，其他 Bocha 能力及凭证
不在范围内。FMP 活动池为已获授权的四个不同 Key，不存在 Bocha AI 排障或实测门禁。

W1 契约基于已授权的干净基线 `a1019f5be8b51597055775cca4e446523e3e0a75`
（tree `d73ece10766d1db9a53a5ce9b81e9027c7eb1209`）冻结。本文件不代表 W2 已实现。
W3、本地 live、发布与全新下载 live 分别受门禁约束。Phase 6B 不在范围内。
不得改写历史记录或历史报告文件。

两次 Bocha smoke 授权已消耗：Web HTTP 200、结构 PASS；AI HTTP 403、FAIL。
仅凭本次响应不能确定是凭证、权限、配额还是其他访问规则导致拒绝。未获授权重试。
该门禁解决前，不得宣称两个能力均健康，也不得发布。

## 同一份权威事实

### Owner 门禁校准 — PHASE6A_RESULTS_CLOSURE_2

后续决定覆盖上面的初始停止条件：AI Search HTTP 403 不阻塞 W2、W3、截图和离线回归。
原响应正文未保留，因此根因为 NOT_PROVEN。Web 为 CONFIGURED + LIVE_PROVEN，禁止
追加 Web 调用；AI 为 CONFIGURED + LIVE_HEALTH_UNPROVEN/403。Owner 在外部确认并修正
权限、余额、配置后，允许恰好一次 AI-only smoke，不得重试，不得写入研究证据。
先完成离线工作，再等待该外部门禁。本次 W2/W3 修改未执行付费 NVDA Run，也未发布。

实现新增只读 GET `/api/research-runs/{run_id}/results-semantics`，校验已发布 Claim、
原 Review 快照、唯一计算事件和不可变恢复审计之间的精确关系。新 HTML/PDF 不展示未经
复核的自由叙述；历史导出保留原文件，浏览器明确提示其版本边界。

A（报告）、B（财务复核）、C（执行记录）是同一 Run、Scheme、ReleasedResult、
Claim、Review、Calculation、Evidence、AgentOutput、Event、Proof 和恢复记录的
只读投影。名称和相同 Actor 标签不能作为关联依据。每条关系必须有精确身份、类型
且不存在歧义。缺失关系保持不可用；计数和展示文案不能创造关系。

无需新增 Run 终态枚举。`RELEASED` 表示释放策略通过，不表示所有分支都成功。
发布有效性、研究限制、追踪覆盖率和文件可用性是相互独立的维度。

## A — 已复核报告内容

- 重要数值和财务结论只能来自已复核的类型化释放包。允许确定性整理，不要求新增模型。
- 当前未进入复核的 Specialist/Synthesis 文本，不能仅因 AgentOutput 成功就成为
  报告重要结论；其真实可观察输出保留在 C。
- 未来新增重要叙述，须先建立 Claim 表示并绑定到 Review 输入；Review 后内容改变
  必须阻断释放/发布。
- 新报告的浏览器与 HTML/PDF 使用统一权威内容块。内容块关联真实 Claim、Calculation
  或 AgentOutput、Review selector，以及已有记录支持的执行事件；不再仅关联 Revenue Growth。
- 历史导出保留原字节/哈希，不补写贡献关系、不追溯宣称未复核文本已复核；展示历史导出限制。
- 专业报告下提供 INPUT、可观察 PROCESS、OUTPUT 追踪；不展示隐藏推理，
  不生成缺失的 Risk、News、Target 结论。

## B — 财务语言投影

使用真实 ReviewChecks 及精确 selector `(review_id, check_code, subject_refs)`。
聚合级检查允许空 subject 列表，不允许重复 selector。保留原状态与数值精度，
白名单投影财务 expected/actual 和解释，不暴露任意内部负载。展开项展示 INPUT、
PROCESS、OUTPUT、VERDICT，不以关系数量替代实际财务比较结果。

分组仅是真实检查的展示元数据。覆盖分支/方案可用性代码、`EVD-` 身份并保留未知代码
回退。参考 Review 有 62 项 PASS，其中一项 cardinality 的 subject 为空。
不能以合成数据替代。Review→Execution 必须有精确唯一的类型化目标；相同 Actor 或
同属于 CanonicalRecord 不等于该检查的执行因果关系。

## C — 技术执行组织

| 类别 | 权威输入 |
| --- | --- |
| 01 Research Lead | 已保留计划/Lead Task 与输出 |
| 02 Specialist Agents | Fundamental、Peer、Research & News、Valuation、Risk、Synthesis |
| 03 Data Providers | 真实证据/Provider 来源，包括 FMP、Bocha |
| 04 Deterministic Code | 计算记录及验证通过的生成能力 |
| 05 Runtime & Recovery | 尝试、策略/预算决策、Owner Run 恢复 |
| 06 Financial Review | 精确 Review 和检查 |
| 07 Proof | 策略、输入承诺、Proof、验证记录 |
| 08 Release / Report / Memory | 持久化释放、文件、Memory 版本身份 |

包含没有成功输出的 Task，并保留失败。不能从通用证据事件推断 FMP，也不能把支持类
Actor 强制标为 COMPLETED。I/P/O 详情来自已有记录。“Used by Report” 必须基于
明确验证过的贡献关系；支持多目标和原生 Calculation+Event，不能虚构 AgentOutput。
其他记录为仅执行/支持证据，不代表报告失败。

## 恢复与限制

复用 `closure_recovery_records` 和迁移 `20260909_0015`，不为命名新增迁移。
有界公开 RunRecoveryAttempt 包含原终态、失败阶段、attempt ID、Owner/Policy 授权、
恢复节点、复用成果引用、执行阶段、新模型/计算/Proof 次数和最终状态。校验 attempt
关联、原终态事件、审计哈希及当前成果身份；不公开完整失败快照。

参考 `RUN-75daae15-9f35-4233-83ff-6d24f2e151ba` 展示原 FAILED、Owner 授权从
Release 恢复、复用 Review/Proof/计算/有效输出、新调用/计算/证明均为 0，随后
RELEASED 与已持久化 Memory。不能把内部 REVIEW 状态标记解释成重新执行复核。
若释放后 Memory 失败，仍是写回未完成，不能追溯把释放改成失败。

有效释放且存在已记录研究限制时使用“已发布 · 存在研究限制”，解释原 Risk 失败和
来源缺口。PDF 缺失和追踪覆盖不足单独标注，不改变 Run 发布状态。

## W2 实现与 W3 验收

Parent 串行修改共享 DTO、投影和前端。增加有界类型字段并严格解码精确身份。
生产数值不来自 V17.1；V17.1 仅作视觉与信息架构参考。不自动重试 Provider 或 Run。

必需测试：真实 62 检查与空 selector、精确比较值、所有重要指标/Claim 追踪、
原生 Calculation/Event 与多贡献、跨 Run/歧义关系拒绝、新 Run 浏览器/导出同源、
八类执行组织、无输出失败、历史恢复不可变、原始审计快照不泄漏、限制与文件缺失
分离、Memory 来源。

W3 只读使用保留的真实数据库，验证 A/B/C 身份、追踪关系、恢复历史、原失败、最终
释放、研究限制、检查数量、Proof、Memory；不调用模型、数据 Provider 或证明。
拍摄真实 S01–S10 截图，索引记录路由、Run ID、状态、证明内容及限制。广泛离线回归、
TypeScript/build、Docker、双语链接和密钥扫描全部通过后，才能使用唯一一次本地新
live Run。发布后才可使用另一次全新下载 Mac live Run。W1 时两次 live 授权均未消耗。
