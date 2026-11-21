"""Render the blog figures from analysis output and raw records.

Run from the repository root after analysis.py (and quality.py for the
first-speech figure):

    uv run --no-project --with numpy --with soundfile \
      --with 'matplotlib>=3.10,<3.11' python -m experiments.blog_analysis.figures

Writes one SVG per figure plus sizes.json, the display size of each figure in
CSS pixels at a consistent text scale.
"""

from __future__ import annotations

import json
import re

import numpy as np
import soundfile
from matplotlib import pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter, NullLocator

from experiments.blog_analysis import data, style
from experiments.blog_analysis.analysis import GAP_SLO_SECONDS, OUTPUT_DIR, TTFA_SLO_SECONDS
from experiments.blog_analysis.playback import chunks_from_record
from experiments.blog_analysis.stats import percentile_with_ci

FIGURE_DIR = OUTPUT_DIR / "figures"
LIGHT = style.LIGHT
INK = LIGHT["ink"]
SECONDARY = LIGHT["ink-secondary"]
MUTED = LIGHT["ink-muted"]
BACKEND_LABEL = {"current": "Serialised server", "omni": "vLLM-Omni"}
SHORT_LABEL = {"current": "Serialised", "omni": "vLLM-Omni"}
BACKEND_COLOUR = {"current": style.CURRENT, "omni": style.OMNI}
BACKEND_MARKER = {"current": "o", "omni": "s"}
PANEL_HEIGHT = 2.45


def plain_number(value: float, _position: int = 0) -> str:
    return f"{value:g}"


def log_axis(axis, ticks: list[float]) -> None:
    axis.set_yscale("log")
    axis.yaxis.set_major_locator(FixedLocator(ticks))
    axis.yaxis.set_major_formatter(FuncFormatter(plain_number))
    axis.yaxis.set_minor_locator(NullLocator())
    axis.yaxis.set_minor_formatter(NullFormatter())


def frames_axis(axis) -> None:
    axis.set_xlim(0.4, 8.6)
    axis.set_xticks([1, 2, 4, 8])
    axis.set_xlabel(r"Codec frames in first packet, $\mathit{k}$")


def concurrency_axis(axis) -> None:
    axis.set_xscale("log", base=2)
    axis.set_xticks([1, 2, 4, 8, 16, 32], ["1", "2", "4", "8", "16", "32"])
    axis.xaxis.set_minor_locator(NullLocator())
    axis.set_xlabel("Requests in flight (closed loop)")


def points_with_ci(
    axis, x_values, estimates, colour, marker, *, scale=1.0, zorder=3, linestyle="-"
):
    values = np.array([item["value"] for item in estimates]) * scale
    lows = np.array([item["low"] for item in estimates]) * scale
    highs = np.array([item["high"] for item in estimates]) * scale
    axis.errorbar(
        x_values,
        values,
        yerr=[values - lows, highs - values],
        color=colour,
        marker=marker,
        markersize=3.6,
        markerfacecolor=colour,
        markeredgecolor=colour,
        markeredgewidth=0.9,
        linewidth=1.1,
        elinewidth=0.8,
        linestyle=linestyle,
        zorder=zorder,
    )
    return values


def label(axis, x, y, text, colour=INK, *, dx=4, dy=0, ha="left", va="center", size=7.5, **kwargs):
    axis.annotate(
        text,
        xy=(x, y),
        xytext=(dx, dy),
        textcoords="offset points",
        ha=ha,
        va=va,
        fontsize=size,
        color=colour,
        **kwargs,
    )


def inline_label(axis, x_values, y_values, buffers, text, side: str) -> None:
    """Label a trajectory along its own slope, just above or below the line."""
    figure_width, figure_height = axis.figure.get_size_inches()
    position = axis.get_position()
    x_low, x_high = axis.get_xlim()
    y_low, y_high = axis.get_ylim()
    inches_per_x = position.width * figure_width / (x_high - x_low)
    inches_per_y = position.height * figure_height / (y_high - y_low)
    index = int(np.searchsorted(buffers, 35))
    run = (x_values[index + 6] - x_values[0]) * inches_per_x
    rise = (y_values[index + 6] - y_values[0]) * inches_per_y
    angle = float(np.degrees(np.arctan2(rise, run)))
    offset = 5 if side == "above" else -5
    axis.annotate(
        text,
        xy=(x_values[index], y_values[index]),
        xytext=(0, offset),
        textcoords="offset points",
        rotation=angle,
        rotation_mode="anchor",
        ha="center",
        va="bottom" if side == "above" else "top",
        fontsize=7,
        color=SECONDARY,
    )


