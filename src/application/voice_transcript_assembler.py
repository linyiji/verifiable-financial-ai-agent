"""Assemble only complete, ordered segment transcripts without rewriting words."""
from __future__ import annotations

from src.domain.voice_job import AudioSegment, SegmentResult


def require_complete_transcript(segments: list[AudioSegment], results: list[SegmentResult],
                                received_samples: int) -> str:
    if not segments or len(results) != len(segments):
        raise ValueError("MISSING_SEGMENT_RESULT")
    by_index = {}
    for result in results:
        if result.index in by_index:
            raise ValueError("DUPLICATE_SEGMENT_RESULT")
        by_index[result.index] = result
    if sorted(by_index) != list(range(len(segments))):
        raise ValueError("MISSING_SEGMENT_RESULT")
    if segments[0].start_sample != 0 or segments[-1].end_sample != received_samples:
        raise ValueError("INCOMPLETE_SEGMENT_COVERAGE")
    for left, right in zip(segments, segments[1:]):
        if left.end_sample != right.start_sample:
            raise ValueError("INCOMPLETE_SEGMENT_COVERAGE")
    parts = []
    for index in range(len(segments)):
        result = by_index[index]
        if result.status != "ok" or not result.text.strip():
            raise ValueError("SEGMENT_INFERENCE_FAILED")
        piece = result.text.strip()
        if parts and parts[-1][-1:].isascii() and parts[-1][-1:].isalnum() \
                and piece[:1].isascii() and piece[:1].isalnum():
            parts.append(" ")
        parts.append(piece)
    return "".join(parts)
