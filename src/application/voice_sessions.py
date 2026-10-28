"""Durable voice control, replay, fencing, and a fixed server-owned deadline."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from contracts.api.voice_session import VoiceEvent, VoiceSessionResponse, VoiceStatus
from src.application.errors import ApplicationError
from src.application.voice_authority import AuthorityReceipt, read_receipt
from src.infrastructure.database.sqlite_configuration import configure_sqlite
from src.infrastructure.database.voice_tables import VoiceEventRow, VoiceSessionRow

logger = logging.getLogger(__name__)
CALL_SECONDS = 15 * 60
WARNING_LEAD_SECONDS = 2 * 60
# Existing 60-minute rows retain their persisted deadline and original
# five-minute warning lead; only create() uses the new duration.
LEGACY_WARNING_LEAD_SECONDS = 5 * 60
LEASE_SECONDS = 8


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def fail(code: str, message: str, status: int = 409, *, retryable: bool = False):
    raise ApplicationError(code, message, status_code=status, details={"retryable": retryable})


class VoiceSessions:
    def __init__(
        self,
        app,
        database_url: str,
        media,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.app, self.media, self.clock = app, media, clock
        self.engine = create_async_engine(database_url)
        configure_sqlite(self.engine.sync_engine)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self._maintenance_task = None
        self._deadline_tasks: dict[str, asyncio.Task] = {}
        self.cleanup_error = False
        self._authority_tasks: dict[str, asyncio.Task] = {}
        self._authority_read_status: dict[str, str] = {}
        self._authority_fail_notified: set[str] = set()

    async def start(self, *, background: bool = True) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(
                lambda sync: VoiceSessionRow.metadata.create_all(
                    sync,
                    tables=[VoiceSessionRow.__table__, VoiceEventRow.__table__],
                )
            )
        await self.sweep()
        if background:
            self._maintenance_task = asyncio.create_task(self._maintenance())

    async def close(self) -> None:
        for task in self._authority_tasks.values():
            task.cancel()
        await asyncio.gather(*self._authority_tasks.values(), return_exceptions=True)
        self._authority_tasks.clear()
        for task in self._deadline_tasks.values():
            task.cancel()
        await asyncio.gather(*self._deadline_tasks.values(), return_exceptions=True)
        self._deadline_tasks.clear()
        if self._maintenance_task:
            self._maintenance_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._maintenance_task
        await self.engine.dispose()

    @contextlib.asynccontextmanager
    async def transaction(self):
        async with self.sessions() as db:
            # SQLite has one writer; PostgreSQL locks the session row below.
            if self.engine.dialect.name == "sqlite":
                await db.execute(text("BEGIN IMMEDIATE"))
            else:
                await db.begin()
            try:
                yield db
                await db.commit()
            except BaseException:
                await db.rollback()
                raise

    async def row(self, db, session_id: str, user_id: str | None = None):
        row = await db.scalar(
            select(VoiceSessionRow)
            .where(
                VoiceSessionRow.id == session_id,
            )
            .with_for_update()
        )
        if row is None or (user_id is not None and row.user_id != user_id):
            fail("VOICE_SESSION_NOT_FOUND", "语音会话不存在。", 404)
        await self.annotate_mode(db, row)
        return row

    async def annotate_mode(self, db, row):
        first = await db.get(VoiceEventRow, (row.id, 1))
        row._interaction_mode = (
            first.payload.get("data", {}).get("interaction_mode", "preview") if first else "preview"
        )

        row._language = first.payload.get("data", {}).get("language", "auto") if first else "auto"

    def active(self, row) -> None:
        if self.clock() >= utc(row.expires_at) or row.ended_reason == "expired":
            fail("VOICE_EXPIRED", "本次语音通话已到期，请从“开始语音”新建会话。", 410)
        if row.status == VoiceStatus.ENDED:
            fail("VOICE_ENDED", "语音通话已经结束。", 410)

    def warning_lead_seconds(self, row) -> int:
        persisted_duration = (utc(row.expires_at) - utc(row.started_at)).total_seconds()
        return (LEGACY_WARNING_LEAD_SECONDS if persisted_duration > CALL_SECONDS
                else WARNING_LEAD_SECONDS)

    def warning_at(self, row) -> datetime:
        return utc(row.expires_at) - timedelta(seconds=self.warning_lead_seconds(row))

    def view(self, row) -> VoiceSessionResponse:
        remaining = max(0, math.ceil((utc(row.expires_at) - self.clock()).total_seconds()))
        return VoiceSessionResponse(
            id=row.id,
            user_id=row.user_id,
            room=row.room,
            status=row.status if remaining else VoiceStatus.ENDED,
            started_at=utc(row.started_at),
            expires_at=utc(row.expires_at),
            warning_at=self.warning_at(row),
            remaining_seconds=remaining,
            task_id=row.task_id,
            chat_session_id=row.chat_session_id,
            event_cursor=row.event_cursor,
            ended_reason=row.ended_reason if remaining else "expired",
            interaction_mode=getattr(row, "_interaction_mode", "preview"),
            language=getattr(row, "_language", "auto"),
        )

    async def emit(self, db, row, kind: str, *, event_id: str | None = None, **values):
        event_id = event_id or f"VE-{uuid4().hex}"
        previous = await db.scalar(
            select(VoiceEventRow).where(
                VoiceEventRow.session_id == row.id,
                VoiceEventRow.event_id == event_id,
            )
        )
        if previous:
            return previous
        row.event_cursor += 1
        event = VoiceEvent(
            event_id=event_id,
            voice_session_id=row.id,
            cursor=row.event_cursor,
            task_id=row.task_id,
            status_seq=row.event_cursor,
            occurred_at=self.clock(),
            kind=kind,
            **values,
        )
        record = VoiceEventRow(
            session_id=row.id,
            cursor=row.event_cursor,
            event_id=event_id,
            payload=event.model_dump(mode="json"),
            consumed=0,
        )
        db.add(record)
        await db.flush()
        return record

    async def create(self, user_id: str, key: str, interaction_mode: str = "preview", language: str = "auto"):
        if not key.strip() or len(key) > 128:
            fail("REQUEST_VALIDATION_ERROR", "需要有效 Idempotency-Key。", 422)
        async with self.transaction() as db:
            existing = await db.scalar(
                select(VoiceSessionRow)
                .where(
                    VoiceSessionRow.user_id == user_id,
                    VoiceSessionRow.idempotency_key == key,
                )
                .with_for_update()
            )
            if existing:
                await self.annotate_mode(db, existing)
                if existing._interaction_mode != interaction_mode or existing._language != language:
                    fail("VOICE_IDEMPOTENCY_CONFLICT", "同一开始请求不能改变交谈模式。", 409)
                return self.view(existing)
            now = self.clock()
            row = VoiceSessionRow(
                id=f"VS-{uuid4().hex}",
                room=f"vefin-{uuid4().hex}",
                user_id=user_id,
                idempotency_key=key,
                status=VoiceStatus.CONNECTING,
                started_at=now,
                expires_at=now + timedelta(seconds=CALL_SECONDS),
                event_cursor=0,
                warned=0,
            )
            db.add(row)
            await db.flush()
            row._interaction_mode = interaction_mode
            row._language = language
            await self.emit(
                db,
                row,
                "session_created",
                data={"status": row.status, "interaction_mode": interaction_mode, "language": language},
            )
            if self._maintenance_task:
                self.schedule_deadline(row)
            return self.view(row)

    def schedule_deadline(self, row):
        if row.id in self._deadline_tasks:
            return

        async def expire():
            delay = max(0, (utc(row.expires_at) - self.clock()).total_seconds())
            await asyncio.sleep(delay)
            await self.end(row.id, reason="expired")

        self._deadline_tasks[row.id] = asyncio.create_task(expire())

    async def get(self, session_id: str, user_id: str):
        async with self.transaction() as db:
            return self.view(await self.row(db, session_id, user_id))

    async def bind(self, session_id: str, user_id: str, task_id: str, chat_id: str | None):
        # Authorizer must verify ownership; the unowned legacy Task schema is not proof.
        await self.app.state.voice_task_authorizer(user_id, task_id)
        if not getattr(self.app.state, "research_task_service", None):
            fail("VOICE_BUSINESS_PORT_UNAVAILABLE", "Research task binding is not installed in this module snapshot.", 503)
        task = await self.app.state.research_task_service.get_research_task(task_id)
        if task is None:
            fail("RESEARCH_TASK_NOT_FOUND", "研究任务不存在。", 404)
        if chat_id:
            try:
                from src.domain.services.research_chat_service import ChatSessionNotFound
            except ModuleNotFoundError:
                fail("VOICE_BUSINESS_PORT_UNAVAILABLE", "Research chat binding is not installed.", 503)

            try:
                chat = await self.app.state.research_chat_service.get_session(chat_id)
            except ChatSessionNotFound:
                fail("CHAT_SESSION_NOT_FOUND", "Chat 会话不存在。", 404)
            if chat.session.research_task_id != task_id:
                fail("VOICE_BINDING_MISMATCH", "Chat 不属于已授权任务。")
        async with self.transaction() as db:
            row = await self.row(db, session_id, user_id)
            self.active(row)
            if row.task_id and (
                row.task_id != task_id or row.chat_session_id not in {None, chat_id}
            ):
                fail("VOICE_ALREADY_BOUND", "同一语音会话不能切换研究任务或 Chat。")
            if row.task_id == task_id and row.chat_session_id == chat_id:
                return self.view(row)
            row.task_id, row.chat_session_id = task_id, chat_id
            await self.emit(db, row, "bound", data={"chat_session_id": chat_id})
            return self.view(row)

    async def credentials(self, session_id: str, user_id: str):
        async with self.transaction() as db:
            row = await self.row(db, session_id, user_id)
            self.active(row)
            if row.task_id:
                await self.app.state.voice_task_authorizer(user_id, row.task_id)
            if not await self.media.healthy():
                fail("VOICE_MEDIA_UNAVAILABLE", "媒体服务暂不可用。", 503, retryable=True)
            identity = f"user:{row.id}"
            expiry = min(utc(row.expires_at), self.clock() + timedelta(seconds=60))
            token = self.media.token(row.room, identity, expiry)
            row.status = VoiceStatus.RECONNECTING
            await self.emit(db, row, "credentials_issued", data={"status": row.status})
            return dict(
                session=self.view(row),
                token=token,
                url=self.media.public_url,
                token_expires_at=expiry,
                participant_identity=identity,
            )

    async def end(self, session_id: str, user_id: str | None = None, *, reason="user_ended", lease_id: str | None = None):
        async with self.transaction() as db:
            row = await self.row(db, session_id, user_id)
            if lease_id is not None:
                self.fence(row, lease_id)
            if row.status != VoiceStatus.ENDED:
                row.status, row.ended_reason = VoiceStatus.ENDED, reason
                row.lease_id, row.lease_until = None, None
                await self.emit(db, row, "ended", reason=reason, data={"status": row.status})
            self.cancel_authority_read(session_id)
            result, room = self.view(row), row.room
        try:
            await self.media.delete_room(room)
        except Exception:
            self.cleanup_error = True
            logger.warning("voice_room_cleanup_retry session=%s", session_id)
        return result

    async def events(self, session_id: str, user_id: str, after: int, limit: int):
        async with self.transaction() as db:
            row = await self.row(db, session_id, user_id)
            if after > row.event_cursor:
                fail("VOICE_CURSOR_INVALID", "事件游标超出会话范围。", 422)
            events = (
                await db.scalars(
                    select(VoiceEventRow)
                    .where(
                        VoiceEventRow.session_id == session_id,
                        VoiceEventRow.cursor > after,
                    )
                    .order_by(VoiceEventRow.cursor)
                    .limit(limit + 1)
                )
            ).all()
            payloads = [VoiceEvent.model_validate(e.payload) for e in events[:limit]]
            return dict(
                events=payloads,
                next_cursor=payloads[-1].cursor if payloads else after,
                has_more=len(events) > limit,
                session=self.view(row),
            )

    async def candidates(self):
        async with self.sessions() as db:
            rows = (
                await db.scalars(
                    select(VoiceSessionRow).where(
                        VoiceSessionRow.status != VoiceStatus.ENDED,
                        VoiceSessionRow.expires_at > self.clock(),
                    )
                )
            ).all()
            for row in rows:
                await self.annotate_mode(db, row)
            return [self.view(row) for row in rows]

    def fence(self, row, lease_id: str):
        self.active(row)
        if row.lease_id != lease_id or not row.lease_until or utc(row.lease_until) <= self.clock():
            fail("VOICE_LEASE_LOST", "Worker 租约已失效。", 409)

    async def claim(self, session_id: str):
        async with self.transaction() as db:
            row = await self.row(db, session_id)
            self.active(row)
            if row.lease_until and utc(row.lease_until) > self.clock():
                fail("VOICE_WORKER_BUSY", "该会话已由 Worker 接管。")
            self.cancel_authority_read(session_id)
            row.lease_id = uuid4().hex
            row.lease_until = self.clock() + timedelta(seconds=LEASE_SECONDS)
            previous = (
                await db.scalars(
                    select(VoiceEventRow)
                    .where(VoiceEventRow.session_id == session_id)
                    .order_by(VoiceEventRow.cursor)
                )
            ).all()
            playback_progress = {}
            unfinished = {}
            for entry in previous:
                data = entry.payload.get("data", {})
                turn_id = data.get("turn_id")
                if data.get("delivery_state") and data.get("response_id"):
                    playback_progress[data["response_id"]] = data
                if entry.payload["kind"] == "turn_result" and turn_id:
                    if data.get("phase") == "queued":
                        unfinished[turn_id] = data
                    else:
                        unfinished.pop(turn_id, None)
            for turn_id, data in unfinished.items():
                await self.emit(
                    db,
                    row,
                    "turn_result",
                    event_id=f"recovered:{turn_id}",
                    text="Worker已恢复；上一轮未完成识别，已终止并保留失败记录，请重新说一次。",
                    data={**data, "phase": "failed", "error_code": "WORKER_RESTART_ABORTED"},
                )
            for response_id, progress in list(playback_progress.items()):
                if progress["delivery_state"] == "PENDING" or (
                    progress["delivery_state"] == "PARTIAL" and not progress.get("delivery_termination")
                ):
                    recovered = {**progress, "phase": "failed", "error_code": "WORKER_RESTART_ABORTED",
                                 "delivery_state": "PARTIAL" if progress.get("published_segments") or progress.get("started_segments") else "FAILED",
                                 "delivery_termination": "worker_lost"}
                    playback_progress[response_id] = recovered
                    await self.emit(db, row, "turn_result",
                        event_id=f"playback-recovered:{response_id}:{row.lease_id}",
                        text="Worker已恢复；上轮音频未完整交付，已完成的段落不会自动重播。", data=recovered)
            # Retire the previous lease's RTC agent before replacement enters a 2-person room.
            # Holding this transaction also serializes competing claims. Never remove the user.
            await self.media.retire_previous_agents(row.room, f"agent:{row.lease_id}")
            self.active(row)
            row.lease_until = self.clock() + timedelta(seconds=LEASE_SECONDS)
            await self.emit(db, row, "worker_attached", data={"status": "connecting"})
            return dict(
                session=self.view(row),
                lease_id=row.lease_id,
                playback_progress=playback_progress,
                token=self.media.token(row.room, f"agent:{row.lease_id}", utc(row.expires_at)),
            )

    async def release(self, session_id: str, lease_id: str):
        async with self.transaction() as db:
            row = await self.row(db, session_id)
            self.fence(row, lease_id)
            self.cancel_authority_read(session_id)
            row.lease_id, row.lease_until = None, None
            row.status = VoiceStatus.RECONNECTING
            await self.emit(db, row, "worker_detached", data={"status": row.status})
            return {"released": True, "session": self.view(row)}

    async def accept_source(self, session_id: str, lease_id: str, receipt: AuthorityReceipt):
        async with self.transaction() as db:
            row = await self.row(db, session_id)
            self.fence(row, lease_id)
            occurred = utc(receipt.occurred_at)
            if (
                receipt.task_id != row.task_id
                or row.source_version == receipt.version
                or (row.source_time and occurred < utc(row.source_time))
                or occurred > self.clock() + timedelta(seconds=5)
            ):
                return
            if receipt.run_id and row.source_time and occurred == utc(row.source_time):
                previous = await db.scalar(
                    select(VoiceEventRow).where(
                        VoiceEventRow.session_id == session_id,
                        VoiceEventRow.event_id == f"authority:{row.source_version}",
                    )
                )
                if previous and receipt.source_event_id < (
                    previous.payload.get("source_event_id") or ""
                ):
                    return
            previous_source = await db.scalar(select(VoiceEventRow).where(
                VoiceEventRow.session_id == session_id,
                VoiceEventRow.event_id == f"authority:{row.source_version}",
            )) if row.source_version else None
            progress_key = hashlib.sha256(
                f"{receipt.task_id}:{receipt.run_id}:{receipt.reason}:{receipt.text}".encode()
            ).hexdigest()
            repeated_progress = bool(
                receipt.reason == "progress" and previous_source
                and previous_source.payload.get("reason") == "progress"
                and previous_source.payload.get("run_id") == receipt.run_id
                and previous_source.payload.get("data", {}).get("authority_text",
                    previous_source.payload.get("text")) == receipt.text
            )
            existing_snapshot = previous_source is None and occurred < utc(row.started_at)
            # Only current authority is offered; evidence capture events with unchanged
            # progress are retained as observations, without repeating the same speech.
            row.source_version, row.source_time = receipt.version, occurred
            await self.emit(
                db,
                row,
                "authority_observed" if repeated_progress else "announcement",
                event_id=f"authority:{receipt.version}",
                run_id=receipt.run_id,
                reason=receipt.reason,
                text=("当前查询到的已有研究状态是：" + receipt.text)
                    if existing_snapshot else receipt.text,
                source_event_id=receipt.source_event_id,
                source_version=receipt.version,
                data={"source_occurred_at": occurred.isoformat(),
                      "authority_text": receipt.text,
                      "progress_semantic_version":
                          progress_key if receipt.reason == "progress" else None,
                      "initial_snapshot": previous_source is None,
                      "notice_mode": "existing_state_snapshot"
                      if existing_snapshot
                      else "new_status_observation"},
            )
            if repeated_progress:
                observed = await db.scalar(select(VoiceEventRow).where(
                    VoiceEventRow.session_id == session_id,
                    VoiceEventRow.event_id == f"authority:{receipt.version}",
                ))
                observed.consumed = 1

    async def poll(self, session_id: str, lease_id: str):
        async with self.transaction() as db:
            row = await self.row(db, session_id)
            self.fence(row, lease_id)
            row.lease_until = self.clock() + timedelta(seconds=LEASE_SECONDS)
            task_id, user_id = row.task_id, row.user_id
        if task_id:
            await self.app.state.voice_task_authorizer(user_id, task_id)
            self.schedule_authority_read(session_id, lease_id, task_id)
        async with self.transaction() as db:
            row = await self.row(db, session_id)
            self.fence(row, lease_id)
            events = (
                await db.scalars(
                    select(VoiceEventRow)
                    .where(
                        VoiceEventRow.session_id == session_id,
                        VoiceEventRow.consumed == 0,
                    )
                    .order_by(VoiceEventRow.cursor)
                )
            ).all()
            pending = [
                e.payload
                for e in events
                if e.payload["kind"]
                in {
                    "announcement",
                    "duration_warning",
                }
            ]
            observed = await db.scalar(select(VoiceEventRow).where(
                VoiceEventRow.session_id == session_id,
                VoiceEventRow.event_id == f"authority:{row.source_version}",
            )) if row.source_version else None
            authority = {"run_id": observed.payload.get("run_id"),
                         "source_version": row.source_version,
                         "source_occurred_at": utc(row.source_time).isoformat(),
                         "reason": observed.payload.get("reason")} if observed else None
            return dict(session=self.view(row), announcements=pending,
                        authority_observation=authority,
                        authority_refresh=self._authority_read_status.get(session_id, "not_bound"))

    def cancel_authority_read(self, session_id: str):
        task = self._authority_tasks.pop(session_id, None)
        if task:
            task.cancel()
        self._authority_read_status.pop(session_id, None)
        self._authority_fail_notified.discard(session_id)

    def schedule_authority_read(self, session_id: str, lease_id: str, task_id: str):
        existing = self._authority_tasks.get(session_id)
        if existing and not existing.done():
            return

        async def refresh():
            started = time.monotonic()
            self._authority_read_status[session_id] = "pending"
            try:
                # Slow read-only business projection cannot hold up lease renewal.
                # The existing authority reader/policy remains unchanged.
                async with asyncio.timeout(3):
                    receipt = await read_receipt(self.app, task_id)
                if receipt:
                    await self.accept_source(session_id, lease_id, receipt)
                self._authority_read_status[session_id] = "ready"
                self._authority_fail_notified.discard(session_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._authority_read_status[session_id] = "unavailable"
                if session_id not in self._authority_fail_notified:
                    with contextlib.suppress(ApplicationError):
                        async with self.transaction() as db:
                            row = await self.row(db, session_id)
                            self.fence(row, lease_id)
                            await self.emit(db, row, "status_notice",
                                text="研究进度暂时无法读取，请稍后重试，通话仍可继续。",
                                data={"error_code": "VOICE_AUTHORITY_UNAVAILABLE"})
                            self._authority_fail_notified.add(session_id)
                logger.warning("voice_authority_read_failed session=%s type=%s elapsed_ms=%.1f",
                               session_id, type(exc).__name__,
                               (time.monotonic() - started) * 1000)
            finally:
                if self._authority_tasks.get(session_id) is asyncio.current_task():
                    self._authority_tasks.pop(session_id, None)

        self._authority_tasks[session_id] = asyncio.create_task(refresh())

    async def consume(self, session_id: str, lease_id: str, event_id: str):
        async with self.transaction() as db:
            row = await self.row(db, session_id)
            self.fence(row, lease_id)
            event = await db.scalar(
                select(VoiceEventRow).where(
                    VoiceEventRow.session_id == session_id,
                    VoiceEventRow.event_id == event_id,
                )
            )
            if event is None or event.consumed:
                return {"speak": False}
            payload = event.payload
            current = payload.get("source_version") in {None, row.source_version}
            if not current and payload.get("reason") == "progress":
                latest = await db.scalar(select(VoiceEventRow).where(
                    VoiceEventRow.session_id == session_id,
                    VoiceEventRow.event_id == f"authority:{row.source_version}",
                ))
                current = bool(latest and latest.payload.get("reason") == "progress"
                               and latest.payload.get("run_id") == payload.get("run_id")
                               and latest.payload.get("data", {}).get("authority_text",
                                   latest.payload.get("text")) == payload.get("data", {}).get(
                                       "authority_text", payload.get("text")))
            age = (self.clock() - datetime.fromisoformat(payload["occurred_at"])).total_seconds()
            event.consumed = 1  # Durable at-most-once, even across a mid-playback crash.
            return {
                "speak": current and age <= 120,
                "event": payload if current and age <= 120 else None,
            }

    async def receipt(self, session_id: str, payload):
        async with self.transaction() as db:
            row = await self.row(db, session_id)
            self.fence(row, payload.lease_id)
            allowed = {
                VoiceStatus.LISTENING,
                VoiceStatus.THINKING,
                VoiceStatus.WAITING_RUN,
                VoiceStatus.SPEAKING,
                VoiceStatus.RECONNECTING,
                VoiceStatus.ERROR,
            }
            if payload.status in allowed:
                row.status = payload.status
            await self.emit(
                db,
                row,
                payload.kind,
                event_id=f"worker:{payload.receipt_id}",
                text=payload.text,
                data={
                    "status": row.status,
                    "requires_explicit_send": row._interaction_mode == "preview",
                    **(
                        payload.metadata.model_dump(mode="json", exclude_none=True)
                        if payload.metadata
                        else {}
                    ),
                },
            )
            return self.view(row)

    async def sweep(self, *, only_session_id: str | None = None):
        now = self.clock()
        async with self.transaction() as db:
            query = select(VoiceSessionRow)
            if only_session_id:
                query = query.where(VoiceSessionRow.id == only_session_id)
            rows = (await db.scalars(query.with_for_update())).all()
            cleanup = []
            for row in rows:
                if row.status != VoiceStatus.ENDED:
                    if self._maintenance_task:
                        self.schedule_deadline(row)
                    if now >= utc(row.expires_at):
                        self.cancel_authority_read(row.id)
                        row.status, row.ended_reason = VoiceStatus.ENDED, "expired"
                        row.lease_id, row.lease_until = None, None
                        await self.emit(
                            db, row, "ended", reason="expired", data={"status": "ended"}
                        )
                    elif not row.warned and now >= self.warning_at(row):
                        row.warned = 1
                        warning_minutes = self.warning_lead_seconds(row) // 60
                        await self.emit(
                            db,
                            row,
                            "duration_warning",
                            reason="duration_limit",
                            text=f"本次语音通话还剩约{warning_minutes}分钟，研究任务不会因挂断而停止。",
                        )
                    elif row.lease_until and utc(row.lease_until) <= now:
                        if row.status != VoiceStatus.RECONNECTING:
                            row.status = VoiceStatus.RECONNECTING
                            await self.emit(db, row, "worker_lost", data={"status": row.status})
                # Retry terminal cleanup after restarts. Also catches server-refreshed RTC tokens.
                if row.status == VoiceStatus.ENDED:
                    cleanup.append((row.id, row.room))
        failed = False
        existing_rooms = await self.media.room_names() if cleanup else set()
        for session_id, room in cleanup:
            if room not in existing_rooms:
                continue
            try:
                await self.media.delete_room(room)
            except Exception:
                failed = True
                logger.warning("voice_room_cleanup_retry session=%s", session_id)
        self.cleanup_error = failed

    async def _maintenance(self):
        while True:
            try:
                await self.sweep()
            except Exception:
                self.cleanup_error = True
                logger.warning("voice_maintenance_retry")
            await asyncio.sleep(1)
