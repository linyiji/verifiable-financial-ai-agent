# 16 — Glossary V1

**Research Object**  
长期研究主体，例如 NVDA。

**Research Goal**  
用户要回答的金融问题。

**Research Scheme Snapshot**  
AI 针对 Object + Goal 生成、用户确认后固化到 Run 的研究方法快照。

**Research Run**  
用户发起的一次完整金融研究执行。

**Task**  
Lead Agent 拆出的可执行研究工作单元。

**Planned Task Graph**  
正式执行前生成的初始任务图。

**Actual Runtime Graph**  
实际执行过程中包含 correction / replan / generated capability 的真实图。

**Research Lead Agent**  
负责整体规划、Replan 决策和整合。

**Specialist Agent**  
负责一个特定金融 Task 的执行。

**Skill**  
Agent 执行某类 Task 的方法包。

**Tool Runtime**  
统一调用 Native / MCP / Generated backend 的执行入口。

**Capability**  
系统实际能执行的业务/技术能力。

**Native Capability**  
直接调用系统内部代码 / Adapter。

**MCP Capability**  
通过 MCP Client/Server 调用的能力。

**Generated Capability**  
运行期间针对明确 Gap 生成并验证的临时能力。

**Self-Correction**  
Task 目标不变，在 Task 内纠错。

**Replan**  
原计划无法继续，需要修改 Graph。

**Evidence**  
经来源、期间、格式、冲突等验证后被接受的正式数据证据。

**Calculation Record**  
可复算金融数字的计算记录。

**AI Judgment**  
模型基于 Evidence / Calculation 形成的金融判断，不等同于 Fact。

**Financial Review**  
独立于 Agent 的金融复核。

**Proof Policy**  
决定哪些确定性步骤 MUST_PROVE。

**ZK Proof**  
证明某个确定性程序对承诺输入正确执行的密码学证明。

**Release Gate**  
最终发布门。

**Canonical Execution Record**  
一次执行的机器 / 审计事实源；B/C 共同来源。

**Released Research Result**  
通过 assurance 后的正式业务结果。

**Financial Report**  
A：面向金融用户的业务主输出。

**Financial Review View**  
B：Claim / Evidence / Calculation / Judgment / Review / Proof。

**Execution Details**  
C：Task / Agent / Skill / Tool / Code / Trace / Cost。

**Object Writeback**  
把可沉淀结果版本化写回 Object。

**POT / Evaluation**  
Run 后对模型、Agent、Skill、Capability、成本和质量进行评价。
