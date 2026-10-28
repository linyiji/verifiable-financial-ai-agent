"""Pluggable ASR adapters. Audio is transient and is never stored in the database."""

from __future__ import annotations

import asyncio
import contextvars
import io
import threading
import time
from uuid import uuid4

import httpx

from src.application.speech_service import (
    MAX_AUDIO_SECONDS,
    AudioInput,
    SpeechError,
    SpeechRecognizer,
)
from src.infrastructure.config.settings import get_settings


class FasterWhisperRecognizer:
    provider_name = "faster-whisper"

    def __init__(self, *, model: str = "base", language: str | None = None) -> None:
        self.model_name = model
        self.language = language
        self._model = None
        self._lock = threading.Lock()

    async def recognize(self, audio: AudioInput) -> str:
        # Decoding, lazy model loading and inference must not block FastAPI's event loop.
        return await asyncio.to_thread(self._recognize, audio)

    def _recognize(self, audio: AudioInput) -> str:
        try:
            import av
            import numpy as np
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise SpeechError(
                "ASR_NOT_CONFIGURED",
                "本地语音识别依赖尚未安装。",
                503,
            ) from exc
        with self._lock:
            # Decode at a fixed rate with a duration bound, including for files whose
            # container omits duration. Stop before inference on invalid/long audio.
            chunks = []
            samples = 0
            try:
                with av.open(io.BytesIO(audio.content)) as container:
                    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
                    for frame in container.decode(audio=0):
                        for converted in resampler.resample(frame):
                            samples += converted.samples
                            if samples > MAX_AUDIO_SECONDS * 16000:
                                raise SpeechError("AUDIO_TOO_LONG", "录音最长为 120 秒。")
                            chunks.append(converted.to_ndarray().flatten())
                    for converted in resampler.resample(None):
                        samples += converted.samples
                        chunks.append(converted.to_ndarray().flatten())
            except SpeechError:
                raise
            except (av.FFmpegError, ValueError, IndexError) as exc:
                raise SpeechError("AUDIO_INVALID", "音频无法解码，请重新录音。") from exc
            if samples > MAX_AUDIO_SECONDS * 16000:
                raise SpeechError("AUDIO_TOO_LONG", "录音最长为 120 秒。")
            if not chunks:
                return ""
            waveform = np.concatenate(chunks).astype(np.float32) / 32768.0
            if self._model is None:
                self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
            segments, _ = self._model.transcribe(
                waveform,
                language=self.language,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            return "".join(segment.text for segment in segments).strip()


class HttpSpeechRecognizer:
    """Configured transcription endpoint: multipart file+model → {text: str}."""

    provider_name = "http-asr"

    def __init__(self, *, url: str, model: str, api_key: str = "") -> None:
        self.url = url
        self.model = model
        self.api_key = api_key
        self._observation = contextvars.ContextVar("http_asr_observation", default=None)

    def observation(self):
        return self._observation.get()

    async def recognize(self, audio: AudioInput) -> str:
        if not self.url:
            raise SpeechError("ASR_NOT_CONFIGURED", "语音识别服务尚未配置。", 503)
        request_id = uuid4().hex
        self._observation.set({"request_id": request_id, "stage": "request_sent"})
        headers = {"X-Request-ID": request_id}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        extension = {
            "audio/mp4": "m4a",
            "audio/webm": "webm",
            "audio/ogg": "ogg",
            "audio/wav": "wav",
            "audio/x-wav": "wav",
            "audio/mpeg": "mp3",
            "audio/aac": "aac",
            "audio/x-m4a": "m4a",
        }[audio.media_type]
        started = time.monotonic_ns()
        try:
            from src.adapters.voice_call_budget import charge
            from urllib.parse import urlsplit
            charge("LOCAL_ASR" if urlsplit(self.url).hostname in {"127.0.0.1", "localhost", "host.docker.internal"} else "ASR", self.provider_name, self.model)
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post(
                    self.url,
                    headers=headers,
                    data={"model": self.model, **({"language":audio.language}
                        if audio.language and audio.language != 'auto' else {})},
                    files={"file": (f"recording.{extension}", audio.content, audio.media_type)},
                )
        except httpx.TimeoutException as exc:
            self._observation.set({"request_id": request_id, "stage": "transport",
                                   "error_class": "timeout"})
            raise SpeechError("ASR_TRANSPORT_TIMEOUT", "语音识别连接超时，请稍后重说。", 503) from exc
        except httpx.RequestError as exc:
            self._observation.set({"request_id": request_id, "stage": "transport",
                                   "error_class": type(exc).__name__})
            raise SpeechError("ASR_TRANSPORT_ERROR", "语音识别连接失败，请稍后重说。", 503) from exc
        echoed_id = response.headers.get("x-request-id") or request_id
        observation = {"request_id": echoed_id,
                       "transport_total_ms": (time.monotonic_ns() - started) / 1e6,
                       "http_status": response.status_code, "model": self.model}
        if response.is_error:
            try:
                detail = response.json().get("detail")
            except (ValueError, AttributeError):
                detail = None
            known = {"INFERENCE_WARMING", "INFERENCE_BUSY", "INFERENCE_FAILED",
                     "ASR_TIMEOUT", "LOCAL_SPEECH_UNAUTHORIZED", "AUDIO_TOO_LARGE"}
            observation["provider_detail"] = detail if isinstance(detail, str) and detail in known else "UNCLASSIFIED"
            self._observation.set(observation)
            codes = {
                "INFERENCE_WARMING": "ASR_PROVIDER_WARMING",
                "INFERENCE_BUSY": "ASR_PROVIDER_BUSY",
                "INFERENCE_FAILED": "ASR_PROVIDER_INFERENCE_FAILED",
                "ASR_TIMEOUT": "ASR_PROVIDER_TIMEOUT",
                "LOCAL_SPEECH_UNAUTHORIZED": "ASR_PROVIDER_UNAUTHORIZED",
                "AUDIO_TOO_LARGE": "AUDIO_TOO_LARGE",
            }
            raise SpeechError(codes.get(detail, "ASR_UNAVAILABLE") if isinstance(detail, str) else "ASR_UNAVAILABLE",
                              "语音识别服务未完成本轮请求，请稍后重说。", response.status_code)
        try:
            body = response.json()
        except ValueError as exc:
            observation["provider_detail"] = "INVALID_JSON"
            self._observation.set(observation)
            raise SpeechError("ASR_INVALID_RESPONSE", "识别服务返回了无效文本。", 502) from exc
        if not isinstance(body, dict):
            observation["provider_detail"] = "INVALID_SHAPE"
            self._observation.set(observation)
            raise SpeechError("ASR_INVALID_RESPONSE", "识别服务返回了无效文本。", 502)
        observation.update(provider_timing=body.get("timing"),
                           decoder_language=body.get("decoder_language"))
        self._observation.set(observation)
        return body.get("text")


class MiMoSpeechRecognizer:
    provider_name = "mimo"

    def __init__(self):
        self._observation = contextvars.ContextVar("mimo_asr_observation", default=None)

    def observation(self):
        return self._observation.get()

    async def recognize(self, audio: AudioInput) -> str:
        import os, wave
        from src.application.voice_dispatcher import MiMoASR
        from src.adapters.voice_call_budget import charge
        # RTC supplies standard WAV; reject incompatible input before any call.
        if audio.media_type not in {"audio/wav", "audio/x-wav"}:
            raise SpeechError("ASR_CAPABILITY_UNSUPPORTED", "MiMo候選需要16kHz單聲道PCM WAV。", 415)
        with wave.open(io.BytesIO(audio.content), "rb") as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
                raise SpeechError("ASR_CAPABILITY_UNSUPPORTED", "MiMo候選需要16kHz單聲道PCM WAV。", 415)
            pcm = wav.readframes(wav.getnframes())
        async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=5)) as client:
            adapter = MiMoASR(client, os.getenv("MIMO_API_KEY", ""))
            charge("ASR", "mimo", "mimo-v2.5-asr")
            try:
                text, metadata = await adapter.transcribe(pcm)
                self._observation.set(metadata)
                return text
            except asyncio.CancelledError:
                self._observation.set({"state": "CANCELLED"})
                raise
            except Exception as exc:
                self._observation.set({"state": "FAILED", "error_type": type(exc).__name__})
                raise SpeechError("ASR_UNAVAILABLE", "MiMo語音識別未完成。", 503) from exc


