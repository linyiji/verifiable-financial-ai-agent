"""Raw RTC + Silero VAD + existing ASR + configurable TTS, with fenced scheduling."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import marshal
import io
import logging
import os
import re
import signal
import time
import wave
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from livekit import rtc
from livekit.agents import vad
from livekit.plugins import silero

from apps.voice_worker.quality import TestTrace, worker_recognizer
from src.adapters.livekit_media import LiveKitMedia
from src.adapters.voice_output import VoiceOutput, voice_output_context
from src.application.speech_service import AudioInput, SpeechService, transcribe_after_warming
from src.application.voice_errors import voice_error_category

logger = logging.getLogger("vefin.voice_worker")


def call_detector(default, profile):
    """Optional operator-only endpointing, isolated to this test Call.

    Silero stream options share their detector's options, so don't mutate the
    shared detector. Load the already bundled VAD for the isolated override.
    This changes end-of-utterance detection, not any model/turn deadline.
    """
    seconds = (profile or {}).get("vad_min_silence_seconds")
    if seconds is None:
        return default
    if profile.get("isolation") != "SELF_TEST_ONLY_NOT_PRODUCT_DEFAULT" or not 0.65 <= seconds <= 1.2:
        raise ValueError("TEST_VAD_ENDPOINTING_UNSUPPORTED")
    return silero.VAD.load(min_silence_duration=seconds, max_buffered_speech=110)


class WorkerRequestError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class Call:
    def __init__(self, client: httpx.AsyncClient, claimed: dict, detector, asr):
        self.client, self.detector, self.asr = client, detector, asr
        self.session = claimed["session"]
        self.id, self.lease = self.session["id"], claimed["lease_id"]
        self.token = claimed["token"]
        self.room = rtc.Room()
        self.trace = TestTrace(self.id)
        candidate_profile=self.trace.node_profile()
        self.detector = call_detector(detector, candidate_profile)
        self.test_profile_active = bool(candidate_profile)
        self.reserve_answer_budget = (candidate_profile or {}).get("reserve_answer_budget", False)
        self.require_content_acceptance = (candidate_profile or {}).get("instruction_revision") == "procedure-provenance-v3-consultation-v1"
        self.turn_deadline_seconds = (candidate_profile or {}).get('turn_deadline_seconds', 120)
        self.accepted_turns = set()
        if candidate_profile:
            self.trace.event('execution_profile_frozen', profile_sha256=hashlib.sha256(
                json.dumps(candidate_profile, sort_keys=True).encode()).hexdigest(),
                profile=candidate_profile, prompt_revision=candidate_profile.get('instruction_revision'),
                immutable_model_versions='UNKNOWN')
        output_factory=VoiceOutput
        if candidate_profile:
            from src.adapters.voice_candidate_profile import candidate_node
            output_factory=lambda **kwargs:candidate_node(candidate_profile,'tts',**kwargs)
        self.output = output_factory(
            observer=lambda event: self.trace.event("tts_transport", **event),
            audio_observer=lambda payload, **details: self.trace.provider_audio(payload, **details),
            audio_reuse=lambda text, language: self.trace.reused_tts(text, language),
        )
        self.test_max_tts_segments = candidate_profile.get('max_TTS_segments') if candidate_profile else None
        if candidate_profile and candidate_profile.get('nodes', {}).get('asr'):
            self.asr = SpeechService(candidate_node(candidate_profile, 'asr',
                observer=lambda event: self.trace.event('candidate_asr', **event)))
        self.asr_warming_retries = 0 if candidate_profile else int(os.getenv('VEFIN_ASR_WARMING_RETRIES', '12'))
        self.source = None
        self.audio_tasks: set[asyncio.Task] = set()
        self.microphone_tasks: dict[str, asyncio.Task] = {}
        self.active_microphone_sid = None
        self.turn_track_sid = None
        self.speech_task = None
        self.turn_task = None
        self.user_speaking = False
        self.connected_once = False
        self.last_heartbeat = time.monotonic()
        self.trace.scope = {
            "task_id": self.session.get("task_id"),
            "chat_session_id": self.session.get("chat_session_id"),
        }
        self.turn_sequence = 0
        self.input_epoch = 0
        self.turn_lock = asyncio.Lock()
        self.pending_turns: dict[asyncio.Task, str] = {}
        self.response_tasks: set[asyncio.Task] = set()
        self.queue_capacity = 5  # One active inference + four waiting utterances.
        self.queue_wait_seconds = 6.0
        # The first utterance or one after a long idle gap may pay a cold
        # local-ASR cost. Keep ordinary consecutive turns under the frozen
        # hot-ASR ceiling and retain a bounded queue.
        self.inference_seconds = 6.0
        self.cold_inference_seconds = 12.0
        self.asr_cold_after_idle_seconds = 300.0
        self.last_asr_success_at = None
        self.playout_sid = None
        self.delivery_progress = claimed.get("playback_progress", {})
        self.frozen_replay_started = False
        self.saved_input_replay_started = False
        self.is_publishing_audio = False

    async def post(self, endpoint, **body):
        response = await self.client.post(
            f"/internal/voice/{self.id}/{endpoint}",
            json={"lease_id": self.lease, **body},
            timeout=10 if endpoint == "dialogue" else 8,
        )
        if response.is_error:
            try:
                code = response.json().get("error", {}).get("code", "VOICE_CONTROL_FAILED")
            except (ValueError, AttributeError):
                code = "VOICE_CONTROL_FAILED"
            raise WorkerRequestError(
                code if re.fullmatch(r"[A-Z0-9_]{1,64}", code) else "VOICE_CONTROL_FAILED"
            )
        return response.json()

    async def receipt(self, kind, *, text=None, status=None, metadata=None):
        return await self.post(
            "receipt",
            kind=kind,
            text=text,
            status=status,
            receipt_id=uuid4().hex,
            **({"metadata": metadata} if metadata else {}),
        )

    def alive(self):
        expires = datetime.fromisoformat(self.session["expires_at"])
        return (
            self.session["status"] != "ended"
            and datetime.now(UTC) < expires
            and time.monotonic() - self.last_heartbeat < 6
        )

    async def interrupt(self):
        self.trace.event(
            "interrupt_started",
            active_playout=bool(self.speech_task and not self.speech_task.done()),
        )
        logger.info(
            "user_speech_start session=%s active_playout=%s",
            self.id,
            bool(self.speech_task and not self.speech_task.done()),
        )
        for task in (*getattr(self, "response_tasks", ()), self.speech_task):
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        if self.source:
            self.source.clear_queue()
        self.trace.event("playout_queue_cleared")
        await self.receipt(
            "interruption",
            status="listening",
            metadata=self.turn_metadata(
                max(1, self.turn_sequence),
                self.active_microphone_sid,
                self.input_epoch,
            )
            if getattr(self, "active_microphone_sid", None)
            else None,
        )

    async def delivery_receipt(self, metadata, progress, *, phase="audio_progress", text=None):
        details = {**metadata, **progress, "phase": phase}
        # These are Worker publication receipts, not acknowledgements from a client speaker.
        self.trace.event("delivery_progress", **details)
        await self.receipt("turn_result", text=text,
                           status="error" if phase == "failed" else None, metadata=details)

    async def speak(self, text, *, reason, metadata=None, language=None, resume=False):
        if not self.alive() or self.user_speaking:
            return
        language = self.session.get("language", "auto") if language is None else language
        metadata = dict(metadata or self.turn_metadata(
            max(1, self.turn_sequence), self.active_microphone_sid or "no-microphone", self.input_epoch))
        digest = hashlib.sha256(text.encode()).hexdigest()
        metadata.setdefault("response_id", "VP-" + digest[:32])
        key = metadata["response_id"]
        parts = re.findall(r"[^。！？!?\n]+[。！？!?\n]?", text) or [text]
        segments = [part[i:i + 120] for part in parts for i in range(0, len(part), 120)]
        prior = self.delivery_progress.get(key)
        if prior and prior["text_sha256"] != digest:
            raise RuntimeError("PLAYBACK_TEXT_CONFLICT")
        if prior and set(prior.get('started_segments', [])) - set(prior['published_segments']):
            raise RuntimeError('PARTIAL_SEGMENT_REQUIRES_EXPLICIT_RESOLUTION')
        if prior and (prior["delivery_state"] == "PUBLISHED" or not resume):
            self.trace.event("playback_duplicate_suppressed", response_id=key)
            return
        progress = {"delivery_state": "PENDING", "segment_count": len(segments),
                    "published_segments": list(prior.get("published_segments", [])) if prior else [],
                    "text_sha256": digest}
        self.delivery_progress[key] = progress
        queued_at = time.monotonic()
        reservation = None
        await self.delivery_receipt(metadata, progress)
        try:
            from src.adapters.voice_call_budget import require_capacity
            require_capacity('TTS', len(segments) - len(progress['published_segments']))
            if getattr(self, 'reserve_answer_budget', False):
                from src.adapters.voice_call_budget import reserve
                reservation = reserve('TTS', len(segments) - len(progress['published_segments']))
            if getattr(self, 'test_max_tts_segments', None) is not None and len(segments) > self.test_max_tts_segments:
                self.trace.event('tts_segment_budget_exceeded', required=len(segments),
                                 available=self.test_max_tts_segments, response_id=key)
                raise RuntimeError('TTS_SEGMENT_BUDGET_EXCEEDED')
            begin = getattr(getattr(self, 'output', None), 'begin_response', None)
            if begin is not None:
                await begin()
            for index, segment in enumerate(segments):
                if index in progress["published_segments"]:
                    continue
                progress["active_segment"] = index
                if not self.alive() or self.user_speaking:
                    raise asyncio.CancelledError
                self.trace.event("tts_segment_planned", text=segment, text_length=len(segment),
                                 segment_index=index, planned_wait_ms=round((time.monotonic()-queued_at)*1000, 3),
                                 response_id=key)
                await self.receipt("status", status="thinking")
                await self.speak_segment(segment, reason, metadata, index, language=language)
                progress["published_segments"].append(index)
                progress["delivery_state"] = "PARTIAL"
                await self.delivery_receipt(metadata, progress)
            progress.pop("active_segment", None)
            progress["delivery_state"] = "PUBLISHED"
            await self.delivery_receipt(metadata, progress, phase="audio_complete")
            self.trace.event("playout_completed", reason=reason, **metadata)
            await self.receipt("status", status=("waiting_run" if self.session["task_id"] else "listening"))
        except BaseException as exc:
            self.is_publishing_audio = False
            progress["delivery_state"] = ("PARTIAL" if progress["published_segments"] or progress.get('started_segments') else
                                           "CANCELLED" if isinstance(exc, asyncio.CancelledError) else "FAILED")
            progress["delivery_termination"] = "cancelled" if isinstance(exc, asyncio.CancelledError) else "failed"
            progress['failure_category'] = voice_error_category(exc)
            message = (f"本轮只完成 {len(progress['published_segments'])}/{len(segments)} 段音频发布，剩余内容尚未交付。"
                       if progress["published_segments"] else "本轮音频未完整交付。")
            with contextlib.suppress(Exception):
                await asyncio.shield(self.delivery_receipt(metadata, progress, phase="failed", text=message))
            raise
        finally:
            if reservation is not None:
                from src.adapters.voice_call_budget import release
                release(reservation)
            # Same VoiceOutput contract for all providers. A response-scoped
            # socket ends here, never between its successfully ordered segments.
            finish = getattr(getattr(self, "output", None), "finish_response", None)
            if finish is not None:
                with contextlib.suppress(Exception):
                    await finish()

    async def speak_segment(self, text, reason, metadata, segment_index, *, language=None):
        metadata = {**metadata, "segment_index": segment_index}
        self.trace.event("tts_started", reason=reason, **metadata)
        token = voice_output_context.set(metadata)
        started = time.monotonic()
        policy = self.output.delivery_policy
        self.trace.event("tts_budget_selected", **policy, **metadata)
        state, saved = {}, bytearray()
        rate = resampler = None
        first_frame = True
        completed = False
        stream = self.output.stream(text, language=language, state=state)
        progress = self.delivery_progress[metadata["response_id"]]

        async def publish(frame):
            nonlocal first_frame
            if (not self.alive() or self.user_speaking
                    or metadata.get('input_epoch', self.input_epoch) != self.input_epoch):
                raise asyncio.CancelledError
            await self.source.capture_frame(frame)
            key = str(segment_index)
            counts = progress.setdefault("published_pcm_samples_24000", {})
            counts[key] = counts.get(key, 0) + frame.samples_per_channel
            if first_frame:
                first_frame = False
                progress.setdefault("started_segments", []).append(segment_index)
                progress['delivery_state'] = 'PARTIAL'
                self.trace.event("playout_first_frame", reason=reason, **metadata)
                await self.delivery_receipt({k:v for k,v in metadata.items() if k!='segment_index'}, progress)
                self.is_publishing_audio = True
                await self.receipt("status", status="speaking")

        try:
            # VoiceOutput owns synthesis/receive/decode deadlines. RTC playback
            # must not consume or extend that generation budget.
            async for pcm, sample_rate in stream:
                if not pcm or len(pcm) % 2 or sample_rate <= 0:
                    raise RuntimeError("TTS_INVALID_PCM")
                if rate is None:
                    rate = sample_rate
                    resampler = rtc.AudioResampler(rate, 24000, num_channels=1)
                    self.trace.event("first_valid_pcm", pcm_samples=len(pcm)//2,
                        sample_rate=rate, elapsed_ms=round((time.monotonic()-started)*1000,3),
                        first_pcm_target_met=(time.monotonic()-started)<=policy["first_pcm_target_seconds"], **metadata)
                if sample_rate != rate:
                    raise RuntimeError("TTS_PCM_RATE_CHANGED")
                saved.extend(pcm)
                if len(saved) > 24*1024*1024:
                    raise RuntimeError("TTS_PCM_LIMIT")
                for offset in range(0, len(pcm), rate//50*2):
                    part = pcm[offset:offset+rate//50*2]
                    for frame in resampler.push(rtc.AudioFrame(part, rate, 1, len(part)//2)):
                        await publish(frame)
            if resampler is None:
                raise RuntimeError("TTS_EMPTY_STREAM")
            for frame in resampler.flush():
                await publish(frame)
            self.trace.event("tts_completed", reason=reason, pcm_samples=len(saved)//2,
                provider_elapsed_ms=state.get("elapsed_ms"), provider_complete=state.get("provider_complete"),
                meaning="all decoded PCM consumed; supplier completion has its own transport timestamp", **metadata)
            await self.source.wait_for_playout()
            if not self.alive() or self.user_speaking:
                raise asyncio.CancelledError
            completed = True
            self.trace.event("segment_playout_completed", reason=reason, **metadata)
        except BaseException:
            self.source.clear_queue()
            self.trace.event("tts_segment_incomplete", published_samples=progress.get("published_pcm_samples_24000",{}).get(str(segment_index),0), **metadata)
            raise
        finally:
            await stream.aclose()
            if saved:
                self.trace.output_audio(bytes(saved), rate, reason=reason,
                    output_track_sid=self.playout_sid, complete=completed, **metadata)
            self.is_publishing_audio = False
            voice_output_context.reset(token)

    def turn_metadata(self, turn, track_sid, epoch, **extra):
        connection_id = self.trace.connection_id
        return {
            "turn_id": f"{connection_id}:{turn}",
            "connection_id": connection_id,
            "track_sid": track_sid,
            "turn": turn,
            "input_epoch": epoch or 0,
            **extra,
        }

    def accept_end_of_speech(self, track_sid):
        """A VAD input epoch can close only once, before assigning a new turn."""
        ended = self.__dict__.setdefault('ended_input_epochs', {})
        if ended.get(track_sid) == self.input_epoch:
            self.trace.event('duplicate_eos_suppressed', track_sid=track_sid, input_epoch=self.input_epoch)
            return False
        ended[track_sid] = self.input_epoch
        return True

    async def answer_turn(self, audio_bytes, turn, track_sid, input_epoch=None, queued_at=None):
        # One VAD/EOS execution per input instance, never a transcript/item cache.
        key = (track_sid, turn, input_epoch)
        accepted = self.__dict__.setdefault('accepted_turns', set())
        if key in accepted:
            self.trace.event('duplicate_turn_suppressed', **self.turn_metadata(turn, track_sid, input_epoch))
            return
        accepted.add(key)
        deadline_at = (queued_at or time.monotonic()) + getattr(self, 'turn_deadline_seconds', 120)
        remaining = getattr(self, "queue_wait_seconds", 6) - (
            time.monotonic() - queued_at if queued_at else 0
        )
        try:
            async with asyncio.timeout(max(0, remaining)):
                await self.turn_lock.acquire()
        except TimeoutError:
            metadata = self.turn_metadata(
                turn, track_sid, input_epoch, phase="failed", error_code="ASR_QUEUE_TIMEOUT"
            )
            self.trace.event("asr_queue_timeout", **metadata)
            if self.alive():
                await self.receipt(
                    "turn_result",
                    text="这句话等待识别超时，尚未转写，请稍后重说。",
                    status="error",
                    metadata=metadata,
                )
            return
        try:
            if self.alive():
                self.trace.event('turn_execution_started', deadline_at=deadline_at,
                    **self.turn_metadata(turn, track_sid, input_epoch))
                async with asyncio.timeout_at(deadline_at):
                    await self._answer_turn(audio_bytes, turn, track_sid, input_epoch)
        except TimeoutError:
            metadata = self.turn_metadata(turn, track_sid, input_epoch,
                phase='failed', error_code='VOICE_TURN_TIMEOUT')
            self.trace.event('turn_deadline_exceeded', **metadata)
            if self.alive():
                await self.receipt('turn_result', status='error', metadata=metadata,
                    text='本轮已到总截止，已交付进度保留，剩余内容未交付。')
        finally:
            self.turn_lock.release()
            self.trace.event('turn_execution_ended', **self.turn_metadata(turn, track_sid, input_epoch))

    async def _answer_turn(self, audio_bytes, turn, track_sid, input_epoch):
        metadata = self.turn_metadata(turn, track_sid, input_epoch)
        recorded_response_id = None
        try:
            if not self.user_speaking:
                await self.receipt("status", status="thinking")
            if not self.alive() or input_epoch != self.input_epoch:
                return
            self.trace.event("asr_started", **metadata)
            last_success = getattr(self, "last_asr_success_at", None)
            idle_seconds = time.monotonic() - last_success if last_success is not None else None
            cold = (turn == 1 or idle_seconds is None or idle_seconds >=
                    getattr(self, "asr_cold_after_idle_seconds", 300.0))
            deadline = (getattr(self, "cold_inference_seconds", getattr(self, "inference_seconds", 5))
                        if cold else getattr(self, "inference_seconds", 5))
            self.trace.event("asr_budget_selected", deadline_seconds=deadline,
                             cold=cold, idle_seconds=idle_seconds, **metadata)
            deadline_at = time.monotonic() + deadline

            def trace_warming(attempt, remaining, observation):
                self.trace.event(
                    "asr_warming_retry", attempt=attempt,
                    remaining_ms=round(remaining * 1000),
                    rejected_request_id=(observation or {}).get("request_id"),
                    provider_detail=(observation or {}).get("provider_detail"),
                    **metadata,
                )

            async with asyncio.timeout(deadline):
                transcript = await transcribe_after_warming(
                    self.asr, AudioInput(audio_bytes, "audio/wav", self.session.get('language'), deadline_at),
                    deadline_at=deadline_at, on_warming=trace_warming,
                    max_warming_retries=getattr(self, 'asr_warming_retries', int(os.getenv("VEFIN_ASR_WARMING_RETRIES", "12"))),
                )
            self.last_asr_success_at = time.monotonic()
            observation = getattr(self.asr.recognizer, "observation", lambda: None)()
            self.trace.event(
                "asr_completed", text=transcript.text, raw_text=getattr(transcript, 'raw_text', transcript.text),
                provider=getattr(transcript, 'provider', 'UNKNOWN'), requested_model=getattr(transcript, 'model', 'UNKNOWN'),
                request_id=getattr(transcript, 'request_id', 'UNKNOWN'), observation=observation, **metadata
            )
            if not self.alive():
                self.trace.event("stale_transcript_discarded", **metadata)
                return
            await self.receipt("transcript", text=transcript.text, metadata=metadata)
            await self.receipt("turn_result", metadata={**metadata, "phase": "asr_completed"})
            self.trace.event("transcript_receipt", **metadata)
            if self.session.get("interaction_mode") == "conversation":
                saved = await self.post(
                    "dialogue",
                    text=transcript.text,
                    turn_id=metadata["turn_id"],
                    metadata=metadata,
                    generate=False,
                )
                recorded_response_id = saved.get("response_id")
                self.trace.event(
                    "ordinary_turn_saved", response_id=recorded_response_id, **metadata
                )
            if (
                self.active_microphone_sid != track_sid
                or self.user_speaking
                or input_epoch != self.input_epoch
            ):
                self.trace.event("superseded_preview_suppressed", **metadata)
                return
            task = asyncio.create_task(
                self.respond(transcript.text, metadata, recorded_response_id)
            )
            self.response_tasks.add(task)
            task.add_done_callback(self.response_tasks.discard)
            # Keep this session's sequencing lock through response/publication.
            # Barge-in explicitly cancels the response and releases this turn.
            await task
        except asyncio.CancelledError:
            self.trace.event("turn_cancelled", **metadata)
            raise
        except Exception as exc:
            code = (
                "ASR_TIMEOUT"
                if isinstance(exc, TimeoutError)
                else getattr(exc, "code", "ASR_OR_RECORD_FAILED")
            )
            self.trace.event(
                "turn_failed", error_type=type(exc).__name__, **metadata, error_code=code,
                failure_category=voice_error_category(exc),
                asr_observation=getattr(getattr(self.asr, "recognizer", None),
                                        "observation", lambda: None)(),
            )
            if self.alive():
                await self.receipt(
                    "turn_result",
                    text="这句话识别或记录失败，未进入业务操作，请稍后重说。",
                    status="error",
                    metadata={**metadata, "phase": "failed", "error_code": code},
                )

    async def respond(self, transcript, metadata, recorded_response_id=None):
        generating = True
        try:
            response_id = recorded_response_id or "VP-" + uuid4().hex
            if self.session.get("interaction_mode") == "conversation":
                if not self.alive() or metadata["input_epoch"] != self.input_epoch:
                    return
                self.trace.event("response_generation_started", response_id=response_id, **metadata)
                result = await self.post(
                    "dialogue",
                    text=transcript,
                    turn_id=metadata["turn_id"],
                    metadata=metadata,
                    generate=True,
                )
                text, response_id = result["text"], result["response_id"]
                acceptance = result.get('content_acceptance')
                if self.require_content_acceptance or acceptance is not None:
                    from src.application.voice_consultation import verify_acceptance
                    if not verify_acceptance(acceptance, self.session['id'], metadata['turn_id'], text):
                        raise RuntimeError('VOICE_CONTENT_ACCEPTANCE_MISMATCH')
                reason = "substantive_response"
                self.trace.event(
                    "response_first_content",
                    **metadata,
                    response_id=response_id,
                    source_version=result.get("source_version"),
                    content_acceptance=result.get("content_acceptance"),
                    text=text,
                )
            else:
                text = f"我识别到：{transcript[:160]}。转写未发送，请核对。"
                reason = "transcript_preview"
            if (
                not self.alive()
                or self.user_speaking
                or metadata["input_epoch"] != self.input_epoch
                or metadata["track_sid"] != self.active_microphone_sid
            ):
                self.trace.event("late_response_suppressed", **metadata, response_id=response_id)
                return
            generating = False
            self.speech_task = asyncio.create_task(
                self.speak(
                    text, reason=reason, metadata={**metadata, "response_id": response_id},
                    language=self.session.get("language", "auto"),
                )
            )
            await self.speech_task
        except asyncio.CancelledError:
            self.trace.event("response_cancelled", response_id=response_id, **metadata)
            raise
        except Exception as exc:
            code = getattr(exc, "code", "RESPONSE_OR_TTS_FAILED")
            self.trace.event(
                "response_failed", error_type=type(exc).__name__, error_code=code,
                failure_category=voice_error_category(exc),
                response_id=response_id, **metadata
            )
            if self.alive():
                delivery = getattr(self, "delivery_progress", {}).get(response_id, {})
                notice = (
                    f"本轮只完成 {len(delivery['published_segments'])}/{delivery['segment_count']} 段音频发布，剩余内容尚未完整交付。"
                    if delivery else "本轮对话已记录，但回应生成或播报失败，请继续或重试。"
                )
                await self.receipt(
                    "turn_result", text=notice, status="error",
                    metadata={**metadata, **delivery, "phase": "failed", "error_code": code},
                )
                if (generating and not getattr(self, 'test_profile_active', False) and not self.user_speaking
                        and metadata["input_epoch"] == self.input_epoch
                        and metadata["track_sid"] == self.active_microphone_sid):
                    # A truthful fault notice is classified separately from substantive replies.
                    # Never recurse when the TTS provider itself failed.
                    with contextlib.suppress(Exception):
                        self.speech_task = asyncio.create_task(self.speak(
                            "这轮回应生成失败，对话原文已保留，请继续或稍后重试。",
                            reason="failure_notice",
                            metadata={**metadata, "response_id": response_id},
                        ))
                        await self.speech_task

    async def receive(self, track):
        stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1, capacity=100)
        detector = self.detector.stream()

        async def feed():
            first_frame = True
            async for item in stream:
                if self.active_microphone_sid != track.sid:
                    break
                if first_frame:
                    logger.info(
                        "microphone_frame_received session=%s sample_rate=%d",
                        self.id,
                        item.frame.sample_rate,
                    )
                    first_frame = False
                    self.trace.event(
                        "microphone_first_frame",
                        sample_rate=item.frame.sample_rate,
                        track_sid=track.sid,
                    )
                detector.push_frame(item.frame)
            detector.end_input()

        feeder = asyncio.create_task(feed())
        try:
            async for event in detector:
                if self.active_microphone_sid != track.sid:
                    break
                if event.type == vad.VADEventType.START_OF_SPEECH:
                    self.trace.event(
                        "vad_start",
                        track_sid=track.sid,
                        samples_index=event.samples_index,
                        vad_timestamp=event.timestamp,
                    )
                    self.user_speaking = True
                    self.input_epoch += 1
                    await self.interrupt()
                elif event.type == vad.VADEventType.END_OF_SPEECH:
                    eos_at = time.monotonic()
                    if not self.accept_end_of_speech(track.sid):
                        continue
                    self.user_speaking = False
                    self.turn_sequence += 1
                    self.turn_track_sid = track.sid
                    self.trace.event(
                        "vad_end",
                        track_sid=track.sid,
                        turn=self.turn_sequence,
                        samples_index=event.samples_index,
                        vad_timestamp=event.timestamp,
                        speech_duration=event.speech_duration,
                        silence_duration=event.silence_duration,
                    )
                    combined = rtc.combine_audio_frames(event.frames)
                    audio = io.BytesIO()
                    with wave.open(audio, "wb") as recording:
                        recording.setnchannels(1)
                        recording.setsampwidth(2)
                        recording.setframerate(combined.sample_rate)
                        recording.writeframes(bytes(combined.data))
                    audio_bytes = audio.getvalue()
                    self.trace.audio(self.turn_sequence, audio_bytes, track_sid=track.sid)
                    metadata = self.turn_metadata(self.turn_sequence, track.sid, self.input_epoch)
                    if len(self.pending_turns) >= self.queue_capacity:
                        self.trace.event("asr_queue_rejected", **metadata)
                        await self.receipt(
                            "turn_result",
                            text="识别队列已满，这句话未进入识别，请稍候重说。",
                            status="error",
                            metadata={
                                **metadata,
                                "phase": "rejected",
                                "error_code": "ASR_QUEUE_FULL",
                            },
                        )
                        continue
                    await self.receipt("turn_result", metadata={**metadata, "phase": "queued"})
                    self.trace.event("asr_queued", queue_depth=len(self.pending_turns), **metadata)
                    self.turn_task = asyncio.create_task(
                        self.answer_turn(
                            audio_bytes,
                            self.turn_sequence,
                            track.sid,
                            self.input_epoch,
                            eos_at,
                        )
                    )
                    self.pending_turns[self.turn_task] = track.sid
                    self.turn_task.add_done_callback(
                        lambda task: self.pending_turns.pop(task, None)
                    )
        finally:
            feeder.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await feeder
            await detector.aclose()
            await stream.aclose()

    def retire_microphone(self, track_sid):
        """Unsubscribe and replacement can arrive in either order during reconnect."""
        receiver = self.microphone_tasks.pop(track_sid, None)
        if receiver is None and self.active_microphone_sid != track_sid:
            return
        if receiver and not receiver.done():
            receiver.cancel()
        if self.turn_track_sid == track_sid:
            if self.speech_task and not self.speech_task.done():
                self.speech_task.cancel()
            if self.source:
                self.source.clear_queue()
            self.turn_track_sid = None
        if self.active_microphone_sid == track_sid:
            self.active_microphone_sid = None
            self.input_epoch = getattr(self, "input_epoch", 0) + 1
            self.user_speaking = False
        self.trace.event("microphone_retired", track_sid=track_sid)

    def subscribe_microphone(self, track, track_sid):
        existing = self.microphone_tasks.get(track_sid)
        if existing and not existing.done():
            return
        for previous_sid in list(self.microphone_tasks):
            self.retire_microphone(previous_sid)
        self.active_microphone_sid = track_sid
        self.trace.event("microphone_subscribed", track_sid=track_sid)
        task = asyncio.create_task(self.receive(track))
        self.microphone_tasks[track_sid] = task
        self.audio_tasks.add(task)

        def finished(receiver):
            self.audio_tasks.discard(receiver)
            if self.microphone_tasks.get(track_sid) is receiver:
                self.microphone_tasks.pop(track_sid, None)

        task.add_done_callback(finished)

    async def run(self):
        deadline = datetime.fromisoformat(self.session["expires_at"])
        # Deadline cancellation is independent of token TTL and control-plane polling.
        async with asyncio.timeout(max(0, (deadline - datetime.now(UTC)).total_seconds())):
            await self.media_loop()

    async def media_loop(self):
        @self.room.on("track_subscribed")
        def subscribed(track, publication, participant):
            if participant.identity != f"user:{self.id}" or track.kind != rtc.TrackKind.KIND_AUDIO:
                return
            logger.info("microphone_subscribed session=%s track=%s", self.id, publication.sid)
            self.subscribe_microphone(track, publication.sid)

        @self.room.on("track_unsubscribed")
        def unsubscribed(track, publication, participant):
            if participant.identity == f"user:{self.id}":
                self.retire_microphone(publication.sid)

        @self.room.on("participant_disconnected")
        def participant_left(participant):
            if participant.identity == f"user:{self.id}":
                for track_sid in list(self.microphone_tasks):
                    self.retire_microphone(track_sid)

        try:
            await self.room.connect(os.environ["LIVEKIT_URL"], self.token)
            self.source = rtc.AudioSource(24000, 1, queue_size_ms=100)
            track = rtc.LocalAudioTrack.create_audio_track("vefin-voice", self.source)
            publication = await self.room.local_participant.publish_track(
                track,
                rtc.TrackPublishOptions(
                    source=rtc.TrackSource.SOURCE_MICROPHONE,
                ),
            )
            self.playout_sid = publication.sid
            logger.info("room_connected session=%s room=%s", self.id, self.session["room"])
            while self.alive():
                result = await self.post("poll")  # Any failed renewal stops audio, fail closed.
                self.last_heartbeat = time.monotonic()
                self.session = result["session"]
                authority = result.get("authority_observation") or {}
                self.trace.scope = {
                    "task_id": self.session.get("task_id"),
                    "chat_session_id": self.session.get("chat_session_id"),
                    "observed_run_id": authority.get("run_id"),
                    "observed_source_version": authority.get("source_version"),
                    "authority_observed_at": authority.get("source_occurred_at"),
                    "authority_refresh": result.get("authority_refresh"),
                }
                user_present = f"user:{self.id}" in {
                    participant.identity for participant in self.room.remote_participants.values()
                }
                if user_present and (
                    not self.connected_once
                    or self.session["status"]
                    in {
                        "connecting",
                        "reconnecting",
                    }
                ):
                    self.connected_once = True
                    restored_status = (
                        "speaking"
                        if self.is_publishing_audio
                        else "thinking"
                        if self.turn_task and not self.turn_task.done()
                        else "listening"
                    )
                    await self.receipt("status", status=restored_status)
                # Explicitly allowlisted local acceptance replay: real TTS/RTC,
                # with the frozen prior text and no ASR or dialogue generation.
                if user_present and self.active_microphone_sid and not self.frozen_replay_started:
                    frozen = self.trace.frozen_reply()
                    if frozen is not None:
                        self.frozen_replay_started = True
                        frozen_meta = self.turn_metadata(1, self.active_microphone_sid, self.input_epoch,
                            response_id="VF-" + hashlib.sha256(frozen.encode()).hexdigest()[:32])
                        self.trace.event("frozen_playback_started", text_sha256=hashlib.sha256(frozen.encode()).hexdigest())
                        self.speech_task = asyncio.create_task(self.speak(frozen, reason="frozen_text_replay", metadata=frozen_meta))
                if user_present and self.active_microphone_sid and not self.saved_input_replay_started:
                    saved = self.trace.saved_asr_input()
                    if saved is not None:
                        self.saved_input_replay_started = True
                        self.turn_sequence += 1
                        self.trace.audio(self.turn_sequence, saved['audio'], track_sid=self.active_microphone_sid)
                        self.trace.event('saved_rtc_input_resumed', source_session_id=saved['source_session_id'],
                            input_sha256=saved['sha256'], scope='ASR_AND_DEPENDENT_NODES_ONLY_NO_NEW_RTC_INPUT')
                        self.turn_task = asyncio.create_task(self.answer_turn(saved['audio'], self.turn_sequence,
                            self.active_microphone_sid, self.input_epoch))
                busy = (
                    any(not t.done() for t in self.response_tasks)
                    or (self.speech_task and not self.speech_task.done())
                    or (self.turn_task and not self.turn_task.done())
                    or self.user_speaking
                )
                pending = result["announcements"]
                warning = any(event["kind"] == "duration_warning" for event in pending)
                if user_present and warning and not self.user_speaking:
                    if busy:
                        await self.interrupt()
                    busy = False
                if user_present and not busy:
                    pending.sort(key=lambda e: (e["kind"] != "duration_warning", -e["cursor"]))
                    for event in pending:
                        consumed = await self.post("consume", event_id=event["event_id"])
                        if consumed["speak"]:
                            self.speech_task = asyncio.create_task(
                                self.speak(
                                    event["text"],
                                    reason=event["reason"],
                                    metadata={**self.turn_metadata(max(1, self.turn_sequence), self.active_microphone_sid or "no-microphone", self.input_epoch),
                                              "response_id": "VA-" + hashlib.sha256(event["event_id"].encode()).hexdigest()[:32]},
                                )
                            )

                            def observe_failure(task):
                                if not task.cancelled() and task.exception():
                                    logger.warning("playout_failed session=%s", self.id)
                                    error = asyncio.create_task(
                                        self.receipt(
                                            "adapter_error",
                                            text="语音播报暂不可用。",
                                            status="error",
                                        )
                                    )
                                    self.audio_tasks.add(error)
                                    error.add_done_callback(self.audio_tasks.discard)

                            self.speech_task.add_done_callback(observe_failure)
                            break
                if not user_present and self.connected_once:
                    await self.receipt("status", status="reconnecting")
                await asyncio.sleep(2)
        finally:
            tasks = {t for t in [*self.audio_tasks, *self.pending_turns,
                     *self.response_tasks, self.speech_task, self.turn_task] if t}
            for task in tasks:
                task.cancel()
            # A slow SDK teardown must not prevent lease release. Media lease expiry remains
            # the independent fallback if process termination prevents graceful cleanup.
            try:
                with contextlib.suppress(Exception):
                    async with asyncio.timeout(2):
                        await asyncio.gather(*tasks, return_exceptions=True)
                # No request or cancelled segment may retain the call's MiMo
                # connection pool after the media lease is released.
                try:
                    async with asyncio.timeout(1):
                        await self.output.aclose()
                    self.trace.event("tts_pool_closed")
                except Exception as exc:
                    logger.warning("tts_pool_close_failed session=%s type=%s", self.id, type(exc).__name__)
                if self.source:
                    self.source.clear_queue()
                    with contextlib.suppress(Exception):
                        async with asyncio.timeout(1):
                            await self.source.aclose()
                with contextlib.suppress(Exception):
                    async with asyncio.timeout(1):
                        await self.room.disconnect()
            finally:
                with contextlib.suppress(Exception):
                    async with asyncio.timeout(2):
                        await self.post("release")
            if datetime.now(UTC) >= datetime.fromisoformat(self.session["expires_at"]):
                # Independent cutoff if the API is unavailable at the fixed deadline.
                with contextlib.suppress(Exception):
                    await LiveKitMedia().delete_room(self.session["room"])
            logger.info("room_stopped session=%s", self.id)


async def main():
    if os.getenv("VEFIN_TTS_PROVIDER") == "quickrouter":
        # Construct the real dedicated client without connecting or generating.
        # A Worker reload discards any clients cached with the previous profile.
        probe = VoiceOutput()
        try:
            client = await probe._quickrouter_http_client()
            logger.info("quickrouter_client_loaded %s", json.dumps({
                **probe.quickrouter_configuration, "client_closed": client.is_closed,
                "transport": type(client._transport._pool).__name__,
            }, sort_keys=True))
        finally:
            await probe.aclose()
    logger.info("worker_code_loaded %s", json.dumps({
        "pid": os.getpid(),
        "voice_output_sha256": hashlib.sha256(Path("src/adapters/voice_output.py").read_bytes()).hexdigest(),
        "worker_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "synthesize_code_sha256": hashlib.sha256(marshal.dumps(VoiceOutput._synthesize_mimo.__code__)).hexdigest(),
        "speak_segment_code_sha256": hashlib.sha256(marshal.dumps(Call.speak_segment.__code__)).hexdigest(),
    }, sort_keys=True))
    detector = silero.VAD.load(min_silence_duration=0.65, max_buffered_speech=110)
    recognizer = worker_recognizer()
    if hasattr(recognizer, "prepare"):
        await recognizer.prepare()
    asr = SpeechService(recognizer)
    active: dict[str, asyncio.Task] = {}
    async with httpx.AsyncClient(
        base_url=os.getenv("VEFIN_VOICE_API_URL", "http://127.0.0.1:8000"),
        timeout=8,
        headers={"Authorization": f"Bearer {os.environ['VEFIN_VOICE_WORKER_SECRET']}"},
    ) as client:

        async def handle(claimed):
            call = Call(client, claimed, detector, asr)
            try:
                await call.run()
            except Exception as exc:
                call.trace.event("call_stopped", error_type=type(exc).__name__)
                logger.warning(
                    "call_stopped session=%s type=%s", claimed["session"]["id"], type(exc).__name__
                )

        shutdown = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, shutdown.set)
        try:
            while not shutdown.is_set():
                try:
                    response = await client.get("/internal/voice/sessions")
                    response.raise_for_status()
                    for session in response.json():
                        session_id = session["id"]
                        if session_id in active and not active[session_id].done():
                            continue
                        claimed = await client.post(
                            f"/internal/voice/{session_id}/claim",
                            json={"worker_id": "vefin-worker"},
                        )
                        if claimed.status_code == 200:
                            active[session_id] = asyncio.create_task(handle(claimed.json()))
                    active = {key: task for key, task in active.items() if not task.done()}
                    # Health means the Worker can reach the authenticated control plane.
                    await asyncio.to_thread(
                        Path("/tmp/vefin-voice-worker-health").write_text,
                        str(time.time()),
                    )
                except Exception as exc:
                    logger.warning("control_unavailable type=%s", type(exc).__name__)
                await asyncio.sleep(2)
        finally:
            for task in active.values():
                task.cancel()
            await asyncio.gather(*active.values(), return_exceptions=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    # SDK/http libraries can include URLs and request payloads in verbose logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(main())
