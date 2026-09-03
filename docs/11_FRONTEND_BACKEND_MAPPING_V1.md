# 11 — Frontend / Backend Mapping V1

Frontend is still visually evolving, so this document freezes only the stable contract.

## 1. Primary pages

### New Task

Backend:

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

### Task List

Displays Research Runs, not internal Tasks.

Backend:

```text
GET /research-runs?...
```

### Research Object

Backend:

```text
GET object
GET state
GET financials
GET runs
```

### Run / AI Research Journey

Backend:

```text
GET run
GET tasks
GET graph
GET SSE events
```

## 2. Task Card

Maps to backend Task.

UI does not create task IDs.

States map 1:1 from TaskStatus.

## 3. Self-Correction

SSE:

```text
task.self_correcting
task.correction_resolved
```

UI updates same card.

Do not add top-level card.

## 4. Replan

SSE:

```text
replan.approved
graph.task_added
```

UI adds a new Task block based on backend payload.

## 5. Capability Gap

SSE:

```text
capability.gap_detected
```

UI prompts user.

Generate action calls API.

## 6. Langfuse

Only show:

```text
Trace Active / Captured
```

by default.

Detailed technical trace belongs to Execution Details.

## 7. Result

A Financial Report:

`GET /result`

B Review:

`GET /review-view`

C Execution:

`GET /execution-view`

B/C must share `canonical_execution_record_id`.

## 8. Frontend must never

- calculate official financial values itself
- infer Task graph from UI rules
- mark Proof PASS without backend event
- mutate Object state directly