def record_size(sizes: dict, name: str) -> None:
    svg = (FIGURE_DIR / f"{name}.svg").read_text()
    width, height = map(float, re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg).groups())
    sizes[name] = {
        "width": round(width * style.DISPLAY_PIXELS_PER_POINT),
        "height": round(height * style.DISPLAY_PIXELS_PER_POINT),
    }


def figure_ttfa_decomposition(summary: dict) -> None:
    stages = summary["packet_study"]["current_localhost_isolated_stages"]
    totals = sorted(
        (
            row
            for row in summary["packet_study"]["conditions"]
            if row["backend"] == "current"
            and row["route"] == "localhost"
            and row["profile"] == "isolated"
        ),
        key=lambda row: row["frames"],
    )
    frames = np.array([row["frames"] for row in stages])
    figure, axis = plt.subplots(figsize=(style.SINGLE_WIDTH_INCHES, 2.7))

    measured = points_with_ci(
        axis,
        [row["frames"] for row in totals],
        [row["ttfa_p50_ms"] for row in totals],
        INK,
        "o",
        linestyle="none",
        zorder=5,
    )
    slope, intercept = np.polyfit(frames, measured, 1)
    fit_x = np.array([0.5, 8.5])
    axis.plot(
        fit_x, intercept + slope * fit_x, color=INK, linewidth=0.8, linestyle=(0, (4, 2)), zorder=4
    )
    label(
        axis,
        4.6,
        intercept + slope * 4.6,
        f"time to first audio\n${intercept:.1f} + {slope:.1f}\\,\\mathit{{k}}$ ms",
        INK,
        dx=-6,
        dy=4,
        ha="right",
        va="bottom",
    )

    components = [
        ("first_packet_decode_ms", "first-packet decode", style.CURRENT, "-", 4, 0),
        ("unattributed_engine_ms", "unattributed engine", SECONDARY, (0, (1.2, 1.2)), 4, 4),
        ("prefill_ms", "prefill", SECONDARY, "-", 4, -4),
    ]
    for key, name, colour, linestyle, dx, dy in components:
        values = [row[key] for row in stages]
        axis.plot(
            frames,
            values,
            color=colour,
            linewidth=1.0,
            linestyle=linestyle,
            marker="o",
            markersize=2.6,
            zorder=3,
        )
        label(axis, frames[-1], values[-1], name, colour, dx=dx, dy=dy)

    frames_axis(axis)
    axis.set_xlim(0.4, 10.6)
    axis.spines["bottom"].set_bounds(0.4, 8.6)
    axis.set_ylim(0, 330)
    axis.set_ylabel("Median latency (ms)")
    style.save(
        figure,
        FIGURE_DIR / "ttfa-decomposition.svg",
        "Median time to first audio at 1, 2, 4 and 8 codec frames per first packet, with a "
        "linear fit of 79.5 plus 28.6 milliseconds per frame, and its server-side stages: "
        "prefill and unattributed engine time stay near 40 ms while first-packet decode "
        "grows linearly from 28 to 220 ms.",
    )


