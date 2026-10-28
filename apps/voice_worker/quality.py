"""Literal ASR observations and opt-in, allowlisted test evidence.

The default decoder options are identical to the existing ASR adapter. Hints only
reach Whisper's decoder; neither the transcript nor research state is rewritten.
Test audio/text are stored only for explicitly listed local test sessions.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import os
import re
import threading
import time
import wave
from pathlib import Path
from uuid import uuid4

from src.adapters.speech import FasterWhisperRecognizer, configured_speech_recognizer
from src.infrastructure.config.settings import get_settings


class _ObservedModel:
    def __init__(self, model_name: str, prompt: str | None, hotwords: str | None):
        self.model_name, self.prompt, self.hotwords = model_name, prompt, hotwords
        self.delegate = None
        self.observation: dict = {}

    def transcribe(self, waveform, **options):
        from faster_whisper import WhisperModel

        if self.delegate is None:
            self.delegate = WhisperModel(self.model_name, device="cpu", compute_type="int8")
        if self.prompt:
            options["initial_prompt"] = self.prompt
        if self.hotwords:
            options["hotwords"] = self.hotwords
        segments, info = self.delegate.transcribe(waveform, **options)
        self.observation = {
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "duration_after_vad": info.duration_after_vad,
            "model": self.model_name,
            "device": "cpu",
            "compute_type": "int8",
            "options": options,
            "segments": [],
        }

        def observed_segments():
            for segment in segments:
                self.observation["segments"].append(
                    {
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment.text,
                        "avg_logprob": segment.avg_logprob,
                        "no_speech_prob": segment.no_speech_prob,
                    }
                )
                yield segment

        return observed_segments(), info


class WorkerWhisperRecognizer(FasterWhisperRecognizer):
    """Reuse the existing bounded decoder and return its exact literal text."""

    def __init__(self, *, model="base", language=None, prompt=None, hotwords=None):
        super().__init__(model=model, language=language)
        self._model = _ObservedModel(model, prompt, hotwords)
        self._capture_lock = threading.Lock()
        self._observation = contextvars.ContextVar("voice_asr_observation", default=None)

    async def prepare(self):
        # Load the configured decoder before accepting calls. No transcript is
        # invented, and no test phrase or business vocabulary reaches the model.
        def load():
            from faster_whisper import WhisperModel

            with self._capture_lock:
                if self._model.delegate is None:
                    self._model.delegate = WhisperModel(
                        self.model_name, device="cpu", compute_type="int8"
                    )

        await asyncio.to_thread(load)

    def _capture(self, audio):
        # Include metadata copying in the lock: concurrently connected calls must
        # never attach another user's language or transcript to their test record.
        with self._capture_lock:
            started = time.monotonic_ns()
            text = super()._recognize(audio)
            detail = json.loads(json.dumps(self._model.observation))
            detail["inference_ms"] = (time.monotonic_ns() - started) / 1e6
            return text, detail

    async def recognize(self, audio):
        text, detail = await asyncio.to_thread(self._capture, audio)
        self._observation.set(detail)
        return text

    def observation(self):
        return self._observation.get()


def worker_recognizer():
    settings = get_settings().speech
    if settings.provider != "faster-whisper":
        return configured_speech_recognizer()
    return WorkerWhisperRecognizer(
        model=settings.model,
        language=settings.language,
        prompt=os.getenv("VEFIN_VOICE_ASR_INITIAL_PROMPT") or None,
        hotwords=os.getenv("VEFIN_VOICE_ASR_HOTWORDS") or None,
    )


class TestTrace:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.connection_id = uuid4().hex
        self.directory = os.getenv("VEFIN_VOICE_TEST_TRACE_DIR")

    def _config(self):
        if not self.directory or not re.fullmatch(r"VS-[a-f0-9]{32}", self.session_id):
            return None
        try:
            config = json.loads((Path(self.directory) / "sessions.json").read_text())
            entry = config.get(self.session_id)
            if entry and entry.get("label") in {
                "AUTOMATED_AUDIO",
                "HUMAN_AUDIO_REPLAY",
                "HUMAN_PRODUCT",
            }:
                return entry
        except (OSError, ValueError, TypeError):
            pass
        return None

    def frozen_reply(self):
        """Existing local test allowlist only; never a remotely supplied playback path."""
        entry = self._config()
        if not entry or not entry.get("frozen_reply"):
            return None
        import hashlib
        root = Path(self.directory).resolve()
        path = (root / entry["frozen_reply"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("FROZEN_REPLY_PATH_INVALID")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != entry.get("frozen_reply_sha256"):
            raise ValueError("FROZEN_REPLY_HASH_MISMATCH")
        text = content.decode("utf-8")
        if not 1 <= len(text) <= 8000:
            raise ValueError("FROZEN_REPLY_LENGTH_INVALID")
        return text

    def node_profile(self):
        """Only an explicitly allowlisted operator file, never session payload."""
        entry=self._config();item=entry.get('node_profile') if entry else None
        if not item:return None
        import hashlib
        root=Path(self.directory).resolve();source=(root/item['file']).resolve()
        if not source.is_relative_to(root):raise ValueError('TEST_NODE_PROFILE_PATH_INVALID')
        raw=source.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('TEST_NODE_PROFILE_HASH_MISMATCH')
        profile=json.loads(raw)
        if profile.get('isolation')!='SELF_TEST_ONLY_NOT_PRODUCT_DEFAULT':raise ValueError('TEST_NODE_PROFILE_SCOPE_INVALID')
        return profile

    def restored_context(self):
        """Explicit operator-owned text context, never old audio or model output replay."""
        entry = self._config()
        item = entry.get('restored_context') if entry else None
        if not item:
            return []
        import hashlib
        root = Path(self.directory).resolve()
        path = (root / item['file']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('RESTORED_CONTEXT_PATH_INVALID')
        raw = path.read_bytes()
        if len(raw) > 40000 or hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('RESTORED_CONTEXT_HASH_INVALID')
        data = json.loads(raw)
        if data.get('version') != 'verified-context-seed-v1' or not re.fullmatch(r'VS-[a-f0-9]{32}', data.get('source_session_id', '')):
            raise ValueError('RESTORED_CONTEXT_SOURCE_INVALID')
        history = data['history']
        if not isinstance(history, list) or len(history) > 20:
            raise ValueError('RESTORED_CONTEXT_LENGTH_INVALID')
        for row in history:
            if (row.get('role') not in {'user', 'assistant'} or not isinstance(row.get('content'), str)
                    or not 1 <= len(row['content']) <= 4000
                    or row.get('restored_from_session') != data['source_session_id']
                    or row.get('source') != ('user_report' if row['role'] == 'user' else 'model_generated_unverified')):
                raise ValueError('RESTORED_CONTEXT_ROLE_OR_PROVENANCE_INVALID')
        return history

    def reused_tts(self, text, language):
        """Exact, explicitly allowlisted prior test audio; never a fallback/cache."""
        import hashlib
        entry = self._config()
        if not entry or not entry.get("frozen_reply"):
            return None
        item = entry.get("reused_tts", {}).get(hashlib.sha256(text.encode()).hexdigest())
        if not item:
            return None
        if language != "yue-HK" or item.get("provider") not in {"quickrouter","qwen_beijing"}:
            raise ValueError("REUSE_IDENTITY_MISMATCH")
        root = Path(self.directory).resolve()
        path = (root / item["file"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("REUSE_PATH_INVALID")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != item["sha256"]:
            raise ValueError("REUSE_AUDIO_HASH_MISMATCH")
        return {"payload": payload, "source_file": item["file"],
                "provider":item['provider'],"encoding":item.get('encoding','mp3'),
                "sample_rate":item.get('sample_rate')}

    def saved_asr_input(self):
        """Local operator-only replay of an already captured RTC boundary.

        This resumes the real ASR/answer/TTS methods, never supplies a transcript
        or a cached answer. It does not claim a new RTC-input acceptance.
        """
        entry = self._config()
        item = entry.get('resume_asr_from') if entry else None
        if not item: return None
        if entry.get('frozen_reply'): raise ValueError('REPLAY_SCOPE_CONFLICT')
        import hashlib
        import io
        root = Path(self.directory).resolve()
        path = (root/item['file']).resolve()
        if not path.is_relative_to(root): raise ValueError('REPLAY_PATH_INVALID')
        data = path.read_bytes()
        if len(data)>10*1024*1024 or hashlib.sha256(data).hexdigest()!=item['sha256']:
            raise ValueError('REPLAY_AUDIO_IDENTITY_INVALID')
        with wave.open(io.BytesIO(data)) as source:
            if (source.getnchannels(),source.getsampwidth(),source.getframerate())!=(1,2,16000):
                raise ValueError('REPLAY_AUDIO_FORMAT_INVALID')
        return {'audio':data, **item}

    def event(self, kind: str, **detail):
        config = self._config()
        if config is None:
            return
        directory = Path(self.directory) / "worker"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        record = {
            "session_id": self.session_id,
            "connection_id": self.connection_id,
            "label": config["label"],
            "phase": config.get("phase"),
            "kind": kind,
            "wall_ns": time.time_ns(),
            "monotonic_ns": time.monotonic_ns(),
            **getattr(self, "scope", {}),
            **detail,
        }
        path = directory / f"{self.session_id}.jsonl"
        with path.open("a") as output:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
        path.chmod(0o600)

    def audio(self, turn: int, content: bytes, *, track_sid: str | None = None):
        if self._config() is None:
            return
        directory = Path(self.directory) / "worker"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        sid = (
            track_sid if track_sid and re.fullmatch(r"[A-Za-z0-9_-]+", track_sid) else "unassigned"
        )
        path = directory / f"{self.session_id}-{self.connection_id}-{sid}-turn-{turn:02d}.wav"
        with path.open("xb") as output:
            output.write(content)
        path.chmod(0o600)
        self.event("input_audio_saved", turn=turn, track_sid=track_sid, file=path.name)

    def provider_audio(self, payload, *, encoding, **metadata):
        """Original vendor bytes for allowlisted tests only, before conversion."""
        if self._config() is None or encoding not in {"wav", "mp3", "pcm_s16le"}:
            return
        import hashlib
        directory = Path(self.directory) / "worker"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / f"{self.session_id}-{self.connection_id}-provider-{uuid4().hex}.{encoding}"
        # Create private from the first write, including truncated diagnostic audio.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(payload)
        self.event("provider_audio_saved", file=path.name, encoding=encoding,
                   bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(), **metadata)

    def output_audio(self, pcm, sample_rate, **metadata):
        if self._config() is None:
            return
        directory = Path(self.directory) / "worker"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / f"{self.session_id}-{self.connection_id}-output-{uuid4().hex}.wav"
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(sample_rate)
            audio.writeframes(pcm)
        path.chmod(0o600)
        self.event("output_pcm_saved", file=path.name, sample_rate=sample_rate, **metadata)
