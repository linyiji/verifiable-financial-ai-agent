"""Shared desktop/mobile continuous voice contract. No research mutation commands."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VoiceStatus(StrEnum):
    CONNECTING = "connecting"
    LISTENING = "listening"
    THINKING = "thinking"
    WAITING_RUN = "waiting_run"
    SPEAKING = "speaking"
    RECONNECTING = "reconnecting"
    ENDED = "ended"
    ERROR = "error"


class VoiceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VoiceErrorDetail(VoiceModel):
    code: str
    message: str
    details: dict
    request_id: str | None


class VoiceErrorEnvelope(VoiceModel):
    error: VoiceErrorDetail


VoiceLanguage = Literal["auto", "yue-HK"]


class VoiceProviderAvailability(VoiceModel):
    provider: Literal["quickrouter", "mimo", "unknown"]
    state: Literal["available", "unavailable", "unknown"]
    blocked: bool
    reason: str
    message: str
    checked_at: datetime | None = None


class CreateVoiceSession(VoiceModel):
    language: VoiceLanguage = "auto"
    # Entry creates an empty draft. Binding is a separate, authorized operation.
    interaction_mode: Literal["preview", "conversation"] = "preview"


class BindVoiceSession(VoiceModel):
    task_id: str = Field(min_length=1, max_length=256)
    chat_session_id: str | None = Field(default=None, min_length=1, max_length=256)


class VoiceSessionResponse(VoiceModel):
    language: VoiceLanguage = "auto"
    id: str
    user_id: str
    room: str
    status: VoiceStatus
    started_at: datetime
    expires_at: datetime
    warning_at: datetime
    remaining_seconds: int
    task_id: str | None
    chat_session_id: str | None
    event_cursor: int
    ended_reason: str | None
    interaction_mode: Literal["preview", "conversation"] = "preview"


class VoiceCredentials(VoiceModel):
    session: VoiceSessionResponse
    url: str
    token: str
    token_expires_at: datetime
    participant_identity: str


class VoiceEvent(VoiceModel):
    event_id: str
    voice_session_id: str
    cursor: int
    task_id: str | None
    run_id: str | None = None
    status_seq: int
    occurred_at: datetime
    kind: str
    reason: str | None = None
    text: str | None = None
    source_event_id: str | None = None
    source_version: str | None = None
    data: dict = Field(default_factory=dict)


class VoiceEventsResponse(VoiceModel):
    events: list[VoiceEvent]
    next_cursor: int
    has_more: bool
    session: VoiceSessionResponse


class WorkerClaim(VoiceModel):
    worker_id: str = Field(min_length=1, max_length=128)


class VoiceTurnMetadata(VoiceModel):
    turn_id: str = Field(min_length=1, max_length=160)
    connection_id: str = Field(min_length=1, max_length=64)
    track_sid: str = Field(min_length=1, max_length=64)
    turn: int = Field(ge=1)
    input_epoch: int = Field(ge=0)
    response_id: str | None = Field(default=None, max_length=64)
    phase: str | None = Field(default=None, max_length=64)
    error_code: str | None = Field(default=None, max_length=64)
    delivery_state: Literal["PENDING", "PARTIAL", "FAILED", "CANCELLED", "PUBLISHED"] | None = None
    delivery_termination: str | None = Field(default=None, max_length=32)
    failure_category: Literal["CANCELLED", "NO_WORDS", "GROUNDING_FAILED", "TIMEOUT",
        "SCHEMA_FAILED", "PROVIDER_REJECTED", "UPLOAD_FAILED", "CONNECTION_FAILED",
        "FORMAT_FAILED", "NODE_FAILED"] | None = None
    segment_count: int | None = Field(default=None, ge=1)
    published_segments: list[int] | None = None
    started_segments: list[int] | None = Field(default=None, max_length=256)
    published_pcm_samples_24000: dict[str, int] | None = None
    active_segment: int | None = Field(default=None, ge=0)
    text_sha256: str | None = Field(default=None, min_length=64, max_length=64)



class WorkerDialogue(VoiceModel):
    lease_id: str
    turn_id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=8000)
    metadata: VoiceTurnMetadata
    generate: bool = False


class WorkerReceipt(VoiceModel):
    lease_id: str
    kind: Literal["transcript", "status", "interruption", "adapter_error", "turn_result"]
    status: VoiceStatus | None = None
    text: str | None = Field(default=None, max_length=8000)
    receipt_id: str = Field(min_length=1, max_length=128)
    metadata: VoiceTurnMetadata | None = None


class WorkerPoll(VoiceModel):
    lease_id: str


class WorkerConsume(WorkerPoll):
    event_id: str