def figure_first_speech(summary: dict) -> None:
    first = summary.get("first_speech")
    if not first:
        print("skipping first-speech figure: run quality.py, then analysis.py")
        return
    condition_dir = data.PACKET_STUDY_DIR / "conditions/current-localhost-isolated-frames-4"
    record = next(
        item
        for item in data.read_jsonl(condition_dir / "runs.jsonl")
        if item["case"] == "assistant"
    )
    samples, sample_rate = soundfile.read(
        condition_dir / record["retained_audio"]["path"], dtype="float32"
    )
    ttfa = record["ttfa_seconds"]
    window = int(0.004 * sample_rate)
    frame_count = len(samples) // window
    envelope = np.abs(samples[: frame_count * window]).reshape(frame_count, window).max(axis=1)
    times = ttfa + np.arange(frame_count) * window / sample_rate
    loud = np.flatnonzero(20 * np.log10(envelope + 1e-12) > -45)
    onset = times[loud[0]]

    figure, (left, right) = plt.subplots(
        1,
        2,
        figsize=(style.FULL_WIDTH_INCHES, PANEL_HEIGHT),
        gridspec_kw={"width_ratios": [2.3, 1], "wspace": 0.32},
    )
    left.axvspan(ttfa, onset, color=LIGHT["band"], linewidth=0, zorder=0)
    left.fill_between(times, -envelope, envelope, color=SECONDARY, linewidth=0, zorder=2)
    for x_value, text in (
        (ttfa, f"first byte\n{ttfa * 1000:.0f} ms"),
        (onset, f"first speech\n{onset * 1000:.0f} ms"),
    ):
        left.axvline(x_value, color=INK, linewidth=0.6, zorder=3)
        label(
            left,
            x_value,
            1.0,
            text,
            INK,
            dx=2,
            ha="left",
            va="top",
            size=7,
            xycoords=("data", "axes fraction"),
        )
    label(
        left,
        (ttfa + onset) / 2,
        0.08,
        "silence",
        SECONDARY,
        dx=0,
        ha="center",
        size=7,
        xycoords=("data", "axes fraction"),
    )
    left.set_xlim(0, 2.0)
    left.set_ylim(-1.15, 1.6)
    left.set_yticks([])
    left.spines["left"].set_visible(False)
    left.set_xlabel("Time since request (s)")
    style.panel_label(left, "a", x_offset=-0.03)

    rows = {row["backend"]: row for row in first["conditions"] if row["frames"] == 4}
    quality = json.loads((OUTPUT_DIR / "quality.json").read_text())
    generator = np.random.default_rng(7)
    for position, backend in enumerate(("current", "omni")):
        condition = f"{backend}:localhost:isolated:pf4"
        silences = np.array(
            [
                clip["leading_silence_s"] * 1000
                for clip in quality["packet_study_clips"]
                if clip["condition"] == condition
            ]
        )
        jitter = generator.uniform(-0.14, 0.14, size=silences.size)
        right.scatter(
            position + jitter, silences, s=9, color=BACKEND_COLOUR[backend], linewidth=0, zorder=3
        )
        median = rows[backend]["leading_silence_p50_ms"]
        right.plot(
            [position - 0.28, position + 0.28],
            [median, median],
            color=INK,
            linewidth=1.0,
            zorder=4,
        )
    right.set_xticks([0, 1], ["Serialised", "vLLM-Omni"])
    right.tick_params(axis="x", length=0)
    right.set_xlim(-0.6, 1.6)
    right.set_ylim(0, 600)
    right.spines["bottom"].set_visible(False)
    right.set_ylabel("Leading silence (ms)")
    style.panel_label(right, "b", x_offset=-0.42)
    style.save(
        figure,
        FIGURE_DIR / "first-speech.svg",
        "Panel a: amplitude envelope of one streamed clip aligned to the request: the first "
        f"byte arrives at {ttfa * 1000:.0f} ms but speech starts at {onset * 1000:.0f} ms. "
        "Panel b: leading silence for all 20 prompts on each backend, medians 420 and 440 ms.",
    )


