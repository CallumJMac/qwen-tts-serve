"""Replay recorded chunk arrivals through a simulated client player.

The capacity study measured starvation with a zero-buffer player. This module
generalises that model to a fixed startup buffer: playback begins a fixed delay
after the first audio byte, then each chunk plays as soon as both the chunk has
arrived and the previous chunk has finished. A gap is any interval where the
player has nothing to play.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    arrival_seconds: float
    audio_seconds: float


@dataclass(frozen=True)
class PlaybackResult:
    audible_start_seconds: float
    longest_gap_seconds: float
    total_gap_seconds: float
    gap_count: int


def simulate_playback(chunks: Iterable[Chunk], startup_buffer_seconds: float) -> PlaybackResult:
    ordered = sorted(chunks, key=lambda chunk: chunk.arrival_seconds)
    if not ordered:
        raise ValueError("cannot simulate playback without audio chunks")

    audible_start = ordered[0].arrival_seconds + startup_buffer_seconds
    playhead_free_at = audible_start
    longest_gap = 0.0
    total_gap = 0.0
    gap_count = 0
    for chunk in ordered:
        gap = chunk.arrival_seconds - playhead_free_at
        if gap > 0:
            longest_gap = max(longest_gap, gap)
            total_gap += gap
            gap_count += 1
        playhead_free_at = max(playhead_free_at, chunk.arrival_seconds) + chunk.audio_seconds

    return PlaybackResult(
        audible_start_seconds=audible_start,
        longest_gap_seconds=longest_gap,
        total_gap_seconds=total_gap,
        gap_count=gap_count,
    )


def chunks_from_record(record: dict) -> list[Chunk]:
    return [
        Chunk(arrival_seconds=timing["arrival_seconds"], audio_seconds=timing["audio_seconds"])
        for timing in record["chunk_timings"]
    ]
