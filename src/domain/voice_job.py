"""Small, media-only voice job contracts shared by product and CVC entrypoints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class VoiceJob:
    job_id: str
    run_item_id: str
    pillar: Literal["asr", "llm", "tts"]
    task: str | None
    text: str | None
    sample_rate: int
    channels: int
    deadline_ms: int


@dataclass
class JobState:
    generation: int = 0
    phase: str = "RECEIVING"
    received_samples: int = 0
    eos_received: bool = False
    response_deadline_at: float | None = None
    first_output_sent: bool = False
    cancelled: bool = False


@dataclass(frozen=True)
class AudioSegment:
    index: int
    start_sample: int
    end_sample: int
    pcm: bytes
    boundary_type: Literal["silence", "forced", "eos"]


@dataclass(frozen=True)
class SegmentResult:
    index: int
    text: str
    status: str
    elapsed_ms: float
    provider_response_id: str | None
    metadata: dict