def figure_capacity(summary: dict) -> None:
    rows = [row for row in summary["capacity"] if row["profile"] == "closed"]
    figure, (left, right) = plt.subplots(
        1, 2, figsize=(style.FULL_WIDTH_INCHES, PANEL_HEIGHT), gridspec_kw={"wspace": 0.38}
    )
    for backend in ("current", "omni"):
        backend_rows = sorted(
            (row for row in rows if row["backend"] == backend), key=lambda row: row["load"]
        )
        loads = [row["load"] for row in backend_rows]
        colour = BACKEND_COLOUR[backend]
        ttfa = points_with_ci(
            left,
            loads,
            [row["ttfa_p95_ms"] for row in backend_rows],
            colour,
            BACKEND_MARKER[backend],
            scale=0.001,
        )
        gaps = points_with_ci(
            right,
            loads,
            [row["longest_gap_p95_ms"] for row in backend_rows],
            colour,
            BACKEND_MARKER[backend],
        )
        label(left, loads[-1], ttfa[-1], SHORT_LABEL[backend], colour)
        label(right, loads[-1], gaps[-1], SHORT_LABEL[backend], colour, dy=0, va="center")
    for axis in (left, right):
        concurrency_axis(axis)
        axis.set_xlim(0.8, 100)
        axis.spines["bottom"].set_bounds(0.8, 40)
    log_axis(left, [0.1, 0.3, 1, 3, 10, 30, 100])
    left.set_ylim(0.1, 200)
    left.set_ylabel("p95 time to first audio (s)")
    style.reference_line(left, TTFA_SLO_SECONDS, "300 ms SLO", align="right", x_range=(0.8, 40))
    right.set_ylim(-30, 1450)
    right.set_ylabel("p95 longest playback gap (ms)")
    style.reference_line(
        right, GAP_SLO_SECONDS * 1000, "100 ms SLO", align="left", x_range=(0.8, 40)
    )
    style.panel_label(left, "a")
    style.panel_label(right, "b", x_offset=-0.17)
    style.save(
        figure,
        FIGURE_DIR / "capacity-closed-loop.svg",
        "Two panels against closed-loop concurrency from 1 to 32. Panel a: p95 time to first "
        "audio on a log scale; the serialised server exceeds the 300 ms SLO from concurrency "
        "2, vLLM-Omni from concurrency 4. Panel b: p95 longest playback gap; the serialised "
        "server never stalls, vLLM-Omni stalls 214 ms at concurrency 1 rising to about "
        "1.3 s. Error bars are bootstrap 95% intervals over 60 requests.",
    )


def _received_and_played(record: dict):
    chunks = sorted(chunks_from_record(record), key=lambda chunk: chunk.arrival_seconds)
    received_times, received_audio, total = [0.0], [0.0], 0.0
    for chunk in chunks:
        received_times += [chunk.arrival_seconds, chunk.arrival_seconds]
        received_audio += [total, total + chunk.audio_seconds]
        total += chunk.audio_seconds
    playhead = chunks[0].arrival_seconds
    played_times, played_audio, played, gaps = [0.0, playhead], [0.0, 0.0], 0.0, []
    for chunk in chunks:
        if chunk.arrival_seconds > playhead:
            gaps.append((playhead, chunk.arrival_seconds))
            played_times.append(chunk.arrival_seconds)
            played_audio.append(played)
            playhead = chunk.arrival_seconds
        playhead += chunk.audio_seconds
        played += chunk.audio_seconds
        played_times.append(playhead)
        played_audio.append(played)
    return received_times, received_audio, played_times, played_audio, gaps


