# 10 — Database, Artifact & Storage V1

[简体中文](10_DATABASE_STORAGE_V1.zh-CN.md)

## 1. Structured DB

Target: PostgreSQL.

Local tests: SQLite.

Suggested tables:

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

## 2. Artifact Store

Do not put large binaries into DB.

MVP local structure:

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

Future: S3 / MinIO / OSS.

## 3. Workspace

Separate from durable artifact store:

```text
workspaces/RUN-023/TASK-E/WS-001/
```

Workspace may be cleaned after retention period.

Promoted outputs are copied to Artifact Store.

## 4. Langfuse

Langfuse stores technical trace.

Business DB only stores trace refs.

## 5. Proofs

Receipt / proof artifact:

- program/image id
- input commitment
- journal/output
- receipt ref
- verifier result
- generated_at

## 6. Versioning

Do not update historical Run records in place.

Object state is versioned.

Released reports should support:

```text
DRAFT
VERIFIED
PUBLISHED
SUPERSEDED
```

even if MVP only uses VERIFIED.

## 7. Retention

Initial policy fields:

```text
artifact_type
retention_class
expires_at?
legal_hold?
```

MVP can keep all local artifacts but schema should not block future cleanup.
