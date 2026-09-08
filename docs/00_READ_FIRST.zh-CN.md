# 00 — 首先阅读

[English](00_READ_FIRST.md)

## 目的

本文件用于防止工程实施过程中再次混淆 Task、Agent、Skill、Capability、Scheme、Run、Object、Review、Langfuse、ZK。

## 冻结的心智模型

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

## 不得回退到以下旧模式

### 错误：用户创建内部任务

用户创建的是 Research Run，不是 TASK-A / TASK-B。

### 错误：Agent 在执行中随意动态创建全部任务

默认先形成完整 Initial Planned Task Graph。运行时只有必要时才 Graph Mutation。

### 错误：每次纠错都创建子任务

Task 内部优先 Self-Correction。只有 scope / dependency 改变时才 Replan。

### 错误：Langfuse 是一项任务

Langfuse 横切 Runtime instrumentation。

### 错误：ZK 是普通 Agent 工具

Proof 属于 Control Plane；Agent 不得决定跳过 mandatory proof。

### 错误：Scheme 是 MVP 中的静态管理配置

当前 Scheme = AI generated run-scoped research method snapshot + user confirmation。

### 错误：Report / Review / Execution 是一条顺序输出链

A 是业务报告；B/C 是同一次 Canonical Execution Record 的两个复核视角。

## 实施纪律

- Domain 不依赖 FastAPI / FMP / FinRobot / Langfuse。
- API route 不承载完整业务流程。
- Adapter 不把第三方数据结构泄漏到整个系统。
- Runtime Event 是前后端唯一动态执行语言。
- Raw provider data 不直接给 Agent / LLM。
- Generated Code 不直接拥有 host shell / secrets / internet。
