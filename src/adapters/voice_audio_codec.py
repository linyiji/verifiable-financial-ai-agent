"""Bounded full-response MP3 bridge. HTTP fragments must be joined before decoding.

One PyAV decoder and one continuous 16 kHz mono resampler live in an isolated
worker. Cancellation/timeout kills and reaps it, including native codec work.
The worker uses the already installed voice-runtime PyAV/NumPy dependencies.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import struct
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_WORKER_PATH = str(Path(__file__).resolve())


class MP3DecodeError(RuntimeError):
    """Safe public category; never includes supplier bytes or decoder diagnostics."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MP3DecodeLimits:
    max_body_bytes: int = 8 * 1024 * 1024
    max_duration_seconds: float = 120.0
    max_source_pcm_bytes: int = 24 * 1024 * 1024
    decode_timeout_seconds: float = 10.0

    def __post_init__(self):
        import math

        if (
            self.max_body_bytes <= 0
            or self.max_source_pcm_bytes <= 0
            or not math.isfinite(self.max_duration_seconds)
            or self.max_duration_seconds <= 0
            or not math.isfinite(self.decode_timeout_seconds)
            or self.decode_timeout_seconds <= 0
        ):
            raise ValueError("invalid MP3 decode limits")


@dataclass(frozen=True)
class DecodedMP3:
    source_pcm: bytes
    source_rate: int
    source_channels: int
    source_samples: int
    source_sha256: str
    pcm16: bytes
    pcm16_sha256: str
    mp3_sha256: str
    duration_seconds: float
    encoding: str = "pcm_s16le"
    sample_rate: int = 16000
    channels: int = 1


