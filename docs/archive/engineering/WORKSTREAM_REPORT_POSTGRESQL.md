# WS-J PostgreSQL Durable Persistence Report

## Scope and baseline

- Branch: `ws/postgresql`
- Base: `0a58386` (`config: pass phase 2 secret safety gate`)
- Runtime used: Python 3.11.16 from the shared project virtual environment
- Ownership observed: database infrastructure, application persistence extension, Alembic,
  PostgreSQL tests, and this report only
- Shared Settings, `pyproject.toml`, domain contracts/enums, API entry point, and parallel status
  were not changed

## Environment classification

`ENVIRONMENT_ABSENT_EXPECTED`

| Probe | Result | Classification |
| --- | --- | --- |
| `pg_isready` | `/tmp:5432 - no response` | PostgreSQL service unavailable |
| Docker engine | socket unavailable | container fallback unavailable |
| configured DB backend | `sqlite+aiosqlite` | existing local configuration retained |
| `asyncpg` import | not installed | optional `postgres` extra not installed |

This is an environment limitation, not a code failure. The real PostgreSQL test is conditional on
both `TEST_POSTGRESQL_URL` (an async SQLAlchemy URL) and `asyncpg`; it skips with a precise reason
when either prerequisite is absent. No database URL or credential is printed by the test or report.

## Delivered implementation

### Schema and migration

Alembic revision `20260904_0001` creates PostgreSQL-native durable tables for:

- ResearchObject, draft, goal, scheme, ResearchRun, and Task
- RuntimeEvent plus a per-run sequence counter
- EvidenceRecord and CalculationRecord
- CorrectionRecord and ReplanRequest
- ReviewRecord
- CanonicalExecutionRecord and ReleasedResearchResult
- RuntimeCheckpoint

The migration uses JSONB payloads, record/run indexes, parent foreign keys with explicit deletion
behavior, positive event sequence checks, unique `(run_id, sequence)`, and one canonical/released
record per run. An offline `alembic upgrade head --sql` compilation completed successfully.

### Repository coverage

| Record | Durable path | Decision |
| --- | --- | --- |
| ResearchObject / ResearchRun | existing `SQLAlchemyApplicationRepository` | reused and migration-backed |
| Task | aggregate writer plus `SQLAlchemyRunRecordRepository` | reused + typed projection |
| RuntimeEvent | existing aggregate writer and new `PostgresRuntimeEventStore` | extended for DB sequencing/replay |
| Evidence | existing `SQLAlchemyEvidenceRepository` | reused and migration-backed |
| Calculation | aggregate writer plus typed run-record repository | reused + typed projection |
| Correction | new row + aggregate persistence + typed repository | added |
| Replan | new row + aggregate persistence + typed repository | added |
| Review | aggregate writer plus typed run-record repository | reused + typed projection |
| Canonical | aggregate writer plus typed single-result lookup | reused + typed projection |
| Released | aggregate writer plus typed single-result lookup | reused + typed projection |

Persisted runtime-event identity is now immutable: an existing event ID cannot be moved to another
run or sequence by an aggregate save.

### Concurrency-safe event sequencing

PostgreSQL owns sequence allocation through a `BEFORE INSERT` trigger:

1. A generated sequence performs atomic `INSERT ... ON CONFLICT DO UPDATE` on the per-run counter.
2. An explicit sequence advances the counter only when it is exactly the next value.
3. Gaps and out-of-order inserts raise SQLSTATE `23514`.
4. `(run_id, sequence)` remains a separate database unique constraint.
5. Concurrent runs allocate independently because the counter key is `run_id`.

`PostgresRuntimeEventStore` exposes append, atomic emit, ordered replay, polling wait, and resume
resolution by sequence or event ID. It implements the existing `RuntimeEventStore` protocol without
changing that shared contract.

### Checkpoint / restore and SSE replay

`SQLAlchemyCheckpointStore` persists immutable checkpoint payloads and deterministically selects
the latest checkpoint by `(created_at, checkpoint_id)`. `restore_runtime_state` validates run ID,
graph version, and task-state consistency before reconstructing a defensive runtime state copy.

The PostgreSQL event store feeds the existing `runtime_event_stream`; replay begins strictly after
the resolved `Last-Event-ID`, then continues through the same durable data path.

## Verification

| Gate | Result |
| --- | --- |
| WS-J module tests | **4 passed, 1 skipped** |
| Full repository tests | **81 passed, 1 skipped** |
| Ruff (`ruff check .`) | **pass** |
| Diff whitespace (`git diff --check`) | **pass** |
| Alembic offline PostgreSQL SQL generation | **pass** |
| Conditional real PostgreSQL concurrency/SSE test | **skipped: environment absent** |

The real PostgreSQL test creates and later drops only a random test-owned schema. When enabled, it
concurrently emits 30 events, verifies the contiguous `1..30` sequence, rejects an out-of-order
append, verifies ordered replay, and validates SSE resume plus event-ID resolution.

## Boundary and security review

- No shared Settings or dependency changes were required.
- No domain contract or enum changes were made.
- No Phase-1 SQLite behavior was removed; new SQLite durability/restore tests pass.
- No hard-coded password, API key, token, or live database URL was introduced.
- Destructive test cleanup is limited to its randomly generated PostgreSQL schema.
- `CONTRACT_CHANGE_REQUEST`: none.

## Follow-up when PostgreSQL is available

Install the declared optional extra (`postgres`) and supply a disposable async PostgreSQL test URL
through `TEST_POSTGRESQL_URL`, then run:

```text
PYTHONPATH=. python -m pytest tests/postgresql/test_postgresql_runtime.py -q
```

This follow-up validates the already-covered trigger semantics against a live PostgreSQL engine; it
does not block the current module gate because the assigned environment explicitly lacks that
service and driver.
