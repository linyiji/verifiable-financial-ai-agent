# Phase 4 Wave 1 边操作传输格式正式确认

[English](PHASE4_WAVE1_EDGE_OPERATION_PROMOTION.md)

状态：主协调方已批准的 VS01 契约澄清<br>
范围：仅 `PathChangeProjectionV1.operations`

冻结的 Phase 4 API 契约规定了 `add_edge` 和 `remove_edge`，但未规定其子字段。对于 Wave 1 VS01，主协调方将现有 A/B 投影编码正式确认为唯一公开传输格式：

```json
{
  "operation": "add_edge",
  "task_id": "<dependent task>",
  "dependency_task_id": "<dependency task>"
}
```

`remove_edge` 使用完全相同的子字段。两个身份标识都必须出现在所属 PathChange 的 `task_refs` 中，并且必须解析为同一权威 Run 图内的 Task。`add_node` 保持为
`{"operation":"add_node","task_id":"<new task>"}`。

本澄清不改变独立冻结的 `graph.edge_added` 和 `graph.edge_removed` RuntimeEvent 载荷；这些事件载荷继续使用 `source_task_id` 和 `target_task_id`。
