"""Real configurable TTS and bounded model intent adapters; no research authority."""

import asyncio
import base64
import binascii
from contextvars import ContextVar
import io
import hashlib
import re
import json
import os
import time
import uuid
import wave

import httpx


class TTSError(RuntimeError):
    """Allowlisted public TTS failure; never includes upstream body or secrets."""

    def __init__(self, code: str, *, request_id: str, status: int | None = None):
        super().__init__(code)
        self.code, self.request_id, self.status = code, request_id, status

    def public(self) -> dict:
        return {"category": self.code, "request_id": self.request_id, "status": self.status}

def quickrouter_url(base=None):
    from urllib.parse import urlsplit
    base = (base or os.getenv("VEFIN_QUICKROUTER_BASE_URL", "https://api.quickrouter.ai")).rstrip("/")
    url = urlsplit(base)
    if (url.scheme != "https" or url.hostname not in {"api.quickrouter.ai", "api.quickrouter.us"}
            or url.username or url.password or url.query or url.fragment or url.path not in {"", "/v1"}):
        raise RuntimeError("QUICKROUTER_ENDPOINT_UNSUPPORTED")
    return base + ("/audio/speech" if url.path == "/v1" else "/v1/audio/speech")
QUICKROUTER_MAX_BYTES = 10_000_000


def quickrouter_connection_config():
    """Freeze an explicit per-adapter connection profile; no credentials in it."""
    from pathlib import Path
    path = os.getenv("VEFIN_QUICKROUTER_CONNECTION_CONFIG")
    if not path:
        return {"version": "legacy-default", "config_sha256": None,
                "endpoint": quickrouter_url(), "proxy": None, "connect_seconds": 5,
                "read_seconds": 45, "completion_seconds": float(os.getenv("VEFIN_QUICKROUTER_TTS_COMPLETION_SECONDS", "20")),
                "first_pcm_target_seconds": 10, "verify": True, "trust_env": False,
                "follow_redirects": False, "retries": 0}
    try:
        raw = Path(path).read_bytes()
        profile = json.loads(raw)
        client = profile["httpx"]
        transport = client["transport"]
        runtime = profile["runtime"]
        # This finite local test profile cannot disable validation or redirect
        # credentials, and affects only QuickRouter's dedicated client.
        if (profile["provider"] != "quickrouter"
                or profile["base_url"] != "https://api.quickrouter.us"
                or profile["TTS_path"] != "/v1/audio/speech"
                or transport["proxy"] not in {None, "http://127.0.0.1:7890"}
                or transport["verify"] is not True or transport["retries"] != 0
                or client["trust_env"] is not False or client["follow_redirects"] is not False
                or runtime["connect_seconds"] != 15 or runtime["completion_seconds"] != 20
                or runtime["read_seconds"] != 45 or runtime["first_pcm_target_seconds"] != 10):
            raise ValueError("Unsupported connection profile")
        return {"version": profile["version"], "config_sha256": hashlib.sha256(raw).hexdigest(),
                "endpoint": quickrouter_url(profile["base_url"]), "proxy": transport["proxy"],
                **runtime, "verify": True, "trust_env": False, "follow_redirects": False, "retries": 0}
    except (OSError, KeyError, TypeError, ValueError):
        raise RuntimeError("QUICKROUTER_CONNECTION_CONFIG_INVALID") from None

CANTONESE_TTS_INSTRUCTIONS = "Speak every Chinese word in Hong Kong Cantonese, never Mandarin. Preserve the supplied text exactly, including the amount, date, identifier, negation and English word autopay. Do not speak these instructions."

def quickrouter_request(text, language=None):
    body = {"model": "gpt-4o-mini-tts", "voice": "alloy", "input": text,
            "response_format": "mp3", "speed": 1.0}
    if language in {"cantonese", "yue-HK"}:
        body["instructions"] = CANTONESE_TTS_INSTRUCTIONS
    return body

voice_output_context = ContextVar("voice_output_context", default={})


