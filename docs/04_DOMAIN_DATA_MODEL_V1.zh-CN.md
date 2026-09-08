# 04 — 领域与数据模型 V1

[English](04_DOMAIN_DATA_MODEL_V1.md)

## 1. 聚合概览

```text
ResearchObject 1 ── N ResearchRun
ResearchRun    1 ── 1 ResearchGoal
ResearchRun    1 ── 1 ResearchSchemeSnapshot
ResearchRun    1 ── N Task
Task           N ── N EvidenceRecord
Task           1 ── N CalculationRecord
Task           1 ── N CorrectionRecord
ResearchRun    1 ── N ReplanRecord
ResearchRun    1 ── N ReviewRecord
ResearchRun    1 ── N ProofRecord
ResearchRun    1 ── 1 CanonicalExecutionRecord
ResearchRun    1 ── 0..1 ReleasedResearchResult
ReleasedResearchResult 1 ── N ReportAsset
```

## 2. ResearchObject

字段：

```text
object_id
object_type
symbol
company_name
exchange
sector
currency
identity_version
created_at
updated_at
```

长期子项：

- ObjectStateVersion
- CanonicalMetricValue
- DataPackage
- ResearchRun 引用
- 报告引用
- 判断引用

## 3. CanonicalMetricValue

唯一性不代表“永远只有一个值”。

建议的自然键：

```text
object_id
metric_code
period
as_of
definition_version
```

字段：

```text
canonical_value_id
value
unit
currency
value_type: FACT | CALCULATION | FORECAST | JUDGMENT
source_evidence_ids[]
calculation_id?
assumption_set_id?
run_id
status
version
```

## 4. ResearchGoal

```text
goal_id
research_object_id
goal_type
goal_text
as_of
preferences
created_at
```

## 5. ResearchSchemeSnapshot

限定于 Run 的 AI 生成研究方法。

```text
scheme_id
goal_id
object_id
scope[]
data_requirements[]
agent_requirements[]
skill_requirements[]
calculation_requirements[]
assurance_requirements
report_requirements[]
limitations[]
generated_by
generated_model
generated_at
confirmed_at
```

确认后绝不修改。新的确认创建新的快照版本。

## 6. ResearchRun

状态：

```text
DRAFT
SCHEME_GENERATING
AWAITING_CONFIRMATION
PLANNING
RUNNING
REVIEW
PROVING
RELEASED
FAILED
CANCELLED
```

字段：

```text
run_id
object_id
goal_id
scheme_id
planned_graph_id
actual_graph_id
execution_target
status
as_of
started_at
completed_at
```

## 7. Task

状态：

```text
CREATED
WAITING
READY
RUNNING
SELF_CORRECTING
BLOCKED
REVIEW
COMPLETED
FAILED
CANCELLED
```

字段：

```text
task_id
run_id
parent_task_id?
task_type
goal
assigned_agent
skill_id
dependencies[]
origin: PLAN | REPLAN | REVIEW_FIX
reason_code?
progress
attempt_count
status
result_ref?
created_at
completed_at
```

## 8. EvidenceRecord

```text
evidence_id
run_id
object_id
provider
source_locator
retrieved_at
period
as_of
raw_artifact_ref
normalized_field
normalized_value
unit
currency
snapshot_hash
validation_status
conflict_status
accepted_at
```

## 9. CalculationRecord

```text
calculation_id
run_id
task_id
capability_id
capability_version
formula_id
code_hash?
input_evidence_ids[]
input_values_snapshot
parameters
output_value
output_unit
status
review_status
proof_ref?
created_at
```

## 10. CorrectionRecord

```text
correction_id
run_id
task_id
problem_code
detected_by
attempt
action
input_refs
output_refs
status: RESOLVED | FAILED | ESCALATED
started_at
resolved_at
```

## 11. ReplanRecord

```text
replan_id
run_id
requesting_task_id
requested_by
reason_code
reason_detail
proposed_graph_change
decision: APPROVED | REJECTED
decided_by
actual_graph_version_before
actual_graph_version_after
created_task_ids[]
```

## 12. Capability

```text
capability_id
version
name
category
backend: NATIVE | MCP | GENERATED
input_schema
output_schema
deterministic
proof_eligible
lifecycle
implementation_ref
owner
```

生成能力生命周期：

```text
GENERATED
TESTED
FINANCIAL_VALIDATED
TASK_APPROVED
REVIEWED
CERTIFIED
DEPRECATED
```

MVP 到 TASK_APPROVED 为止。

## 13. CanonicalExecutionRecord

B/C 投影的业务事实源。

```text
record_id
run_id
object_snapshot_ref
goal_ref
scheme_ref
planned_graph
actual_graph
task_refs[]
evidence_refs[]
calculation_refs[]
decision_refs[]
correction_refs[]
replan_refs[]
generated_capability_refs[]
review_refs[]
proof_refs[]
trace_refs[]
token_usage
cost
latency
runtime_outcome
created_at
```

## 14. ReleasedResearchResult

仅在通过 Release Gate 后产生。

```text
result_id
run_id
structured_financial_results
released_claims[]
judgments[]
assumption_refs[]
risk_output
limitations[]
released_at
```

## 15. 对象回写

回写规则：

- FACT → 接受后进入规范状态
- CALCULATION → 带代码／计算引用的版本化指标
- FORECAST → 要求 assumption_set + run
- JUDGMENT → 仅作为版本化判断，绝不覆盖规范事实
