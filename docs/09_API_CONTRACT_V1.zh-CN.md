# 09 — API 契约 V1

[English](09_API_CONTRACT_V1.md)

前缀：`/api`

## 1. 对象

### POST `/objects`

```json
{
  "symbol": "NVDA",
  "company_name": "NVIDIA Corporation",
  "exchange": "NASDAQ",
  "currency": "USD"
}
```

### GET `/objects`

### GET `/objects/{object_id}`

### GET `/objects/{object_id}/state`

### GET `/objects/{object_id}/financials`

### GET `/objects/{object_id}/runs`

## 2. 准备新研究

### POST `/research-runs/prepare`

请求：

```json
{
  "research_object_id": "OBJ-NVDA",
  "research_goal": "评估 NVIDIA 当前的基本面、估值、主要风险以及未来投资价值。",
  "as_of": "2026-09-03",
  "preferences": {
    "depth": "standard"
  }
}
```

响应：

```json
{
  "draft_id": "DRAFT-023",
  "goal": {},
  "scheme_snapshot": {
    "research_scope": [],
    "data_requirements": [],
    "assurance_requirements": {},
    "report_requirements": []
  },
  "status": "awaiting_confirmation"
}
```

## 3. 确认 Run

### POST `/research-runs`

```json
{
  "draft_id": "DRAFT-023",
  "confirm_scheme": true
}
```

响应：

```json
{
  "run_id": "RUN-023",
  "status": "planning"
}
```

## 4. Run

### GET `/research-runs/{run_id}`

### GET `/research-runs/{run_id}/tasks`

### GET `/research-runs/{run_id}/graph`

同时返回：

- planned_graph
- actual_graph

### GET `/research-runs/{run_id}/result`

### GET `/research-runs/{run_id}/review-view`

### GET `/research-runs/{run_id}/execution-view`

## 5. SSE

### GET `/research-runs/{run_id}/events`

Content-Type: `text/event-stream`

## 6. 审查（Review）

### POST `/reviews/{review_id}/resolve`

```json
{
  "action": "ACCEPT_AUTO_FIX"
}
```

## 7. 能力缺口（Capability Gap）

### POST `/research-runs/{run_id}/capability-gaps/{gap_id}/generate`

### POST `/research-runs/{run_id}/capability-gaps/{gap_id}/skip`

## 8. 错误模型

```json
{
  "error": {
    "code": "EVIDENCE_NOT_ACCEPTED",
    "message": "...",
    "details": {},
    "request_id": "..."
  }
}
```

## 9. 幂等性

可重试的写操作应支持：

`Idempotency-Key`

尤其包括：

- 创建对象
- 确认 Run
- 处理审查
- 生成能力

## 10. 身份认证

虽然不是参赛 MVP 核心，但 API 设计应预留：

- user_id
- workspace_id
- actor_id

这些字段，但不在本地原型中将其设为必填。
