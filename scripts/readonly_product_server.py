"""Strict local acceptance server; real product responses, production DB read-only.

Run with VFAS_ACCEPTANCE_ENV_FILE pointing to the existing private settings file:
PYTHONPATH=. .venv/bin/uvicorn scripts.readonly_product_server:app --port 8010
This entry point is deliberately separate from normal writable production startup.
No schema changes, fake responses, scheduler, outbound HTTP, or mutation endpoints.
"""
import os
from collections import Counter
import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import event

import apps.api.main as production
from src.infrastructure.config.settings import Settings
from src.infrastructure.database import composition
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend

stats = Counter()
_original_engine = composition.create_async_engine

def readonly_engine(*args, **kwargs):
    connect = dict(kwargs.get("connect_args", {}))
    server = dict(connect.get("server_settings", {}))
    server["default_transaction_read_only"] = "on"
    connect["server_settings"] = server
    kwargs["connect_args"] = connect
    engine = _original_engine(*args, **kwargs)
    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def statement(connection, cursor, sql, parameters, context, executemany):
        verb = sql.lstrip().split(None, 1)[0].upper()
        stats["sql_" + verb] += 1
        if verb in {"INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "ALTER", "DROP", "TRUNCATE"}:
            stats["blocked_sql_writes"] += 1
            raise RuntimeError("READ_ONLY_ACCEPTANCE_WRITE_BLOCKED")
    @event.listens_for(engine.sync_engine, "commit")
    def commit(connection):
        stats["db_commits"] += 1
    return engine

async def no_scheduler(self):
    stats["scheduler_disabled"] += 1

async def block_async_http(*args, **kwargs):
    stats["blocked_outbound_http"] += 1
    raise RuntimeError("READ_ONLY_ACCEPTANCE_PROVIDER_DISABLED")

def block_sync_http(*args, **kwargs):
    stats["blocked_outbound_http"] += 1
    raise RuntimeError("READ_ONLY_ACCEPTANCE_PROVIDER_DISABLED")

composition.create_async_engine = readonly_engine
PostgreSQLPhase4ProductBackend.start = no_scheduler
httpx.AsyncClient.send = block_async_http
httpx.Client.send = block_sync_http
settings = Settings(_env_file=os.environ.get("VFAS_ACCEPTANCE_ENV_FILE"))
production.get_settings = lambda: settings
app = production.create_app()

@app.middleware("http")
async def mutations_disabled(request: Request, call_next):
    stats["http_" + request.method] += 1
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        stats["blocked_mutation_requests"] += 1
        return JSONResponse({"error":"READ_ONLY_ACCEPTANCE_MUTATION_DISABLED"},status_code=403)
    return await call_next(request)

@app.get("/__acceptance__/status")
async def acceptance_status():
    backend = app.state.phase4_product_backend
    async with backend.sessions() as session:
        from sqlalchemy import text
        readonly = await session.scalar(text("SHOW transaction_read_only"))
    return {"counters": dict(stats), "transaction_read_only":readonly,
            "scheduler_running":backend._worker is not None,
            "executions":len(backend._executions)}
