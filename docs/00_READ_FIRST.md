# 00 — READ FIRST

## Purpose

本文件用于防止工程实施过程中再次混淆 Task、Agent、Skill、Capability、Scheme、Run、Object、Review、Langfuse、ZK。

## Frozen mental model

```text
Research Object
   +
Research Goal
   ↓
AI-generated Research Scheme
   ↓ User Confirm
Research Run
   ↓
Research Lead Agent
   ↓
Initial Planned Task Graph
   ↓
Dynamic Runtime
   ↓
Parallel / Dependent Tasks
   ↓
Specialist Agent
   ↓
Skill
   ↓
Tool Runtime
   ↓
Capability
   ↓
Evidence + Financial Code + AI Judgment
   ↓
Independent Financial Review
   ↓
Proof Policy / ZK if required
   ↓
Release
   ↓
A. Financial Report
B. Financial Review View
C. Execution Details
   ↓
Object Writeback + Evaluation
```

## Do not regress to these old patterns

### Wrong: user creates internal tasks

用户创建的是 Research Run，不是 TASK-A / TASK-B。

### Wrong: Agent dynamically invents every task during execution

默认先形成完整 Initial Planned Task Graph。运行时只有必要时才 Graph Mutation。

### Wrong: every correction creates a child task

Task 内部优先 Self-Correction。只有 scope / dependency 改变时才 Replan。

### Wrong: Langfuse is a task

Langfuse 横切 Runtime instrumentation。

### Wrong: ZK is a normal Agent tool

Proof 属于 Control Plane；Agent 不得决定跳过 mandatory proof。

### Wrong: Scheme is a static admin configuration for MVP

当前 Scheme = AI generated run-scoped research method snapshot + user confirmation。

### Wrong: Report / Review / Execution are one sequential output chain

A 是业务报告；B/C 是同一次 Canonical Execution Record 的两个复核视角。

## Implementation discipline

- Domain 不依赖 FastAPI / FMP / FinRobot / Langfuse。
- API route 不承载完整业务流程。
- Adapter 不把第三方数据结构泄漏到整个系统。
- Runtime Event 是前后端唯一动态执行语言。
- Raw provider data 不直接给 Agent / LLM。
- Generated Code 不直接拥有 host shell / secrets / internet。
