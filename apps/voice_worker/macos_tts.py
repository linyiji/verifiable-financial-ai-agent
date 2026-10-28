"""Local macOS TTS provider behind the Worker's existing HTTP PCM adapter.

No browser synthesis, prerecorded replies, business actions, or retained audio.
This host adapter is not a production/cloud or Prudential platform assertion.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
import tempfile
import wave
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
slots = asyncio.Semaphore(2)


class SpeechRequest(BaseModel):
    input: str = Field(min_length=1, max_length=4000)
    model: str = "macos-native"
    voice: str = "Tingting"
    response_format: str = "pcm"


async def command(*args: str, input_text: str | None = None):
    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if input_text is not None else None,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(
            process.communicate(input_text.encode() if input_text is not None else None), 30
        )
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise
    if process.returncode:
        raise RuntimeError("NATIVE_TTS_PROCESS_FAILED")


async def synthesize(text: str, voice: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="vefin-tts-") as directory:
        aiff, wav = Path(directory) / "speech.aiff", Path(directory) / "speech.wav"
        await command(
            "/usr/bin/say", "-v", voice, "-r", "180", "-o", str(aiff), "-f", "-", input_text=text
        )
        await command(
            "/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16@24000", "-c", "1", str(aiff), str(wav)
        )
        with wave.open(str(wav), "rb") as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 24000):
                raise RuntimeError("NATIVE_TTS_INVALID_FORMAT")
            if not 0 < audio.getnframes() <= 24000 * 120:
                raise RuntimeError("NATIVE_TTS_INVALID_DURATION")
            return audio.readframes(audio.getnframes())


@app.get("/health")
async def health():
    return {
        "provider": "macos-native",
        "platform_available": sys.platform == "darwin",
        "configured": bool(os.getenv("VEFIN_LOCAL_TTS_SECRET")),
    }


@app.post("/v1/audio/speech")
async def speech(request: SpeechRequest, authorization: str | None = Header(default=None)):
    secret = os.getenv("VEFIN_LOCAL_TTS_SECRET", "")
    if not secret or not secrets.compare_digest(authorization or "", "Bearer " + secret):
        raise HTTPException(401, "TTS_UNAUTHORIZED")
    if sys.platform != "darwin":
        raise HTTPException(503, "TTS_PLATFORM_UNAVAILABLE")
    if (
        request.model != "macos-native"
        or request.response_format != "pcm"
        or request.voice not in {"Tingting", "Samantha"}
    ):
        raise HTTPException(422, "TTS_UNSUPPORTED_OPTIONS")
    try:
        async with asyncio.timeout(40):
            async with slots:
                pcm = await synthesize(request.input, request.voice)
        return Response(pcm, media_type="audio/pcm", headers={"X-Audio-Sample-Rate": "24000"})
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(503, "TTS_SYNTHESIS_FAILED") from exc
