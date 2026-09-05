# Phase 4 Wave 1 edge-operation wire promotion

Status: Parent-approved VS01 contract clarification  
Scope: `PathChangeProjectionV1.operations` only

The frozen Phase 4 API contract names `add_edge` and `remove_edge` but does not
name their child fields. For Wave 1 VS01, the Parent promotes the existing A/B
projection encoding as the sole public wire form:

```json
{
  "operation": "add_edge",
  "task_id": "<dependent task>",
  "dependency_task_id": "<dependency task>"
}
```

`remove_edge` uses the identical child fields. Both identities MUST occur in
the containing PathChange `task_refs` and MUST resolve to Tasks in the same
authoritative Run graph. `add_node` remains exactly
`{"operation":"add_node","task_id":"<new task>"}`.

This clarification does not change the separately frozen RuntimeEvent payload
for `graph.edge_added` and `graph.edge_removed`; those event payloads continue
to use `source_task_id` and `target_task_id`.
