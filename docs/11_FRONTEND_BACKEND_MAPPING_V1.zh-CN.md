# 11 — 前端／后端映射 V1

[English](11_FRONTEND_BACKEND_MAPPING_V1.md)

前端视觉仍在演进，因此本文仅冻结稳定契约。

## 1. 主要页面

### 新建任务

后端：

```text
GET objects
POST research-runs/prepare
POST research-runs
```

UX:

```text
Object
→ Goal
→ AI Scheme
→ User Confirm
→ Start
```

### 任务列表

展示 Research Run，而非内部 Task。

后端：

```text
GET /research-runs?...
```

### 研究对象

后端：

```text
GET object
GET state
GET financials
GET runs
```

### Run／AI 研究流程

后端：

```text
GET run
GET tasks
GET graph
GET SSE events
```

## 2. 任务卡片

映射到后端 Task。

UI 不创建任务 ID。

状态与 TaskStatus 一一对应。

## 3. 自纠

SSE:

```text
task.self_correcting
task.correction_resolved
```

UI 更新同一张卡片。

不要新增顶层卡片。

## 4. 重新规划（Replan）

SSE:

```text
replan.approved
graph.task_added
```

UI 根据后端载荷添加新的 Task 块。

## 5. 能力缺口（Capability Gap）

SSE:

```text
capability.gap_detected
```

UI 提示用户。

生成操作调用 API。

## 6. Langfuse

默认只显示：

```text
Trace Active / Captured
```

上述状态。

详细技术追踪属于 Execution Details。

## 7. 结果

A 财务报告：

`GET /result`

B 审查：

`GET /review-view`

C 执行：

`GET /execution-view`

B/C 必须共享 `canonical_execution_record_id`。

## 8. 前端绝不能

- 自行计算正式财务数值
- 根据 UI 规则推断任务图
- 没有后端事件就标记 Proof PASS
- 直接修改对象状态