def figure_playback_timeline(capacity: dict) -> None:
    figure, axes = plt.subplots(
        1,
        2,
        figsize=(style.FULL_WIDTH_INCHES, PANEL_HEIGHT),
        sharey=True,
        gridspec_kw={"wspace": 0.12},
    )
    for axis, backend, letter in zip(axes, ("current", "omni"), "ab"):
        records = data.successful(capacity[data.CapacityCondition(backend, "closed", 1.0)])
        record = next(item for item in records if item["case"] == "assistant")
        received_t, received_a, played_t, played_a, gaps = _received_and_played(record)
        for start, end in gaps:
            axis.axvspan(start, end, color=LIGHT["band"], linewidth=0, zorder=0)
            axis.annotate(
                "",
                xy=(start, 0.9),
                xytext=(end, 0.9),
                arrowprops={
                    "arrowstyle": "|-|,widthA=0.25,widthB=0.25",
                    "color": INK,
                    "linewidth": 0.6,
                },
            )
            label(
                axis,
                (start + end) / 2,
                0.9,
                f"stall\n{(end - start) * 1000:.0f} ms",
                INK,
                dx=0,
                dy=4,
                ha="center",
                va="bottom",
                size=7,
            )
        colour = BACKEND_COLOUR[backend]
        axis.plot(received_t, received_a, color=colour, linewidth=1.1)
        axis.plot(played_t, played_a, color=INK, linewidth=0.9)
        axis.set_xlim(0, 2.4)
        axis.set_xlabel("Time since request (s)")
        axis.text(
            0.02,
            0.97,
            BACKEND_LABEL[backend],
            transform=axis.transAxes,
            fontsize=8,
            color=INK,
            ha="left",
            va="top",
        )
        style.panel_label(axis, letter, x_offset=-0.11 if letter == "a" else -0.04)
        index = int(np.searchsorted(received_t, 1.55))
        label(
            axis,
            received_t[index],
            received_a[index],
            "received",
            colour,
            dx=-4,
            dy=6,
            ha="right",
            va="bottom",
        )
        label(
            axis,
            2.0,
            np.interp(2.0, played_t, played_a),
            "played",
            INK,
            dx=2,
            dy=-6,
            ha="left",
            va="top",
        )
    axes[0].set_ylim(0, 7.6)
    axes[0].set_ylabel("Audio (s)")
    style.save(
        figure,
        FIGURE_DIR / "playback-timeline.svg",
        "Cumulative audio received and played against time for the same prompt at "
        "concurrency 1. The serialised server delivers 0.32 s chunks every 0.14 s and never "
        "stalls. vLLM-Omni delivers a 0.32 s first chunk, then 2 s blocks every 0.5 s, so the "
        "player stalls for about 0.2 s after the first chunk.",
    )


def figure_omni_gap_mechanism(summary: dict) -> None:
    rows = sorted(
        (
            row
            for row in summary["packet_study"]["conditions"]
            if row["backend"] == "omni" and row["profile"] == "isolated"
        ),
        key=lambda row: row["frames"],
    )
    wait_ms = summary["omni_chunk_mechanism"]["omni_first_to_second_arrival_ms_p50"]
    figure, (left, right) = plt.subplots(
        1, 2, figsize=(style.FULL_WIDTH_INCHES, PANEL_HEIGHT), gridspec_kw={"wspace": 0.38}
    )

    model_x = np.linspace(0.5, 8.5, 400)
    left.plot(
        model_x,
        np.maximum(0, wait_ms - 80 * model_x),
        color=INK,
        linewidth=0.8,
        linestyle=(0, (4, 2)),
        zorder=2,
    )
    points_with_ci(
        left,
        [row["frames"] for row in rows],
        [row["longest_gap_p95_ms"] for row in rows],
        style.OMNI,
        "s",
        linestyle="none",
    )
    label(
        left,
        2.6,
        wait_ms - 80 * 2.6,
        f"model: max(0, ${wait_ms:.0f} - 80\\,\\mathit{{k}}$) ms",
        INK,
        dx=5,
        dy=4,
        ha="left",
        va="bottom",
    )
    label(left, 1, rows[0]["longest_gap_p95_ms"]["value"], "measured p95", style.OMNI, dx=5, dy=2)
    style.reference_line(left, GAP_SLO_SECONDS * 1000, "100 ms SLO", align="right")
    frames_axis(left)
    left.set_ylim(-20, 560)
    left.set_ylabel("p95 longest playback gap (ms)")

    sweep = summary["buffer_sweep"]["conditions"]
    right.set_xlim(0, 760)
    right.set_ylim(-20, 560)
    right.fill_between(
        [0, TTFA_SLO_SECONDS * 1000],
        0,
        GAP_SLO_SECONDS * 1000,
        color=LIGHT["band"],
        linewidth=0,
        zorder=0,
    )
    label(right, 8, 8, "both SLOs met", SECONDARY, dx=0, ha="left", va="bottom", size=7)
    for key, name, marker, side in (
        ("omni:closed:1", "1 in flight", "s", "above"),
        ("omni:closed:2", "2 in flight", "D", "below"),
        ("omni:open:0.25", "0.25 RPS open loop", "^", "above"),
    ):
        points = [point for point in sweep[key]["points"] if point["buffer_ms"] <= 400]
        starts = np.array([point["audible_start_p95_ms"] for point in points])
        gaps = np.array([point["longest_gap_p95_ms"] for point in points])
        right.plot(starts, gaps, color=style.OMNI, linewidth=1.0, zorder=3)
        buffers = np.array([point["buffer_ms"] for point in points])
        ticks = np.isin(buffers, [0, 100, 200, 300, 400])
        right.plot(
            starts[ticks],
            gaps[ticks],
            linestyle="none",
            marker=marker,
            markersize=3.2,
            color=style.OMNI,
            zorder=4,
        )
        inline_label(right, starts, gaps, buffers, name, side)
        if key == "omni:closed:1":
            tick_starts, tick_gaps, tick_buffers = starts[ticks], gaps[ticks], buffers[ticks]
            for start, gap, buffer in zip(tick_starts[1:4], tick_gaps[1:4], tick_buffers[1:4]):
                text = f"{buffer:.0f} ms buffer" if buffer == 100 else f"{buffer:.0f}"
                label(
                    right,
                    start,
                    gap,
                    text,
                    SECONDARY,
                    dx=4,
                    dy=2,
                    ha="left",
                    va="bottom",
                    size=6.5,
                )
    right.set_xlabel("p95 audible start, including buffer (ms)")
    right.set_ylabel("p95 longest playback gap (ms)")
    style.panel_label(left, "a")
    style.panel_label(right, "b")
    style.save(
        figure,
        FIGURE_DIR / "omni-gap-mechanism.svg",
        "Panel a: vLLM-Omni p95 longest playback gap against frames in the first packet; "
        f"measured gaps of 449, 368, 207 and 0 ms follow a model of a {wait_ms:.0f} ms wait for "
        "the first 25-frame block minus the audio already delivered. Panel b: recorded chunk "
        "arrivals replayed with startup buffers from 0 to 400 ms; each buffer millisecond "
        "moves a condition one millisecond right and down, so only concurrency 1 briefly "
        "enters the region where both SLOs are met.",
    )


