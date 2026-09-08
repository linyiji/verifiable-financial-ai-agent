# 受控用户 Alpha 会话指南

[English](USER_ALPHA_SESSION_GUIDE.md)

依据：[就绪 / 范围 / 严重程度门禁](USER_ALPHA_READINESS.zh-CN.md)。计划邀请 3–5 位用户，每场 20–30 分钟。这是产品研究，不是技术基准、销售演示或投资建议。

## 参与者到场前

检查就绪文档中的受控环境门禁。从 `http://127.0.0.1:4173/objects/OBJ-NVDA` 开始。使用有监督的只读导航，不执行新研究、prepare、确认、重执行或记忆写入。不启动生产调度器。R1/v1 和 R5/v2 须已存在。使用 Object 和 Results 路由；避开已发布 Run 生命周期路由的自动记忆重放。不提供不受限参与者凭据或公开部署。

获得记录脱敏笔记的同意。默认不录音 / 录像或截图；这些需要另行明确同意。分配化名 `ALPHA-###` 会话 ID。招募前确定删除日期：建议原始笔记保留 30 天；此后如同意允许，仅保留去身份化发现。笔记仅研究团队可访问。不将参与者笔记提交到仓库。

## 中性旅程（不要先展示答案）

1. 询问希望研究什么公司 / 问题。只记录可选、非敏感意图；说明今天检查既有 NVDA 研究，不提交问题或创建新 Run。
2. 在 Object 页给予约 30 秒，不作教学。询问 A1。
3. 请其寻找当前研究、保留材料及来源（A2/A3）。
4. 请其查看历史，区分知识基线和失败尝试（A5）。R1–R5 是选定别名，不是完整 40 个 Run 的历史。
5. 询问此前研究与当前研究有何变化（A4）。使用 Base vs Current 及精确历史 / 当前 Results 链接。仅在必要时解释。
6. 打开 R5 A（报告）、B（复核）、C（执行）。询问哪些内容增加或未能增加信任（A7）。保留 PARTIAL 来源 / 贡献映射及财务限制。
7. 在 C 中请其用自己的话描述一次真实恢复序列（A6）。
8. 询问是否希望此 Object 再次更新，以及原因（A8）。仅记录意图，不点击 `开始新研究`。

| 问题 | 中性提问 | 观察内容（不是教学脚本） |
| --- | --- | --- |
| A1 | 你认为这个产品做什么？ | 约 30 秒后的自主解释 |
| A2 | 请找到当前 NVDA 研究及其来源 | Object → 当前 v2 → R5 路径 |
| A3 | 这与报告文件夹有区别吗？有什么区别？ | 累积的受治理材料与出处 |
| A4 | 相比此前研究，什么变了？ | 使用比较；未变指标也可独立重新验证 |
| A5 | 哪项工作是基线？这些失败项是什么？ | R1 已发布基线与 R2/R3/R4 执行历史的区别 |
| A6 | 供应商 / 模型失败时发生了什么？ | 同 Run/Task 恢复与新 Run 重执行的区别 |
| A7 | Report、Review 和 Execution 如何增加信任？ | 具体证据及承认限制，而非笼统正确性 |
| A8 | 你希望此 Object 再次更新吗？为什么？ | YES/MAYBE/NO 及解释 |

对每个 A1–A8 分别记录 `UNASSISTED / ASSISTED / NOT_DEMONSTRATED / NOT_OBSERVED`。`NOT_DEMONSTRATED` 表示尝试了但未展示；`NOT_OBSERVED` 表示未询问 / 未看到。记录提示及提供时间。不把辅助后答案算作无帮助，也不从浏览器链接有效推断真人理解。

## 主持解释，仅在观察之后

- Object = 公司 / 研究资产。Run = 一次执行尝试。Memory = 保留的已发布来源研究材料，不是所有此前输出。
- 此处“上次研究”表示此前**已发布知识基线 R1/v1**，不是最近失败尝试。R5 使用 R1 基线，从失败 R4 重新执行 S1。
- Peer：MiMo 超时；在同一 R5 Task 中获准切换至 Sol 并成功。
- Fundamental：Sol 超时；Luna 通过独立能力检查，然后生产尝试成功。这是模型切换，不是供应商切换。Fundamental MiMo 保持 UNKNOWN，未测试。
- Main Agent 提议；Policy 授权。仅使用已注册供应商、能力门禁和固定恢复预算。这不是无限供应商搜索。
- Review 和计算 Proof 提供范围限定的证据，不代表投资适当性或模型普遍正确。失败尝试不继承之后的 PASS 结果。

## 简明反馈模板（空白，无合成参与者）

```text
session_id: ALPHA-###
date:
participant_category: optional broad category
first_time: YES / NO
consent_to_notes: YES / NO
delete_raw_notes_after:
task_context: existing OBJ-NVDA R1–R5, read-only
desired_research_question: optional sanitized text

A1 through A8, each:
  outcome: UNASSISTED / ASSISTED / NOT_DEMONSTRATED / NOT_OBSERVED
  participant_answer:
  observed_action_or_evidence:
  hint_given_and_when:
  elapsed_seconds: optional / NOT_OBSERVED

PRODUCT_COMPREHENSION: 1–5 / NOT_ANSWERED
MEMORY_VALUE: 1–5 / NOT_ANSWERED
INCREMENTAL_VALUE: 1–5 / NOT_ANSWERED
REPORT_TRUST: 1–5 / NOT_ANSWERED
REVIEW_VALUE: 1–5 / NOT_ANSWERED
EXECUTION_TRACE_VALUE: 1–5 / NOT_ANSWERED
BASE_VS_CURRENT_VALUE: 1–5 / NOT_ANSWERED
RECOVERY_COMPREHENSION: 1–5 / NOT_ANSWERED
WOULD_USE_AGAIN: YES / MAYBE / NO / NOT_ANSWERED
PRIMARY_CONFUSION:
MOST_VALUABLE_FEATURE:
BLOCKED_ACTION:
severity: P0 / P1 / P2 / P3 / NONE
safe_reproduction_steps:
expected_vs_observed:
facilitator_intervention:
qualitative_feedback:
```

评分是自报的 Alpha 研究证据。不把它们平均成供应商 / 模型 / 产品分数，也不用来修改路由。保留未回答状态。

## 最小产品遥测与停止条件

手动事件笔记足够：`session_id`、已观测时的经过时间、允许界面、意图操作、结果、帮助程度、问题 ID 和严重程度。不建立分析平台、跟踪脚本或网络日志采集。优先使用 R1–R5 别名，而非 ID。不收集姓名、联系方式、持仓、凭据、原始提示词、私有 CoT、供应商输出转储或私有研究目标。若有人提供敏感信息，停止记录并从保留笔记中脱敏。

出现跨身份 / 数据暴露、主要工作流误导、意外写入或供应商活动，或新增 P0/P1 时停止。继续前先分类并报告。P2/P3 保留记录。3–5 场后，逐问题总结观察、辅助 / 无辅助模式、再次使用意图及严重程度；不宣称统计验证，不启动路由选择 / POT。