def _validate_frames(body: bytes) -> None:
    """Require complete contiguous Layer III frames, not just a MIME or magic.

    MP3 without CRC cannot detect every payload bit flip. Decoder errors and
    structural corruption are rejected; no claim of cryptographic integrity.
    Free-format and changing geometry are outside this bridge's verified format.
    """
    pos = 0
    end = len(body)
    if body.startswith(b"ID3"):
        if end < 10 or body[3] not in (2, 3, 4) or any(x & 128 for x in body[6:10]):
            raise MP3DecodeError("INVALID_MP3")
        size = sum(x << shift for x, shift in zip(body[6:10], (21, 14, 7, 0), strict=True))
        pos = 10 + size + (10 if body[3] == 4 and body[5] & 16 else 0)
        if pos > end:
            raise MP3DecodeError("INVALID_MP3")
    if end - pos >= 128 and body[end - 128 : end - 125] == b"TAG":
        end -= 128
    count = 0
    geometry = None
    declared_frames = None
    while pos < end:
        if end - pos < 4:
            raise MP3DecodeError("INVALID_MP3")
        header = int.from_bytes(body[pos : pos + 4], "big")
        version = (header >> 19) & 3
        layer = (header >> 17) & 3
        bitrate_index = (header >> 12) & 15
        rate_index = (header >> 10) & 3
        if (
            header >> 21 != 0x7FF
            or version == 1
            or layer != 1
            or bitrate_index in (0, 15)
            or rate_index == 3
            or header & 3 == 2
        ):
            raise MP3DecodeError("INVALID_MP3")
        rates = (44100, 48000, 32000)
        rate = rates[rate_index] // (1 if version == 3 else 2 if version == 2 else 4)
        bitrates = (
            (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
            if version == 3
            else (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
        )
        length = (144000 if version == 3 else 72000) * bitrates[bitrate_index] // rate
        length += (header >> 9) & 1
        channels = 1 if (header >> 6) & 3 == 3 else 2
        current = (rate, channels)
        if geometry is not None and geometry != current:
            raise MP3DecodeError("INVALID_MP3")
        geometry = current
        if length < 4 or pos + length > end:
            raise MP3DecodeError("INVALID_MP3")
        if count == 0:
            side_size = (
                (17 if channels == 1 else 32) if version == 3 else (9 if channels == 1 else 17)
            )
            xing_pos = pos + 4 + (0 if header & (1 << 16) else 2) + side_size
            if body[xing_pos : xing_pos + 4] in (b"Xing", b"Info"):
                if xing_pos + 8 > pos + length:
                    raise MP3DecodeError("INVALID_MP3")
                flags = int.from_bytes(body[xing_pos + 4 : xing_pos + 8], "big")
                if flags & 1:
                    if xing_pos + 12 > pos + length:
                        raise MP3DecodeError("INVALID_MP3")
                    declared_frames = int.from_bytes(body[xing_pos + 8 : xing_pos + 12], "big")
        pos += length
        count += 1
    if count < 2 or (declared_frames is not None and declared_frames != count - 1):
        raise MP3DecodeError("INVALID_MP3")


def _decode_worker(body: bytes, limits: MP3DecodeLimits) -> DecodedMP3:
    try:
        import av
    except ImportError:
        raise MP3DecodeError("AUDIO_DECODER_UNAVAILABLE") from None
    _validate_frames(body)
    original = bytearray()
    output = bytearray()
    rate = channels = samples = 0
    # Explicit MP3 demuxing prevents arbitrary formats entering the PCM contract.
    try:
        with av.open(
            io.BytesIO(body), format="mp3", options={"err_detect": "explode+crccheck"}
        ) as container:
            if len(container.streams.audio) != 1:
                raise MP3DecodeError("INVALID_MP3")
            stream = container.streams.audio[0]
            stream.codec_context.options = {"err_detect": "explode+crccheck"}
            source_resampler = None
            target_resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)

            def append(frames, target):
                for converted in frames:
                    target.extend(
                        converted.to_ndarray().reshape(-1).astype("<i2", copy=False).tobytes()
                    )

            for frame in container.decode(audio=0):
                current_rate = frame.sample_rate
                current_channels = len(frame.layout.channels)
                if not rate:
                    rate, channels = current_rate, current_channels
                    if not 8000 <= rate <= 48000 or channels not in (1, 2):
                        raise MP3DecodeError("INVALID_MP3")
                    source_resampler = av.AudioResampler(
                        format="s16", layout=frame.layout, rate=rate
                    )
                if (current_rate, current_channels) != (rate, channels):
                    raise MP3DecodeError("INVALID_MP3")
                samples += frame.samples
                if (
                    samples / rate > limits.max_duration_seconds
                    or samples * channels * 2 > limits.max_source_pcm_bytes
                ):
                    raise MP3DecodeError("AUDIO_LIMIT")
                append(source_resampler.resample(frame), original)
                append(target_resampler.resample(frame), output)
            if source_resampler is None:
                raise MP3DecodeError("NO_AUDIO")
            append(source_resampler.resample(None), original)
            append(target_resampler.resample(None), output)
    except MP3DecodeError:
        raise
    except Exception:
        raise MP3DecodeError("INVALID_MP3") from None
    if not output or len(output) % 2 or len(original) != samples * channels * 2:
        raise MP3DecodeError("INVALID_MP3")
    return DecodedMP3(
        source_pcm=bytes(original),
        source_rate=rate,
        source_channels=channels,
        source_samples=samples,
        source_sha256=hashlib.sha256(original).hexdigest(),
        pcm16=bytes(output),
        pcm16_sha256=hashlib.sha256(output).hexdigest(),
        mp3_sha256=hashlib.sha256(body).hexdigest(),
        duration_seconds=samples / rate,
    )


async def decode_mp3(mp3: bytes, *, limits: MP3DecodeLimits | None = None) -> DecodedMP3:
    """Decode one complete supplier body with resource and cancellation bounds."""
    limits = limits or MP3DecodeLimits()
    if not mp3:
        raise MP3DecodeError("NO_AUDIO")
    if len(mp3) > limits.max_body_bytes:
        raise MP3DecodeError("AUDIO_LIMIT")
    if mp3.lstrip().startswith((b"{", b"[")):
        raise MP3DecodeError("INVALID_MP3")
    process = None
    try:
        async with asyncio.timeout(limits.decode_timeout_seconds):
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                _WORKER_PATH,
                "--worker",
                json.dumps(asdict(limits)),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )

            # Read concurrently with writing, avoiding pipe-capacity deadlocks.
            async def write_body():
                process.stdin.write(mp3)
                await process.stdin.drain()
                process.stdin.close()
                await process.stdin.wait_closed()

            async def read_body():
                payload = bytearray()
                max_output = (
                    limits.max_source_pcm_bytes + int(limits.max_duration_seconds * 32000) + 4096
                )
                while chunk := await process.stdout.read(65536):
                    payload.extend(chunk)
                    if len(payload) > max_output:
                        raise MP3DecodeError("AUDIO_LIMIT")
                return bytes(payload)

            writer = asyncio.create_task(write_body())
            reader = asyncio.create_task(read_body())
            try:
                _, payload = await asyncio.gather(writer, reader)
                await process.wait()
            finally:
                for task in (writer, reader):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(writer, reader, return_exceptions=True)
            if process.returncode or len(payload) < 4:
                raise MP3DecodeError("INVALID_MP3")
            meta_length = struct.unpack("!I", payload[:4])[0]
            if meta_length > 4096 or len(payload) < 4 + meta_length:
                raise MP3DecodeError("INVALID_MP3")
            meta = json.loads(payload[4 : 4 + meta_length])
            if "error" in meta:
                raise MP3DecodeError(meta["error"])
            source_length = meta.pop("source_length")
            pcm_length = meta.pop("pcm_length")
            audio = payload[4 + meta_length :]
            if len(audio) != source_length + pcm_length:
                raise MP3DecodeError("INVALID_MP3")
            return DecodedMP3(source_pcm=audio[:source_length], pcm16=audio[source_length:], **meta)
    except TimeoutError:
        raise MP3DecodeError("AUDIO_DECODE_TIMEOUT") from None
    except (OSError, BrokenPipeError):
        raise MP3DecodeError("AUDIO_DECODER_UNAVAILABLE") from None
    finally:
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()