class VoiceOutput:
    async def begin_response(self):
        """Explicit new answer boundary; never a retry of an old segment."""
        if self._closed:
            raise RuntimeError('TTS_ADAPTER_CLOSED')
        if self.candidate:
            await self.candidate.begin_response()

    async def prepare(self, state):
        if self.candidate is None:raise RuntimeError('TTS_PREPARATION_CAPABILITY_UNSUPPORTED')
        await self.candidate.prepare(state)

    def __init__(self, observer=None, *, audio_observer=None, audio_reuse=None, configuration=None) -> None:
        # The worker owns one adapter per call. Keep MiMo connections for all
        # segments/turns in that call, then close them during call teardown.
        self._mimo_client: httpx.AsyncClient | None = None
        self._mimo_client_lock = asyncio.Lock()
        self._quickrouter_client = None
        self.quickrouter_configuration = (quickrouter_connection_config()
            if os.getenv("VEFIN_TTS_PROVIDER") == "quickrouter" else None)
        self._quickrouter_total_timeout_seconds = float(os.getenv("VEFIN_QUICKROUTER_TTS_COMPLETION_SECONDS", "20"))
        if self.quickrouter_configuration:
            self._quickrouter_total_timeout_seconds = self.quickrouter_configuration["completion_seconds"]
        self._closed = False
        self.observer = observer
        self.audio_observer = audio_observer
        self.audio_reuse = audio_reuse
        self.candidate = None
        self.candidate_replay_only=bool(configuration and configuration.get('replay_only'))
        if configuration is not None:
            from src.adapters.qwen_voice_output import QwenRealtimeVoiceOutput
            # Retain the original turn/segment association for incremental
            # provider events and audio, just as the existing providers do.
            self.candidate=QwenRealtimeVoiceOutput(configuration,
                observer=(lambda event: observer({**voice_output_context.get(), **event})) if observer else None,
                audio_observer=self._capture_audio)

    def _capture_audio(self, payload, *, encoding, request_id, **details):
        # The caller supplies an explicitly allowlisted test sink. Normal logs
        # never receive audio, HTTP bodies, authentication, or request headers.
        if self.audio_observer is not None:
            try:
                self.audio_observer(payload, encoding=encoding, request_id=request_id,
                                    **voice_output_context.get(), **details)
            except Exception:
                pass

    def _capture_quickrouter(self, capture):
        body, metadata = capture["body"], capture["metadata"]
        if body and body.lstrip()[:1] not in {b"{", b"["}:
            self._capture_audio(body, encoding="mp3", request_id=capture["request_id"],
                                provider="quickrouter", provider_complete=metadata["provider_complete"],
                                requested_model=metadata["model"], response_model="UNKNOWN",
                                provider_request_id=metadata.get("provider_request_id"),
                                response_headers_ms=metadata.get("response_headers_ms"),
                                first_valid_pcm_ms=metadata.get("first_valid_pcm_ms"),
                                duration_seconds=metadata.get("duration_seconds"),
                                source_sample_rate=metadata.get("source_rate_hz"))

    @property
    def delivery_policy(self):
        if self.candidate:
            return {'completion_seconds':20,'connect_seconds':5,'first_pcm_target_seconds':5}
        provider = os.getenv("VEFIN_TTS_PROVIDER", "espeak")
        if provider == "mimo":
            return {"completion_seconds": float(os.getenv("VEFIN_MIMO_TTS_COMPLETION_SECONDS", "12")),
                    "connect_seconds": 5, "first_pcm_target_seconds": 5}
        if provider == "quickrouter":
            return {"completion_seconds": self._quickrouter_total_timeout_seconds,
                    "connect_seconds": self.quickrouter_configuration["connect_seconds"],
                    "first_pcm_target_seconds": self.quickrouter_configuration["first_pcm_target_seconds"]}
        return {"completion_seconds": float(os.getenv("VEFIN_TTS_DEADLINE_SECONDS", "5")),
                "connect_seconds": 5, "first_pcm_target_seconds": 5}

    def _pool_state(self):
        """Best-effort, read-only diagnostics; unsupported transports stay unknown."""
        client = self._mimo_client
        state = {"client_closed": client.is_closed if client else None,
                 "connections": "UNKNOWN", "requests_total": "UNKNOWN",
                 "queued_requests": "UNKNOWN", "assigned_requests": "UNKNOWN"}
        try:
            pool = client._transport_for_url(
                httpx.URL("https://api.xiaomimimo.com/v1/chat/completions")
            )._pool
            state["connections"] = [
                {"closed": c.is_closed(), "idle": c.is_idle(), "available": c.is_available()}
                for c in pool.connections
            ]
            requests = list(pool._requests)
            state["requests_total"] = len(requests)
            state["queued_requests"] = sum(r.is_queued() for r in requests)
            state["assigned_requests"] = len(requests) - state["queued_requests"]
        except Exception:
            pass
        return state

    def _observe(self, request_id, stage, **details):
        if self.observer is not None:
            try:
                self.observer({"request_id": request_id, "stage": stage,
                               "monotonic_ns": time.monotonic_ns(), **voice_output_context.get(), **details})
            except Exception:
                # Observability must never change synthesis or cancellation.
                pass

    async def _mimo_http_client(self) -> httpx.AsyncClient:
        async with self._mimo_client_lock:
            if self._closed:
                raise RuntimeError("TTS_ADAPTER_CLOSED")
            if self._mimo_client is None:
                self._mimo_client = httpx.AsyncClient(timeout=45)
            return self._mimo_client

    async def _quickrouter_http_client(self) -> httpx.AsyncClient:
        async with self._mimo_client_lock:
            if self._closed:
                raise RuntimeError("TTS_ADAPTER_CLOSED")
            if self._quickrouter_client is None:
                config = self.quickrouter_configuration or quickrouter_connection_config()
                # No redirect forwarding, HTTP transport retries, or hidden fallback.
                self._quickrouter_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(config["read_seconds"], connect=config["connect_seconds"]),
                    follow_redirects=False, trust_env=False,
                    transport=httpx.AsyncHTTPTransport(retries=0, verify=True, proxy=config["proxy"]))
                self._observe("client-configuration", "client_created", **config)
            return self._quickrouter_client

    async def synthesize_quickrouter(self, text: str, *, language=None, state: dict | None = None, capture=None, incremental_decoder=None):
        """One total receive/decode budget also bounds ordinary VeFin calls."""
        state = state if state is not None else {}
        try:
            async with asyncio.timeout(self._quickrouter_total_timeout_seconds):
                return await self._synthesize_quickrouter(text, language=language, state=state, capture=capture,
                                                          incremental_decoder=incremental_decoder)
        except TimeoutError:
            error = TTSError("UPSTREAM_TOTAL_TIMEOUT",
                request_id=state.get("adapter_request_id", uuid.uuid4().hex),
                status=state.get("provider_status"))
            state["error"] = error.public()
            state["cancelled"] = False
            raise error from None

    async def _synthesize_quickrouter(self, text: str, *, language=None, state: dict | None = None, capture=None, incremental_decoder=None):
        """Bounded complete MP3 reception then decode; not streaming generation."""
        from src.adapters.voice_audio_codec import decode_mp3, MP3DecodeError
        state = state if state is not None else {}
        started = time.monotonic()
        request_id = uuid.uuid4().hex
        state.update({"adapter_request_id": request_id, "provider": "quickrouter",
                      "model": "gpt-4o-mini-tts", "voice_id": "alloy",
                      "audio_format": "mp3", "stream": False, "retries": 0,
                      "fallback": False, "input_sha256": hashlib.sha256(text.encode()).hexdigest(),
                      "input_characters": len(text), "provider_status": None,
                      "provider_request_id": None, "response_body_first_ms": None,
                      "vendor_audio_bytes": 0, "provider_complete": False,
                      "actual_upstream_model": "UNKNOWN"})
        key = os.getenv("QUICKROUTER_API_KEY", "")
        if not key:
            raise TTSError("CONFIGURATION_MISSING", request_id=request_id)
        body = bytearray()
        config = self.quickrouter_configuration or quickrouter_connection_config()
        self._observe(request_id, "request_started", provider="quickrouter", **config)
        self._observe(request_id, "language_control", language=language or "auto",
                      control_version="hk-cantonese-v1",
                      instructions=quickrouter_request(text, language).get("instructions"),
                      requested_model="gpt-4o-mini-tts", response_model="UNKNOWN", voice="alloy")
        async def trace(event, info):
            # Allowlist only timing, status and TLS policy. Never serialize info,
            # request/response headers, authentication or request bodies.
            details = {}
            if event.endswith("receive_response_headers.complete"):
                value = info.get("return_value")
                if isinstance(value, tuple): details["http_status"] = value[1]
            if event.endswith("start_tls.started"):
                import ssl
                context = info.get("ssl_context")
                details.update(server_hostname=info.get("server_hostname"),
                    CERT_REQUIRED=getattr(context, "verify_mode", None) == ssl.CERT_REQUIRED,
                    check_hostname=getattr(context, "check_hostname", None))
            if event.endswith("start_tls.complete"):
                try:
                    stream = info.get("return_value")
                    tls = stream.get_extra_info("ssl_object") if stream else None
                    if tls:
                        details.update(TLS_version=tls.version(),
                            certificate_sha256=hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest())
                except (AttributeError, TypeError, ValueError):
                    details["TLS_metadata_available"] = False
            self._observe(request_id, event, **details)
        decoder_start = asyncio.create_task(incremental_decoder.start()) if incremental_decoder else None
        try:
            client = await self._quickrouter_http_client()
            async with client.stream("POST", config["endpoint"],
                    headers={"Authorization": f"Bearer {key}"},
                    json=quickrouter_request(text, language), extensions={"trace": trace}) as response:
                status = response.status_code
                state["provider_status"] = status
                state["response_headers_ms"] = round((time.monotonic()-started)*1000, 2)
                response_id = response.headers.get("x-request-id") or response.headers.get("request-id")
                if response_id and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", response_id):
                    state["provider_request_id"] = response_id
                self._observe(request_id, "response_headers", status=status)
                if status != 200:
                    category = (f"HTTP_{status}" if status in {400,401,403,429}
                                else "HTTP_5XX" if status >= 500 else "HTTP_UNEXPECTED")
                    raise TTSError(category, request_id=request_id, status=status)
                async for chunk in response.aiter_bytes():
                    if not chunk:
                        continue
                    if state["response_body_first_ms"] is None:
                        state["response_body_first_ms"] = round((time.monotonic()-started)*1000, 2)
                        self._observe(request_id, "response_body_first_chunk")
                    if len(body) + len(chunk) > QUICKROUTER_MAX_BYTES:
                        raise TTSError("AUDIO_LIMIT", request_id=request_id, status=status)
                    body.extend(chunk)
                    if incremental_decoder:
                        await decoder_start
                        await incremental_decoder.feed(chunk)
                state["vendor_audio_bytes"] = len(body)
                state["response_body_complete_ms"] = round((time.monotonic()-started)*1000, 2)
                self._observe(request_id, "response_body_completed", bytes=len(body))
            if not body:
                raise TTSError("NO_AUDIO", request_id=request_id, status=200)
            if bytes(body).lstrip()[:1] in {b"{", b"["}:
                raise TTSError("INVALID_MP3", request_id=request_id, status=200)
            state["provider_complete"] = True
            audio = await incremental_decoder.finish() if incremental_decoder else await decode_mp3(bytes(body))
            state.update({"source_rate_hz": audio.source_rate,
                          "source_channels": audio.source_channels,
                          "source_samples": audio.source_samples,
                          "source_pcm_sha256": audio.source_sha256,
                          "mp3_sha256": audio.mp3_sha256,
                          "output_pcm_sha256": audio.pcm16_sha256,
                          "duration_seconds": audio.duration_seconds,
                          "provider_audio_duration_ms": audio.duration_seconds * 1000,
                          "first_valid_pcm_ms": state.get("first_valid_pcm_ms", round((time.monotonic()-started)*1000, 2)),
                          "output_audio_bytes": len(audio.pcm16)})
            self._observe(request_id, "audio_decode_completed", sample_rate=audio.sample_rate,
                          source_sample_rate=audio.source_rate, pcm_samples=len(audio.pcm16)//2,
                          pcm_sha256=audio.pcm16_sha256, source_pcm_sha256=audio.source_sha256)
            return bytes(body), audio
        except asyncio.CancelledError:
            state["cancelled"] = True
            self._observe(request_id, "cancelled_after_response_cleanup")
            raise
        except TTSError as exc:
            state["error"] = exc.public()
            raise
        except MP3DecodeError as exc:
            error = TTSError(exc.code, request_id=request_id, status=state["provider_status"])
            state["error"] = error.public()
            raise error from None
        except httpx.TimeoutException as exc:
            code = "UPSTREAM_CONNECT_TIMEOUT" if isinstance(exc, httpx.ConnectTimeout) else "UPSTREAM_READ_TIMEOUT"
            error = TTSError(code, request_id=request_id)
            state["error"] = error.public()
            raise error from None
        except httpx.RemoteProtocolError:
            error = TTSError("UPSTREAM_DISCONNECTED", request_id=request_id)
            state["error"] = error.public()
            raise error from None
        except httpx.RequestError:
            error = TTSError("CONNECTION_FAILED", request_id=request_id)
            state["error"] = error.public()
            raise error from None
        finally:
            if decoder_start:
                if not decoder_start.done(): decoder_start.cancel()
                await asyncio.gather(decoder_start, return_exceptions=True)
                await incremental_decoder.close()
            state["elapsed_ms"] = round((time.monotonic()-started)*1000, 2)
            if capture is not None:
                try:
                    capture({"pillar": "tts_transport_capture", "request_id": request_id,
                             "body": bytes(body), "metadata": dict(state)})
                except Exception:
                    pass
            self._observe(request_id, "request_finished", provider="quickrouter",
                          elapsed_ms=state["elapsed_ms"], provider_complete=state["provider_complete"],
                          error=state.get("error"), provider_request_id=state.get("provider_request_id"))

    async def stream(self, text: str, *, language=None, state=None):
        """Optional incremental PCM contract; other adapters retain their tuple API.

        The existing buffered synthesize method stays compatible. This makes no
        promise about supplier generation timing: only actual decoded PCM is
        yielded, with a single persistent parser, decoder and resampler.
        """
        if self.candidate:
            reused=self.audio_reuse(text,language) if self.audio_reuse else None
            if reused is not None:
                if (reused.get('provider')!='qwen_beijing' or reused.get('encoding')!='pcm_s16le'
                        or reused.get('sample_rate')!=16000 or not reused['payload']
                        or len(reused['payload'])%2):
                    raise ValueError('CANDIDATE_REUSE_AUDIO_CONTRACT_MISMATCH')
                if state is not None:state.update(reused=True,provider_complete=True,complete=True)
                self._observe('reuse-'+hashlib.sha256(reused['payload']).hexdigest()[:24],
                    'explicit_generated_audio_reused',provider='qwen_beijing',source_file=reused['source_file'])
                yield reused['payload'],16000
                return
            if self.candidate_replay_only:raise RuntimeError('EXPLICIT_REPLAY_AUDIO_MISSING')
            async for frame in self.candidate.stream(text,language=language,state=state):yield frame
            return
        if os.getenv('VEFIN_TTS_PROVIDER') != 'quickrouter':
            async with asyncio.timeout(self.delivery_policy['completion_seconds']):
                result = await self.synthesize(text, language=language)
            yield result
            return
        if self.audio_reuse is not None and self.audio_reuse(text, language) is not None:
            yield await self.synthesize(text, language=language)
            return
        from src.adapters.voice_call_budget import charge
        from src.adapters.voice_audio_codec import IncrementalMP3Decoder
        charge('TTS', 'quickrouter', 'gpt-4o-mini-tts')
        state = state if state is not None else {}
        # Decoder limits bound bytes/duration. Do not put RTC backpressure into
        # the provider's generation deadline: generation and playout are separate.
        queue = asyncio.Queue()
        started = time.monotonic()
        prefix = bytearray()
        first = True
        async def pcm_received(pcm):
            nonlocal first
            if first:
                prefix.extend(pcm)
                # Genuine decoded sound, never a synthetic silence/early marker.
                import array
                values = array.array('h', pcm)
                if not any(abs(x) > 8 for x in values): return
                pcm = bytes(prefix); prefix.clear(); first = False
                state['first_valid_pcm_ms'] = round((time.monotonic()-started)*1000, 2)
                self._observe(state.get('adapter_request_id'), 'first_incremental_pcm',
                    elapsed_ms=state['first_valid_pcm_ms'], pcm_bytes=len(pcm))
            await queue.put(pcm)
        decoder = IncrementalMP3Decoder(pcm_received)
        producer = asyncio.create_task(self.synthesize_quickrouter(text, language=language,
            state=state, capture=self._capture_quickrouter, incremental_decoder=decoder))
        pending = None
        try:
            while True:
                if producer.done() and queue.empty():
                    await producer
                    if first: raise TTSError('NO_AUDIO', request_id=state.get('adapter_request_id','unknown'))
                    state['complete'] = True
                    break
                pending = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({pending, producer}, return_when=asyncio.FIRST_COMPLETED)
                if pending in done:
                    pcm = pending.result(); pending = None
                    yield pcm, 16000
                elif producer.done():
                    await producer
                    pending.cancel(); await asyncio.gather(pending, return_exceptions=True); pending = None
        finally:
            if pending:
                pending.cancel(); await asyncio.gather(pending, return_exceptions=True)
            if not producer.done(): producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)
            await decoder.close()

    async def finish_response(self) -> None:
        """Release a provider session after the answer's ordered segments.

        Providers without response-scoped sessions keep their existing behavior.
        """
        if self.candidate:
            await self.candidate.finish_response()

    async def aclose(self) -> None:
        if self.candidate:await self.candidate.aclose()
        async with self._mimo_client_lock:
            self._closed = True
            if self._quickrouter_client is not None:
                await self._quickrouter_client.aclose()
                self._quickrouter_client = None
            if self._mimo_client is not None:
                await self._mimo_client.aclose()
                self._mimo_client = None

    async def synthesize(self, text: str, *, language: str | None = None) -> tuple[bytes, int]:
        if self.candidate:
            chunks=[]
            async for pcm,rate in self.candidate.stream(text,language=language):chunks.append(pcm)
            return b''.join(chunks),16000
        provider = os.getenv("VEFIN_TTS_PROVIDER", "espeak")
        if provider == "quickrouter" and self.audio_reuse is not None:
            reused = self.audio_reuse(text, language)
            if reused is not None:
                from src.adapters.voice_audio_codec import decode_mp3
                async with asyncio.timeout(self._quickrouter_total_timeout_seconds):
                    audio = await decode_mp3(reused["payload"])
                request_id = "reuse-" + audio.mp3_sha256[:24]
                self._observe(request_id, "historical_audio_reused", provider="quickrouter",
                    source_file=reused["source_file"], input_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    mp3_sha256=audio.mp3_sha256, pcm_sha256=audio.pcm16_sha256,
                    sample_rate=audio.sample_rate, duration_seconds=audio.duration_seconds)
                self._capture_audio(reused["payload"], encoding="mp3", request_id=request_id,
                    provider="quickrouter", provider_complete=True, reused=True,
                    requested_model="gpt-4o-mini-tts", response_model="UNKNOWN")
                return audio.pcm16, audio.sample_rate
        if provider in {"mimo", "quickrouter", "http"}:
            from src.adapters.voice_call_budget import charge
            charge("TTS", provider, {"mimo": "mimo-v2.5-tts", "quickrouter": "gpt-4o-mini-tts"}.get(provider, os.getenv("VEFIN_TTS_MODEL", "UNKNOWN")))
        if provider == "quickrouter":
            _, audio = await self.synthesize_quickrouter(
                text, language=language, capture=self._capture_quickrouter)
            return audio.pcm16, audio.sample_rate
        if provider == "espeak":
            process = await asyncio.create_subprocess_exec(
                "espeak-ng", "--stdout", "-v", os.getenv("VEFIN_TTS_VOICE", "cmn"),
                "-s", "165", "--stdin", stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                output, _ = await asyncio.wait_for(process.communicate(text.encode()), 30)
            except BaseException:
                if process.returncode is None:
                    process.terminate()
                    await process.wait()
                raise
            if process.returncode:
                raise RuntimeError("TTS_PROCESS_FAILED")
            with wave.open(io.BytesIO(output)) as audio:
                return audio.readframes(audio.getnframes()), audio.getframerate()
        if provider == "mimo":
            return await self._synthesize_mimo(text, language=language)
        if provider != "http":
            raise RuntimeError("TTS_NOT_CONFIGURED")
        key = os.getenv("VEFIN_TTS_API_KEY", "")
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                os.environ["VEFIN_TTS_URL"],
                headers={"Authorization": f"Bearer {key}"} if key else {},
                json={"model": os.environ["VEFIN_TTS_MODEL"], "input": text,
                      "voice": os.getenv("VEFIN_TTS_VOICE", "alloy"), "response_format": "pcm"},
            )
            response.raise_for_status()
            # OpenAI-compatible raw signed 16-bit LE mono PCM, configurable sample rate.
            return response.content, int(os.getenv("VEFIN_TTS_SAMPLE_RATE", "24000"))

    async def _synthesize_mimo(self, text: str, *, language: str | None = None) -> tuple[bytes, int]:
        """MiMo's chat-completion WAV contract; returns verified mono PCM to the worker.

        The current worker buffers a segment before playout. This method does not
        represent MiMo's server-side streaming API or claim streaming latency.
        """
        key = os.getenv("MIMO_API_KEY", "")
        if not key:
            raise RuntimeError("MIMO_API_KEY_MISSING")
        voice = os.getenv("VEFIN_MIMO_TTS_VOICE", "mimo_default")
        if voice not in {"mimo_default", "冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean"}:
            raise RuntimeError("MIMO_TTS_VOICE_UNSUPPORTED")
        # MiMo's language control belongs only to the supplier request. The
        # dialogue text, receipts, and research records retain the clean reply.
        supplier_text = "(粤语)" + text if language in {"cantonese", "yue-HK"} else text
        request_id = uuid.uuid4().hex
        self._observe(request_id, "language_control", language=language or "auto",
                      control_version="mimo-cantonese-tag-v1", assistant_prefix="(粤语)" if language in {"cantonese", "yue-HK"} else "",
                      requested_model="mimo-v2.5-tts", voice=voice,
                      input_sha256=hashlib.sha256(text.encode()).hexdigest())
        self._observe(request_id, "request_started", pool=self._pool_state())

        async def trace(event, info):
            # Never serialize info: it may contain credentials, headers or body.
            self._observe(request_id, event)

        try:
            client = await self._mimo_http_client()
            self._observe(request_id, "client_acquired", pool=self._pool_state())
            # Transport chunks are observed, but the full JSON/WAV is still
            # buffered before returning PCM. Supplier stream remains False.
            async with client.stream(
                "POST",
                "https://api.xiaomimimo.com/v1/chat/completions",
                headers={"api-key": key, "Content-Type": "application/json"},
                json={
                    "model": "mimo-v2.5-tts",
                    "messages": [{"role": "assistant", "content": supplier_text}],
                    "audio": {"format": "wav", "voice": voice},
                    "stream": False,
                },
                extensions={"trace": trace},
                timeout=httpx.Timeout(12, connect=5),
            ) as response:
                self._observe(request_id, "response_headers", status=response.status_code)
                response.raise_for_status()
                chunks = []
                async for chunk in response.aiter_bytes():
                    if chunk and not chunks:
                        self._observe(request_id, "response_body_first_chunk")
                    if chunk:
                        chunks.append(chunk)
                body = b"".join(chunks)
                self._observe(request_id, "response_body_complete", bytes=len(body))
        except asyncio.CancelledError:
            self._observe(request_id, "cancelled_after_response_cleanup")
            raise
        except Exception as exc:
            self._observe(request_id, "request_failed", error_type=type(exc).__name__)
            raise
        finally:
            self._observe(request_id, "request_finished", pool=self._pool_state())
        try:
            self._observe(request_id, "audio_decode_started")
            result = json.loads(body)
            self._observe(request_id, "response_metadata", response_model=result.get("model"), usage=result.get("usage"))
            encoded = result["choices"][0]["message"]["audio"]["data"]
            wav_bytes = base64.b64decode(encoded, validate=True)
            self._capture_audio(wav_bytes, encoding="wav", request_id=request_id,
                                provider="mimo", requested_model="mimo-v2.5-tts",
                                response_model=result.get("model") or "UNKNOWN")
            with wave.open(io.BytesIO(wav_bytes), "rb") as audio:
                if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or audio.getcomptype() != "NONE":
                    raise ValueError("unsupported WAV encoding")
                sample_rate = audio.getframerate()
                if sample_rate <= 0:
                    raise ValueError("invalid WAV sample rate")
                expected_frames = audio.getnframes()
                pcm = audio.readframes(expected_frames)
                if not pcm or len(pcm) != expected_frames * 2:
                    raise ValueError("invalid PCM length")
                self._observe(request_id, "audio_decode_completed", pcm_samples=len(pcm)//2,
                              declared_frames=expected_frames, sample_rate=sample_rate,
                              supplier_audio_sha256=hashlib.sha256(wav_bytes).hexdigest(),
                              pcm_sha256=hashlib.sha256(pcm).hexdigest())
                return pcm, sample_rate
        except (KeyError, IndexError, TypeError, ValueError, EOFError, wave.Error, binascii.Error) as exc:
            raise RuntimeError("MIMO_TTS_INVALID_AUDIO") from exc

    async def classify(self, text: str) -> str:
        provider = os.getenv("VEFIN_VOICE_MODEL_PROVIDER", "disabled")
        if provider == "disabled":
            return "preview"
        if provider != "http":
            raise RuntimeError("VOICE_MODEL_NOT_CONFIGURED")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                os.environ["VEFIN_VOICE_MODEL_URL"],
                headers={"Authorization": f"Bearer {os.environ['VEFIN_VOICE_MODEL_API_KEY']}"},
                json={
                    "model": os.environ["VEFIN_VOICE_MODEL"], "temperature": 0,
                    "max_tokens": 40,
                    "messages": [
                        {"role": "system", "content":
                         'Classify only. Return JSON {"intent":"preview"} or '
                         '{"intent":"request_send"}. request_send means the user explicitly '
                         'asks to send their question. Never answer the question.'},
                        {"role": "user", "content": text[:4000]},
                    ],
                },
            )
            response.raise_for_status()
            result = json.loads(response.json()["choices"][0]["message"]["content"])
            # Model output is never spoken and never grants research permissions.
            return "request_send" if result.get("intent") == "request_send" else "preview"
