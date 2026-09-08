# 16 — 术语表 V1

[English](16_GLOSSARY_V1.md)

**Research Object**<br>
长期研究主体，例如 NVDA。

**Research Goal**<br>
用户要回答的金融问题。

**Research Scheme Snapshot**<br>
AI 针对 Object + Goal 生成、用户确认后固化到 Run 的研究方法快照。

**Research Run**<br>
用户发起的一次完整金融研究执行。

**Task**<br>
Lead Agent 拆出的可执行研究工作单元。

**Planned Task Graph**<br>
正式执行前生成的初始任务图。

**Actual Runtime Graph**<br>
实际执行过程中包含 correction / replan / generated capability 的真实图。

**Research Lead Agent**<br>
负责整体规划、Replan 决策和整合。

**Specialist Agent**<br>
负责一个特定金融 Task 的执行。

**Skill**<br>
Agent 执行某类 Task 的方法包。

**Tool Runtime**<br>
统一调用 Native / MCP / Generated backend 的执行入口。

**Capability**<br>
系统实际能执行的业务/技术能力。

**Native Capability**<br>
直接调用系统内部代码 / Adapter。

**MCP Capability**<br>
通过 MCP Client/Server 调用的能力。

**Generated Capability**<br>
运行期间针对明确 Gap 生成并验证的临时能力。

**Self-Correction**<br>
Task 目标不变，在 Task 内纠错。

**Replan**<br>
原计划无法继续，需要修改 Graph。

**Evidence**<br>
经来源、期间、格式、冲突等验证后被接受的正式数据证据。

**Calculation Record**<br>
可复算金融数字的计算记录。

**AI Judgment**<br>
模型基于 Evidence / Calculation 形成的金融判断，不等同于 Fact。

**Financial Review**<br>
独立于 Agent 的金融复核。

**Proof Policy**<br>
决定哪些确定性步骤 MUST_PROVE。

**ZK Proof**<br>
证明某个确定性程序对承诺输入正确执行的密码学证明。

**Release Gate**<br>
最终发布门。

**Canonical Execution Record**<br>
一次执行的机器 / 审计事实源；B/C 共同来源。

**Released Research Result**<br>
通过 assurance 后的正式业务结果。

**Financial Report**<br>
A：面向金融用户的业务主输出。

**Financial Review View**<br>
B：Claim / Evidence / Calculation / Judgment / Review / Proof。

**Execution Details**<br>
C：Task / Agent / Skill / Tool / Code / Trace / Cost。

**Object Writeback**<br>
把可沉淀结果版本化写回 Object。

**POT / Evaluation**<br>
Run 后对模型、Agent、Skill、Capability、成本和质量进行评价。