def _worker_main():
    limits = MP3DecodeLimits(**json.loads(sys.argv[2]))
    body = sys.stdin.buffer.read(limits.max_body_bytes + 1)
    try:
        if len(body) > limits.max_body_bytes:
            raise MP3DecodeError("AUDIO_LIMIT")
        result = _decode_worker(body, limits)
        meta = asdict(result)
        source = meta.pop("source_pcm")
        pcm = meta.pop("pcm16")
        meta.update(source_length=len(source), pcm_length=len(pcm))
    except MP3DecodeError as error:
        meta, source, pcm = {"error": error.code}, b"", b""
    encoded = json.dumps(meta, separators=(",", ":")).encode()
    sys.stdout.buffer.write(struct.pack("!I", len(encoded)) + encoded + source + pcm)


class IncrementalMP3Decoder:
    """One isolated parser/decoder/resampler for the entire HTTP response.

    Startup overlaps the HTTP wait. Frames are never decoded as standalone MP3
    files. EOF validates the complete container; output before a bad EOF is
    partial and must not be reported as a completed synthesis.
    """
    def __init__(self, on_pcm, limits=None):
        self.limits = limits or MP3DecodeLimits()
        self.on_pcm = on_pcm
        self.process = self.reader = None
        self.source = bytearray()
        self.pcm = bytearray()
        self.metadata = None

    async def start(self):
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, _WORKER_PATH, '--stream-worker', json.dumps(asdict(self.limits)),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        kind, value = await self._read()
        if kind != b'R': raise MP3DecodeError('AUDIO_DECODER_UNAVAILABLE')
        self.reader = asyncio.create_task(self._consume())

    async def _read(self):
        header = await self.process.stdout.readexactly(5)
        size = struct.unpack('!I', header[1:])[0]
        if size > self.limits.max_source_pcm_bytes:
            raise MP3DecodeError('AUDIO_LIMIT')
        return header[:1], await self.process.stdout.readexactly(size)

    async def _consume(self):
        try:
            while True:
                kind, body = await self._read()
                if kind == b'S': self.source.extend(body)
                elif kind == b'P':
                    self.pcm.extend(body)
                    if len(self.pcm) > self.limits.max_source_pcm_bytes:
                        raise MP3DecodeError('AUDIO_LIMIT')
                    await self.on_pcm(body)
                elif kind == b'D':
                    self.metadata = json.loads(body)
                    return
                elif kind == b'E': raise MP3DecodeError(json.loads(body)['error'])
                else: raise MP3DecodeError('INVALID_MP3')
        except asyncio.IncompleteReadError:
            raise MP3DecodeError('AUDIO_DECODER_EXITED') from None

    async def feed(self, body):
        if self.reader.done(): await self.reader
        self.process.stdin.write(struct.pack('!I', len(body)) + body)
        await self.process.stdin.drain()

    async def finish(self):
        self.process.stdin.write(struct.pack('!I', 0))
        await self.process.stdin.drain()
        await self.reader
        await self.process.wait()
        if self.process.returncode or not self.pcm or not self.metadata:
            raise MP3DecodeError('INVALID_MP3')
        return DecodedMP3(source_pcm=bytes(self.source), pcm16=bytes(self.pcm), **self.metadata)

    async def close(self):
        if self.reader and not self.reader.done(): self.reader.cancel()
        if self.reader: await asyncio.gather(self.reader, return_exceptions=True)
        if self.process and self.process.returncode is None:
            self.process.kill()
            await self.process.wait()


