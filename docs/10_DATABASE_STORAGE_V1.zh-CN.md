# 10 — 数据库、产物与存储 V1

[English](10_DATABASE_STORAGE_V1.md)

## 1. 结构化数据库

目标：PostgreSQL。

本地测试：SQLite。

建议表：

- research_objects
- research_object_state_versions
- canonical_metric_values
- research_goals
- research_scheme_snapshots
- research_runs
- tasks
- task_dependencies
- runtime_events
- evidence_records
- calculation_records
- agent_decisions
- correction_records
- replan_records
- capabilities
- generated_capability_records
- review_records
- proof_records
- canonical_execution_records
- released_research_results
- report_assets
- evaluation_records

## 2. 产物存储

不要把大型二进制文件放入数据库。

MVP 本地结构：

```text
artifacts/
├── objects/
│   └── OBJ-NVDA/
├── runs/
│   └── RUN-023/
│       ├── evidence/
│       ├── normalized/
│       ├── charts/
│       ├── reports/
│       ├── proofs/
│       └── generated_capabilities/
└── manifests/
```

未来：S3 / MinIO / OSS。

## 3. 工作区

与持久化产物存储分离：

```text
workspaces/RUN-023/TASK-E/WS-001/
```

工作区可在保留期过后清理。

被提升为持久产物的输出复制到 Artifact Store。

## 4. Langfuse

Langfuse 保存技术追踪。

业务数据库仅保存追踪引用。

## 5. 证明

Receipt／证明产物：

- 程序／镜像 id
- 输入承诺
- journal／输出
- receipt 引用
- 验证器结果
- generated_at

## 6. 版本管理

不得原地更新历史 Run 记录。

对象状态采用版本管理。

已发布报告应支持：

```text
DRAFT
VERIFIED
PUBLISHED
SUPERSEDED
```

即使 MVP 仅使用 VERIFIED。

## 7. 保留策略

初始策略字段：

```text
artifact_type
retention_class
expires_at?
legal_hold?
```

MVP 可以保留全部本地产物，但 schema 不应阻碍未来清理。
