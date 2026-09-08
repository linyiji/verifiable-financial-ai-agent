# 09 — API Contract V1

[简体中文](09_API_CONTRACT_V1.zh-CN.md)

Prefix: `/api`

## 1. Objects

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

## 2. Prepare new research

### POST `/research-runs/prepare`

Request:

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

Response:

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

## 3. Confirm run

### POST `/research-runs`

```json
{
  "draft_id": "DRAFT-023",
  "confirm_scheme": true
}
```

Response:

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

Returns both:

- planned_graph
- actual_graph

### GET `/research-runs/{run_id}/result`

### GET `/research-runs/{run_id}/review-view`

### GET `/research-runs/{run_id}/execution-view`

## 5. SSE

### GET `/research-runs/{run_id}/events`

Content-Type: `text/event-stream`

## 6. Review

### POST `/reviews/{review_id}/resolve`

```json
{
  "action": "ACCEPT_AUTO_FIX"
}
```

## 7. Capability Gap

### POST `/research-runs/{run_id}/capability-gaps/{gap_id}/generate`

### POST `/research-runs/{run_id}/capability-gaps/{gap_id}/skip`

## 8. Error model

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

## 9. Idempotency

Writes that can be retried should support:

`Idempotency-Key`

especially:

- create object
- confirm run
- review resolve
- capability generate

## 10. Auth

Not competition-MVP core, but API design should leave:

- user_id
- workspace_id
- actor_id

fields without making them mandatory in local prototype.