def _stream_worker_main():
    import av
    limits = MP3DecodeLimits(**json.loads(sys.argv[2]))
    def send(kind, value):
        sys.stdout.buffer.write(kind + struct.pack('!I', len(value)) + value)
        sys.stdout.buffer.flush()
    # Match the demuxer's existing floating-point decoder, avoiding a hidden
    # integer-vs-float decoding change when only transport timing is optimized.
    decoder = av.CodecContext.create('mp3float', 'r')
    decoder.options = {'err_detect': 'explode+crccheck'}
    source_resampler = None
    target_resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
    body = bytearray()
    original, output = hashlib.sha256(), hashlib.sha256()
    rate = channels = samples = 0
    def emit(frames, kind, digest):
        for frame in frames:
            payload = frame.to_ndarray().reshape(-1).astype('<i2', copy=False).tobytes()
            digest.update(payload)
            if payload: send(kind, payload)
    def frames(values):
        nonlocal rate, channels, samples, source_resampler
        for frame in values:
            geometry = frame.sample_rate, len(frame.layout.channels)
            if not rate:
                rate, channels = geometry
                if not 8000 <= rate <= 48000 or channels not in (1, 2):
                    raise MP3DecodeError('INVALID_MP3')
                source_resampler = av.AudioResampler(format='s16', layout=frame.layout, rate=rate)
            if geometry != (rate, channels): raise MP3DecodeError('INVALID_MP3')
            samples += frame.samples
            if samples/rate > limits.max_duration_seconds or samples*channels*2 > limits.max_source_pcm_bytes:
                raise MP3DecodeError('AUDIO_LIMIT')
            emit(source_resampler.resample(frame), b'S', original)
            emit(target_resampler.resample(frame), b'P', output)
    try:
        send(b'R', b'')
        while True:
            header = sys.stdin.buffer.read(4)
            if len(header) != 4: raise MP3DecodeError('TRUNCATED_INPUT')
            size = struct.unpack('!I', header)[0]
            if not size: break
            if len(body)+size > limits.max_body_bytes: raise MP3DecodeError('AUDIO_LIMIT')
            chunk = sys.stdin.buffer.read(size)
            if len(chunk) != size: raise MP3DecodeError('TRUNCATED_INPUT')
            body.extend(chunk)
            for packet in decoder.parse(chunk): frames(decoder.decode(packet))
        _validate_frames(bytes(body))
        for packet in decoder.parse(b''): frames(decoder.decode(packet))
        frames(decoder.decode(None))
        if not source_resampler: raise MP3DecodeError('NO_AUDIO')
        emit(source_resampler.resample(None), b'S', original)
        emit(target_resampler.resample(None), b'P', output)
        send(b'D', json.dumps(dict(source_rate=rate, source_channels=channels, source_samples=samples,
            source_sha256=original.hexdigest(), pcm16_sha256=output.hexdigest(),
            mp3_sha256=hashlib.sha256(body).hexdigest(), duration_seconds=samples/rate)).encode())
    except Exception as error:
        send(b'E', json.dumps({'error':error.code if isinstance(error, MP3DecodeError) else 'INVALID_MP3'}).encode())


if __name__ == "__main__" and len(sys.argv) == 3:
    if sys.argv[1] == '--worker': _worker_main()
    elif sys.argv[1] == '--stream-worker': _stream_worker_main()