def figure_open_loop(summary: dict, capacity: dict) -> None:
    queueing = summary["queueing"]["open_loop"]
    rates = sorted(float(rate) for rate in queueing)
    figure, axis = plt.subplots(figsize=(style.SINGLE_WIDTH_INCHES, 2.7))
    model = [queueing[f"{rate:g}"]["fifo_model_ttfa_p95_s"] for rate in rates]
    axis.plot(rates, model, color=INK, linewidth=0.9, linestyle=(0, (3, 2)), zorder=4)
    for backend in ("current", "omni"):
        estimates = []
        for rate in rates:
            records = data.successful(capacity[data.CapacityCondition(backend, "open", rate)])
            from_arrival = [
                record["ttfa_seconds"] + record["queue_wait_seconds"] for record in records
            ]
            estimates.append(percentile_with_ci(from_arrival, 95).as_dict())
        values = points_with_ci(
            axis, rates, estimates, BACKEND_COLOUR[backend], BACKEND_MARKER[backend], zorder=3
        )
        label(
            axis,
            rates[-1],
            values[-1],
            SHORT_LABEL[backend],
            BACKEND_COLOUR[backend],
            dy=6 if backend == "current" else 0,
        )
    label(axis, rates[-1], model[-1], "FIFO model", INK, dy=-6)
    capacity_rps = summary["queueing"]["service_capacity_rps"]
    axis.axvline(capacity_rps, color=MUTED, linewidth=0.6, linestyle=(0, (1, 1.5)), zorder=1)
    label(
        axis,
        capacity_rps,
        0.98,
        f"serialised capacity\n{capacity_rps:.2f} RPS",
        SECONDARY,
        dx=3,
        ha="left",
        va="top",
        size=6.8,
        xycoords=("data", "axes fraction"),
    )
    axis.set_xscale("log", base=2)
    axis.set_xticks(rates, [f"{rate:g}" for rate in rates])
    axis.xaxis.set_minor_locator(NullLocator())
    axis.set_xlim(0.2, 5.5)
    axis.spines["bottom"].set_bounds(0.2, 2.4)
    log_axis(axis, [0.1, 0.3, 1, 3, 10, 30, 100])
    axis.set_ylim(0.1, 400)
    style.reference_line(axis, TTFA_SLO_SECONDS, "300 ms SLO", align="right", x_range=(0.2, 2.4))
    axis.set_xlabel("Offered load (requests per second, Poisson)")
    axis.set_ylabel("p95 time to first audio\nfrom arrival (s)")
    style.save(
        figure,
        FIGURE_DIR / "open-loop-queue.svg",
        "p95 time to first audio, measured from scheduled arrival, against Poisson offered "
        "load of 0.25 to 2 requests per second. The serialised server's measurements sit on "
        "a single-server FIFO queue model built only from its concurrency-1 service times. "
        "vLLM-Omni meets the 300 ms TTFA target only at 0.25 RPS, where it still fails the "
        "playback-gap SLO.",
    )


