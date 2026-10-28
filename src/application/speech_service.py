"""Audio → text only. This boundary has no research or conversation dependencies."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_AUDIO_SECONDS = 120
AUDIO_MEDIA_TYPES = frozenset({
    "audio/webm", "audio/mp4", "audio/ogg", "audio/wav", "audio/x-wav",
    "audio/mpeg", "audio/aac", "audio/x-m4a",
})


class SpeechError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class AudioInput:
    content: bytes
    media_type: str
    language: str | None = None
    deadline_at: float | None = None


class SpeechRecognizer(Protocol):
    """Implementations must return literal speech text, never intent or a plan."""

    @property
    def provider_name(self) -> str: ...

    async def recognize(self, audio: AudioInput) -> str: ...


@dataclass(frozen=True)
class SpeechTranscript:
    text: str
    provider: str
    raw_text: str | None = None
    model: str = "UNKNOWN"
    request_id: str = "UNKNOWN"
    metadata: dict = field(default_factory=dict)


class SpeechService:
    def __init__(self, recognizer: SpeechRecognizer) -> None:
        self.recognizer = recognizer

    async def transcribe(self, audio: AudioInput) -> SpeechTranscript:
        if not audio.content:
            raise SpeechError("AUDIO_EMPTY", "录音为空，请重新录音。")
        if len(audio.content) > MAX_AUDIO_BYTES:
            raise SpeechError("AUDIO_TOO_LARGE", "录音超过 10 MB，请缩短录音。", 413)
        media_type = audio.media_type.split(";", 1)[0].strip().lower()
        if media_type not in AUDIO_MEDIA_TYPES:
            raise SpeechError("AUDIO_FORMAT_UNSUPPORTED", "不支持此音频格式。", 415)
        try:
            async with asyncio.timeout_at(audio.deadline_at):
                text = await self.recognizer.recognize(AudioInput(
                    audio.content, media_type, audio.language, audio.deadline_at))
        except SpeechError:
            raise
        except TimeoutError:
            raise
        except Exception as exc:
            raise SpeechError("ASR_UNAVAILABLE", "语音识别服务暂不可用，请重试。", 503) from exc
        if not isinstance(text, str):
            raise SpeechError("ASR_INVALID_RESPONSE", "识别服务返回了无效文本。", 502)
        raw_text = text
        text = text.strip()
        if not text:
            raise SpeechError("NO_SPEECH_DETECTED", "没有识别到语音，请重新录音。")
        observation = getattr(self.recognizer, "observation", lambda: None)() or {}
        return SpeechTranscript(text=text, provider=self.recognizer.provider_name,
            raw_text=raw_text, model=observation.get("requested_model", observation.get("model", "UNKNOWN")),
            request_id=observation.get("request_id") or "UNKNOWN", metadata=observation)


async def transcribe_after_warming(
    service: SpeechService,
    audio: AudioInput,
    *,
    deadline_at: float,
    on_warming: Callable[[int, float, dict | None], None] | None = None,
    max_warming_retries: int = 12,
) -> SpeechTranscript:
    """Retry only a provider that explicitly rejected a request before inference.

    This does not extend the caller's ASR deadline, retry an accepted/failed
    inference, or deliver a prior attempt's result. Every retry has a new HTTP
    request ID supplied by the recognizer; the callback records rejected IDs.
    """
    warming_rejections = 0
    while True:
        try:
            return await service.transcribe(audio)
        except SpeechError as exc:
            if exc.code != "ASR_PROVIDER_WARMING":
                raise
            remaining = deadline_at - time.monotonic()
            if warming_rejections >= max_warming_retries or remaining <= 1.5:
                raise
            warming_rejections += 1
            observation = getattr(service.recognizer, "observation", lambda: None)()
            if on_warming:
                on_warming(warming_rejections, remaining, observation)
            await asyncio.sleep(min(0.4, remaining - 1.5))
