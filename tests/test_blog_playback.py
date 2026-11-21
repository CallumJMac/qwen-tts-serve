from experiments.blog_analysis.playback import Chunk, simulate_playback


def test_zero_buffer_matches_recorded_capacity_underrun() -> None:
    # Recorded vLLM-Omni request from the capacity study: 0.32s first chunk at 0.644s,
    # next chunk at 1.292s, recorded underrun 0.328s.
    chunks = [
        Chunk(arrival_seconds=0.6438605339999413, audio_seconds=0.32),
        Chunk(arrival_seconds=1.2920833000002858, audio_seconds=1.3651666666666666),
        Chunk(arrival_seconds=1.2923122550000699, audio_seconds=0.6348333333333334),
        Chunk(arrival_seconds=1.5001771750003172, audio_seconds=0.88),
    ]
    result = simulate_playback(chunks, startup_buffer_seconds=0.0)
    assert abs(result.audible_start_seconds - 0.6438605339999413) < 1e-12
    assert abs(result.longest_gap_seconds - 0.32822276600018085) < 1e-9
    assert result.gap_count == 1


def test_startup_buffer_delays_start_and_absorbs_gap() -> None:
    chunks = [
        Chunk(arrival_seconds=0.2, audio_seconds=0.3),
        Chunk(arrival_seconds=0.7, audio_seconds=1.0),
    ]
    unbuffered = simulate_playback(chunks, startup_buffer_seconds=0.0)
    assert abs(unbuffered.longest_gap_seconds - 0.2) < 1e-12

    buffered = simulate_playback(chunks, startup_buffer_seconds=0.2)
    assert abs(buffered.audible_start_seconds - 0.4) < 1e-12
    assert buffered.longest_gap_seconds == 0.0
    assert buffered.total_gap_seconds == 0.0


def test_total_gap_sums_every_stall() -> None:
    chunks = [
        Chunk(arrival_seconds=0.0, audio_seconds=0.1),
        Chunk(arrival_seconds=0.3, audio_seconds=0.1),
        Chunk(arrival_seconds=0.5, audio_seconds=0.1),
    ]
    result = simulate_playback(chunks, startup_buffer_seconds=0.0)
    assert abs(result.longest_gap_seconds - 0.2) < 1e-12
    assert abs(result.total_gap_seconds - 0.3) < 1e-12
    assert result.gap_count == 2