class UnavailableSpeechRecognizer:
    provider_name = "unavailable"

    async def recognize(self, audio: AudioInput) -> str:
        raise SpeechError("ASR_NOT_CONFIGURED", "语音识别服务尚未配置。", 503)


def configured_speech_recognizer() -> SpeechRecognizer:
    settings = get_settings().speech
    if settings.provider == "faster-whisper":
        return FasterWhisperRecognizer(
            model=settings.model,
            language=settings.language,
        )
    if settings.provider == "mimo":
        return MiMoSpeechRecognizer()
    if settings.provider == "http":
        return HttpSpeechRecognizer(
            url=settings.url,
            model=settings.model,
            api_key=settings.api_key.get_secret_value() if settings.api_key else "",
        )
    return UnavailableSpeechRecognizer()


def candidate_speech_recognizer(provider: str, configuration: dict, **options) -> SpeechRecognizer:
    """Explicit independently injected candidate; never changes the live profile.

    The caller reads its authorized private configuration. Business callers still
    receive exactly SpeechRecognizer and use the existing SpeechService contract.
    """
    from src.adapters.candidate_asr import (
        QwenASRConfig, QwenSpeechRecognizer, XfyunASRConfig, XfyunDialectRecognizer,
    )
    if provider == 'qwen':
        if configuration.get('provider') != 'dashscope':
            raise ValueError('QWEN_PROVIDER_CONFIGURATION_MISMATCH')
        return QwenSpeechRecognizer(QwenASRConfig(model=configuration['model'],
            region=configuration['region'],api_key=configuration['api_key']),**options)
    if provider == 'xfyun':
        if configuration.get('provider') != 'xfyun' or configuration.get('service') != 'dialect_asr':
            raise ValueError('XFYUN_PRODUCT_CONFIGURATION_MISMATCH')
        return XfyunDialectRecognizer(XfyunASRConfig(endpoint=configuration['endpoint'],
            app_id=configuration['app_id'],api_key=configuration['api_key'],
            api_secret=configuration['api_secret'],**configuration['parameters']),**options)
    raise ValueError('UNKNOWN_ASR_CANDIDATE')
