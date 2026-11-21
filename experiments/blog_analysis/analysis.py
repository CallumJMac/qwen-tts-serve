"""Compute every statistic cited by the Qwen3-TTS blog posts.

Run from the repository root:

    uv run --with numpy python -m experiments.blog_analysis.analysis

Writes experiments/blog_analysis/output/summary.json plus one CSV per figure.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

from experiments.blog_analysis import data
from experiments.blog_analysis.playback import chunks_from_record, simulate_playback
from experiments.blog_analysis.queueing import fifo_waits, pollaczek_khinchine_mean_wait
from experiments.blog_analysis.stats import percentile_with_ci

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
TTFA_SLO_SECONDS = 0.300
GAP_SLO_SECONDS = 0.100
SUCCESS_SLO = 0.99
BUFFERS_SECONDS = [round(step * 0.005, 3) for step in range(0, 101)]
G5_XLARGE_USD_PER_HOUR = 1.006
HOSTED_PRICES_USD_PER_MILLION_CHARACTERS = {
    "OpenAI tts-1": 15.0,
    "Amazon Polly Neural": 16.0,
    "Deepgram Aura-2": 30.0,
    "Google Chirp 3 HD": 30.0,
    "ElevenLabs Flash": 40.0,
}


def milliseconds(estimate) -> dict:
    return {
        key: value * 1000 if key != "count" else value for key, value in estimate.as_dict().items()
    }


def condition_label(condition) -> str:
    load = f"{condition.load:g}"
    return f"{condition.backend}:{condition.profile}:{load}"


def endpoint_summary() -> dict:
    by_case: dict[str, list[float]] = defaultdict(list)
    for record in data.successful(data.load_endpoint_runs()):
        by_case[record["case"]].append(record["ttfa_seconds"])
    ttfa = {
        case: {
            "p50_ms": milliseconds(percentile_with_ci(values, 50)),
            "p95_ms": milliseconds(percentile_with_ci(values, 95)),
        }
        for case, values in by_case.items()
    }

    rtf: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    durations: dict[str, dict[str, set[float]]] = defaultdict(lambda: defaultdict(set))
    for record in data.successful(data.load_throughput_runs()):
        rtf[record["backend"]][record["case"]].append(record["rtf"])
        durations[record["backend"]][record["case"]].add(record["audio_seconds"])
    throughput = {
        backend: {
            case: {
                "rtf_p50": percentile_with_ci(values, 50).as_dict(),
                "audio_seconds": sorted(durations[backend][case]),
            }
            for case, values in cases.items()
        }
        for backend, cases in rtf.items()
    }
    return {"ttfa_by_case": ttfa, "throughput": throughput}


def capacity_summary(capacity: dict) -> tuple[list[dict], dict]:
    reported = json.loads(
        (
            data.RESULTS_DIR / f"{data.CAPACITY_RUN_ID}-capacity-analysis/capacity-summary.json"
        ).read_text()
    )
    reported_by_key = {
        (
            item["condition"]["backend"],
            item["condition"]["profile"],
            float(item["condition"].get("concurrency") or item["condition"].get("offered_rps")),
        ): item
        for item in reported["conditions"]
    }
    rows = []
    for condition, records in sorted(
        capacity.items(), key=lambda pair: (pair[0].backend, pair[0].profile, pair[0].load)
    ):
        ok = data.successful(records)
        ttfa = [record["ttfa_seconds"] for record in ok]
        gaps = [record["max_underrun_seconds"] for record in ok]
        reported_item = reported_by_key[(condition.backend, condition.profile, condition.load)]
        rows.append(
            {
                "condition": condition_label(condition),
                "backend": condition.backend,
                "profile": condition.profile,
                "load": condition.load,
                "requests": len(records),
                "successful": len(ok),
                "ttfa_p50_ms": milliseconds(percentile_with_ci(ttfa, 50)),
                "ttfa_p95_ms": milliseconds(percentile_with_ci(ttfa, 95)),
                "longest_gap_p95_ms": milliseconds(percentile_with_ci(gaps, 95)),
                "achieved_rps": reported_item["achieved_request_rate_rps"],
                "audio_seconds_per_wall_second": reported_item[
                    "audio_throughput_seconds_per_second"
                ],
                "meets_zero_buffer_slo": reported_item["meets_slos"],
            }
        )
    return rows, reported["slos"]


def buffer_sweep(capacity: dict) -> dict:
    sweep = {}
    for condition, records in capacity.items():
        ok = data.successful(records)
        success_rate = len(ok) / len(records)
        points = []
        for buffer_seconds in BUFFERS_SECONDS:
            results = [
                simulate_playback(chunks_from_record(record), buffer_seconds) for record in ok
            ]
            start_p95 = float(np.percentile([item.audible_start_seconds for item in results], 95))
            gap_p95 = float(np.percentile([item.longest_gap_seconds for item in results], 95))
            points.append(
                {
                    "buffer_ms": buffer_seconds * 1000,
                    "audible_start_p95_ms": start_p95 * 1000,
                    "longest_gap_p95_ms": gap_p95 * 1000,
                    "meets_slo": success_rate >= SUCCESS_SLO
                    and start_p95 <= TTFA_SLO_SECONDS
                    and gap_p95 <= GAP_SLO_SECONDS,
                }
            )
        passing = [point["buffer_ms"] for point in points if point["meets_slo"]]
        sweep[condition_label(condition)] = {
            "points": points,
            "passing_buffer_ms_range": [min(passing), max(passing)] if passing else None,
        }

    safe = {}
    for backend in ("current", "omni"):
        for profile in ("closed", "open"):
            loads = sorted(
                condition.load
                for condition in capacity
                if condition.backend == backend
                and condition.profile == profile
                and sweep[condition_label(condition)]["passing_buffer_ms_range"]
            )
            safe[f"{backend}:{profile}"] = max(loads) if loads else None
    return {"conditions": sweep, "safe_load_with_best_buffer": safe}


def omni_chunk_mechanism(capacity: dict) -> dict:
    records = data.successful(capacity[data.CapacityCondition("omni", "closed", 1.0)])
    first_audio = []
    first_to_second = []
    steady_intervals = []
    for record in records:
        arrivals = [timing["arrival_seconds"] for timing in record["chunk_timings"]]
        first_audio.append(record["chunk_timings"][0]["audio_seconds"])
        if len(arrivals) > 1:
            first_to_second.append(arrivals[1] - arrivals[0])
        steady_intervals += [
            later - earlier
            for earlier, later in zip(arrivals[1:], arrivals[2:])
            if later - earlier > 0.01
        ]
    current_records = data.successful(capacity[data.CapacityCondition("current", "closed", 1.0)])
    current_intervals = []
    for record in current_records:
        arrivals = [timing["arrival_seconds"] for timing in record["chunk_timings"]]
        current_intervals += [later - earlier for earlier, later in zip(arrivals, arrivals[1:])]
    return {
        "omni_first_chunk_audio_ms_p50": float(np.median(first_audio)) * 1000,
        "omni_first_to_second_arrival_ms_p50": float(np.median(first_to_second)) * 1000,
        "omni_steady_block_interval_ms_p50": float(np.median(steady_intervals)) * 1000,
        "omni_steady_block_audio_ms": 2000.0,
        "omni_config": {"initial_codec_chunk_frames": 4, "codec_chunk_frames": 25},
        "current_chunk_audio_ms": 320.0,
        "current_chunk_interval_ms_p50": float(np.median(current_intervals)) * 1000,
    }


def queueing_check(capacity: dict) -> dict:
    baseline = data.successful(capacity[data.CapacityCondition("current", "closed", 1.0)])
    service_by_case: dict[str, list[float]] = defaultdict(list)
    onset_by_case: dict[str, list[float]] = defaultdict(list)
    for record in baseline:
        service_by_case[record["case"]].append(record["elapsed_seconds"])
        onset_by_case[record["case"]].append(record["ttfa_seconds"])
    mean_service = {case: float(np.mean(values)) for case, values in service_by_case.items()}
    mean_onset = {case: float(np.mean(values)) for case, values in onset_by_case.items()}
    all_services = [value for values in service_by_case.values() for value in values]

    rates = {}
    for condition, records in capacity.items():
        if condition.backend != "current" or condition.profile != "open":
            continue
        ok = data.successful(records)
        origin = min(record["scheduled_at"] for record in ok)
        arrivals = [record["scheduled_at"] - origin for record in ok]
        services = [mean_service[record["case"]] for record in ok]
        waits = fifo_waits(arrivals, services)
        predicted = [wait + mean_onset[record["case"]] for wait, record in zip(waits, ok)]
        observed = [record["ttfa_seconds"] for record in ok]
        # The client caps in-flight requests at 32; TTFA is timed from send, so add the
        # client-side wait to recover latency from the scheduled arrival.
        from_arrival = [record["ttfa_seconds"] + record["queue_wait_seconds"] for record in ok]
        rates[f"{condition.load:g}"] = {
            "offered_rps": condition.load,
            "utilisation": condition.load * float(np.mean(all_services)),
            "client_wait_max_s": max(record["queue_wait_seconds"] for record in ok),
            "observed_ttfa_p50_s": float(np.percentile(observed, 50)),
            "observed_ttfa_p95_s": float(np.percentile(observed, 95)),
            "observed_from_arrival_p50_s": float(np.percentile(from_arrival, 50)),
            "observed_from_arrival_p95_s": float(np.percentile(from_arrival, 95)),
            "fifo_model_ttfa_p50_s": float(np.percentile(predicted, 50)),
            "fifo_model_ttfa_p95_s": float(np.percentile(predicted, 95)),
            "mg1_steady_state_mean_wait_s": pollaczek_khinchine_mean_wait(
                condition.load, all_services
            ),
        }
    return {
        "mean_service_seconds": float(np.mean(all_services)),
        "service_capacity_rps": 1 / float(np.mean(all_services)),
        "service_coefficient_of_variation": float(np.std(all_services) / np.mean(all_services)),
        "open_loop": rates,
    }


def packet_study() -> dict:
    rows = []
    for condition, records in sorted(
        data.load_packet_study().items(),
        key=lambda pair: (pair[0].backend, pair[0].route, pair[0].profile, pair[0].frames),
    ):
        ok = data.successful(records)
        ttfa = [record["ttfa_seconds"] for record in ok]
        gaps = [record["max_underrun_seconds"] for record in ok]
        rows.append(
            {
                "backend": condition.backend,
                "route": condition.route,
                "profile": condition.profile,
                "frames": condition.frames,
                "successful": len(ok),
                "requests": len(records),
                "ttfa_p50_ms": milliseconds(percentile_with_ci(ttfa, 50)),
                "ttfa_p95_ms": milliseconds(percentile_with_ci(ttfa, 95)),
                "longest_gap_p95_ms": milliseconds(percentile_with_ci(gaps, 95)),
                "rtf_p50": float(np.median([record["rtf"] for record in ok])),
            }
        )
    alb_overhead = {}
    for frames in (1, 2, 4, 8):
        by_route = {
            row["route"]: row["ttfa_p50_ms"]["value"]
            for row in rows
            if row["backend"] == "current"
            and row["profile"] == "isolated"
            and row["frames"] == frames
        }
        alb_overhead[str(frames)] = by_route["alb"] - by_route["localhost"]

    stages = []
    for item in data.load_packet_latency_budget():
        condition = item["condition"]
        if condition["backend"] != "current" or condition["profile"] != "isolated":
            continue
        if condition["route"] != "localhost":
            continue
        stage_ms = {stage["stage"]: stage["p50_ms"] for stage in item["stages"]}
        stages.append(
            {
                "frames": condition["packet_frames"],
                "prefill_ms": stage_ms["prefill_ms"],
                "first_packet_decode_ms": stage_ms["decode_ms"],
                "unattributed_engine_ms": stage_ms["unattributed_engine_ms"],
                "send_and_transport_ms": stage_ms["first_chunk_serialize_ms"]
                + stage_ms["first_chunk_send_ms"]
                + stage_ms["transport_residual_ms"],
                "queue_wait_ms": stage_ms["queue_wait_ms"],
            }
        )
    return {
        "conditions": rows,
        "alb_minus_localhost_ttfa_p50_ms": alb_overhead,
        "current_localhost_isolated_stages": sorted(stages, key=lambda row: row["frames"]),
    }


def cost_model(capacity: dict, capacity_rows: list[dict], sweep: dict) -> dict:
    corpus = data.load_capacity_corpus()
    mean_characters = float(np.mean([len(text) for text in corpus.values()]))
    rows_by_label = {row["condition"]: row for row in capacity_rows}

    def at_full_duty(label: str) -> dict:
        row = rows_by_label[label]
        characters_per_hour = row["achieved_rps"] * mean_characters * 3600
        audio_hours_per_hour = row["audio_seconds_per_wall_second"]
        return {
            "condition": label,
            "characters_per_hour": characters_per_hour,
            "usd_per_million_characters": G5_XLARGE_USD_PER_HOUR / characters_per_hour * 1e6,
            "usd_per_audio_hour": G5_XLARGE_USD_PER_HOUR / audio_hours_per_hour,
        }

    safe_current = at_full_duty("current:closed:1")
    safe_omni_load = sweep["safe_load_with_best_buffer"]["omni:closed"]
    safe_omni = at_full_duty(f"omni:closed:{safe_omni_load:g}") if safe_omni_load else None
    saturated_omni = at_full_duty("omni:closed:16")
    breakeven = {
        name: safe_current["usd_per_million_characters"] / price
        for name, price in HOSTED_PRICES_USD_PER_MILLION_CHARACTERS.items()
    }
    return {
        "instance_usd_per_hour": G5_XLARGE_USD_PER_HOUR,
        "mean_prompt_characters": mean_characters,
        "slo_safe_current": safe_current,
        "slo_safe_omni_with_buffer": safe_omni,
        "saturated_omni_not_slo_safe": saturated_omni,
        "hosted_prices_usd_per_million_characters": HOSTED_PRICES_USD_PER_MILLION_CHARACTERS,
        "hosted_prices_accessed": "2026-11-21",
        "breakeven_utilisation_current": breakeven,
    }


def comparable(transcript: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", transcript.lower()).split())


def first_speech(packets: dict) -> dict | None:
    """Combine packet-study TTFA with measured leading silence from quality.py output."""
    quality_path = OUTPUT_DIR / "quality.json"
    if not quality_path.exists():
        return None
    quality = json.loads(quality_path.read_text())
    leading: dict[str, list[float]] = defaultdict(list)
    for clip in quality["packet_study_clips"]:
        leading[clip["condition"]].append(clip["leading_silence_s"])
    rows = []
    for row in packets["conditions"]:
        if row["route"] != "localhost" or row["profile"] != "isolated":
            continue
        condition = f"{row['backend']}:localhost:isolated:pf{row['frames']}"
        silence_ms = float(np.median(leading[condition])) * 1000
        rows.append(
            {
                "backend": row["backend"],
                "frames": row["frames"],
                "ttfa_p50_ms": row["ttfa_p50_ms"]["value"],
                "leading_silence_p50_ms": silence_ms,
                "leading_silence_range_ms": [
                    min(leading[condition]) * 1000,
                    max(leading[condition]) * 1000,
                ],
                "first_speech_p50_ms": row["ttfa_p50_ms"]["value"] + silence_ms,
            }
        )
    pairs = quality["streaming_pairs"]
    return {
        "silence_threshold_dbfs": quality["silence_threshold_dbfs"],
        "conditions": rows,
        "streaming_pairs": {
            "count": len(pairs),
            "identical_transcripts": sum(
                comparable(pair["full"]["transcript"])
                == comparable(pair["streamed"]["transcript"])
                for pair in pairs
            ),
            "speaker_similarity": sorted(pair["speaker_similarity"] for pair in pairs),
        },
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    flat_rows = []
    for row in rows:
        flat = {}
        for key, value in row.items():
            if isinstance(value, dict):
                for inner_key, inner_value in value.items():
                    flat[f"{key}_{inner_key}"] = inner_value
            else:
                flat[key] = value
        flat_rows.append(flat)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat_rows[0]))
        writer.writeheader()
        writer.writerows(flat_rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    capacity = data.load_capacity()
    capacity_rows, slos = capacity_summary(capacity)
    sweep = buffer_sweep(capacity)
    packets = packet_study()
    summary = {
        "slos": slos,
        "endpoint": endpoint_summary(),
        "capacity": capacity_rows,
        "buffer_sweep": sweep,
        "omni_chunk_mechanism": omni_chunk_mechanism(capacity),
        "queueing": queueing_check(capacity),
        "packet_study": packets,
        "cost": cost_model(capacity, capacity_rows, sweep),
        "first_speech": first_speech(packets),
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    write_csv(OUTPUT_DIR / "capacity.csv", capacity_rows)
    write_csv(OUTPUT_DIR / "packet-study.csv", packets["conditions"])
    write_csv(OUTPUT_DIR / "ttfa-stages.csv", packets["current_localhost_isolated_stages"])
    sweep_rows = [
        {"condition": label, **point}
        for label, item in sweep["conditions"].items()
        for point in item["points"]
    ]
    write_csv(OUTPUT_DIR / "buffer-sweep.csv", sweep_rows)
    print(f"wrote {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