def figure_cost(summary: dict) -> None:
    cost = summary["cost"]
    utilisation = np.linspace(0.06, 1.0, 300)
    figure, axis = plt.subplots(figsize=(style.SINGLE_WIDTH_INCHES, 2.7))
    current_cost = cost["slo_safe_current"]["usd_per_million_characters"]
    by_price: dict[float, list[str]] = {}
    for name, price in cost["hosted_prices_usd_per_million_characters"].items():
        by_price.setdefault(price, []).append(name)
    for index, (price, names) in enumerate(sorted(by_price.items())):
        axis.axhline(price, color=LIGHT["rule"], linewidth=0.6, zorder=1)
        below = index == 0
        label(
            axis,
            0.995,
            price,
            ", ".join(names),
            SECONDARY,
            dx=0,
            dy=-1.5 if below else 1.5,
            ha="right",
            va="top" if below else "bottom",
            size=6.6,
            xycoords=("axes fraction", "data"),
        )
        axis.plot(
            current_cost / price * 100,
            price,
            marker="o",
            markersize=3.2,
            color=style.CURRENT,
            markerfacecolor=LIGHT["surface"],
            markeredgewidth=0.8,
            zorder=5,
        )
    axis.plot(utilisation * 100, current_cost / utilisation, color=style.CURRENT, zorder=3)
    label(
        axis,
        86,
        current_cost / 0.86,
        "Serialised",
        style.CURRENT,
        dx=0,
        dy=-4,
        ha="center",
        va="top",
        size=7,
    )
    if cost["slo_safe_omni_with_buffer"]:
        omni_cost = cost["slo_safe_omni_with_buffer"]["usd_per_million_characters"]
        axis.plot(utilisation * 100, omni_cost / utilisation, color=style.OMNI, zorder=3)
        label(
            axis,
            55,
            omni_cost / 0.55,
            "vLLM-Omni, 1 stream",
            style.OMNI,
            dx=0,
            dy=-4,
            ha="center",
            va="top",
            size=7,
        )
    log_axis(axis, [5, 10, 20, 50, 100])
    axis.set_ylim(4, 120)
    axis.set_xlim(0, 100)
    axis.set_xlabel("GPU utilisation at the SLO-safe load (%)")
    axis.set_ylabel("USD per million characters")
    style.save(
        figure,
        FIGURE_DIR / "cost-per-character.svg",
        "Self-hosted cost per million characters on one g5.xlarge at 1.006 USD per hour "
        "against GPU utilisation, with hosted list prices from 15 to 40 USD as horizontal "
        "lines and break-even points marked. The serialised server costs 9.60 USD at full "
        "utilisation and matches OpenAI tts-1 at about 64% utilisation.",
    )


def main() -> None:
    style.apply()
    summary = json.loads((OUTPUT_DIR / "summary.json").read_text())
    capacity = data.load_capacity()
    figure_ttfa_decomposition(summary)
    figure_first_speech(summary)
    figure_capacity(summary)
    figure_playback_timeline(capacity)
    figure_omni_gap_mechanism(summary)
    figure_open_loop(summary, capacity)
    figure_cost(summary)
    sizes: dict = {}
    for path in sorted(FIGURE_DIR.glob("*.svg")):
        record_size(sizes, path.stem)
    (FIGURE_DIR / "sizes.json").write_text(json.dumps(sizes, indent=2, sort_keys=True))
    print(f"wrote {FIGURE_DIR}")


if __name__ == "__main__":
    main()
