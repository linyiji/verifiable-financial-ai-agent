# WS-R — PostgreSQL Real Integration Report

## Outcome

**PASS** for P2-019 and INFRA-001 through INFRA-007 against the running PostgreSQL
service. The existing database began with no Alembic revision and was upgraded in place through the
append-only chain to `20260904_0003`. No container, volume, database, or schema was deleted or
recreated.

## Runtime and database verification

| Probe | Result |
|---|---|
| PostgreSQL server | `PostgreSQL 16.15 (Debian 16.15-1.pgdg13+2)` |
| Database | `verifiable_financial_agent` |
| User | `vfa` |
| Initial Alembic revision | none |
| Final Alembic revision | `20260904_0003` |
| Final application table count | 18 |
| Test-owned rows after cleanup | 0 |

The connection was supplied to Unified Settings only in the verification process environment. The
database URL and credentials were never printed, written into repository files, or included in test
artifacts. The checked `.env.local` contains no database setting, so it was not modified.

The live database itself provided the empty migration target: revision `0001`, existing append-only
revision `0002`, and new append-only revision `0003` were applied without a downgrade or any
temporary-schema/database workaround. Revisions `0001` and `0002` were not edited.

## Delivered implementation

### Composition and migration boundary

`create_postgresql_persistence()` creates one async SQLAlchemy engine/session factory and supplies:

- `SQLAlchemyApplicationRepository`;
- `SessionFactoryEvidenceRepository`;
- `PostgresRuntimeEventStore`;
- `SQLAlchemyCheckpointStore`; and
- `SQLAlchemyRunRecordRepository`.

Its representation is credential-safe, and it rejects non-PostgreSQL or non-`asyncpg` URLs.
`upgrade_postgresql_database()` injects the URL directly into an in-memory Alembic configuration,
without persisting or logging it. The command-line migration script uses Unified Settings.

### Durable record coverage

| Record | PostgreSQL behavior verified |
|---|---|
| ResearchObject / Goal / Scheme / Run | aggregate save and independent-repository restore |
| Task | planned seven-task graph and actual eight-task graph restored |
| TaskDependency | planned and actual edges independently queryable and ordered |
| RuntimeEvent | concurrent atomic sequence, ordered replay, SSE resume |
| Evidence | four accepted records restored through SQLAlchemy repository |
| Calculation | two records restored with Evidence, Review, and Canonical lineage |
| Correction | complete domain payload round-trip |
| Replan | complete domain payload round-trip |
| Review | complete domain payload round-trip |
| Canonical | complete domain payload round-trip |
| Released result | complete domain payload round-trip |
| Runtime checkpoint | latest checkpoint restart and graph-version restore |

Revision `20260904_0003` adds `task_dependencies` with separate `PLANNED` and `ACTUAL` graph kinds,
ordered dependency positions, foreign keys, a no-self-edge check, and uniqueness constraints. The
aggregate repository refreshes only the target run's dependency projection inside its existing
transaction.

The controlled full run persisted 14 planned dependency edges and 15 actual edges. It proved the
mandatory replan rewiring:

```text
planned: Risk ───────────────→ Synthesis
actual:  Risk → Follow-up Task → Synthesis
```

The restored actual graph remained at version 2, and the checkpoint retained the same dependency
ordering. Review occurred only after synthesis through the existing application workflow.

### Runtime event concurrency and replay

A live concurrency probe emitted 50 events for one confirmed run in parallel. PostgreSQL allocated
one contiguous sequence with no duplicate or gap, and rejected an explicit out-of-order append.
Database `COUNT`, `COUNT(DISTINCT sequence)`, `MIN`, and `MAX` matched the replayed stream. SSE
resumed strictly after both a numeric `Last-Event-ID` and a persisted event ID.

## Acceptance matrix

| Gate | Result | Evidence |
|---|---|---|
| P2-019 PostgreSQL real integration | **PASS** | real full run, restore, lineage, replay |
| INFRA-001 running PostgreSQL | **PASS** | live PostgreSQL 16.15 probe |
| INFRA-002 Unified Settings connection | **PASS** | injected settings used by migration and composition |
| INFRA-003 Alembic empty-database migration | **PASS** | live DB: no revision → `20260904_0003`; no downgrade/rebuild |
| INFRA-004 all-entity persistence | **PASS** | object through released-result typed restores |
| INFRA-005 concurrent event sequence | **PASS** | 50 concurrent events; no gap or duplicate |
| INFRA-006 checkpoint/restart | **PASS** | new repository instance + latest checkpoint restore |
| INFRA-007 SSE replay/resume | **PASS** | ordered replay after sequence and event ID |

## Verification

```text
$ PYTHONPATH=. pytest -q tests/postgresql
9 passed in 1.44s

$ PYTHONPATH=. pytest -q
154 passed, 1 warning in 2.31s

$ ruff check .
All checks passed!

$ ruff format --check <nine WS-R Python files>
9 files already formatted

$ python -m compileall -q src apps tests
PASS

$ git diff --check
PASS
```

The warning is an installed Starlette/AnyIO `BlockingPortal` deprecation; it is unrelated to this
workstream. Focused PostgreSQL tests performed exact, test-owned row cleanup and left zero matching
rows.

## Coordinator wiring API

After migration, Coordinator can compose every durable adapter without duplicating business logic:

```python
settings = get_settings()
upgrade_postgresql_database(settings.database)  # synchronous startup migration
persistence = create_postgresql_persistence(settings.database)

service = ResearchApplicationService(
    repository=persistence.application_repository,
    evidence_repository=persistence.evidence_repository,
    event_store=persistence.event_store,
    checkpoint_store=persistence.checkpoint_store,
)

# application shutdown
await persistence.close()
```

Coordinator commit `fe6a120` owns the service constructor injection. This workstream intentionally
does not edit `service.py` or the API entry point. Read-side inspection uses:

```python
records = persistence.run_record_repository
planned = await records.list_task_dependencies(
    run_id,
    graph_kind=TaskDependencyGraphKind.PLANNED,
)
actual = await records.list_task_dependencies(
    run_id,
    graph_kind=TaskDependencyGraphKind.ACTUAL,
)
```

## Ownership, contract, and secret gates

- No shared domain contract, enum, Settings schema, dependency manifest, API entry point,
  application service/execution module, or parallel status file was changed.
- No database URL, password, API key, token, or credential preview was added to tracked content.
- No `docker run`, volume deletion, schema deletion/recreation, Alembic downgrade, or destructive
  broad cleanup was used.
- `CONTRACT_CHANGE_REQUEST`: none.

## Known hardening item

The application aggregate, runtime-event store, and checkpoint store share an engine but perform
separate repository transactions; there is not yet a cross-adapter transactional outbox/unit of
work. The current workflow and recovery tests close the required restore loop, but atomic commit
across all three adapters remains a later resilience enhancement rather than a Phase-2 blocker.
