"""Lossless no-overlap PCM segmentation for bounded ASR experiments.

Energy is used only to choose a boundary; every original sample is retained.
The default production mode remains whole utterance.
"""
from __future__ import annotations

import math
import numpy as np

from src.domain.voice_job import AudioSegment


class ContinuousSegmenter:
    def __init__(self, *, sample_rate: int = 16000, min_seconds: float = 10,
                 preferred_max_seconds: float = 20, max_seconds: float = 25,
                 silence_ms: int = 400, frame_ms: int = 20,
                 silence_rms: float = 0.012, max_segments: int = 256):
        if sample_rate != 16000 or frame_ms <= 0 or max_segments <= 0:
            raise ValueError("UNSUPPORTED_SEGMENTER_CONFIG")
        self.sample_rate = sample_rate
        self.frame_samples = sample_rate * frame_ms // 1000
        self.min_samples = int(min_seconds * sample_rate)
        self.preferred_max_samples = int(preferred_max_seconds * sample_rate)
        self.max_samples = int(max_seconds * sample_rate)
        self.silence_frames = math.ceil(silence_ms / frame_ms)
        self.silence_rms = silence_rms
        self.max_segments = max_segments
        self.buffer = bytearray()
        self._carry = b""
        self._scan_sample = 0
        self._start_sample = 0
        self._quiet_start: int | None = None
        self._frame_energy: list[tuple[int, float]] = []
        self.segments: list[AudioSegment] = []
        self.closed = False

    @property
    def received_samples(self) -> int:
        return len(self.buffer) // 2

    def _emit(self, cut: int, kind: str) -> AudioSegment:
        if len(self.segments) >= self.max_segments:
            raise ValueError("SEGMENT_COUNT_LIMIT")
        if not self._start_sample < cut <= self.received_samples:
            raise ValueError("INVALID_SEGMENT_BOUNDARY")
        segment = AudioSegment(len(self.segments), self._start_sample, cut,
                               bytes(self.buffer[self._start_sample * 2:cut * 2]), kind)
        self.segments.append(segment)
        self._start_sample = cut
        self._quiet_start = None
        self._frame_energy = [(pos, rms) for pos, rms in self._frame_energy if pos >= cut]
        return segment

    def append(self, raw: bytes) -> list[AudioSegment]:
        if self.closed:
            raise RuntimeError("SEGMENTER_CLOSED")
        data = self._carry + bytes(raw)
        usable = len(data) & ~1
        self._carry = data[usable:]
        self.buffer.extend(data[:usable])
        emitted = []
        while self._scan_sample + self.frame_samples <= self.received_samples:
            pos = self._scan_sample
            frame = np.frombuffer(self.buffer, dtype="<i2", count=self.frame_samples,
                                  offset=pos * 2).astype(np.float32)
            rms = float(np.sqrt(np.mean((frame / 32768.0) ** 2)))
            self._frame_energy.append((pos, rms))
            if rms < self.silence_rms:
                if self._quiet_start is None:
                    self._quiet_start = pos
            else:
                self._quiet_start = None
            self._scan_sample += self.frame_samples
            length = self._scan_sample - self._start_sample
            if (self._quiet_start is not None
                and self._scan_sample - self._quiet_start >= self.silence_frames * self.frame_samples
                and length >= self.min_samples
                and length <= self.preferred_max_samples):
                cut = max(self._start_sample + self.min_samples,
                          (self._quiet_start + self._scan_sample) // 2)
                emitted.append(self._emit(cut, "silence"))
            elif length >= self.max_samples:
                lookback = self._scan_sample - 2 * self.sample_rate
                choices = [(rms, pos) for pos, rms in self._frame_energy
                           if lookback <= pos < self._scan_sample and pos > self._start_sample]
                cut = min(choices)[1] if choices else self._scan_sample
                emitted.append(self._emit(cut, "forced"))
        return emitted

    def flush_tail(self) -> AudioSegment | None:
        if self.closed:
            raise RuntimeError("SEGMENTER_CLOSED")
        self.closed = True
        if self._carry:
            raise ValueError("ODD_PCM_BYTE_AT_EOS")
        if self._start_sample == self.received_samples:
            return None
        return self._emit(self.received_samples, "eos")

    def require_coverage(self) -> None:
        if not self.closed or not self.segments:
            raise ValueError("INCOMPLETE_SEGMENT_COVERAGE")
        if self.segments[0].start_sample != 0 or self.segments[-1].end_sample != self.received_samples:
            raise ValueError("INCOMPLETE_SEGMENT_COVERAGE")
        for left, right in zip(self.segments, self.segments[1:]):
            if left.end_sample != right.start_sample:
                raise ValueError("INCOMPLETE_SEGMENT_COVERAGE")
        if sum(x.end_sample - x.start_sample for x in self.segments) != self.received_samples:
            raise ValueError("INCOMPLETE_SEGMENT_COVERAGE")
